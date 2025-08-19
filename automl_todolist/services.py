"""Business logic services for the AutoML TodoList CLI application."""

import json
import logging
from datetime import datetime, timezone, timedelta, time
from typing import List, Optional, Dict, Any
from dateutil.tz import gettz

import pandas as pd
import plotly.express as px
import pmdarima as pm # Import pmdarima
from sklearn.linear_model import LinearRegression # Import LinearRegression
import numpy as np # Import numpy
# from scipy.interpolate import UnivariateSpline # Import UnivariateSpline
import warnings
# from sklearn.utils.deprecation import is_deprecated # Import is_deprecated

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import webbrowser
import threading
import time as time_module
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json as json_lib

from sqlalchemy import func
from sqlalchemy.orm import Session

from rich.table import Table
from rich.console import Console

from .config import (
    DOW_MAP, DIFFICULTY_MAP_INT_TO_STR, POINTS_MAP, 
    DIFFICULTY_NORMALIZATION_MAP, DEFAULT_TIMEZONE,
    MINUTES_PER_HOUR, ROUNDING_INTERVAL_MINUTES,
    MIN_DIFFICULTY_LEVEL, MAX_DIFFICULTY_LEVEL,
    MIN_DOW_VALUE, MAX_DOW_VALUE
)
from .database import get_db_session
from .models import Season, Task
from .exceptions import (
    NoActiveSeasonError, TaskNotFoundError, SeasonNotFoundError,
    InvalidDifficultyError, InvalidDayOfWeekError, InvalidTimezoneError,
    BackupFileNotFoundError, BackupImportError
)

# Configure logging
logger = logging.getLogger(__name__)

# Global timezone state (managed through service methods)
# _current_timezone = DEFAULT_TIMEZONE # REMOVED


class ValidationService:
    """Service for input validation and data conversion."""
    
    @staticmethod
    def validate_and_convert_difficulty(difficulty: Optional[int]) -> Optional[str]:
        """
        Validate and convert difficulty from integer to string.
        
        Args:
            difficulty: Integer difficulty level (1-5) or None
            
        Returns:
            String difficulty level or None
            
        Raises:
            InvalidDifficultyError: If difficulty is invalid
        """
        if difficulty is None:
            return None
            
        if difficulty not in range(MIN_DIFFICULTY_LEVEL, MAX_DIFFICULTY_LEVEL + 1):
            raise InvalidDifficultyError(difficulty)
            
        return DIFFICULTY_MAP_INT_TO_STR[difficulty]
    
    @staticmethod
    def validate_and_convert_dow(dow: Optional[int]) -> Optional[str]:
        """
        Validate and convert day of week from integer to string.
        
        Args:
            dow: Integer day of week (0-6) or None
            
        Returns:
            String day of week abbreviation or None
            
        Raises:
            InvalidDayOfWeekError: If dow is invalid
        """
        if dow is None:
            return None
            
        if dow not in range(MIN_DOW_VALUE, MAX_DOW_VALUE + 1):
            raise InvalidDayOfWeekError(dow)
            
        return DOW_MAP[str(dow)]
    
    @staticmethod
    def validate_timezone(timezone_string: str):
        """
        Validate timezone string and return timezone object.
        
        Args:
            timezone_string: IANA timezone string
            
        Returns:
            Timezone object
            
        Raises:
            InvalidTimezoneError: If timezone string is invalid
        """
        timezone_obj = gettz(timezone_string)
        if timezone_obj is None:
            raise InvalidTimezoneError(timezone_string)
        return timezone_obj


class LPCalculationService:
    """Service for Life Points calculations."""
    
    @staticmethod
    def calculate_lp_gain(task: Task, season_timezone: Any) -> Optional[float]:
        """
        Calculate LP gain based on difficulty and duration.
        
        Args:
            task: Task object with difficulty and timing information
            
        Returns:
            Calculated LP gain or None if cannot be calculated
        """
        if not task.difficulty:
            return None

        base_points = POINTS_MAP.get(task.difficulty, 0)
        
        duration_minutes = 0
        if task.time_taken_minutes is not None:
            duration_minutes = task.time_taken_minutes
        elif task.start_time and task.finish_time:
            # Ensure both are timezone-aware and in UTC for safe subtraction
            start_dt = task.start_time
            finish_dt = task.finish_time

            # If a datetime object loaded from DB is naive, assume it's in the application's current timezone
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=season_timezone)
            if finish_dt.tzinfo is None:
                finish_dt = finish_dt.replace(tzinfo=season_timezone)

            # Convert both to UTC before subtraction to avoid offset issues if timezones were different
            start_dt_utc = start_dt.astimezone(timezone.utc)
            finish_dt_utc = finish_dt.astimezone(timezone.utc)

            duration_minutes = (finish_dt_utc - start_dt_utc).total_seconds() / 60
        
        if duration_minutes > 0:
            # Round to the nearest 15-minute interval
            rounded_minutes = round(duration_minutes / ROUNDING_INTERVAL_MINUTES) * ROUNDING_INTERVAL_MINUTES
            duration_hours = rounded_minutes / MINUTES_PER_HOUR
            return base_points * duration_hours
        
        return 0.0


class SeasonService:
    """Service for season management operations."""
    
    @staticmethod
    def get_active_season(session: Session) -> Season:
        """
        Get the currently active season.
        
        Args:
            session: Database session
            
        Returns:
            Active season object
            
        Raises:
            NoActiveSeasonError: If no active season exists
        """
        season = session.query(Season).filter(Season.is_active == True).first()
        if not season:
            raise NoActiveSeasonError()
        return season
    
    @staticmethod
    def create_season(name: str) -> Season:
        """
        Create a new season and deactivate the old one.
        
        Args:
            name: Name for the new season
            
        Returns:
            Newly created season
        """
        with get_db_session() as session:
            now = datetime.now(timezone.utc) # Use UTC for consistency
            
            # Deactivate old season
            try:
                active_season = SeasonService.get_active_season(session)
                active_season.is_active = False
                active_season.end_date = now
                session.add(active_season)
                logger.info(f"Deactivated season: {active_season.name}")
            except NoActiveSeasonError:
                logger.info("No active season to deactivate")
            
            # Create new season using system's local timezone as default
            system_tz = gettz()
            if not system_tz:
                system_tz = gettz("UTC") # Fallback
            now = datetime.now(system_tz)

            new_season = Season(
                name=name, 
                is_active=True, 
                start_date=now,
                timezone_string=str(system_tz),
                day_start_hour=0 # Default to midnight
            )
            session.add(new_season)
            session.flush()
            session.refresh(new_season)
            session.expunge(new_season)
            logger.info(f"Created new season: {name}")
            return new_season
    
    @staticmethod
    def list_seasons() -> List[Season]:
        """Get all seasons ordered by ID."""
        with get_db_session() as session:
            seasons = session.query(Season).order_by(Season.id).all()
            for season in seasons:
                session.expunge(season)
            return seasons
    
    @staticmethod
    def switch_season(season_id: int) -> Season:
        """
        Switch to a different season.
        
        Args:
            season_id: ID of the season to activate
            
        Returns:
            Newly activated season
            
        Raises:
            SeasonNotFoundError: If season doesn't exist
        """
        with get_db_session() as session:
            # Deactivate current season
            try:
                active_season = SeasonService.get_active_season(session)
                active_season.is_active = False
                session.add(active_season)
            except NoActiveSeasonError:
                pass
            
            # Activate new season
            new_season = session.query(Season).filter(Season.id == season_id).first()
            if not new_season:
                raise SeasonNotFoundError(season_id)
            
            new_season.is_active = True
            session.add(new_season)
            session.flush()
            session.refresh(new_season)
            session.expunge(new_season)
            logger.info(f"Switched to season: {new_season.name}")
            return new_season
    
    @staticmethod
    def get_current_season() -> Season:
        """Get the current active season."""
        with get_db_session() as session:
            season = SeasonService.get_active_season(session)
            # Expunge from session so it can be accessed after session closes
            session.expunge(season)
            return season
    
    @staticmethod
    def set_decay(decay_value: float) -> Season:
        """
        Set daily decay for the active season.
        
        Args:
            decay_value: New daily decay value
            
        Returns:
            Updated season
        """
        with get_db_session() as session:
            season = SeasonService.get_active_season(session)
            season.daily_decay = decay_value
            session.add(season)
            session.flush()
            session.refresh(season)
            session.expunge(season)
            logger.info(f"Set decay to {decay_value} for season: {season.name}")
            return season

    @staticmethod
    def set_timezone(timezone_string: str) -> Season:
        """Set the timezone for the active season."""
        ValidationService.validate_timezone(timezone_string)
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            active_season.timezone_string = timezone_string
            session.add(active_season)
            session.flush()
            session.refresh(active_season)
            session.expunge(active_season)
            logger.info(f"Set timezone to {timezone_string} for season: {active_season.name}")
            return active_season

    @staticmethod
    def get_active_season_timezone() -> Any:
        """Get the timezone object for the currently active season."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            if not active_season.timezone_string:
                logger.warning(f"Season '{active_season.name}' has no timezone set. Defaulting to UTC.")
                return gettz("UTC")
            return ValidationService.validate_timezone(active_season.timezone_string)

    @staticmethod
    def set_day_start_hour(hour: int) -> Season:
        """
        Set the custom day start hour for the active season.
        
        Args:
            hour: The hour (0-23) at which a new day begins for decay calculation.
            
        Returns:
            Updated season.
            
        Raises:
            ValueError: If the hour is not between 0 and 23.
            NoActiveSeasonError: If no active season exists.
        """
        if not (0 <= hour <= 23):
            raise ValueError("Day start hour must be between 0 and 23.")

        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            active_season.day_start_hour = hour
            session.add(active_season)
            session.flush()
            session.refresh(active_season)
            session.expunge(active_season)
            logger.info(f"Set day start hour to {hour} for season: {active_season.name}")
            return active_season


class TaskService:
    """Service for task management operations."""
    
    @staticmethod
    def create_task(
        task_description: str,
        project: Optional[str] = None,
        difficulty: Optional[int] = None,
        # dow: Optional[int] = None, # No longer needed, will be auto-detected
        duration: Optional[int] = None,
        completed: bool = False,
        finish_time_str: Optional[str] = None
    ) -> Task:
        """
        Create a new task.
        
        Args:
            task_description: Description of the task
            project: Project or category
            difficulty: Difficulty level (1-5)
            # dow: Day of week (0-6)
            duration: Manual duration in minutes
            completed: Whether task is completed
            
        Returns:
            Created task
            
        Raises:
            NoActiveSeasonError: If no active season exists
            InvalidDifficultyError: If difficulty is invalid
            InvalidDayOfWeekError: If dow is invalid
        """
        # Validate inputs
        difficulty_str = ValidationService.validate_and_convert_difficulty(difficulty)
        
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            season_tz = ValidationService.validate_timezone(active_season.timezone_string)
            now = datetime.now(season_tz)
            
            task_finish_time = None
            if completed:
                if finish_time_str:
                    try:
                        naive_dt = datetime.strptime(finish_time_str, "%Y-%m-%d %H:%M:%S")
                        task_finish_time = naive_dt.replace(tzinfo=season_tz)
                    except ValueError as e:
                        logger.error(f"Invalid finish time format '{finish_time_str}': {e}. Using current time.")
                        task_finish_time = now # Fallback to current time on error
                else:
                    task_finish_time = now

            # DoW is based on created_at time. It will be updated if the task is started later.
            dow_str = now.strftime('%a')

            new_task = Task(
                task=task_description,
                project=project,
                difficulty=difficulty_str,
                dow=dow_str,
                time_taken_minutes=duration,
                completed=completed,
                finish_time=task_finish_time,
                created_at=now,
                season_id=active_season.id
            )
            
            # Calculate LP if completed
            if completed:
                new_task.lp_gain = LPCalculationService.calculate_lp_gain(new_task, season_tz)
            
            session.add(new_task)
            session.flush()
            session.refresh(new_task)
            session.expunge(new_task)
            logger.info(f"Created task: {task_description} (ID: {new_task.id})")
            return new_task
    
    @staticmethod
    def get_active_tasks() -> List[Task]:
        """Get all active (incomplete) tasks in the current season."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            tasks = session.query(Task).filter(
                Task.season_id == active_season.id,
                Task.completed == False
            ).order_by(Task.id).all()
            # Expunge all tasks from session
            for task in tasks:
                session.expunge(task)
            return tasks
    
    @staticmethod
    def get_completed_tasks() -> List[Task]:
        """Get all completed tasks in the current season."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            tasks = session.query(Task).filter(
                Task.season_id == active_season.id,
                Task.completed == True
            ).order_by(Task.finish_time.desc()).all()
            # Expunge all tasks from session
            for task in tasks:
                session.expunge(task)
            return tasks

    @staticmethod
    def get_completed_tasks_as_df() -> pd.DataFrame:
        """Get all completed tasks for the active season as a pandas DataFrame."""
        tasks = TaskService.get_completed_tasks()
        if not tasks:
            return pd.DataFrame()

        # Get active season to access timezone for localizing naive datetimes.
        active_season = SeasonService.get_current_season()
        season_timezone = timezone.utc # Default to UTC if no season
        if active_season and active_season.timezone_string:
            try:
                season_timezone = gettz(active_season.timezone_string)
            except Exception:
                logger.warning(f"Invalid timezone string '{active_season.timezone_string}'. Falling back to UTC.")
                season_timezone = timezone.utc
        
        data = [
            {
                'finish_time': task.finish_time,
                'lp_gain': task.lp_gain
            } for task in tasks
        ]
        
        df = pd.DataFrame(data)
        if 'finish_time' in df.columns:
            df['finish_time'] = pd.to_datetime(df['finish_time'])
            # Ensure all timestamps are timezone-aware. Localize naive ones to the season's timezone.
            df['finish_time'] = df['finish_time'].apply(
                lambda x: x.tz_localize(season_timezone) if pd.notna(x) and x.tzinfo is None else x
            )
        return df

    @staticmethod
    def get_completed_tasks_table(limit: Optional[int] = None) -> Table:
        """Get a Rich Table of completed tasks for the active season.

        Args:
            limit: If provided, only the most recent N completed tasks are shown.
        """
        active_season = SeasonService.get_current_season()
        tasks = TaskService.get_completed_tasks()
        if limit is not None and limit > 0:
            tasks = tasks[:limit]

        table = Table(title=f"Completed Tasks for {active_season.name}")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("DoW", style="white", no_wrap=True)
        table.add_column("Project", style="yellow", no_wrap=True)
        table.add_column("Task", style="magenta")
        table.add_column("Finished At", style="green", no_wrap=True)
        table.add_column("Time Taken", style="red", no_wrap=True)
        table.add_column("Difficulty", style="blue", no_wrap=True)
        table.add_column("LP Gain", style="green", no_wrap=True)
        table.add_column("Reflection", style="white")

        # Get the active season's timezone
        season_timezone = gettz(active_season.timezone_string)
        if season_timezone is None:
            # Fallback if timezone string is invalid, though validation should prevent this
            season_timezone = SeasonService.get_active_season_timezone() 

        for task in tasks:
            finish_time_str = "N/A"
            if task.finish_time:
                # Handle potentially naive datetimes before converting timezone
                task_finish_time = task.finish_time
                if task_finish_time.tzinfo is None:
                    task_finish_time = task_finish_time.replace(tzinfo=season_timezone)

                # Convert UTC finish_time to the season's timezone for display
                localized_finish_time = task_finish_time.astimezone(season_timezone)
                finish_time_str = localized_finish_time.strftime("%Y-%m-%d %H:%M")
            
            time_taken = "N/A"
            if task.time_taken_minutes is not None:
                time_taken = f"{task.time_taken_minutes} min (manual)"
            elif task.start_time and task.finish_time:
                time_taken_delta = task.finish_time - task.start_time
                time_taken = str(time_taken_delta).split(".")[0]

            table.add_row(
                str(task.id),
                task.dow or "N/A",
                task.project or "N/A",
                task.task,
                finish_time_str,
                time_taken,
                task.difficulty or "N/A",
                str(task.lp_gain) if task.lp_gain is not None else "N/A",
                task.reflection or "N/A",
            )
        return table
    
    @staticmethod
    def get_task(task_id: int) -> Task:
        """
        Get a task by ID in the current season.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task object
            
        Raises:
            TaskNotFoundError: If task doesn't exist in current season
        """
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            task = session.query(Task).filter(
                Task.id == task_id,
                Task.season_id == active_season.id
            ).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            session.expunge(task)
            return task
    
    @staticmethod
    def start_task(task_id: int) -> Task:
        """Start a task by setting start_time."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            task = session.query(Task).filter(
                Task.id == task_id,
                Task.season_id == active_season.id
            ).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            season_tz = ValidationService.validate_timezone(active_season.timezone_string)
            task.start_time = datetime.now(season_tz)
            task.dow = task.start_time.strftime('%a') # Set/update dow on start
            session.add(task)
            session.flush()
            session.refresh(task)
            session.expunge(task)
            logger.info(f"Started task: {task.task} (ID: {task_id})")
            return task
    
    @staticmethod
    def stop_task(task_id: int) -> Task:
        """Stop a task by setting finish_time."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            task = session.query(Task).filter(
                Task.id == task_id,
                Task.season_id == active_season.id
            ).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            season_tz = ValidationService.validate_timezone(active_season.timezone_string)
            task.finish_time = datetime.now(season_tz)
            session.add(task)
            session.flush()
            session.refresh(task)
            session.expunge(task)
            logger.info(f"Stopped task: {task.task} (ID: {task_id})")
            return task
    
    @staticmethod
    def complete_task(task_id: int) -> Task:
        """Complete a task and calculate LP gain."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            task = session.query(Task).filter(
                Task.id == task_id,
                Task.season_id == active_season.id
            ).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            task.completed = True
            season_tz = ValidationService.validate_timezone(active_season.timezone_string)
            if not task.finish_time:
                task.finish_time = datetime.now(season_tz)
            
            task.lp_gain = LPCalculationService.calculate_lp_gain(task, season_tz)
            session.add(task)
            session.flush()
            session.refresh(task)
            session.expunge(task)
            logger.info(f"Completed task: {task.task} (ID: {task_id})")
            return task
    
    @staticmethod
    def update_task(
        task_id: int,
        task_description: Optional[str] = None,
        project: Optional[str] = None,
        difficulty: Optional[int] = None,
        # dow: Optional[int] = None, # No longer needed, will be auto-detected
        duration: Optional[int] = None,
        reflection: Optional[str] = None,
        finish_time_str: Optional[str] = None
    ) -> Task:
        """Update any attribute of a task."""
        # Validate inputs
        difficulty_str = ValidationService.validate_and_convert_difficulty(difficulty) if difficulty is not None else None
        # dow_str = ValidationService.validate_and_convert_dow(dow) if dow is not None else None # No longer needed
        
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            task = session.query(Task).filter(
                Task.id == task_id,
                Task.season_id == active_season.id
            ).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            # Update fields
            if task_description is not None:
                task.task = task_description
            if project is not None:
                task.project = project
            if difficulty_str is not None:
                task.difficulty = difficulty_str
            # if dow_str is not None: # No longer needed
            #     task.dow = dow_str
            if duration is not None:
                task.time_taken_minutes = duration
            if reflection is not None:
                task.reflection = reflection
            
            # Update finish time if provided
            if finish_time_str is not None:
                try:
                    naive_dt = datetime.strptime(finish_time_str, "%Y-%m-%d %H:%M:%S")
                    season_tz = ValidationService.validate_timezone(active_season.timezone_string)
                    task.finish_time = naive_dt.replace(tzinfo=season_tz)
                except ValueError as e:
                    logger.error(f"Invalid finish time format '{finish_time_str}': {e}")
                    # Optionally, you could raise an exception here to notify the user
                    pass  # Or raise a custom exception

            # Recalculate LP if task is completed
            if task.completed:
                season_tz = ValidationService.validate_timezone(active_season.timezone_string)
                task.lp_gain = LPCalculationService.calculate_lp_gain(task, season_tz)
            
            session.add(task)
            session.flush()
            session.refresh(task)
            session.expunge(task)
            logger.info(f"Updated task: {task.task} (ID: {task_id})")
            return task
    
    @staticmethod
    def delete_task(task_id: int):
        """Delete a task by its ID."""
        with get_db_session() as session:
            task = session.query(Task).filter(Task.id == task_id).first()
            
            if not task:
                raise TaskNotFoundError(task_id)
            
            session.delete(task)
            session.commit()
            logger.info(f"Deleted task: {task.task} (ID: {task_id})")
    
    @staticmethod
    def recalculate_all_lp() -> int:
        """Recalculate LP for all completed tasks in the active season."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            completed_tasks = session.query(Task).filter(
                Task.season_id == active_season.id,
                Task.completed == True
            ).all()
            
            if not completed_tasks:
                return 0
            
            season_tz = ValidationService.validate_timezone(active_season.timezone_string)
            recalculated_count = 0
            for task in completed_tasks:
                # Normalize legacy difficulty values
                if task.difficulty in DIFFICULTY_NORMALIZATION_MAP:
                    task.difficulty = DIFFICULTY_NORMALIZATION_MAP[task.difficulty]
                
                new_lp = LPCalculationService.calculate_lp_gain(task, season_tz)
                if task.lp_gain != new_lp:
                    task.lp_gain = new_lp
                    recalculated_count += 1
            
            if recalculated_count > 0:
                session.commit()
                logger.info(f"Recalculated LP for {recalculated_count} tasks")
            
            return recalculated_count


class StatusService:
    """Service for status and statistics calculations."""
    
    @staticmethod
    def format_timedelta(td: timedelta) -> str:
        """Formats a timedelta into a human-readable string of hours and minutes."""
        if not isinstance(td, timedelta):
            return "N/A"
        hours, remainder = divmod(td.total_seconds(), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{int(hours)} hours, {int(minutes)} minutes"

    @staticmethod
    def get_lp_status(week: int = 0) -> dict:
        """
        Get the current LP status for the active season.

        Returns:
            dict: A dictionary containing LP status details.
        """
        active_season = SeasonService.get_current_season()
        if not active_season:
            raise NoActiveSeasonError("Cannot get LP status because there is no active season.")

        with get_db_session() as session:
            # Establish the season's specific timezone and day start hour
            season_tz_str = active_season.timezone_string
            season_timezone = gettz(season_tz_str)
            day_start_hour = active_season.day_start_hour
            daily_decay = active_season.daily_decay

            # Get all completed tasks for the season to build a DataFrame
            df_completed = TaskService.get_completed_tasks_as_df()
            
            # Calculate total LP gain for the season
            total_lp_gain = df_completed['lp_gain'].sum() if not df_completed.empty else 0.0

            # Current time in season's timezone
            now_in_season_tz = datetime.now(season_timezone)

            # Determine today's date for LP gain comparison
            today_for_lp_gain_comparison = now_in_season_tz.date()
            if now_in_season_tz.time() < time(day_start_hour):
                today_for_lp_gain_comparison = (now_in_season_tz - timedelta(days=1)).date()

            # Decay calculation
            season_start_dt_in_season_tz = active_season.start_date.astimezone(season_timezone)
            first_decay_point_for_season = datetime.combine(season_start_dt_in_season_tz.date(), time(day_start_hour), tzinfo=season_timezone)
            if first_decay_point_for_season < season_start_dt_in_season_tz:
                first_decay_point_for_season += timedelta(days=1)
            
            time_since_first_decay = now_in_season_tz - first_decay_point_for_season
            days_passed = max(0, int(time_since_first_decay.total_seconds() // (24 * 3600)))
            total_decay = days_passed * active_season.daily_decay

            # Helper function to determine if a task's finish time falls on today's LP gain date
            def is_task_for_today_lp(row):
                task_finish_time = row['finish_time']
                if pd.notna(task_finish_time):
                    task_finish_time_in_season_tz = task_finish_time.astimezone(season_timezone)
                    
                    task_lp_date = task_finish_time_in_season_tz.date()
                    if task_finish_time_in_season_tz.time() < time(day_start_hour):
                        task_lp_date = (task_finish_time_in_season_tz - timedelta(days=1)).date()
                    
                    return task_lp_date == today_for_lp_gain_comparison
                return False

            # Calculate daily LP gain and LP per day for the target week (offset by weeks)
            if df_completed.empty:
                daily_lp_gain = 0.0
                lp_by_day = {day: 0.0 for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']}
            else:
                # LP today (relative to current date only)
                daily_lp_gain = df_completed[df_completed.apply(is_task_for_today_lp, axis=1)]['lp_gain'].sum()

                # Calculate LP per day for the selected week (Mon-Sun), offset by week
                today_date = now_in_season_tz.date()
                current_week_start = today_date - timedelta(days=today_date.weekday())
                start_of_week = current_week_start + timedelta(weeks=week)
                end_of_week = start_of_week + timedelta(days=6)

                # Helper to map finish_time to its LP day for weekly summary
                def get_lp_day(row):
                    task_finish_time = row['finish_time']
                    if pd.notna(task_finish_time):
                        task_finish_time_in_season_tz = task_finish_time.astimezone(season_timezone)
                        
                        task_lp_date = task_finish_time_in_season_tz.date()
                        if task_finish_time_in_season_tz.time() < time(day_start_hour):
                            task_lp_date = (task_finish_time_in_season_tz - timedelta(days=1)).date()
                        
                        if start_of_week <= task_lp_date <= end_of_week:
                            # Use the adjusted date to get the day of the week, not the original timestamp
                            return task_lp_date.strftime('%a')
                    return None

                df_completed['lp_day_of_week'] = df_completed.apply(get_lp_day, axis=1)
                weekly_lp = df_completed.groupby('lp_day_of_week')['lp_gain'].sum()
                
                # Ensure all days of the week are present
                days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                lp_by_day = {day: weekly_lp.get(day, 0.0) for day in days}

                # Weekly totals (LP gain and decay) and delta for the selected week
                weekly_lp_total = sum(lp_by_day.values())

                # Determine weekly decay events to count within the selected week window
                week_window_start = datetime.combine(start_of_week, time(day_start_hour), tzinfo=season_timezone)
                if week == 0:
                    week_window_end = now_in_season_tz
                else:
                    week_window_end = datetime.combine(end_of_week + timedelta(days=1), time(day_start_hour), tzinfo=season_timezone)

                decay_count_in_week = 0
                current_decay_point_for_week = max(first_decay_point_for_season, week_window_start)
                # Count decay events that occur within [week_window_start, week_window_end) (end exclusive)
                while current_decay_point_for_week < week_window_end:
                    decay_count_in_week += 1
                    current_decay_point_for_week += timedelta(days=1)
                weekly_decay = decay_count_in_week * daily_decay
                weekly_delta = weekly_lp_total - weekly_decay

            # Calculate time until next decay
            todays_decay_point = now_in_season_tz.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
            if now_in_season_tz >= todays_decay_point:
                next_decay_point = todays_decay_point + timedelta(days=1)
            else:
                next_decay_point = todays_decay_point
            time_until_next_decay = next_decay_point - now_in_season_tz

            # Calculate LP needed to survive next decay
            net_total_lp = total_lp_gain - total_decay
            breakeven_lp_gain_required = max(0, daily_decay - net_total_lp)

            return {
                'total_lp_gain': total_lp_gain,
                'total_decay': total_decay,
                'net_total_lp': net_total_lp,
                'daily_lp_gain': daily_lp_gain,
                'time_until_next_decay': time_until_next_decay,
                'breakeven_lp_gain_required': breakeven_lp_gain_required,
                'lp_by_day': lp_by_day,
                'season_name': active_season.name,
                'week': week,
                'weekly_lp_total': weekly_lp_total if not df_completed.empty else 0.0,
                'weekly_decay': weekly_decay if not df_completed.empty else 0.0,
                'weekly_delta': weekly_delta if not df_completed.empty else 0.0
            }

    @staticmethod
    def get_status_string(week: int = 0) -> str:
        """Format the LP status dictionary into a readable string."""
        status = StatusService.get_lp_status(week=week)
        active_season = SeasonService.get_current_season()
        season_name = status.get('season_name', 'N/A')

        total_lp_gain = status.get('total_lp_gain', 0.0)
        total_decay = status.get('total_decay', 0.0)
        net_total_lp = status.get('net_total_lp', 0.0)
        daily_lp_gain = status.get('daily_lp_gain', 0.0)
        time_until_next_decay = status.get('time_until_next_decay')
        breakeven_lp_gain_required = status.get('breakeven_lp_gain_required', 0.0)
        lp_by_day = status.get('lp_by_day', {})
        weekly_lp_total = status.get('weekly_lp_total', 0.0)
        weekly_decay = status.get('weekly_decay', 0.0)
        weekly_delta = status.get('weekly_delta', 0.0)

        status_str = f"Current Season: {season_name}\n"
        if week != 0:
            status_str += f"Viewing week offset: {week} (Mon-Sun)\n"
        status_str += f"Total LP Gain: {total_lp_gain:.2f}\n"
        status_str += f"Total Decay: {total_decay:.2f}\n"
        status_str += f"Net Total LP: {net_total_lp:.2f}\n"
        status_str += "--------------------\n"
        
        # Add LP by Day of Week
        status_str += "LP by Day of Week:\n"
        day_lp_parts = []
        daily_decay = active_season.daily_decay

        for day, lp in lp_by_day.items():
            if lp < daily_decay:
                day_lp_parts.append(f"[cyan]{day}[/cyan]: [bold red]{lp:.2f}[/bold red]")
            else:
                day_lp_parts.append(f"[cyan]{day}[/cyan]: [bold green]{lp:.2f}[/bold green]")
        
        status_str += " | ".join(day_lp_parts) + "\n"
        status_str += "--------------------\n"
        status_str += f"Selected Week LP Gain: {weekly_lp_total:.2f} | Decay: {weekly_decay:.2f} | Delta: {weekly_delta:.2f}\n"

        status_str += f"Today's LP Gain: {daily_lp_gain:.2f}\n"
        
        if time_until_next_decay:
            status_str += f"Survival Delta: You need to gain {breakeven_lp_gain_required:.2f} LP in the next {StatusService.format_timedelta(time_until_next_decay)} to break even.\n"
        else:
            status_str += f"Survival Delta: You will survive the next decay. Next decay in {StatusService.format_timedelta(time_until_next_decay)}.\n"

        return status_str


class BackupService:
    """Service for backup and restore operations."""
    
    @staticmethod
    def export_data(filename: str) -> None:
        """Export all data to a JSON file."""
        with get_db_session() as session:
            seasons = session.query(Season).all()
            
            backup_data = []
            for season in seasons:
                season_data = {c.name: getattr(season, c.name) for c in season.__table__.columns if hasattr(season, c.name)}
                season_data["tasks"] = [
                    {c.name: getattr(task, c.name) for c in task.__table__.columns if hasattr(task, c.name)}
                    for task in season.tasks
                ]
                backup_data.append(season_data)
        
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        
        try:
            with open(filename, "w") as f:
                json.dump(backup_data, f, indent=4, default=default_serializer)
            logger.info(f"Data exported to {filename}")
        except Exception as e:
            logger.error(f"Failed to export data: {e}")
            raise BackupImportError(f"Failed to export data to {filename}: {e}") from e
    
    @staticmethod
    def import_data(filename: str) -> None:
        """Import data from a JSON file, completely replacing current data."""
        try:
            with open(filename, "r") as f:
                backup_data = json.load(f)
        except FileNotFoundError:
            raise BackupFileNotFoundError(filename)
        except Exception as e:
            raise BackupImportError(f"Failed to read backup file {filename}: {e}") from e
        
        # Reset database
        from .database import reset_database
        reset_database()
        
        # Import data
        with get_db_session() as session:
            season_columns = {c.name for c in Season.__table__.columns}
            task_columns = {c.name for c in Task.__table__.columns}
            
            for season_data in backup_data:
                # Filter and convert season data
                filtered_season_data = {k: v for k, v in season_data.items() if k in season_columns}
                
                for key in ["start_date", "end_date"]:
                    if key in filtered_season_data and filtered_season_data[key]:
                        filtered_season_data[key] = datetime.fromisoformat(filtered_season_data[key])
                
                filtered_season_data.pop("tasks", None)
                new_season = Season(**filtered_season_data)
                session.add(new_season)
                session.flush()
                
                # Import tasks for this season
                for task_data in season_data.get("tasks", []):
                    filtered_task_data = {k: v for k, v in task_data.items() if k in task_columns}
                    
                    for key in ["start_time", "finish_time", "created_at"]:
                        if key in filtered_task_data and filtered_task_data[key]:
                            filtered_task_data[key] = datetime.fromisoformat(filtered_task_data[key])
                    
                    filtered_task_data["season_id"] = new_season.id
                    new_task = Task(**filtered_task_data)
                    session.add(new_task)
        
        logger.info(f"Data imported successfully from {filename}") 


class AnalysisService:
    """Service for data analysis and plotting."""
    
    @staticmethod
    def get_lp_timeseries_data() -> pd.DataFrame:
        """
        Get a timeseries of cumulative net LP, with data points for each event (task completion or decay).
        
        Returns:
            pd.DataFrame: DataFrame with 'timestamp', 'lp_change', 'type', and 'cumulative_lp'.
        """
        active_season = SeasonService.get_current_season()
        if not active_season:
            return pd.DataFrame()

        # Get season parameters
        season_tz_str = active_season.timezone_string
        season_timezone = gettz(season_tz_str)
        day_start_hour = active_season.day_start_hour
        daily_decay = active_season.daily_decay
        season_start_dt = active_season.start_date.astimezone(season_timezone)

        # 1. Create a list of all LP-changing events
        events = []
        
        # Add an initial event for the season start
        events.append({
            'timestamp': season_start_dt,
            'lp_change': 0.0,
            'type': 'season_start'
        })
        
        # 2. Add task completion events
        completed_tasks = TaskService.get_completed_tasks()
        for task in completed_tasks:
            if task.finish_time and task.lp_gain is not None:
                # Ensure finish_time is timezone-aware
                finish_time = task.finish_time
                if finish_time.tzinfo is None:
                    # Assume season timezone for naive datetimes
                    finish_time = finish_time.replace(tzinfo=season_timezone)
                
                events.append({
                    'timestamp': finish_time.astimezone(season_timezone),
                    'lp_change': task.lp_gain,
                    'type': 'gain'
                })

        # 3. Add decay events
        now_in_season_tz = datetime.now(season_timezone)
        
        # Determine the first decay point for the season
        first_decay_point = datetime.combine(season_start_dt.date(), time(day_start_hour), tzinfo=season_timezone)
        if first_decay_point < season_start_dt:
            first_decay_point += timedelta(days=1)
        
        current_decay_point = first_decay_point
        while current_decay_point <= now_in_season_tz:
            events.append({
                'timestamp': current_decay_point,
                'lp_change': -daily_decay,
                'type': 'decay'
            })
            current_decay_point += timedelta(days=1)

        if not events or len(events) < 2:
            return pd.DataFrame()

        # 4. Create DataFrame, sort, and calculate cumulative LP
        df = pd.DataFrame(events)
        df = df.sort_values(by='timestamp').reset_index(drop=True)
        df['cumulative_lp'] = df['lp_change'].cumsum()
        
        return df
        
    @staticmethod
    def _fit_and_forecast_sarimax(series: pd.Series, forecast_steps: int = 7) -> pd.Series:
        """
        Fits a SARIMAX model and generates a forecast.
        
        Args:
            series: The time series data (cumulative LP).
            forecast_steps: Number of steps to forecast into the future.
            
        Returns:
            pd.Series: Forecasted values with corresponding timestamps.
        """
        # Use auto_arima to find the best SARIMAX parameters
        # m=7 for weekly seasonality (7 days in a week)
        # suppress_warnings=True to keep output clean
        # stepwise=True for faster search
        
        # If not enough data for meaningful seasonal analysis, disable seasonal fitting
        # seasonal_arg = True
        # if len(daily_series) < 14: # Less than two full weeks of daily data
        #     seasonal_arg = False
        #     logger.warning("Insufficient data for seasonal SARIMAX. Fitting non-seasonal model.")

        if len(series) < 2: # Not enough data even for non-seasonal model (changed from daily_series to series)
            logger.warning("Very limited data. Cannot fit SARIMAX model. Returning last known LP as forecast.")
            # Return a simple flat forecast based on the last known value
            last_lp = series.iloc[-1] if not series.empty else 0.0
            last_date = series.index[-1] if not series.empty else datetime.now(timezone.utc) # Fallback if series is empty
            # For event-based forecasting, extend by timedelta, not days, for closer spacing if needed
            # For simplicity, forecasting daily points into future from last event.
            forecast_index = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
            return pd.Series(last_lp, index=forecast_index)

        # Temporarily suppress the specific FutureWarning from sklearn about 'force_all_finite'
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning, module=r'sklearn\.utils\.deprecation', message=".*force_all_finite.*")
            model = pm.auto_arima(series, # Changed from daily_series
                                  seasonal=False, m=1, # Changed to non-seasonal, m=1
                                  suppress_warnings=True,
                                  stepwise=True)
        
        # Generate forecast
        forecast_values = model.predict(n_periods=forecast_steps)
        
        # Create a date range for the forecast. This will still be daily points for forecasting.
        last_date = series.index[-1] # Changed from daily_series.index[-1]
        forecast_index = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
        forecast_series = pd.Series(forecast_values, index=forecast_index)
        
        # Prepend the last actual data point to the forecast for smooth plotting
        full_forecast_index = series.index[-1:].union(forecast_index) # Changed from daily_series.index[-1:]
        full_forecast_values = np.concatenate(([series.iloc[-1]], forecast_values)) # Changed from daily_series.iloc[-1]
        full_forecast_series = pd.Series(full_forecast_values, index=full_forecast_index)
        
        return full_forecast_series
        
    @staticmethod
    def _fit_and_predict_linear_regression(df: pd.DataFrame, forecast_steps: int = 0) -> pd.Series:
        """
        Fits a linear regression model to cumulative LP data and generates predictions.
        
        Args:
            df: DataFrame containing 'timestamp' and 'cumulative_lp'.
            forecast_steps: Number of steps to forecast into the future.
            
        Returns:
            pd.Series: Predicted LP values with corresponding timestamps.
        """
        if df.empty or len(df) < 2:
            logger.warning("Insufficient data for linear regression. Returning empty series.")
            return pd.Series()

        # Convert timestamps to numerical values (e.g., seconds since epoch)
        X_hist = (df['timestamp'].astype(np.int64) // 10**9).values.reshape(-1, 1)
        y_hist = df['cumulative_lp'].values
        
        model = LinearRegression()
        model.fit(X_hist, y_hist)
        
        if forecast_steps > 0:
            last_timestamp = df['timestamp'].max()
            # Generate future timestamps (daily frequency)
            future_timestamps = pd.date_range(start=last_timestamp + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
            X_future = (future_timestamps.astype(np.int64) // 10**9).values.reshape(-1, 1)
            
            # Combine historical and future X for prediction
            X_full = np.concatenate((X_hist, X_future))
            timestamps_full = pd.concat([df['timestamp'], pd.Series(future_timestamps)])
        else:
            X_full = X_hist
            timestamps_full = df['timestamp']

        predictions = model.predict(X_full)
        return pd.Series(predictions, index=timestamps_full)

    # @staticmethod
    # def _fit_and_predict_spline(df: pd.DataFrame, forecast_steps: int = 0) -> pd.Series:
    #     """
    #     Fits a univariate spline model to cumulative LP data and generates predictions.
    #     
    #     Args:
    #         df: DataFrame containing 'timestamp' and 'cumulative_lp'.
    #         forecast_steps: Number of steps to forecast into the future.
    #         
    #     Returns:
    #         pd.Series: Predicted LP values with corresponding timestamps.
    #     """
    #     if df.empty or len(df) < 2:
    #         logger.warning("Insufficient data for spline regression. Returning empty series.")
    #         return pd.Series()

    #     # Convert timestamps to numerical values (e.g., seconds since epoch)
    #     x_hist = (df['timestamp'].astype(np.int64) // 10**9).values
    #     y_hist = df['cumulative_lp'].values

    #     try:
    #         spl = UnivariateSpline(x_hist, y_hist, k=3)
            
    #         if forecast_steps > 0:
    #             last_timestamp = df['timestamp'].max()
    #             # Generate future timestamps (daily frequency)
    #             future_timestamps = pd.date_range(start=last_timestamp + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
    #             x_future = (future_timestamps.astype(np.int64) // 10**9).values
                
    #             # Combine historical and future x for prediction
    #             x_full = np.concatenate((x_hist, x_future))
    #             timestamps_full = pd.concat([df['timestamp'], pd.Series(future_timestamps)])
    #         else:
    #             x_full = x_hist
    #             timestamps_full = df['timestamp']

    #         predictions = spl(x_full)
    #     except Exception as e:
    #         logger.error(f"Error fitting spline: {e}")
    #         return pd.Series() # Return empty on error
        
    #     return pd.Series(predictions, index=timestamps_full)

    @staticmethod
    def plot_lp_timeseries_plotly(save_png: bool = False, filename="lp_plot.png", 
                                  include_forecast: bool = False, include_linear_regression: bool = False,
                                  # include_spline: bool = False, 
                                  forecast_steps: int = 7, interactive: bool = False):
        """
        Generate and either serve or save a Plotly plot of LP over time.
        Can include a SARIMAX forecast, a linear regression line, and/or a spline fit.
        If interactive=True, serves a clickable plot for backlogging tasks.
        """
        lp_df = AnalysisService.get_lp_timeseries_data()
        
        if lp_df.empty:
            print("Not enough data to plot.")
            return

        fig = px.line(
            lp_df,
            x='timestamp',
            y='cumulative_lp',
            title='Cumulative Net LP Over Time',
            labels={'timestamp': 'Timestamp', 'cumulative_lp': 'Cumulative Net LP'},
            markers=True # Add markers for each event
        )
        
        max_x_axis_date = lp_df['timestamp'].max()

        if include_forecast:
            # Need to create a Series with a DatetimeIndex for auto_arima
            lp_series_for_arima = lp_df.set_index('timestamp')['cumulative_lp']
            forecast_series = AnalysisService._fit_and_forecast_sarimax(lp_series_for_arima, forecast_steps=forecast_steps)
            
            # Add forecast to the plot
            fig.add_scatter(
                x=forecast_series.index,
                y=forecast_series.values,
                mode='lines',
                name='SARIMAX Forecast',
                line=dict(dash='dash', color='red')
            )
            # Update max_x_axis_date to include forecast range
            max_x_axis_date = max(max_x_axis_date, forecast_series.index.max())

        if include_linear_regression:
            linear_regression_series = AnalysisService._fit_and_predict_linear_regression(lp_df, forecast_steps=forecast_steps)
            if not linear_regression_series.empty:
                fig.add_scatter(
                    x=linear_regression_series.index,
                    y=linear_regression_series.values,
                    mode='lines',
                    name='Linear Regression',
                    line=dict(color='goldenrod', dash='dot') # Changed from green to goldenrod
                )
            # Update max_x_axis_date to include forecast range
            max_x_axis_date = max(max_x_axis_date, linear_regression_series.index.max() if not linear_regression_series.empty else max_x_axis_date)

        # if include_spline:
        #     spline_series = AnalysisService._fit_and_predict_spline(lp_df, forecast_steps=forecast_steps)
        #     if not spline_series.empty:
        #         fig.add_scatter(
        #             x=spline_series.index,
        #             y=spline_series.values,
        #             mode='lines',
        #             name='Spline Fit',
        #             line=dict(color='teal', dash='dashdot') # Changed from purple to teal
        #         )
        #     # Update max_x_axis_date to include forecast range
        #     max_x_axis_date = max(max_x_axis_date, spline_series.index.max() if not spline_series.empty else max_x_axis_date)
        
        fig.update_layout(
            template="plotly_white",
            xaxis=dict(tickformat="%Y-%m-%d %H:%M", range=[lp_df['timestamp'].min(), max_x_axis_date]),
            yaxis=dict(gridcolor='lightgrey'),
            xaxis_title="Timestamp",
            yaxis_title="Cumulative Net LP",
        )
        
        if interactive:
            AnalysisService._serve_interactive_plot(fig)
        elif save_png:
            fig.write_image(filename)
            print(f"Plot saved to {filename}")
        else:
            fig.show()

    @staticmethod
    def _serve_interactive_plot(fig):
        """Serve an interactive plot that allows clicking to add tasks."""
        
        class InteractiveHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    
                    # Always get fresh data on each page load to show new tasks
                    fresh_lp_df = AnalysisService.get_lp_timeseries_data()
                    if fresh_lp_df.empty:
                        # Return a simple message if no data
                        self.wfile.write(b'<html><body><h1>No LP data available</h1></body></html>')
                        return
                    
                    # Create fresh plot with current data
                    fresh_fig = px.line(
                        fresh_lp_df,
                        x='timestamp',
                        y='cumulative_lp',
                        title='Cumulative Net LP Over Time',
                        labels={'timestamp': 'Timestamp', 'cumulative_lp': 'Cumulative Net LP'},
                        markers=True
                    )
                    fresh_fig.update_layout(
                        template="plotly_white",
                        xaxis=dict(tickformat="%Y-%m-%d %H:%M"),
                        yaxis=dict(gridcolor='lightgrey'),
                        xaxis_title="Timestamp",
                        yaxis_title="Cumulative Net LP",
                    )
                    
                    # Create HTML with embedded plot and click handling
                    plot_json = fresh_fig.to_json()
                    
                    # Build HTML template manually to avoid f-string issues
                    html = """<!DOCTYPE html>
<html>
<head>
    <title>Interactive LP Plot - Click to Add Tasks</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .form-container { 
            position: fixed; top: 10px; right: 10px; 
            background: white; border: 2px solid #333; 
            padding: 15px; border-radius: 5px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 300px;
        }
        .form-container input, .form-container select { 
            width: 100%; margin: 5px 0; padding: 5px; 
            border: 1px solid #ccc; border-radius: 3px;
        }
        .form-container button { 
            width: 48%; margin: 5px 1%; padding: 8px; 
            border: none; border-radius: 3px; cursor: pointer;
        }
        .submit-btn { background: #28a745; color: white; }
        .cancel-btn { background: #dc3545; color: white; }
        #plot { width: 70%; height: 80vh; }
        .instructions { 
            background: #e9ecef; padding: 10px; border-radius: 5px; margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="instructions">
        <strong>Interactive Task Backlogging</strong><br>
        Click anywhere on the plot area (including empty spaces between points) to add a task at that exact time.
        <button onclick="location.reload()" style="float: right; background: #007bff; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">Refresh Data</button>
    </div>
    
    <div id="plot"></div>
    
    <div id="form-container" class="form-container" style="display: none;">
        <h4>Add Task</h4>
        <p id="selected-time"></p>
        <input type="text" id="task-desc" placeholder="Task description" required>
        <input type="text" id="project" placeholder="Project (optional)">
        <select id="difficulty">
            <option value="">Select difficulty (optional)</option>
            <option value="1">Easy</option>
            <option value="2">Easy-Med</option>
            <option value="3">Med</option>
            <option value="4">Med-Hard</option>
            <option value="5">Hard</option>
        </select>
        <input type="number" id="duration" placeholder="Duration in minutes (optional)">
        <button class="submit-btn" onclick="submitTask()">Add Task</button>
        <button class="cancel-btn" onclick="hideForm()">Cancel</button>
    </div>

    <script>
        var plotData = """ + plot_json + """;
        var selectedTimestamp = null;

        Plotly.newPlot('plot', plotData.data, plotData.layout);
        
        var plotDiv = document.getElementById('plot');
        
        // Create click detection for the entire plot area
        plotDiv.addEventListener('click', function(event) {
            var plotRect = plotDiv.getBoundingClientRect();
            var x = event.clientX - plotRect.left;
            var y = event.clientY - plotRect.top;
            
            // Use Plotly's built-in coordinate conversion
            if (plotDiv._fullLayout && plotDiv._fullLayout.xaxis) {
                var xaxis = plotDiv._fullLayout.xaxis;
                var yaxis = plotDiv._fullLayout.yaxis;
                
                // Check if click is within plot area
                if (x >= xaxis._offset && x <= xaxis._offset + xaxis._length &&
                    y >= yaxis._offset && y <= yaxis._offset + yaxis._length) {
                    
                    // Convert pixel coordinates to data coordinates
                    var relativeX = (x - xaxis._offset) / xaxis._length;
                    var xMin = new Date(xaxis.range[0]).getTime();
                    var xMax = new Date(xaxis.range[1]).getTime();
                    
                    selectedTimestamp = new Date(xMin + relativeX * (xMax - xMin)).toISOString();
                    
                    document.getElementById('selected-time').textContent = 
                        'Time: ' + new Date(selectedTimestamp).toLocaleString();
                    document.getElementById('form-container').style.display = 'block';
                    document.getElementById('task-desc').focus();
                }
            }
        });
        
        // Still handle point clicks for existing behavior
        plotDiv.on('plotly_click', function(data) {
            if (data.points.length > 0) {
                selectedTimestamp = data.points[0].x;
                document.getElementById('selected-time').textContent = 
                    'Time: ' + new Date(selectedTimestamp).toLocaleString();
                document.getElementById('form-container').style.display = 'block';
                document.getElementById('task-desc').focus();
            }
        });

        function hideForm() {
            document.getElementById('form-container').style.display = 'none';
            selectedTimestamp = null;
        }

        function submitTask() {
            var taskDesc = document.getElementById('task-desc').value.trim();
            if (!taskDesc) {
                alert('Please enter a task description');
                return;
            }

            var formData = new URLSearchParams();
            formData.append('timestamp', selectedTimestamp);
            formData.append('task', taskDesc);
            formData.append('project', document.getElementById('project').value);
            formData.append('difficulty', document.getElementById('difficulty').value);
            formData.append('duration', document.getElementById('duration').value);

            fetch('/add-task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message and reload after a brief delay
                    alert('Task added successfully! Refreshing plot to show new data...');
                    setTimeout(() => {
                        location.reload(); // Refresh to show updated plot
                    }, 500);
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                alert('Error adding task: ' + error);
            });

            hideForm();
        }
    </script>
</body>
</html>"""
                    self.wfile.write(html.encode())
                    
                elif self.path == '/add-task':
                    # This shouldn't be reached via GET, but handle gracefully
                    self.send_response(405)
                    self.end_headers()
                    
            def do_POST(self):
                if self.path == '/add-task':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length).decode('utf-8')
                    params = urllib.parse.parse_qs(post_data)
                    
                    try:
                        # Extract parameters
                        timestamp_str = params['timestamp'][0]
                        task_desc = params['task'][0]
                        project = params.get('project', [''])[0] or None
                        difficulty_str = params.get('difficulty', [''])[0]
                        duration_str = params.get('duration', [''])[0]
                        
                        # Parse timestamp
                        finish_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        
                        # Parse optional fields
                        difficulty = int(difficulty_str) if difficulty_str else None
                        duration = int(duration_str) if duration_str else None
                        
                        # Use TaskService to create the task
                        TaskService.create_task(
                            task_description=task_desc,
                            project=project,
                            difficulty=difficulty,
                            duration=duration,
                            completed=True,
                            finish_time_str=finish_time.strftime("%Y-%m-%d %H:%M:%S")
                        )
                        
                        response = {'success': True}
                        
                    except Exception as e:
                        logger.error(f"Error adding task via interactive plot: {e}")
                        response = {'success': False, 'error': str(e)}
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json_lib.dumps(response).encode())
                    
            def log_message(self, format, *args):
                # Suppress server logs
                pass
        
        # Start server in background thread
        port = 8000
        server = HTTPServer(('localhost', port), InteractiveHandler)
        
        def run_server():
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                server.shutdown()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Open browser
        url = f'http://localhost:{port}'
        print(f"Interactive plot server started at {url}")
        print("Click anywhere on the plot area (including empty spaces) to add a task at that exact time.")
        print("Press Ctrl+C to stop the server and return to CLI.")
        
        webbrowser.open(url)
        
        try:
            while True:
                time_module.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down interactive plot server...")
            server.shutdown()
            server_thread.join(timeout=2) 
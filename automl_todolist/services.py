"""Business logic services for the AutoML TodoList CLI application."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from dateutil.tz import gettz

import pandas as pd
import plotly.express as px

import panel as pn
# import hvplot.pandas 

pn.extension()

from sqlalchemy import func
from sqlalchemy.orm import Session

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
_current_timezone = DEFAULT_TIMEZONE


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
    def calculate_lp_gain(task: Task) -> Optional[float]:
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
                start_dt = start_dt.replace(tzinfo=_current_timezone)
            if finish_dt.tzinfo is None:
                finish_dt = finish_dt.replace(tzinfo=_current_timezone)

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
            now = datetime.now(_current_timezone)
            
            # Deactivate old season
            try:
                active_season = SeasonService.get_active_season(session)
                active_season.is_active = False
                active_season.end_date = now
                session.add(active_season)
                logger.info(f"Deactivated season: {active_season.name}")
            except NoActiveSeasonError:
                logger.info("No active season to deactivate")
            
            # Create new season
            new_season = Season(
                name=name, 
                is_active=True, 
                start_date=now,
                timezone_string=_current_timezone.key if hasattr(_current_timezone, 'key') else str(_current_timezone) # Initialize with current app timezone
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


class TaskService:
    """Service for task management operations."""
    
    @staticmethod
    def create_task(
        task_description: str,
        project: Optional[str] = None,
        difficulty: Optional[int] = None,
        dow: Optional[int] = None,
        duration: Optional[int] = None,
        completed: bool = False
    ) -> Task:
        """
        Create a new task.
        
        Args:
            task_description: Description of the task
            project: Project or category
            difficulty: Difficulty level (1-5)
            dow: Day of week (0-6)
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
        dow_str = ValidationService.validate_and_convert_dow(dow)
        
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            now = datetime.now(_current_timezone)
            
            new_task = Task(
                task=task_description,
                project=project,
                difficulty=difficulty_str,
                dow=dow_str,
                time_taken_minutes=duration,
                completed=completed,
                finish_time=now if completed else None,
                created_at=now,
                season_id=active_season.id
            )
            
            # Calculate LP if completed
            if completed:
                new_task.lp_gain = LPCalculationService.calculate_lp_gain(new_task)
            
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
            
            task.start_time = datetime.now(_current_timezone)
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
            
            task.finish_time = datetime.now(_current_timezone)
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
            if not task.finish_time:
                task.finish_time = datetime.now(_current_timezone)
            
            task.lp_gain = LPCalculationService.calculate_lp_gain(task)
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
        dow: Optional[int] = None,
        duration: Optional[int] = None,
        reflection: Optional[str] = None
    ) -> Task:
        """Update a task with new values."""
        # Validate inputs
        difficulty_str = ValidationService.validate_and_convert_difficulty(difficulty) if difficulty is not None else None
        dow_str = ValidationService.validate_and_convert_dow(dow) if dow is not None else None
        
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
            if dow_str is not None:
                task.dow = dow_str
            if duration is not None:
                task.time_taken_minutes = duration
            if reflection is not None:
                task.reflection = reflection
            
            # Recalculate LP if task is completed
            if task.completed:
                task.lp_gain = LPCalculationService.calculate_lp_gain(task)
            
            session.add(task)
            session.flush()
            session.refresh(task)
            session.expunge(task)
            logger.info(f"Updated task: {task.task} (ID: {task_id})")
            return task
    
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
            
            recalculated_count = 0
            for task in completed_tasks:
                # Normalize legacy difficulty values
                if task.difficulty in DIFFICULTY_NORMALIZATION_MAP:
                    task.difficulty = DIFFICULTY_NORMALIZATION_MAP[task.difficulty]
                
                new_lp = LPCalculationService.calculate_lp_gain(task)
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
    def get_lp_status() -> Dict[str, float]:
        """Get LP status for the current season."""
        with get_db_session() as session:
            active_season = SeasonService.get_active_season(session)
            
            # Total LP gain
            total_lp_gain = session.query(func.sum(Task.lp_gain)).filter(
                Task.season_id == active_season.id,
                Task.completed == True
            ).scalar() or 0
            
            # Today's LP gain
            today = datetime.now(_current_timezone).date()
            daily_lp_gain = session.query(func.sum(Task.lp_gain)).filter(
                Task.season_id == active_season.id,
                Task.completed == True,
                func.date(Task.finish_time) == today
            ).scalar() or 0
            
            # Decay calculation
            start_date_utc = active_season.start_date.astimezone(timezone.utc).date()
            today_utc = datetime.now(timezone.utc).date()
            days_passed = (today_utc - start_date_utc).days
            total_decay = days_passed * active_season.daily_decay
            net_total_lp = total_lp_gain - total_decay
            
            return {
                'total_lp_gain': total_lp_gain,
                'daily_lp_gain': daily_lp_gain,
                'total_decay': total_decay,
                'net_total_lp': net_total_lp,
                'days_passed': days_passed,
                'daily_decay_rate': active_season.daily_decay,
                'season_name': active_season.name
            }


class TimezoneService:
    """Service for timezone management."""
    
    @staticmethod
    def set_timezone(timezone_string: str) -> None:
        """Set the application timezone."""
        global _current_timezone
        timezone_obj = ValidationService.validate_timezone(timezone_string)
        _current_timezone = timezone_obj
        logger.info(f"Timezone set to: {timezone_string}")

        # Additionally, update the active season's timezone_string in the database
        with get_db_session() as session:
            try:
                active_season = SeasonService.get_active_season(session)
                active_season.timezone_string = timezone_string
                session.add(active_season)
                session.commit() # Commit immediately to persist the timezone change for the active season
                logger.info(f"Updated active season '{active_season.name}' timezone to: {timezone_string}")
            except NoActiveSeasonError:
                logger.warning("No active season to update timezone for. Timezone set globally but not persisted to a season.")
    
    @staticmethod
    def get_current_timezone():
        """Get the current timezone."""
        return _current_timezone


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
        Get a timeseries of cumulative net LP for the active season.
        
        Returns:
            pd.DataFrame: DataFrame with daily LP gain, decay, and cumulative net LP
        """
        active_season = SeasonService.get_current_season()
        completed_tasks = TaskService.get_completed_tasks()
        
        if not completed_tasks:
            return pd.DataFrame()
            
        # Create a DataFrame from tasks
        df = pd.DataFrame([
            {
                'finish_date': task.finish_time.date(),
                'lp_gain': task.lp_gain
            } 
            for task in completed_tasks if task.finish_time and task.lp_gain is not None
        ])
        
        if df.empty:
            return pd.DataFrame()

        # Group by day and sum LP gains
        daily_lp = df.groupby('finish_date')['lp_gain'].sum().reset_index()
        daily_lp = daily_lp.rename(columns={'finish_date': 'date', 'lp_gain': 'daily_lp_gain'})
        
        # Ensure 'date' column is in datetime format for merging
        daily_lp['date'] = pd.to_datetime(daily_lp['date'])
        
        # Create a full date range for the season
        start_date = min(daily_lp['date'])
        end_date = max(daily_lp['date'])
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # Create a DataFrame for the full date range
        season_df = pd.DataFrame(date_range, columns=['date'])
        
        # Merge daily LP gains with the full date range
        season_df = pd.merge(season_df, daily_lp, on='date', how='left').fillna(0)
        
        # Calculate daily decay and cumulative LP
        season_df['daily_decay'] = active_season.daily_decay
        season_df['net_daily_lp'] = season_df['daily_lp_gain'] - season_df['daily_decay']
        season_df['cumulative_net_lp'] = season_df['net_daily_lp'].cumsum()
        
        # Set date as index for cleaner plotting
        season_df = season_df.set_index('date')
        
        return season_df
        
    @staticmethod
    def plot_lp_timeseries_plotly(save_png: bool = False, filename="lp_plot.png"):
        """
        Generate and either serve or save a Plotly plot.
        """
        lp_df = AnalysisService.get_lp_timeseries_data()
        
        if lp_df.empty or len(lp_df) < 2:
            print("Not enough data to plot.")
            return

        fig = px.line(
            lp_df,
            x=lp_df.index,
            y='cumulative_net_lp',
            title='Cumulative Net LP Over Time',
            labels={'date': 'Date', 'cumulative_net_lp': 'Cumulative Net LP'}
        )
        
        fig.update_layout(
            template="plotly_white",
            xaxis=dict(tickformat="%Y-%m-%d"),
            yaxis=dict(gridcolor='lightgrey'),
            xaxis_title="Date",
            yaxis_title="Cumulative Net LP",
        )
        
        if save_png:
            fig.write_image(filename)
            print(f"Plot saved to {filename}")
        else:
            fig.show() 
"""Database models for the AutoML TodoList CLI application."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

Base = declarative_base()


class Season(Base):
    """Model representing a season/period for task organization.
    
    Attributes:
        id: Unique identifier for the season
        name: Human-readable name for the season
        start_date: When the season was started
        end_date: When the season was archived (None if active)
        is_active: Whether this is the currently active season
        daily_decay: Daily LP decay rate for this season
        tasks: Related tasks in this season
    """
    __tablename__ = "seasons"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    daily_decay = Column(Float, default=56.0, nullable=False)
    
    # Relationships
    tasks = relationship("Task", back_populates="season")

    def __repr__(self) -> str:
        return f"<Season(id={self.id}, name='{self.name}', active={self.is_active})>"


class Task(Base):
    """Model representing a task within a season.
    
    Attributes:
        id: Unique identifier for the task
        dow: Day of week (abbreviated, e.g., 'Mon')
        task: Description of the task
        project: Project or category the task belongs to
        difficulty: Difficulty level (Easy, Easy-Med, Med, Med-Hard, Hard)
        start_time: When the task was started
        finish_time: When the task was finished/stopped
        time_taken_minutes: Manual override for task duration
        lp_gain: Life points gained from completing the task
        reflection: User's reflection on the completed task
        completed: Whether the task is marked as complete
        created_at: When the task was created
        season_id: Foreign key to the season this task belongs to
        season: Related season object
    """
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    dow = Column(String, nullable=True)
    task = Column(String, index=True, nullable=False)
    project = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=True)
    finish_time = Column(DateTime, nullable=True)
    time_taken_minutes = Column(Integer, nullable=True)
    lp_gain = Column(Float, nullable=True)
    reflection = Column(String, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    
    # Relationships
    season = relationship("Season", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, task='{self.task}', completed={self.completed})>" 
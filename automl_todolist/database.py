"""Database configuration and session management for AutoML TodoList CLI."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from .config import DATABASE_URL, DEFAULT_SEASON_NAME
from .models import Base, Season
from .exceptions import DatabaseError

# Configure logging
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Provides proper session lifecycle management with automatic
    rollback on exceptions and cleanup on exit.
    
    Yields:
        Session: SQLAlchemy database session
        
    Raises:
        DatabaseError: If database operation fails
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        raise DatabaseError(f"Database operation failed: {e}") from e
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error during database operation: {e}")
        raise DatabaseError(f"Unexpected database error: {e}") from e
    finally:
        session.close()


def init_database() -> None:
    """
    Initialize the database schema and create default season if needed.
    
    Raises:
        DatabaseError: If database initialization fails
    """
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully")
        
        # Create default season if none exists
        with get_db_session() as session:
            if not session.query(Season).count():
                from datetime import datetime
                from .config import DEFAULT_TIMEZONE
                default_season = Season(
                    name=DEFAULT_SEASON_NAME, 
                    is_active=True,
                    start_date=datetime.now(DEFAULT_TIMEZONE)
                )
                session.add(default_season)
                logger.info(f"Created default season: {DEFAULT_SEASON_NAME}")
                
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise DatabaseError(f"Database initialization failed: {e}") from e


def reset_database() -> None:
    """
    Drop all tables and recreate the schema.
    
    WARNING: This will destroy all data!
    
    Raises:
        DatabaseError: If database reset fails
    """
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        logger.warning("Database reset completed - all data destroyed")
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        raise DatabaseError(f"Database reset failed: {e}") from e 
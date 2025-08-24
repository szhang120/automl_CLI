"""Database configuration and session management for AutoML TodoList CLI."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
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

# Ensure schema initialized lazily and safely (idempotent)
_schema_initialized = False

def _ensure_schema_initialized() -> None:
    global _schema_initialized
    if _schema_initialized:
        return
    try:
        # Idempotent: creates missing tables only, does not drop existing
        Base.metadata.create_all(bind=engine)

        # Lightweight, safe column migrations for SQLite
        with engine.connect() as conn:
            # Ensure 'deadline' column on 'tasks'
            try:
                result = conn.exec_driver_sql("PRAGMA table_info('tasks')")
                cols = [row[1] for row in result.fetchall()]
                if 'deadline' not in cols:
                    conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN deadline DATETIME")
                    logger.debug("Added missing column tasks.deadline")
                if 'importance' not in cols:
                    conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN importance VARCHAR")
                    logger.debug("Added missing column tasks.importance")
            except Exception as _:
                # Do not fail app startup due to PRAGMA limitations
                pass

        _schema_initialized = True
        logger.debug("Verified database schema (create_all + light migrations).")
    except Exception as e:
        logger.error(f"Failed to ensure database schema: {e}")
        raise DatabaseError(f"Failed to ensure database schema: {e}") from e


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
    # Ensure tables exist before opening a session (safe, no data loss)
    _ensure_schema_initialized()

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
                    start_date=datetime.now(DEFAULT_TIMEZONE),
                    timezone_string=DEFAULT_TIMEZONE.key if hasattr(DEFAULT_TIMEZONE, 'key') else "UTC"
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
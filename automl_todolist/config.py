"""Configuration settings and constants for the AutoML TodoList CLI application."""

import os
from typing import Dict
from dateutil.tz import gettz

# Database configuration
DEFAULT_DATABASE_URL = "sqlite:///tasks.db"
DATABASE_URL = os.getenv("AUTOML_TODOLIST_DATABASE_URL", DEFAULT_DATABASE_URL)

# Default timezone configuration
DEFAULT_TIMEZONE_STRING = "America/New_York"
DEFAULT_TIMEZONE = gettz(DEFAULT_TIMEZONE_STRING)

# Day of Week mapping
DOW_MAP: Dict[str, str] = {
    "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
    "4": "Thu", "5": "Fri", "6": "Sat",
}

# Valid day of week abbreviations (for validation)
VALID_DOW_ABBREVS = set(DOW_MAP.values())

# Difficulty mapping from integer to string
DIFFICULTY_MAP_INT_TO_STR: Dict[int, str] = {
    1: "Easy",
    2: "Easy-Med",
    3: "Med",
    4: "Med-Hard",
    5: "Hard",
}

# Valid difficulty levels (for validation)
VALID_DIFFICULTIES = set(DIFFICULTY_MAP_INT_TO_STR.values())

# Points mapping for LP calculation
POINTS_MAP: Dict[str, int] = {
    "Easy": 1,
    "Easy-Med": 2,
    "Med": 4,
    "Med-Hard": 8,
    "Hard": 16,
}

# Legacy difficulty mapping for normalization
DIFFICULTY_NORMALIZATION_MAP: Dict[str, str] = {
    "Medium": "Med"
}

# Default season settings
DEFAULT_SEASON_NAME = "Default Season"
DEFAULT_DAILY_DECAY = 56.0

# Time calculation constants
MINUTES_PER_HOUR = 60
ROUNDING_INTERVAL_MINUTES = 15

# Validation ranges
MIN_DIFFICULTY_LEVEL = 1
MAX_DIFFICULTY_LEVEL = 5
MIN_DOW_VALUE = 0
MAX_DOW_VALUE = 6

# Application metadata
APP_NAME = "AutoML TodoList CLI"
APP_VERSION = "0.1.0" 
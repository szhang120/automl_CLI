"""Custom exceptions for the AutoML TodoList CLI application."""


class AutoMLTodolistError(Exception):
    """Base exception for all AutoML Todolist-specific errors."""
    pass


class DatabaseError(AutoMLTodolistError):
    """Raised when database operations fail."""
    pass


class NoActiveSeasonError(AutoMLTodolistError):
    """Raised when an operation requires an active season but none exists."""
    
    def __init__(self, message: str = "No active season found. Use 'season start' to begin."):
        super().__init__(message)


class TaskNotFoundError(AutoMLTodolistError):
    """Raised when a requested task cannot be found."""
    
    def __init__(self, task_id: int):
        super().__init__(f"Task with ID {task_id} not found in the current season.")
        self.task_id = task_id


class SeasonNotFoundError(AutoMLTodolistError):
    """Raised when a requested season cannot be found."""
    
    def __init__(self, season_id: int):
        super().__init__(f"Season with ID {season_id} not found.")
        self.season_id = season_id


class ValidationError(AutoMLTodolistError):
    """Raised when input validation fails."""
    pass


class InvalidDifficultyError(ValidationError):
    """Raised when an invalid difficulty value is provided."""
    
    def __init__(self, difficulty_value):
        super().__init__(
            f"Invalid difficulty value '{difficulty_value}'. "
            f"Please use an integer between 1 and 5."
        )
        self.difficulty_value = difficulty_value


class InvalidDayOfWeekError(ValidationError):
    """Raised when an invalid day of week value is provided."""
    
    def __init__(self, dow_value):
        super().__init__(
            f"Invalid Day of Week value '{dow_value}'. "
            f"Please use an integer between 0 and 6."
        )
        self.dow_value = dow_value


class InvalidTimezoneError(ValidationError):
    """Raised when an invalid timezone string is provided."""
    
    def __init__(self, timezone_string: str):
        super().__init__(f"Invalid timezone string '{timezone_string}'.")
        self.timezone_string = timezone_string


class BackupFileNotFoundError(AutoMLTodolistError):
    """Raised when a backup file cannot be found."""
    
    def __init__(self, filename: str):
        super().__init__(f"Backup file '{filename}' not found.")
        self.filename = filename


class BackupImportError(AutoMLTodolistError):
    """Raised when backup import fails."""
    pass 
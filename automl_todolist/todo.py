"""AutoML TodoList CLI - A powerful command-line to-do list application."""

import logging
import typer
from rich.console import Console
from rich.table import Table
from typing import Optional
from dateutil.tz import gettz

from .database import init_database
from .services import (
    SeasonService, TaskService, StatusService, 
    BackupService, ValidationService, AnalysisService,
    RecurringTaskService
)
from .exceptions import (
    AutoMLTodolistError, NoActiveSeasonError, TaskNotFoundError, 
    SeasonNotFoundError, InvalidDifficultyError, InvalidDayOfWeekError,
    InvalidTimezoneError, BackupFileNotFoundError, BackupImportError,
    RecurringTaskNotFoundError
)
from . import calendar_sync

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Typer application setup
app = typer.Typer(help="AutoML TodoList CLI - A powerful task management tool")
season_app = typer.Typer(help="Season management commands")
backup_app = typer.Typer(help="Backup and restore commands")
calendar_app = typer.Typer(help="Google Calendar integration commands")
recurring_app = typer.Typer(
    help="Manage templates for recurring tasks. Tasks are only generated when you run 'todo recurring run'."
)
# analysis_app = typer.Typer(help="Data analysis commands") # This will be removed as plot-lp is moved

app.add_typer(season_app, name="season")
app.add_typer(backup_app, name="backup")
app.add_typer(recurring_app, name="recurring")
app.add_typer(calendar_app, name="calendar")
# app.add_typer(analysis_app, name="analysis") # Removed


# Rich console for beautiful output
console = Console()



def handle_errors(func):
    """Decorator to handle common errors and display them in a standard format."""
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AutoMLTodolistError as e:
            error_style = "bold red"
            console.print(f"Error: {e}", style=error_style)
        except Exception as e:
            logger.error("Unexpected error occurred", exc_info=True)
            error_style = "bold red"
            console.print(f"Unexpected Error: {e}", style=error_style)
    return wrapper

@app.command()
@handle_errors
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Force reinitialization, deleting existing data."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt when using --force."),
):
    """Initialize the database."""
    if force:
        if not yes and not typer.confirm("This will delete the existing database. Are you sure?"):
            raise typer.Abort()
        from .database import reset_database
        reset_database()
        console.print("[bold yellow]Existing database deleted.[/bold yellow]")
    init_database()
    console.print("[bold green]Database initialized.[/bold green]")
    console.print("[bold blue]Created a default season.[/bold blue]")

@season_app.command("start")
@handle_errors
def season_start(name: str):
    """Start a new season, archiving the old one."""
    new_season = SeasonService.create_season(name)
    console.print(f"[bold green]Archived old season and started new season:[/bold green] '{name}'")

@season_app.command("list")
@handle_errors
def season_list():
    """List all seasons."""
    seasons = SeasonService.list_seasons()

    table = Table(title="All Seasons")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Status", style="green")

    for season in seasons:
        status = "Active" if season.is_active else "Archived"
        table.add_row(str(season.id), season.name, status)
    
    console.print(table)

@season_app.command("switch")
@handle_errors
def season_switch(season_id: int):
    """Switch the active season."""
    new_season = SeasonService.switch_season(season_id)
    console.print(f"[bold green]Switched active season to:[/bold green] '{new_season.name}'")

@season_app.command("current")
@handle_errors
def season_current():
    """Show the current active season."""
    season = SeasonService.get_current_season()
    console.print(f"The current active season is: [bold blue]{season.name}[/bold blue]")

@season_app.command("get-timezone")
@handle_errors
def season_get_timezone():
    """Show the timezone assigned to the current active season."""
    season = SeasonService.get_current_season()
    console.print(f"The timezone for season '{season.name}' is: [bold blue]{season.timezone_string}[/bold blue]")

@season_app.command("set-decay")
@handle_errors
def season_set_decay(decay_value: float):
    """Set the daily LP decay for the active season."""
    season = SeasonService.set_decay(decay_value)
    console.print(
        f"[bold green]Daily decay for season '{season.name}' set to:[/bold green] {decay_value}"
    )

@season_app.command("set-timezone")
@handle_errors
def season_set_timezone(tz_string: str):
    """Set the timezone for the application.

    The timezone string should be a valid IANA Time Zone Database name,
    e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo', or 'UTC'.
    """
    SeasonService.set_timezone(tz_string)
    console.print(f"[bold green]Timezone set to:[/bold green] {tz_string}")

@season_app.command("set-day-start-hour")
@handle_errors
def season_set_day_start_hour(hour: int = typer.Argument(..., min=0, max=23, help="The hour (0-23) at which a new day begins for LP decay calculation.")):
    """Set the custom day start hour for the active season.

    This allows you to define when a new 'day' begins for the purpose of
    daily LP decay, typically when your activities for the previous day end.
    For example, setting to 4 would mean 4:00 AM is the start of a new day.
    """
    try:
        season = SeasonService.set_day_start_hour(hour)
        console.print(f"[bold green]Day start hour for season '{season.name}' set to:[/bold green] {hour}:00")
    except ValueError as e:
        console.print(f"[bold red]Validation Error:[/bold red] {e}")
        raise typer.Exit(1)


@season_app.command("recalculate-lp") # Moved back to season_app
@handle_errors
def season_recalculate_lp(
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt."),
):
    """Recalculate LP for all completed tasks in the active season based on the current rules."""
    completed_tasks = TaskService.get_completed_tasks()
    
    if not completed_tasks:
        console.print("[bold blue]No completed tasks found in the active season to recalculate.[/bold blue]")
        return

    season = SeasonService.get_current_season()
    if not yes:
        console.print(f"[bold yellow]This will recalculate LP for {len(completed_tasks)} completed tasks in the '{season.name}' season. This cannot be undone.[/bold yellow]")
        if not typer.confirm("Are you sure you want to continue?"):
            raise typer.Abort()

    recalculated_count = TaskService.recalculate_all_lp()
    
    if recalculated_count > 0:
        console.print(f"[bold green]Successfully recalculated LP for {recalculated_count} tasks.[/bold green]")
    else:
        console.print("[bold blue]All task LP values are already up-to-date.[/bold blue]")

@backup_app.command("export")
@handle_errors
def backup_export(filename: str = typer.Argument("backup.json")):
    """Export all data to a JSON file."""
    BackupService.export_data(filename)
    console.print(f"[bold green]Data exported to {filename}[/bold green]")


@backup_app.command("import")
@handle_errors
def backup_import(
    filename: str = typer.Argument("backup.json"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt."),
):
    """Import data from a JSON file, overwriting the current database."""
    if not yes and not typer.confirm("This will overwrite your current database. Are you sure you want to continue?"):
        raise typer.Abort()

    BackupService.import_data(filename)
    console.print(f"[bold green]Data imported successfully from {filename}.[/bold green]")


@recurring_app.command("add")
@handle_errors
def recurring_add(
    task: str = typer.Argument(..., help="Description of the recurring task."),
    frequency: str = typer.Option(..., "--frequency", "--freq", "-f", help="Frequency of the task. e.g., 'daily', 'weekdays', 'weekends', or a comma-separated list like 'Mon,Wed,Fri'."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project or category for the task."),
    level: Optional[int] = typer.Option(None, "--level", "-l", min=1, max=5, help="Difficulty level (1-5)."),
    minutes: Optional[int] = typer.Option(None, "--minutes", "-m", help="Default duration in minutes."),
    due_time: Optional[str] = typer.Option(None, "--due-time", "-d", help="A due time to append to the task description (e.g., '22:00').")
):
    """Create a template for a task that repeats on a schedule."""
    RecurringTaskService.create_recurring_task(
        task_description=task,
        frequency=frequency,
        project=project,
        difficulty=level,
        duration=minutes,
        due_time=due_time
    )
    console.print(f"[bold green]Added recurring task template:[/bold green] '{task}' with frequency '{frequency}'")

@recurring_app.command("list")
@handle_errors
def recurring_list():
    """List all active recurring task templates for the current season."""
    templates = RecurringTaskService.list_recurring_tasks()
    season = SeasonService.get_current_season()

    table = Table(title=f"Recurring Task Templates for {season.name}")
    table.add_column("ID", style="cyan")
    table.add_column("Task", style="magenta")
    table.add_column("Project", style="yellow")
    table.add_column("Frequency", style="blue")
    table.add_column("Difficulty", style="white")
    table.add_column("Minutes", style="red")
    table.add_column("Due Time", style="green")

    for t in templates:
        table.add_row(
            str(t.id),
            t.task,
            t.project or "N/A",
            t.frequency,
            t.difficulty or "N/A",
            str(t.time_taken_minutes) if t.time_taken_minutes is not None else "N/A",
            t.due_time or "N/A"
        )
    
    console.print(table)

@recurring_app.command("delete")
@handle_errors
def recurring_delete(
    template_id: int = typer.Argument(..., help="The ID of the recurring task template to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt."),
):
    """Delete a recurring task template by its ID. Does not affect tasks already generated."""
    if not yes:
        console.print(f"[bold red]You are about to delete recurring task template {template_id}. This cannot be undone.[/bold red]")
        if not typer.confirm("Are you sure you want to delete this template?"):
            raise typer.Abort()
            
    RecurringTaskService.delete_recurring_task(template_id)
    console.print(f"[bold green]Successfully deleted recurring task template {template_id}.[/bold green]")


@recurring_app.command("run")
@handle_errors
def recurring_run():
    """Run recurring templates to create tasks for today.

    This command checks for any recurring templates due today and creates any
    missing tasks. It's automatically invoked by `todo list` but can be run
    explicitly via `todo recurring run`.
    """
    generated_count = RecurringTaskService.generate_tasks_from_templates()
    if generated_count > 0:
        console.print(f"[bold green]Created {generated_count} recurring task(s) for today.[/bold green]")
    else:
        console.print("[bold blue]No new recurring tasks to create for today.[/bold blue]")


@calendar_app.command("connect")
@handle_errors
def calendar_connect(credentials: str = typer.Option("credentials.json", "--credentials", "-c", help="Path to Google OAuth client secrets JSON.")):
    """Connect your Google account (OAuth) and store token locally."""
    token_path = calendar_sync.connect(credentials_path=credentials)
    console.print(f"[bold green]Google account connected. Token saved at:[/bold green] {token_path}")


@calendar_app.command("list-calendars")
@handle_errors
def calendar_list_calendars():
    """List available calendars for your Google account."""
    cals = calendar_sync.list_calendars()
    table = Table(title="Google Calendars")
    table.add_column("Calendar ID", style="cyan")
    table.add_column("Summary", style="magenta")
    for cal_id, summary in cals:
        table.add_row(cal_id, summary)
    console.print(table)


@calendar_app.command("set-calendar")
@handle_errors
def calendar_set_calendar(calendar_id: str = typer.Argument(..., help="Calendar ID to use by default for sync.")):
    """Set the default Google Calendar for sync operations."""
    calendar_sync.set_default_calendar(calendar_id)
    console.print(f"[bold green]Default calendar set to:[/bold green] {calendar_id}")


@calendar_app.command("sync")
@handle_errors
def calendar_sync_cmd(
    direction: str = typer.Option("both", "--direction", "-d", help="Sync direction: push, pull, or both.", case_sensitive=False),
    days_back: int = typer.Option(14, "--days-back", help="Include events/tasks this many days back."),
    days_forward: int = typer.Option(14, "--days-forward", help="Include events/tasks this many days forward."),
):
    """Synchronize tasks with Google Calendar (two-way)."""
    direction = direction.lower()
    if direction not in {"push", "pull", "both"}:
        raise typer.BadParameter("--direction must be one of: push, pull, both")
    counts = calendar_sync.sync(direction=direction, days_back=days_back, days_forward=days_forward)
    console.print(f"[bold green]Sync complete:[/bold green] pushed={counts['pushed']}, pulled={counts['pulled']}")


@app.command()
@handle_errors
def add(
    task: str,
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    level: Optional[int] = typer.Option(None, "--level", "-l", min=1, max=5, help="Difficulty level (1-5)."),
    # day: Optional[int] = typer.Option(None, "--day", "-d", min=0, max=6, help="Day of week (0-6, or Mon, Tue, etc.)."), # Removed
    minutes: Optional[int] = typer.Option(None, "--minutes", "-m", help="Expected or manual duration in minutes."),
    deadline: Optional[str] = typer.Option(None, "--deadline", "-d", help="Deadline (YYYY-MM-DD HH:MM:SS) for scheduling/GCAL."),
    importance: Optional[int] = typer.Option(None, "--importance", "-i", help="Importance: 1=Critical, 0=Non-Critical"),
    finish_time: Optional[str] = typer.Option(None, "--finish-time", "-f", help="Specify a historical finish time (YYYY-MM-DD HH:MM:SS) if --completed is used."),
    completed: bool = typer.Option(False, "--completed", "-C", help="Mark the task as completed immediately."),
):
    """Add a new task to the active season."""
    new_task = TaskService.create_task(
        task_description=task,
        project=project,
        difficulty=level,
        # dow=day, # Removed
        duration=minutes,
        deadline_str=deadline,
        importance=importance,
        completed=completed,
        finish_time_str=finish_time
    )
    
    if completed:
        console.print(f"[bold green]Logged completed task:[/bold green] '{task}'")
    else:
        console.print(f"[bold green]Added task:[/bold green] '{task}'")

@app.command(name="list")
@handle_errors
def list_tasks():
    """List all active (incomplete) tasks.
    
    Also generates any recurring tasks that are due today.
    """
    tasks = TaskService.get_active_tasks()
    season = SeasonService.get_current_season()

    table = Table(title=f"Active Tasks for {season.name}")
    table.add_column("ID", style="cyan")
    table.add_column("DoW", style="white")
    table.add_column("Project", style="yellow")
    table.add_column("Task", style="magenta")
    table.add_column("Difficulty", style="blue")
    table.add_column("Importance", style="red")
    table.add_column("Deadline", style="green")
    table.add_column("Status", style="green")

    for t in tasks:
        status = "In Progress" if t.start_time and not t.finish_time else "Not Started"
        table.add_row(
            str(t.id),
            t.dow or "N/A",
            t.project or "N/A",
            t.task,
            t.difficulty or "N/A",
            t.importance or "Non-Critical",
            (t.deadline.astimezone(gettz(season.timezone_string)).strftime("%Y-%m-%d %H:%M") if t.deadline else "N/A"),
            status,
        )
    
    console.print(table)


@app.command()
@handle_errors
def done(task_id: int):
    """Complete a task in the current season."""
    task = TaskService.complete_task(task_id)
    console.print(f"[bold green]Completed task:[/bold green] {task.task}")

@app.command()
@handle_errors
def log(
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="Number of most recent completed tasks to show.")
):
    """List completed tasks for the current season (most recent first)."""
    active_season = SeasonService.get_current_season()
    if not active_season:
        raise NoActiveSeasonError("No active season found.")

    console.print(f"Completed Tasks for {active_season.name} (last {limit})", style="bold cyan")
    
    table = TaskService.get_completed_tasks_table(limit=limit)
    console.print(table)

    status_string = StatusService.get_status_string()
    console.print(status_string)


@app.command()
@handle_errors
def start(task_id: int):
    """Start a task in the current season."""
    task = TaskService.start_task(task_id)
    console.print(f"[bold green]Started task:[/bold green] {task.task}")

@app.command()
@handle_errors
def stop(task_id: int):
    """Stop a task in the current season."""
    task = TaskService.stop_task(task_id)
    console.print(f"[bold green]Stopped task:[/bold green] {task.task}")

@app.command()
@handle_errors
def update(
    task_id: int,
    new_task_name: Optional[str] = typer.Option(None, "--task", "-t", help="New description of the task."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="New project or category."),
    level: Optional[int] = typer.Option(None, "--level", "-l", min=1, max=5, help="New difficulty level (1-5)."),
    # day: Optional[int] = typer.Option(None, "--day", "-d", min=0, max=6, help="New Day of Week (0-6, or Mon, Tue, etc.)."), # Removed
    minutes: Optional[int] = typer.Option(None, "--minutes", "-m", help="Expected or manual duration in minutes."),
    deadline: Optional[str] = typer.Option(None, "--deadline", "-d", help="Deadline (YYYY-MM-DD HH:MM:SS)."),
    importance: Optional[int] = typer.Option(None, "--importance", "-i", help="Importance: 1=Critical, 0=Non-Critical"),
    reflection: Optional[str] = typer.Option(None, "--reflection", "-r", help="New reflection notes."),
    finish_time: Optional[str] = typer.Option(None, "--finish-time", "-f", help="New finish time (YYYY-MM-DD HH:MM:SS)."),
):
    """Update a task in the current season."""
    task_obj = TaskService.update_task(
        task_id=task_id,
        task_description=new_task_name,
        project=project,
        difficulty=level,
        # dow=day, # Removed
        duration=minutes,
        reflection=reflection,
        finish_time_str=finish_time,
        deadline_str=deadline,
        importance=importance
    )
    console.print(f"[bold green]Updated task:[/bold green] {task_obj.task}")

@app.command()
@handle_errors
def status(
    week: Optional[int] = typer.Option(None, "--week", "-w", help="Week offset relative to current week. Use -1 for last week, -2 for two weeks ago, etc."),
    week_arg: Optional[int] = typer.Argument(None, help="Optional positional week offset. Tip: for negative values use --week -1 or `-- -1`.")
):
    """Show the LP status for the active season, with optional week offset for weekly breakdown."""
    selected_week = week if week is not None else (week_arg if week_arg is not None else 0)
    status_string = StatusService.get_status_string(week=selected_week)
    console.print(status_string)

@app.command("plot") # Changed from @analysis_app.command("plot-lp")
@handle_errors
def plot_lp(
    save_png: bool = typer.Option(False, "--save-png", "-s", help="Save the plot as a PNG image file instead of serving it."),
    filename: str = typer.Option("lp_plot.png", "--filename", "-f", help="Filename for the saved PNG plot."),
    include_forecast: bool = typer.Option(True, "--forecast", "-F", help="Include SARIMAX forecast in the plot."),
    include_linear_regression: bool = typer.Option(True, "--linear-regression", "--lr", "-R", help="Include linear regression in the plot."),
    forecast_days: int = typer.Option(1, "--forecast-days", "-D", help="Number of days to forecast into the future for all models."),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Start interactive mode for clicking to backlog tasks on the timeline.")
):
    """Generate and serve a plot of cumulative net LP over time."""
    from .services import AnalysisService
    
    if interactive:
        console.print("[bold green]Starting interactive plotting mode for task backlogging...[/bold green]")
        AnalysisService.plot_lp_timeseries_plotly(
            include_forecast=include_forecast, 
            include_linear_regression=include_linear_regression, 
            forecast_steps=forecast_days,
            interactive=True
        )
    elif save_png:
        console.print(f"[bold green]Generating and saving plot to {filename}...[/bold green]")
        AnalysisService.plot_lp_timeseries_plotly(save_png=True, filename=filename, 
                                                  include_forecast=include_forecast, 
                                                  include_linear_regression=include_linear_regression, 
                                                  forecast_steps=forecast_days)
    else:
        console.print("[bold green]Generating and serving interactive plot...[/bold green]")
        AnalysisService.plot_lp_timeseries_plotly(include_forecast=include_forecast, 
                                                  include_linear_regression=include_linear_regression, 
                                                  forecast_steps=forecast_days)
        console.print("[bold blue]Plot server started. Check your browser.[/bold blue]")


@app.command("delete")
@handle_errors
def delete_task(
    task_id: int = typer.Argument(..., help="The ID of the task to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt."),
):
    """Delete a task by its ID."""
    task = TaskService.get_task(task_id) # First, fetch to confirm it exists
    
    if not yes:
        console.print(f"[bold red]You are about to delete task {task.id}: '{task.task}'. This cannot be undone.[/bold red]")
        if not typer.confirm("Are you sure you want to delete this task?"):
            raise typer.Abort()
            
    TaskService.delete_task(task_id)
    console.print(f"[bold green]Successfully deleted task {task_id}.[/bold green]")


if __name__ == "__main__":
    app() 
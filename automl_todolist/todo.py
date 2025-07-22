"""AutoML TodoList CLI - A powerful command-line to-do list application."""

import logging
import typer
from rich.console import Console
from rich.table import Table
from typing import Optional
from dateutil.tz import gettz

from .database import init_database
from .services import (
    SeasonService, TaskService, StatusService, TimezoneService, 
    BackupService, ValidationService
)
from .exceptions import (
    AutoMLTodolistError, NoActiveSeasonError, TaskNotFoundError, 
    SeasonNotFoundError, InvalidDifficultyError, InvalidDayOfWeekError,
    InvalidTimezoneError, BackupFileNotFoundError, BackupImportError
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Typer application setup
app = typer.Typer(help="AutoML TodoList CLI - A powerful task management tool")
season_app = typer.Typer(help="Season management commands")
backup_app = typer.Typer(help="Backup and restore commands")
analysis_app = typer.Typer(help="Data analysis commands")
app.add_typer(season_app, name="season")
app.add_typer(backup_app, name="backup")
app.add_typer(analysis_app, name="analysis")

# Rich console for beautiful output
console = Console()


def handle_errors(func):
    """Decorator to handle common exceptions and display user-friendly error messages."""
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NoActiveSeasonError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
        except (TaskNotFoundError, SeasonNotFoundError) as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
        except (InvalidDifficultyError, InvalidDayOfWeekError, InvalidTimezoneError) as e:
            console.print(f"[bold red]Validation Error:[/bold red] {e}")
            raise typer.Exit(1)
        except (BackupFileNotFoundError, BackupImportError) as e:
            console.print(f"[bold red]Backup Error:[/bold red] {e}")
            raise typer.Exit(1)
        except AutoMLTodolistError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
        except Exception as e:
            logger.exception("Unexpected error occurred")
            console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
            raise typer.Exit(1)
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
    TimezoneService.set_timezone(tz_string)
    console.print(f"[bold green]Timezone set to:[/bold green] {tz_string}")


@season_app.command("recalculate-lp")
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


@app.command()
@handle_errors
def add(
    task: str,
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    difficulty: Optional[int] = typer.Option(None, "--difficulty", "-d"),
    dow: Optional[int] = typer.Option(None, "--dow", help="Day of the week (e.g., '1' for Monday)."),
    duration: Optional[int] = typer.Option(None, "--duration", help="Manually set time taken in minutes."),
    completed: bool = typer.Option(False, "--completed", "-C", help="Mark the task as completed upon creation."),
):
    """Add a new task to the active season."""
    new_task = TaskService.create_task(
        task_description=task,
        project=project,
        difficulty=difficulty,
        dow=dow,
        duration=duration,
        completed=completed
    )
    
    if completed:
        console.print(f"[bold green]Logged completed task:[/bold green] '{task}'")
    else:
        console.print(f"[bold green]Added task:[/bold green] '{task}'")

@app.command(name="list")
@handle_errors
def list_tasks():
    """List all active tasks in the current season."""
    tasks = TaskService.get_active_tasks()
    season = SeasonService.get_current_season()

    table = Table(title=f"Active Tasks for {season.name}")
    table.add_column("ID", style="cyan")
    table.add_column("DoW", style="white")
    table.add_column("Project", style="yellow")
    table.add_column("Task", style="magenta")
    table.add_column("Difficulty", style="blue")
    table.add_column("Status", style="green")

    for t in tasks:
        status = "In Progress" if t.start_time and not t.finish_time else "Not Started"
        table.add_row(
            str(t.id),
            t.dow or "N/A",
            t.project or "N/A",
            t.task,
            t.difficulty or "N/A",
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
def log():
    """List all completed tasks in the current season."""
    tasks = TaskService.get_completed_tasks()
    season = SeasonService.get_current_season()

    table = Table(title=f"Completed Tasks for {season.name}")
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
    season_timezone = gettz(season.timezone_string)
    if season_timezone is None:
        # Fallback if timezone string is invalid, though validation should prevent this
        season_timezone = TimezoneService.get_current_timezone() 

    for task in tasks:
        finish_time_str = "N/A"
        if task.finish_time:
            # Convert UTC finish_time to the season's timezone for display
            localized_finish_time = task.finish_time.astimezone(season_timezone)
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

    console.print(table)

    # Get LP status
    status = StatusService.get_lp_status()

    # Display LP status
    console.print("\n[bold cyan]Current LP Status[/bold cyan]")
    console.print(f"[bold green]Total LP Gain:[/bold green] {status['total_lp_gain']:.2f}")
    console.print(f"[bold red]Total Decay:[/bold red] ({status['days_passed']} days * {status['daily_decay_rate']} LP/day) = {status['total_decay']:.2f}")
    console.print(f"[bold yellow]Net Total LP:[/bold yellow] {status['net_total_lp']:.2f}")
    console.print(f"--------------------")
    console.print(f"[bold blue]Today's LP Gain:[/bold blue] {status['daily_lp_gain']:.2f}")


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
    new_task_name: Optional[str] = typer.Option(None, "--task", "-t"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    difficulty: Optional[int] = typer.Option(None, "--difficulty", "-d"),
    dow: Optional[int] = typer.Option(None, "--dow", help="Day of the week (e.g., '0' for Sunday)."),
    duration: Optional[int] = typer.Option(None, "--duration", help="Manually set time taken in minutes."),
    reflection: Optional[str] = typer.Option(None, "--reflection", "-r"),
):
    """Update a task in the current season."""
    task_obj = TaskService.update_task(
        task_id=task_id,
        task_description=new_task_name,
        project=project,
        difficulty=difficulty,
        dow=dow,
        duration=duration,
        reflection=reflection
    )
    console.print(f"[bold green]Updated task:[/bold green] {task_obj.task}")

@app.command()
@handle_errors
def status():
    """Show LP status for the current season."""
    status_data = StatusService.get_lp_status()

    # Display
    console.print(f"[bold cyan]Stats for season: {status_data['season_name']}[/bold cyan]")
    console.print(f"[bold green]Total LP Gain:[/bold green] {status_data['total_lp_gain']:.2f}")
    console.print(f"[bold red]Total Decay:[/bold red] ({status_data['days_passed']} days * {status_data['daily_decay_rate']} LP/day) = {status_data['total_decay']:.2f}")
    console.print(f"[bold yellow]Net Total LP:[/bold yellow] {status_data['net_total_lp']:.2f}")
    console.print(f"--------------------")
    console.print(f"[bold blue]Today's LP Gain:[/bold blue] {status_data['daily_lp_gain']:.2f}")

@analysis_app.command("plot-lp")
@handle_errors
def plot_lp(
    save_png: bool = typer.Option(False, "--save-png", "-s", help="Save the plot as a PNG file instead of serving it."),
    filename: str = typer.Option("lp_plot.png", "--filename", "-f", help="Filename for the saved PNG plot.")
):
    """Generate and serve a plot of cumulative net LP over time."""
    from .services import AnalysisService
    
    if save_png:
        console.print(f"[bold green]Generating and saving plot to {filename}...[/bold green]")
        AnalysisService.plot_lp_timeseries_plotly(save_png=True, filename=filename)
    else:
        console.print("[bold green]Generating and serving interactive plot...[/bold green]")
        AnalysisService.plot_lp_timeseries_plotly()
        console.print("[bold blue]Plot server started. Check your browser.[/bold blue]")

if __name__ == "__main__":
    app() 
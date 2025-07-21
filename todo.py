import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, func, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime, timezone
from typing import Optional
import json

# Database setup
DATABASE_URL = "sqlite:///tasks.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLAlchemy model for seasons
class Season(Base):
    __tablename__ = "seasons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    start_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False)
    daily_decay = Column(Float, default=30.0)
    tasks = relationship("Task", back_populates="season")

# SQLAlchemy model for tasks
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    dow = Column(String, nullable=True) # Day of Week
    task = Column(String, index=True)
    project = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=True)
    finish_time = Column(DateTime, nullable=True)
    time_taken_minutes = Column(Integer, nullable=True)
    lp_gain = Column(Float, nullable=True)
    reflection = Column(String, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    season_id = Column(Integer, ForeignKey("seasons.id"))
    season = relationship("Season", back_populates="tasks")

# Typer application
app = typer.Typer()
season_app = typer.Typer()
backup_app = typer.Typer()
app.add_typer(season_app, name="season")
app.add_typer(backup_app, name="backup")
console = Console()

# Day of Week mapping
DOW_MAP = {
    "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
    "4": "Thu", "5": "Fri", "6": "Sat",
}

# Helper function to get the active season
def get_active_season(db):
    return db.query(Season).filter(Season.is_active == True).first()

def calculate_lp_gain(task: Task) -> Optional[float]:
    """Calculate LP gain based on difficulty and duration."""
    if not task.difficulty:
        return None

    difficulty_map = {"Easy": 2.5, "Medium": 5, "Hard": 10} # LP per hour
    lp_per_hour = difficulty_map.get(task.difficulty, 0)

    duration_minutes = 0
    if task.time_taken_minutes is not None:
        duration_minutes = task.time_taken_minutes
    elif task.start_time and task.finish_time:
        duration_minutes = (task.finish_time - task.start_time).total_seconds() / 60
    
    if duration_minutes > 0:
        # Round to the nearest 15-minute interval
        rounded_minutes = round(duration_minutes / 15) * 15
        return (lp_per_hour / 60) * rounded_minutes
    
    return None

@app.command()
def init():
    """Initialize the database."""
    Base.metadata.create_all(bind=engine)
    console.print("[bold green]Database initialized.[/bold green]")

    # Create a default season if none exists
    db = SessionLocal()
    if not db.query(Season).count():
        default_season = Season(name="Default Season", is_active=True)
        db.add(default_season)
        db.commit()
        console.print("[bold blue]Created a default season.[/bold blue]")
    db.close()

@season_app.command("start")
def season_start(name: str):
    """Start a new season, archiving the old one."""
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    
    # Deactivate and set end_date for old season
    active_season = get_active_season(db)
    if active_season:
        active_season.is_active = False
        active_season.end_date = now
        db.add(active_season)

    # Create and activate new season
    new_season = Season(name=name, is_active=True, start_date=now)
    db.add(new_season)
    db.commit()
    console.print(f"[bold green]Archived old season and started new season:[/bold green] '{name}'")
    db.close()

@season_app.command("list")
def season_list():
    """List all seasons."""
    db = SessionLocal()
    seasons = db.query(Season).order_by(Season.id).all()
    db.close()

    table = Table(title="All Seasons")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Status", style="green")

    for season in seasons:
        status = "Active" if season.is_active else "Archived"
        table.add_row(str(season.id), season.name, status)
    
    console.print(table)

@season_app.command("switch")
def season_switch(season_id: int):
    """Switch the active season."""
    db = SessionLocal()
    
    # Deactivate current active season
    active_season = get_active_season(db)
    if active_season:
        active_season.is_active = False
        db.add(active_season)

    # Activate the new season
    new_active_season = db.query(Season).filter(Season.id == season_id).first()
    if new_active_season:
        new_active_season.is_active = True
        db.add(new_active_season)
        db.commit()
        console.print(f"[bold green]Switched active season to:[/bold green] '{new_active_season.name}'")
    else:
        console.print("[bold red]Season not found.[/bold red]")
    
    db.close()

@season_app.command("current")
def season_current():
    """Show the current active season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    db.close()

    if active_season:
        console.print(f"The current active season is: [bold blue]{active_season.name}[/bold blue]")
    else:
        console.print("[bold red]No active season found.[/bold red]")


@season_app.command("set-decay")
def season_set_decay(decay_value: float):
    """Set the daily LP decay for the active season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if active_season:
        active_season.daily_decay = decay_value
        db.commit()
        console.print(
            f"[bold green]Daily decay for season '{active_season.name}' set to:[/bold green] {decay_value}"
        )
    else:
        console.print("[bold red]No active season found.[/bold red]")
    db.close()


@backup_app.command("export")
def backup_export(filename: str = typer.Argument("backup.json")):
    """Export all data to a JSON file."""
    db = SessionLocal()
    seasons = db.query(Season).all()
    
    backup_data = []
    for season in seasons:
        season_data = {c.name: getattr(season, c.name) for c in season.__table__.columns}
        season_data["tasks"] = [
            {c.name: getattr(task, c.name) for c in task.__table__.columns}
            for task in season.tasks
        ]
        backup_data.append(season_data)
        
    db.close()

    def default_serializer(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

    with open(filename, "w") as f:
        json.dump(backup_data, f, indent=4, default=default_serializer)
        
    console.print(f"[bold green]Data exported to {filename}[/bold green]")


@backup_app.command("import")
def backup_import(
    filename: str = typer.Argument("backup.json"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass the confirmation prompt."),
):
    """Import data from a JSON file, overwriting the current database."""
    if not yes and not typer.confirm("This will overwrite your current database. Are you sure you want to continue?"):
        raise typer.Abort()

    try:
        with open(filename, "r") as f:
            backup_data = json.load(f)
    except FileNotFoundError:
        console.print(f"[bold red]Error: Backup file '{filename}' not found.[/bold red]")
        raise typer.Exit(1)

    # Re-initialize the database to ensure a clean slate with the latest schema
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Get the columns of the current Season and Task models
    season_columns = {c.name for c in Season.__table__.columns}
    task_columns = {c.name for c in Task.__table__.columns}

    for season_data in backup_data:
        # Filter out old columns that no longer exist in the model
        filtered_season_data = {k: v for k, v in season_data.items() if k in season_columns}
        
        # Convert ISO date strings back to datetime objects
        for key in ["start_date", "end_date"]:
            if key in filtered_season_data and filtered_season_data[key]:
                filtered_season_data[key] = datetime.fromisoformat(filtered_season_data[key])
        
        # We handle tasks separately
        filtered_season_data.pop("tasks", None)

        new_season = Season(**filtered_season_data)
        db.add(new_season)
        db.flush() # Flush to get the new season ID

        for task_data in season_data.get("tasks", []):
            filtered_task_data = {k: v for k, v in task_data.items() if k in task_columns}
            for key in ["start_time", "finish_time", "created_at"]:
                 if key in filtered_task_data and filtered_task_data[key]:
                    filtered_task_data[key] = datetime.fromisoformat(filtered_task_data[key])
            
            filtered_task_data["season_id"] = new_season.id
            new_task = Task(**filtered_task_data)
            db.add(new_task)

    db.commit()
    db.close()
    
    console.print(f"[bold green]Data imported successfully from {filename}.[/bold green]")


@app.command()
def add(
    task: str,
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d"),
    dow: Optional[str] = typer.Option(None, "--dow", help="Day of the week (e.g., '1' for Monday)."),
    duration: Optional[int] = typer.Option(None, "--duration", help="Manually set time taken in minutes."),
    completed: bool = typer.Option(False, "--completed", "-C", help="Mark the task as completed upon creation."),
):
    """Add a new task to the active season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season. Use 'season start' to begin.[/bold red]")
        db.close()
        return

    now = datetime.now(timezone.utc)
    
    # Map DoW if it's a number
    dow_to_store = DOW_MAP.get(dow, dow) if dow else None

    new_task = Task(
        task=task,
        project=project,
        difficulty=difficulty,
        dow=dow_to_store,
        time_taken_minutes=duration,
        completed=completed,
        finish_time=now if completed else None,
        season_id=active_season.id
    )

    # Calculate LP gain if task is added as completed
    if new_task.completed:
        new_task.lp_gain = calculate_lp_gain(new_task)

    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    db.close()
    
    if completed:
        console.print(f"[bold green]Logged completed task:[/bold green] '{task}'")
    else:
        console.print(f"[bold green]Added task:[/bold green] '{task}'")

@app.command(name="list")
def list_tasks():
    """List all active tasks in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season. Use 'season start' to begin.[/bold red]")
        db.close()
        return

    tasks = db.query(Task).filter(
        Task.season_id == active_season.id, Task.completed == False
    ).order_by(Task.id).all()
    db.close()

    table = Table(title=f"Active Tasks for {active_season.name}")
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
def done(task_id: int):
    """Complete a task in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season found.[/bold red]")
        db.close()
        return
        
    task = db.query(Task).filter(Task.id == task_id, Task.season_id == active_season.id).first()
    if task:
        task.completed = True
        if not task.finish_time:
            task.finish_time = datetime.now(timezone.utc)
        
        # Calculate LP gain on completion
        task.lp_gain = calculate_lp_gain(task)

        db.commit()
        console.print(f"[bold green]Completed task:[/bold green] {task.task}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def log():
    """List all completed tasks in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season. Use 'season start' to begin.[/bold red]")
        db.close()
        return
        
    tasks = db.query(Task).filter(
        Task.season_id == active_season.id, Task.completed == True
    ).order_by(Task.finish_time.desc()).all()

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

    for task in tasks:
        finish_time_str = (
            task.finish_time.strftime("%Y-%m-%d %H:%M") if task.finish_time else "N/A"
        )
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

    # --- LP and Decay Calculation ---
    total_lp_gain = db.query(func.sum(Task.lp_gain)).filter(
        Task.season_id == active_season.id, Task.completed == True
    ).scalar() or 0
    
    today = datetime.now(timezone.utc).date()
    daily_lp_gain = db.query(func.sum(Task.lp_gain)).filter(
        Task.season_id == active_season.id,
        Task.completed == True,
        func.date(Task.finish_time) == today
    ).scalar() or 0
    
    # Convert start_date to naive UTC for calculation to avoid offset mismatch
    start_date_naive = active_season.start_date
    if start_date_naive.tzinfo is not None:
        start_date_naive = start_date_naive.replace(tzinfo=None)
    days_passed = (datetime.utcnow() - start_date_naive).days
    total_decay = days_passed * active_season.daily_decay
    net_total_lp = total_lp_gain - total_decay
    
    db.close()

    # --- Display ---
    console.print("\n[bold cyan]Current LP Status[/bold cyan]")
    console.print(f"[bold green]Total LP Gain:[/bold green] {total_lp_gain:.2f}")
    console.print(f"[bold red]Total Decay:[/bold red] ({days_passed} days * {active_season.daily_decay} LP/day) = {total_decay:.2f}")
    console.print(f"[bold yellow]Net Total LP:[/bold yellow] {net_total_lp:.2f}")
    console.print(f"--------------------")
    console.print(f"[bold blue]Today's LP Gain:[/bold blue] {daily_lp_gain:.2f}")


@app.command()
def start(task_id: int):
    """Start a task in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season found.[/bold red]")
        db.close()
        return

    task = db.query(Task).filter(Task.id == task_id, Task.season_id == active_season.id).first()
    if task:
        task.start_time = datetime.now(timezone.utc)
        db.commit()
        console.print(f"[bold green]Started task:[/bold green] {task.task}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def stop(task_id: int):
    """Stop a task in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season found.[/bold red]")
        db.close()
        return

    task = db.query(Task).filter(Task.id == task_id, Task.season_id == active_season.id).first()
    if task:
        task.finish_time = datetime.now(timezone.utc)
        db.commit()
        console.print(f"[bold green]Stopped task:[/bold green] {task.task}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def update(
    task_id: int,
    new_task_name: Optional[str] = typer.Option(None, "--task", "-t"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d"),
    dow: Optional[str] = typer.Option(None, "--dow", help="Day of the week (e.g., '0' for Sunday)."),
    duration: Optional[int] = typer.Option(None, "--duration", help="Manually set time taken in minutes."),
    reflection: Optional[str] = typer.Option(None, "--reflection", "-r"),
):
    """Update a task in the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season found.[/bold red]")
        db.close()
        return

    task_obj = db.query(Task).filter(Task.id == task_id, Task.season_id == active_season.id).first()
    if task_obj:
        if new_task_name:
            task_obj.task = new_task_name
        if project:
            task_obj.project = project
        if dow:
            task_obj.dow = DOW_MAP.get(dow, dow)
        if duration is not None:
            task_obj.time_taken_minutes = duration
        if difficulty:
            task_obj.difficulty = difficulty

        # Recalculate LP gain if task is complete
        if task_obj.completed:
            task_obj.lp_gain = calculate_lp_gain(task_obj)

        db.commit()
        console.print(f"[bold green]Updated task:[/bold green] {task_obj.task}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def status():
    """Show LP status for the current season."""
    db = SessionLocal()
    active_season = get_active_season(db)
    if not active_season:
        console.print("[bold red]No active season. Use 'season start' to begin.[/bold red]")
        db.close()
        return
    
    # --- LP Calculation ---
    total_lp_gain = db.query(func.sum(Task.lp_gain)).filter(
        Task.season_id == active_season.id, Task.completed == True
    ).scalar() or 0
    
    today = datetime.now(timezone.utc).date()
    daily_lp_gain = db.query(func.sum(Task.lp_gain)).filter(
        Task.season_id == active_season.id,
        Task.completed == True,
        func.date(Task.finish_time) == today
    ).scalar() or 0
    
    # --- Decay Calculation ---
    start_date_naive = active_season.start_date
    if start_date_naive.tzinfo is not None:
        start_date_naive = start_date_naive.replace(tzinfo=None)
    days_passed = (datetime.utcnow() - start_date_naive).days
    total_decay = days_passed * active_season.daily_decay
    net_total_lp = total_lp_gain - total_decay
    
    db.close()

    # --- Display ---
    console.print(f"[bold cyan]Stats for season: {active_season.name}[/bold cyan]")
    console.print(f"[bold green]Total LP Gain:[/bold green] {total_lp_gain:.2f}")
    console.print(f"[bold red]Total Decay:[/bold red] ({days_passed} days * {active_season.daily_decay} LP/day) = {total_decay:.2f}")
    console.print(f"[bold yellow]Net Total LP:[/bold yellow] {net_total_lp:.2f}")
    console.print(f"--------------------")
    console.print(f"[bold blue]Today's LP Gain:[/bold blue] {daily_lp_gain:.2f}")

if __name__ == "__main__":
    app() 
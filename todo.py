import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float, func
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timezone
from typing import Optional

# Database setup
DATABASE_URL = "sqlite:///tasks.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLAlchemy model for tasks
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    assignment = Column(String, index=True)
    course = Column(String, nullable=True)
    expected_difficulty = Column(String, nullable=True)
    actual_difficulty = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=True)
    finish_time = Column(DateTime, nullable=True)
    lp_gain = Column(Float, nullable=True)
    takeaways = Column(String, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Typer application
app = typer.Typer()
console = Console()

@app.command()
def init():
    """Initialize the database."""
    Base.metadata.create_all(bind=engine)
    console.print("[bold green]Database initialized.[/bold green]")

@app.command()
def add(
    assignment: str,
    course: Optional[str] = typer.Option(None, "--course", "-c"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d"),
):
    """Add a new task."""
    db = SessionLocal()
    task = Task(
        assignment=assignment, course=course, expected_difficulty=difficulty
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    db.close()
    console.print(f"[bold green]Added task:[/bold green] '{assignment}'")

@app.command(name="list")
def list_tasks():
    """List all active tasks."""
    db = SessionLocal()
    tasks = db.query(Task).filter(Task.completed == False).order_by(Task.id).all()
    db.close()

    table = Table(title="Active Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Course", style="yellow")
    table.add_column("Assignment", style="magenta")
    table.add_column("Expected Difficulty", style="blue")
    table.add_column("Status", style="green")

    for task in tasks:
        status = "In Progress" if task.start_time and not task.finish_time else "Not Started"
        table.add_row(
            str(task.id),
            task.course or "N/A",
            task.assignment,
            task.expected_difficulty or "N/A",
            status,
        )
    
    console.print(table)


@app.command()
def done(task_id: int):
    """Complete a task and set its finish time."""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.completed = True
        if not task.finish_time:
            task.finish_time = datetime.now(timezone.utc)
        db.commit()
        console.print(f"[bold green]Completed task:[/bold green] {task.assignment}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def log():
    """List all completed tasks."""
    db = SessionLocal()
    tasks = db.query(Task).filter(Task.completed == True).order_by(Task.finish_time.desc()).all()
    db.close()

    table = Table(title="Completed Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Course", style="yellow")
    table.add_column("Assignment", style="magenta")
    table.add_column("Finished At", style="green")
    table.add_column("Time Taken", style="red")
    table.add_column("Actual Difficulty", style="blue")
    table.add_column("LP Gain", style="green")
    table.add_column("Takeaways", style="white")

    for task in tasks:
        finish_time_str = (
            task.finish_time.strftime("%Y-%m-%d %H:%M") if task.finish_time else "N/A"
        )
        time_taken = "N/A"
        if task.start_time and task.finish_time:
            time_taken = str(task.finish_time - task.start_time).split(".")[0]

        table.add_row(
            str(task.id),
            task.course or "N/A",
            task.assignment,
            finish_time_str,
            time_taken,
            task.actual_difficulty or "N/A",
            str(task.lp_gain) if task.lp_gain is not None else "N/A",
            task.takeaways or "N/A",
        )

    console.print(table)

@app.command()
def start(task_id: int):
    """Start a task."""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.start_time = datetime.now(timezone.utc)
        db.commit()
        console.print(f"[bold green]Started task:[/bold green] {task.assignment}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def stop(task_id: int):
    """Stop a task."""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.finish_time = datetime.now(timezone.utc)
        db.commit()
        console.print(f"[bold green]Stopped task:[/bold green] {task.assignment}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def update(
    task_id: int,
    actual_difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d"),
    takeaways: Optional[str] = typer.Option(None, "--takeaways", "-t"),
):
    """Update a task's actual difficulty and takeaways."""
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        if actual_difficulty:
            task.actual_difficulty = actual_difficulty
        if takeaways:
            task.takeaways = takeaways
        
        # Calculate LP gain
        if actual_difficulty:
            difficulty_map = {"Easy": 2.5, "Medium": 5, "Hard": 10}
            task.lp_gain = difficulty_map.get(actual_difficulty, 0)

        db.commit()
        console.print(f"[bold green]Updated task:[/bold green] {task.assignment}")
    else:
        console.print(f"[bold red]Task not found.[/bold red]")
    db.close()

@app.command()
def status():
    """Show LP status."""
    db = SessionLocal()
    
    total_lp = db.query(func.sum(Task.lp_gain)).filter(Task.completed == True).scalar() or 0
    
    today = datetime.now(timezone.utc).date()
    daily_lp = db.query(func.sum(Task.lp_gain)).filter(
        Task.completed == True,
        func.date(Task.finish_time) == today
    ).scalar() or 0
    
    db.close()

    console.print(f"[bold green]Total LP:[/bold green] {total_lp}")
    console.print(f"[bold blue]Daily LP:[/bold blue] {daily_lp}")

if __name__ == "__main__":
    app() 
# AutoML TodoList CLI

A powerful, command-line to-do list application for detailed life and task tracking.

## Features

- **Detailed Task Management:** Create tasks with associated courses, expected difficulty, and more.
- **Time Tracking:** Start and stop tasks to automatically record the time spent.
- **Progress Tracking with "Life Points" (LP):**
    - Automatically calculates "LP Gain" based on the actual difficulty of a task.
    - A `status` command provides a summary of your total and daily LP.
- **Post-Completion Updates:** Update tasks with actual difficulty and your takeaways after completion.
- **Local SQLite Database:** All data is stored in a local `tasks.db` file.
- **Rich Terminal Output:** Clean, readable tables for viewing tasks and logs.
- **Backup and Restore:** Export all your data to a JSON file and import it back, allowing for data preservation even after schema changes.

## Data Storage

The application uses a local SQLite database named `tasks.db`. It contains two main tables:

### `seasons` Schema
- `id`: (Integer) The unique ID of the season.
- `name`: (String) The name of the season (e.g., "Summer 2025").
- `start_date`: (DateTime) The timestamp when the season was started.
- `end_date`: (DateTime) The timestamp when the season was archived.
- `is_active`: (Boolean) A flag to mark the current season.
- `daily_decay`: (Float) The daily LP decay value for the season (default: 56.0).

### `tasks` Schema
- `id`: (Integer) The unique ID of the task.
- `dow`: (String) The Day of Week for the task.
- `task`: (String) The description of the task.
- `project`: (String) The project or category for the task.
- `difficulty`: (String) The difficulty of the task.
- `start_time`: (DateTime) The timestamp when the task was started.
- `finish_time`: (DateTime) The timestamp when the task was stopped or completed.
- `lp_gain`: (Float) The "Life Points" gained from the task.
- `reflection`: (String) Your notes or reflection on the task.
- `completed`: (Boolean) Whether the task is complete.
- `created_at`: (DateTime) The timestamp when the task was created.
- `season_id`: (Integer) A link to the `seasons` table.

## Setup

1.  **Create and activate a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install the AutoML TodoList CLI package in editable mode:**

    ```bash
    pip install -e .
    ```

3.  **Initialize the database:**
    This command creates the `tasks.db` file in your project directory with the correct schema. You only need to run this once.

    ```bash
    python -m automl_todolist.todo init
    ```

## Usage

The application is organized into two main groups of commands: task management commands (like `add`, `list`, `log`) and season management commands (under the `season` subcommand). All commands operate on the currently **active season**.

---
### Season Management (`todo season`)

This set of commands allows you to archive your tasks and start fresh for a new period in your life (e.g., a new semester, a work sprint, etc.).

#### `season start <NAME>`

Archives the current season and starts a new one. This gives you a fresh, empty task list and log.

- **Usage:** `todo season start <NAME>`
- **Example:**
    ```bash
    todo season start "Fall Quarter 2025"
    ```

#### `season list`

Displays all your seasons, showing which one is currently active.

- **Usage:** `todo season list`

#### `season switch <SEASON_ID>`

Switches the active season. All subsequent commands will operate on the tasks within this newly activated season.

- **Usage:** `todo season switch <SEASON_ID>`
- **Example:**
    ```bash
    todo season switch 1
    ```

#### `season set-decay <VALUE>`

Sets the daily LP decay for the current active season.

- **Usage:** `todo season set-decay <VALUE>`
- **Example:**
    ```bash
    todo season set-decay 15.5
    ```

#### `season current`

Shows the name of the currently active season.

- **Usage:** `todo season current`

#### `season get-timezone`

Shows the timezone assigned to the currently active season. This is the timezone used for displaying timestamps for tasks within that season.

- **Usage:** `todo season get-timezone`

---
### Backup and Restore (`todo backup`)

This set of commands allows you to export your data to a safe format and import it back into the application. This is crucial for preserving your data if future versions of the app require database schema changes, such as adding new fields or modifying existing ones. The backup process now intelligently handles evolving schemas by ensuring timezone information is preserved for seasons and tasks.

#### `backup export [FILENAME]`

Exports all seasons and tasks to a JSON file. This backup includes all data necessary to fully restore your application state, including timezone information associated with each season and task timestamps.

- **Usage:** `todo backup export [FILENAME]`
- **Default Filename:** If you don't provide a filename, it defaults to `backup.json`.
- **Example:**
    ```bash
    todo backup export my_life_backup.json
    ```

#### `backup import [FILENAME]`

Imports data from a JSON backup file. This is a **destructive operation** and will completely overwrite your current database. Ensure you have backed up any current data you wish to keep before proceeding.

During import, the application will recreate the database schema based on the current application version and then populate it with data from the backup file. It intelligently handles the import of timezone-aware timestamps and season-specific timezone settings.

- **Usage:** `todo backup import [FILENAME] [OPTIONS]`
- **Default Filename:** If you don't provide a filename, it defaults to `backup.json`.
- **Options:**
    - `--yes` or `-y`: Bypasses the confirmation prompt, which is useful for scripting.
- **Example:**
    ```bash
    todo backup import my_life_backup.json --yes
    ```

#### **Handling Schema Migrations with Backup/Restore:**

If the application's database schema changes (e.g., a new column is added), direct `init` commands on an existing database might lead to errors or data loss. The recommended procedure to safely migrate your data is:

1.  **Export Existing Data:** Use `todo backup export` to create a JSON backup of your current data. This backup captures all essential information.
    ```bash
    todo backup export initial_backup.json
    ```

2.  **Reinitialize Database:** Force the database to reinitialize. This will drop all existing tables and recreate them with the latest schema defined in the application's models. This will also create a new default season.
    ```bash
    todo init --force --yes
    ```

3.  **Import Data:** Import your data from the backup file. The import process is designed to be compatible with schema changes and will correctly populate the newly structured database.
    ```bash
    todo backup import initial_backup.json --yes
    ```

This process ensures that your data is safely transferred to the new schema, preserving your history and settings.

---

### Data Analysis (`todo analysis`)

This set of commands allows you to visualize your productivity and LP trends over time.

#### `analysis plot-lp`

Generates a plot of your cumulative net LP for the current season. By default, it launches an interactive plot in your web browser and includes SARIMAX forecast and linear regression lines.

- **Usage:** `todo analysis plot-lp [OPTIONS]`
- **Options:**
    - `--save-png` or `-s`: Save the plot as a PNG image file instead of opening it in a browser.
    - `--filename` or `-f`: Specify the filename for the saved PNG image (default: `lp_plot.png`).
    - `--forecast` or `-F`: Include SARIMAX forecast in the plot (enabled by default).
    - `--linear-regression` or `--lr` or `-R`: Include linear regression in the plot (enabled by default).
    - `--forecast-days` or `-D`: Number of days to forecast into the future for all models (default: 2).
- **Example (interactive plot with all defaults):**
    ```bash
    todo analysis plot-lp
    ```
- **Example (saving to a file without forecast):**
    ```bash
    todo analysis plot-lp --save-png --filename my_progress.png --no-forecast
    ```

---

### Task Management

These commands manage the tasks within the currently active season.

---

### `add`

Adds a new task. By default, tasks are added to the active list, but they can be logged as completed immediately.

- **Usage:** `todo add <TASK> [OPTIONS]`
- **Options:**
    - `--project` or `-p`: Specify the project or category.
    - `--difficulty` or `-d`: Set the difficulty.
    - `--dow`: Set the Day of Week. You can use a number (`0` for Sunday) or a string (`"Sun"`, `"Monday"`).
    - `--completed` or `-C`: A flag to log a task as already completed. This bypasses the need for `start` and `done`.
- **Example (adding a new active task):**
    ```bash
    todo add "Work on the final report" -p "Academics" -d "Hard" --dow 0
    ```
- **Example (logging a task after-the-fact):**
    ```bash
    todo add "Read chapter 5" -p "Books" --completed
    ```

---

### `list`

Displays all active (incomplete) tasks.

- **Usage:** `todo list`
- **Output:** A table showing the `ID`, `Project`, `Task`, `Difficulty`, and `Status` (`In Progress` or `Not Started`).

---

### `start`

Marks the beginning of work on a task. Sets the `start_time`.

- **Usage:** `todo start <TASK_ID>`
- **Example:**
    ```bash
    todo start 1
    ```

---

### `stop`

Marks the end of work on a task. Sets the `finish_time`.

- **Usage:** `todo stop <TASK_ID>`
- **Example:**
    ```bash
    todo stop 1
    ```

---

### `done`

Marks a task as complete, sets the `finish_time` if it isn't already set, and **calculates `lp_gain`** based on the task's difficulty.

- **Usage:** `todo done <TASK_ID>`
- **Example:**
    ```bash
    todo done 1
    ```

---

### `update`

Updates any attribute of a task, whether it is active or complete.

- **Usage:** `todo update <TASK_ID> [OPTIONS]`
- **Options:**
    - `--task` or `-t`: Change the main description of the task.
    - `--project` or `-p`: Change the project or category.
    - `--difficulty` or `-d`: Change the difficulty. If the task is already complete, this will also **recalculate the `lp_gain`**.
    - `--dow`: Change the Day of Week. You can provide a number (0-6, Sunday-Saturday) which will be stored as an abbreviation (e.g., 'Sun'), or provide a string which will be stored as-is.
    - `--duration`: Manually set the time taken in minutes for a task.
    - `--reflection` or `-r`: Add or change your reflection on the task.
---

### `log`

Displays a log of all completed tasks. At the end of the log, it also shows a full LP status report, including decay.

- **Usage:** `todo log`
- **Output:** A detailed table of completed tasks, followed by the LP status summary.

---

### `status`

Shows a detailed summary of your Life Points (LP), including the daily decay.

- **Usage:** `todo status`
- **Output:** Displays:
    - `Total LP Gain`: The sum of all LP from completed tasks.
    - `Total Decay`: The total LP decay calculated from the season's start date.
    - `Net Total LP`: The final, decay-adjusted LP for the season.
    - `Today's LP Gain`: The LP gained from tasks completed today. 

# TaskMaster CLI

A powerful, command-line to-do list application for detailed life and task tracking, inspired by a comprehensive Google Sheet.

## Features

- **Detailed Task Management:** Create tasks with associated courses, expected difficulty, and more.
- **Time Tracking:** Start and stop tasks to automatically record the time spent.
- **Progress Tracking with "Life Points" (LP):**
    - Automatically calculates "LP Gain" based on the actual difficulty of a task.
    - A `status` command provides a summary of your total and daily LP.
- **Post-Completion Updates:** Update tasks with actual difficulty and your takeaways after completion.
- **Local SQLite Database:** All data is stored in a local `tasks.db` file.
- **Rich Terminal Output:** Clean, readable tables for viewing tasks and logs.

## Data Storage

The application uses a local SQLite database named `tasks.db` to store all data. A single table, `tasks`, is used with the following schema:

- `id`: (Integer) The unique ID of the task.
- `assignment`: (String) The description of the task.
- `course`: (String) The course or category for the task.
- `expected_difficulty`: (String) The initial estimated difficulty.
- `actual_difficulty`: (String) The actual difficulty, set after completion.
- `start_time`: (DateTime) The timestamp when the task was started.
- `finish_time`: (DateTime) The timestamp when the task was stopped or completed.
- `lp_gain`: (Float) The "Life Points" gained from the task.
- `takeaways`: (String) Notes or takeaways from the task.
- `completed`: (Boolean) Whether the task is complete.
- `created_at`: (DateTime) The timestamp when the task was created.

## Setup

1.  **Create and activate a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install dependencies and the CLI command:**
    This command reads the `pyproject.toml` file, installs all required libraries, and creates the `todo` command-line tool within your virtual environment.

    ```bash
    pip install -e .
    ```

3.  **Initialize the database:**
    This command creates the `tasks.db` file in your project directory with the correct schema. You only need to run this once.

    ```bash
    todo init
    ```

## Usage

Once installed, all commands are run using the `todo` executable from your terminal (as long as your virtual environment is active).

---

### `add`

Adds a new task to the list.

- **Usage:** `todo add <ASSIGNMENT>`
- **Options:**
    - `--course` or `-c`: Specify the course or category.
    - `--difficulty` or `-d`: Set the expected difficulty.
- **Example:**
    ```bash
    todo add "Implement the new feature" -c "Work" -d "Hard"
    ```

---

### `list`

Displays all active (incomplete) tasks.

- **Usage:** `todo list`
- **Output:** A table showing the `ID`, `Course`, `Assignment`, `Expected Difficulty`, and `Status` (`In Progress` or `Not Started`).

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

Marks a task as complete. If the task has no `finish_time`, it will be set to the current time.

- **Usage:** `todo done <TASK_ID>`
- **Example:**
    ```bash
    todo done 1
    ```

---

### `update`

Updates a task with its actual difficulty and any takeaways. This command also calculates the `LP Gain`.

- **Usage:** `todo update <TASK_ID>`
- **Options:**
    - `--difficulty` or `-d`: Set the actual difficulty (`Easy`, `Medium`, `Hard`).
    - `--takeaways` or `-t`: Add notes or takeaways.
- **LP Calculation:** `lp_gain` is calculated based on the `actual_difficulty`:
    - `Easy`: 2.5 LP
    - `Medium`: 5 LP
    - `Hard`: 10 LP
- **Example:**
    ```bash
    todo update 1 -d "Hard" -t "The backend logic was tricky."
    ```

---

### `log`

Displays a log of all completed tasks.

- **Usage:** `todo log`
- **Output:** A detailed table including `ID`, `Course`, `Assignment`, `Finished At`, `Time Taken`, `Actual Difficulty`, `LP Gain`, and `Takeaways`.

---

### `status`

Shows a summary of your Life Points (LP).

- **Usage:** `todo status`
- **Output:** Displays your `Total LP` (from all completed tasks) and `Daily LP` (from tasks completed today). 
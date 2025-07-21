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

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Initialize the database:**
    This command creates the `tasks.db` file in your project directory with the correct schema.

    ```bash
    python3 todo.py init
    ```

## Usage

All commands are run using `python3 todo.py`.

---

### `add`

Adds a new task to the list.

- **Usage:** `python3 todo.py add <ASSIGNMENT>`
- **Options:**
    - `--course` or `-c`: Specify the course or category.
    - `--difficulty` or `-d`: Set the expected difficulty.
- **Example:**
    ```bash
    python3 todo.py add "Implement the new feature" -c "Work" -d "Hard"
    ```

---

### `list`

Displays all active (incomplete) tasks.

- **Usage:** `python3 todo.py list`
- **Output:** A table showing the `ID`, `Course`, `Assignment`, `Expected Difficulty`, and `Status` (`In Progress` or `Not Started`).

---

### `start`

Marks the beginning of work on a task. Sets the `start_time`.

- **Usage:** `python3 todo.py start <TASK_ID>`
- **Example:**
    ```bash
    python3 todo.py start 1
    ```

---

### `stop`

Marks the end of work on a task. Sets the `finish_time`.

- **Usage:** `python3 todo.py stop <TASK_ID>`
- **Example:**
    ```bash
    python3 todo.py stop 1
    ```

---

### `done`

Marks a task as complete. If the task has no `finish_time`, it will be set to the current time.

- **Usage:** `python3 todo.py done <TASK_ID>`
- **Example:**
    ```bash
    python3 todo.py done 1
    ```

---

### `update`

Updates a task with its actual difficulty and any takeaways. This command also calculates the `LP Gain`.

- **Usage:** `python3 todo.py update <TASK_ID>`
- **Options:**
    - `--difficulty` or `-d`: Set the actual difficulty (`Easy`, `Medium`, `Hard`).
    - `--takeaways` or `-t`: Add notes or takeaways.
- **LP Calculation:** `lp_gain` is calculated based on the `actual_difficulty`:
    - `Easy`: 2.5 LP
    - `Medium`: 5 LP
    - `Hard`: 10 LP
- **Example:**
    ```bash
    python3 todo.py update 1 -d "Hard" -t "The backend logic was tricky."
    ```

---

### `log`

Displays a log of all completed tasks.

- **Usage:** `python3 todo.py log`
- **Output:** A detailed table including `ID`, `Course`, `Assignment`, `Finished At`, `Time Taken`, `Actual Difficulty`, `LP Gain`, and `Takeaways`.

---

### `status`

Shows a summary of your Life Points (LP).

- **Usage:** `python3 todo.py status`
- **Output:** Displays your `Total LP` (from all completed tasks) and `Daily LP` (from tasks completed today). 
"""Google Calendar integration for AutoML TodoList CLI.

This module implements a minimal two-way sync without modifying the DB schema.
It stores Google OAuth tokens, user settings (default calendar), and an
event<->task mapping in the user's home config directory.
"""

import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

from dateutil.tz import gettz

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except Exception as _e:  # pragma: no cover - optional import until installed
    # Defer hard failure until usage
    Credentials = None  # type: ignore
    InstalledAppFlow = None  # type: ignore
    build = None  # type: ignore
    Request = None  # type: ignore

logger = logging.getLogger(__name__)


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _app_data_dir() -> str:
    root = os.path.expanduser("~/.automl_todolist")
    os.makedirs(root, exist_ok=True)
    return root


def _settings_path() -> str:
    return os.path.join(_app_data_dir(), "gcal_settings.json")


def _token_path() -> str:
    return os.path.join(_app_data_dir(), "gcal_token.json")


def _mapping_path() -> str:
    return os.path.join(_app_data_dir(), "gcal_mapping.json")


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_google_libs():
    if Credentials is None or InstalledAppFlow is None or build is None:
        raise RuntimeError(
            "Google API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )


def connect(credentials_path: str = "credentials.json") -> str:
    """Perform OAuth flow and store token locally.

    Args:
        credentials_path: Path to Google API OAuth client secrets JSON.

    Returns:
        Path to the stored token file.
    """
    _ensure_google_libs()
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(
            f"Google OAuth client file not found at '{credentials_path}'. Download it from Google Cloud Console and place it there."
        )

    creds = None
    token_path = _token_path()
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token and Request is not None:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        _save_json(token_path, json.loads(creds.to_json()))

    return token_path


def _get_service() -> Any:
    _ensure_google_libs()
    token_path = _token_path()
    if not os.path.exists(token_path):
        raise RuntimeError("Google token not found. Run 'todo calendar connect' first.")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds.valid and creds.refresh_token and Request is not None:
        creds.refresh(Request())
        _save_json(token_path, json.loads(creds.to_json()))
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> List[Tuple[str, str]]:
    service = _get_service()
    items: List[Tuple[str, str]] = []
    page_token = None
    while True:
        cal_list = service.calendarList().list(pageToken=page_token).execute()
        for c in cal_list.get("items", []):
            items.append((c.get("id", ""), c.get("summary", "")))
        page_token = cal_list.get("nextPageToken")
        if not page_token:
            break
    return items


def set_default_calendar(calendar_id: str) -> None:
    settings = _load_json(_settings_path(), {})
    settings["default_calendar_id"] = calendar_id
    _save_json(_settings_path(), settings)


def get_default_calendar() -> Optional[str]:
    settings = _load_json(_settings_path(), {})
    return settings.get("default_calendar_id")


def _load_mapping() -> Dict[str, Dict[str, str]]:
    mapping = _load_json(_mapping_path(), {})
    mapping.setdefault("event_to_task", {})
    mapping.setdefault("task_to_event", {})
    return mapping


def _save_mapping(mapping: Dict[str, Dict[str, str]]) -> None:
    _save_json(_mapping_path(), mapping)


def _isoformat_tz(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _status_label_for_task(task: Any) -> str:
    try:
        if getattr(task, 'completed', False):
            return "[DONE]"
        if getattr(task, 'start_time', None) and not getattr(task, 'finish_time', None):
            return "[IN PROGRESS]"
    except Exception:
        pass
    return "[TODO]"


def _build_event_payload_for_task(task: Any) -> Dict[str, Any]:
    """Build event body (summary/description/start/end) for a task."""
    # Determine timing
    if getattr(task, 'completed', False) and getattr(task, 'finish_time', None) and task.time_taken_minutes:
        start_dt = task.finish_time - timedelta(minutes=task.time_taken_minutes)
        end_dt = task.finish_time
    elif getattr(task, 'deadline', None) and task.time_taken_minutes:
        start_dt = task.deadline - timedelta(minutes=task.time_taken_minutes)
        end_dt = task.deadline
    elif getattr(task, 'start_time', None) and getattr(task, 'finish_time', None):
        start_dt = task.start_time
        end_dt = task.finish_time
    else:
        start_dt = task.created_at
        duration_minutes = task.time_taken_minutes if task.time_taken_minutes is not None else 30
        end_dt = start_dt + timedelta(minutes=duration_minutes)

    status_label = _status_label_for_task(task)
    summary = f"{status_label} {task.task}"

    # Format times in the season's timezone for readability
    try:
        # Local import to avoid circular import
        from .services import SeasonService as _SS
        season = _SS.get_current_season()
        tz = gettz(season.timezone_string)
    except Exception:
        tz = timezone.utc

    def fmt_local(dt: Optional[datetime]) -> str:
        if not dt:
            return "N/A"
        dt_local = dt.astimezone(tz)
        tz_abbr = dt_local.tzname() or ""
        return dt_local.strftime("%Y-%m-%d %H:%M") + (f" {tz_abbr}" if tz_abbr else "")

    expected_str = f"{task.time_taken_minutes} min" if task.time_taken_minutes is not None else "N/A"
    status_human = "Done" if getattr(task, 'completed', False) else ("In Progress" if getattr(task, 'start_time', None) and not getattr(task, 'finish_time', None) else "To-Do")

    # Nicely grouped sections with bullets
    description_lines = [
        "Task",
        f"- ID: {getattr(task, 'id', 'N/A')}",
        f"- Project: {task.project or 'N/A'}",
        f"- Difficulty: {task.difficulty or 'N/A'}",
        f"- Importance: {getattr(task, 'importance', 'Non-Critical')}",
        f"- Status: {status_human}",
        f"- Expected: {expected_str}",
        "",
        "Timing",
        f"- Start: {fmt_local(start_dt)}",
        f"- End: {fmt_local(end_dt)}",
        f"- Deadline: {fmt_local(getattr(task, 'deadline', None)) if getattr(task, 'deadline', None) else 'N/A'}",
        f"- Created: {fmt_local(getattr(task, 'created_at', None))}",
        "",
        "Metrics",
        f"- LP Gain: {getattr(task, 'lp_gain', 'N/A')}",
    ]

    ev_body = {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {"dateTime": _isoformat_tz(start_dt)},
        "end": {"dateTime": _isoformat_tz(end_dt)},
    }
    return ev_body


def sync(direction: str = "push", days_back: int = 14, days_forward: int = 14) -> Dict[str, int]:
    """One-way sync: push CLI tasks to Google Calendar.

    Args:
        direction: Only 'push' is supported; other values are ignored.
        days_back: Unused (kept for API compatibility).
        days_forward: Unused (kept for API compatibility).

    Returns:
        Dict with counts: {'pushed': int, 'pulled': 0}
    """
    service = _get_service()
    default_cal = get_default_calendar()
    if not default_cal:
        raise RuntimeError("No default calendar set. Run 'todo calendar set-calendar CAL_ID' after 'todo calendar list-calendars'.")

    mapping = _load_mapping()
    counts = {"pushed": 0, "pulled": 0}

    # Push tasks -> create events if not mapped yet
    from .services import TaskService as _TS  # local alias
    tasks = _TS.get_active_tasks()  # only active (incomplete) tasks
    for t in tasks:
        if str(t.id) in mapping["task_to_event"]:
            continue

        ev_body = _build_event_payload_for_task(t)
        try:
            created = service.events().insert(calendarId=default_cal, body=ev_body).execute()
            event_id = created.get("id")
            if event_id:
                mapping["task_to_event"][str(t.id)] = event_id
                mapping["event_to_task"][event_id] = str(t.id)
                counts["pushed"] += 1
        except Exception as e:
            logger.error(f"Failed to push task '{t.task}' to calendar: {e}")

    _save_mapping(mapping)
    return counts


def ensure_event_for_task(task: Any) -> bool:
    """Create or update a Google Calendar event for a single task.

    Returns True if an event was created/updated; False if skipped or failed.
    """
    try:
        service = _get_service()
        default_cal = get_default_calendar()
        if not default_cal:
            return False
    except Exception:
        return False

    mapping = _load_mapping()
    task_id_str = str(task.id)
    event_id = mapping["task_to_event"].get(task_id_str)

    # Determine start/end
    if getattr(task, 'deadline', None) and task.time_taken_minutes:
        start_dt = task.deadline - timedelta(minutes=task.time_taken_minutes)
        end_dt = task.deadline
    else:
        start_dt = task.created_at
        duration_minutes = task.time_taken_minutes if task.time_taken_minutes is not None else 30
        end_dt = start_dt + timedelta(minutes=duration_minutes)

    ev_body = _build_event_payload_for_task(task)

    try:
        if event_id:
            updated = service.events().patch(calendarId=get_default_calendar(), eventId=event_id, body=ev_body).execute()
            return True if updated else False
        created = service.events().insert(calendarId=get_default_calendar(), body=ev_body).execute()
        new_id = created.get("id") if created else None
        if new_id:
            mapping["task_to_event"][task_id_str] = new_id
            mapping["event_to_task"][new_id] = task_id_str
            _save_mapping(mapping)
            return True
    except Exception as e:
        logger.error(f"Failed to ensure event for task {task.id}: {e}")
    return False


def delete_event_for_task(task_id: int) -> bool:
    """Delete the mapped Google Calendar event for a task, if present."""
    try:
        service = _get_service()
        default_cal = get_default_calendar()
        if not default_cal:
            return False
    except Exception:
        return False

    mapping = _load_mapping()
    task_id_str = str(task_id)
    event_id = mapping["task_to_event"].get(task_id_str)
    if not event_id:
        return False
    try:
        service.events().delete(calendarId=default_cal, eventId=event_id).execute()
    except Exception as e:
        logger.error(f"Failed to delete event for task {task_id}: {e}")
        # Still proceed to remove mapping locally
    mapping["task_to_event"].pop(task_id_str, None)
    mapping["event_to_task"].pop(event_id, None)
    _save_mapping(mapping)
    return True



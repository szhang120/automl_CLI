import sqlite3
import json
from datetime import datetime

# Database path (from config.py)
DATABASE_URL = "sqlite:///tasks.db" 
DB_PATH = DATABASE_URL.split("///")[1]

# Backup filename
BACKUP_FILENAME = "backup.json"

def sqlite_dict_factory(cursor, row):
    """Factory to return rows as dictionaries."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def export_to_json():
    """Export data from SQLite to a JSON file."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite_dict_factory
        cursor = conn.cursor()

        # Fetch all seasons
        cursor.execute("SELECT * FROM seasons")
        seasons = cursor.fetchall()
        
        # Fetch all tasks
        cursor.execute("SELECT * FROM tasks")
        tasks = cursor.fetchall()

        conn.close()

        # Structure data for backup
        backup_data = []
        for season in seasons:
            season_id = season['id']
            # Add default timezone if missing
            if 'timezone_string' not in season:
                season['timezone_string'] = "America/New_York"
            season['tasks'] = [task for task in tasks if task['season_id'] == season_id]
            backup_data.append(season)

        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        with open(BACKUP_FILENAME, 'w') as f:
            json.dump(backup_data, f, indent=4, default=default_serializer)

        print(f"Data successfully exported to {BACKUP_FILENAME}")

    except Exception as e:
        print(f"An error occurred during export: {e}")

if __name__ == "__main__":
    export_to_json() 
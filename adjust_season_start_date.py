from datetime import datetime
from dateutil.tz import gettz
from sqlalchemy.orm import Session

from automl_todolist.database import get_db_session
from automl_todolist.models import Season
from automl_todolist.services import SeasonService
from automl_todolist.exceptions import NoActiveSeasonError


def adjust_season_start_date(new_start_date_str: str):
    """
    Adjusts the start_date of the current active season.
    """
    with get_db_session() as session:
        try:
            active_season = SeasonService.get_active_season(session)
            
            # Get the season's timezone
            season_timezone = gettz(active_season.timezone_string)
            if season_timezone is None:
                print(f"Error: Invalid timezone string '{active_season.timezone_string}' for active season. Using UTC.")
                season_timezone = gettz("UTC")

            # Parse the new start date string and make it timezone-aware
            # Assume the input string is in the season's local time
            new_start_dt_naive = datetime.strptime(new_start_date_str, "%Y-%m-%d %H:%M:%S")
            new_start_dt_aware = new_start_dt_naive.replace(tzinfo=season_timezone)

            print(f"Current season '{active_season.name}' (ID: {active_season.id}) has start_date: {active_season.start_date}")
            print(f"Attempting to set new start_date to: {new_start_dt_aware.isoformat()}")

            active_season.start_date = new_start_dt_aware
            session.add(active_season)
            session.commit()
            print(f"Successfully updated start_date for season '{active_season.name}' to {active_season.start_date.isoformat()}")
            print("Please run 'todo log' to verify the decay calculation.")

        except NoActiveSeasonError:
            print("Error: No active season found.")
        except ValueError as e:
            print(f"Error: Invalid date format. Please use YYYY-MM-DD HH:MM:SS. {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # The user observed decay not hitting for 7/21 into 7/22.
    # This implies the season started on 7/22, but they want 7/21 to be the first day with decay possible.
    # So, setting the start date to 7/21 at 00:00:00 in the season's timezone.
    adjust_season_start_date("2025-07-21 00:00:00") 
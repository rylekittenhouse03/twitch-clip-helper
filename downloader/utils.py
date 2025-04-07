import datetime
import sys
import subprocess
import os
from constants import TWITCHTRACKER_URL_TEMPLATE


def get_formatted_date(days_offset=0):
    """Gets today's or a past date formatted as YYYYMMDD."""
    target_date = datetime.date.today() - datetime.timedelta(days=days_offset)
    return target_date.strftime("%Y%m%d")


def construct_tracker_url(username, date_str):
    """Constructs the TwitchTracker URL."""
    if not username:
        return None
    return TWITCHTRACKER_URL_TEMPLATE.format(username=username, date_str=date_str)


def check_command_exists(command):
    """Checks if a command exists in the system PATH."""
    try:
        check_cmd = "where" if sys.platform == "win32" else "which"
        subprocess.run(
            [check_cmd, command],
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )  # added text=True, errors="ignore"
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def create_directory_if_not_exists(dir_path, status_callback):
    """Creates a directory if it doesn't exist."""
    if not os.path.isdir(dir_path):
        status_callback(
            f"Directory '{dir_path}' does not exist. Attempting to create it."
        )
        try:
            os.makedirs(dir_path, exist_ok=True)
            status_callback(
                f"Successfully created directory: {dir_path}", tag="success"
            )  # changed tag
            return True
        except OSError as e:
            status_callback(
                f"Failed to create directory '{dir_path}': {e}", is_error=True
            )
            return False
    return True

import json
import os
from constants import USERNAME_HISTORY_FILE


def load_username_history():
    """Loads username history from the JSON file."""
    if not os.path.exists(USERNAME_HISTORY_FILE):
        return []
    try:
        # Ensure file is not empty before loading
        if os.path.getsize(USERNAME_HISTORY_FILE) == 0:
            return []
        with open(USERNAME_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

        # Validate and deduplicate
        if isinstance(history, list):
            seen = set()
            unique_history = []
            for item in history:
                # Ensure item is a non-empty string before processing
                if isinstance(item, str) and item.strip():
                    item_lower = item.lower()
                    if item_lower not in seen:
                        seen.add(item_lower)
                        unique_history.append(item)  # Keep original casing
            return unique_history
        return []  # Return empty if format is incorrect
    except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
        print(f"Error loading username history from {USERNAME_HISTORY_FILE}: {e}")
        # Attempt to handle potential corruption by returning an empty list
        # Consider adding backup/recovery logic here if needed
        # try:
        #     os.rename(USERNAME_HISTORY_FILE, f"{USERNAME_HISTORY_FILE}.bak_{int(time.time())}")
        # except OSError:
        #     pass
        return []


def save_username_history(history):
    """Saves username history to the JSON file, ensuring uniqueness."""
    try:
        seen = set()
        unique_history = []
        for item in history:
            # Ensure item is a non-empty string before processing
            if isinstance(item, str) and item.strip():
                item_lower = item.lower()
                if item_lower not in seen:
                    seen.add(item_lower)
                    unique_history.append(item)  # Keep original casing

        with open(USERNAME_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_history, f, indent=4)
    except IOError as e:
        print(f"Error saving username history to {USERNAME_HISTORY_FILE}: {e}")
    except (
        TypeError
    ) as e:  # Catch potential non-serializable types if list gets corrupted
        print(f"Error serializing username history: {e}. History data: {history}")


def add_username_to_history(username, history):
    """Adds a username to the beginning of the history list, ensuring uniqueness (case-insensitive)."""
    # Ensure username is a non-empty string
    if not username or not isinstance(username, str) or not username.strip():
        return history

    uname_cleaned = username.strip()
    uname_lower = uname_cleaned.lower()

    # Remove existing entries (case-insensitive) and create new list
    updated_history = [u for u in history if u.lower() != uname_lower]

    # Insert the new username (with original casing) at the beginning
    updated_history.insert(0, uname_cleaned)

    return updated_history

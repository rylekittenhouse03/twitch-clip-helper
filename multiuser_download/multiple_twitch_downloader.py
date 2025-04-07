import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext, PhotoImage
import json
import os
import subprocess
import threading
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions

# Core imports
import re
import sys
import logging
import time

# Theme
import sv_ttk


# --- Constants ---
USER_DATA_FILE = "twitch_user_data.json"  # Changed filename
DOWNLOAD_BASE_DIR = "twitch_clips_downloads"
DEFAULT_MAX_DOWNLOADS = 0  # 0 means unlimited

YT_DLP_PATH = (
    "yt-dlp"  # Assumes yt-dlp is in PATH
    # Example: "C:/path/to/yt-dlp.exe" # Uncomment and set if not in PATH
)

CHROME_DRIVER_PATH = (
    None  # Assumes chromedriver is in PATH or managed by Selenium Manager
    # Example: "C:/path/to/chromedriver.exe" # Uncomment and set if needed
)


# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# --- Utility Functions ---


def get_formatted_date(offset_days=0):
    """Gets today's or a past date formatted as YYYYMMDD."""
    target_date = date.today() - timedelta(days=offset_days)
    return target_date.strftime("%Y%m%d"), target_date


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def load_user_data_from_file():
    """Loads user data (username, max_downloads) from the JSON file."""
    if not os.path.exists(USER_DATA_FILE):
        return []
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Validate and potentially migrate old format (list of strings)
                processed_data = []
                usernames_seen = set()
                for item in data:
                    if isinstance(item, str):  # Old format
                        username = item.lower().strip()
                        if username and username not in usernames_seen:
                            processed_data.append(
                                {
                                    "username": username,
                                    "max_downloads": DEFAULT_MAX_DOWNLOADS,
                                }
                            )
                            usernames_seen.add(username)
                        else:
                            logging.warning(
                                f"Ignoring duplicate or empty username from old format: '{item}'"
                            )
                    elif isinstance(item, dict) and "username" in item:
                        username = item.get("username", "").lower().strip()
                        if not username:
                            logging.warning(
                                f"Ignoring entry with empty username: {item}"
                            )
                            continue
                        if username in usernames_seen:
                            logging.warning(
                                f"Ignoring duplicate username entry: '{username}'"
                            )
                            continue

                        max_downloads = item.get("max_downloads", DEFAULT_MAX_DOWNLOADS)
                        try:
                            max_downloads = int(max_downloads)
                            if max_downloads < 0:
                                max_downloads = (
                                    DEFAULT_MAX_DOWNLOADS  # Ensure non-negative
                                )
                        except (ValueError, TypeError):
                            logging.warning(
                                f"Invalid max_downloads '{max_downloads}' for user '{username}'. Using default {DEFAULT_MAX_DOWNLOADS}."
                            )
                            max_downloads = DEFAULT_MAX_DOWNLOADS

                        processed_data.append(
                            {"username": username, "max_downloads": max_downloads}
                        )
                        usernames_seen.add(username)
                    else:
                        logging.warning(
                            f"Ignoring invalid item in {USER_DATA_FILE}: {item}"
                        )
                # Sort by username before returning
                processed_data.sort(key=lambda x: x["username"])
                return processed_data
            else:
                logging.warning(
                    f"Invalid format in {USER_DATA_FILE}, expected a list. Starting fresh."
                )
                return []
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Error loading user data from {USER_DATA_FILE}: {e}")
        messagebox.showerror(
            "Load Error",
            f"Failed to load user data from {USER_DATA_FILE}.\n{e}\nStarting with an empty list.",
        )
        return []


def save_user_data_to_file(user_data_list):
    """Saves user data to the JSON file."""
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(USER_DATA_FILE) or ".", exist_ok=True)
        # Ensure uniqueness and sort before saving
        unique_user_data = []
        usernames_seen = set()
        for item in user_data_list:
            if isinstance(item, dict) and "username" in item:
                username = item.get("username", "").lower().strip()
                if username and username not in usernames_seen:
                    max_downloads = item.get("max_downloads", DEFAULT_MAX_DOWNLOADS)
                    try:
                        max_downloads = int(max_downloads)
                        if max_downloads < 0:
                            max_downloads = DEFAULT_MAX_DOWNLOADS
                    except (ValueError, TypeError):
                        max_downloads = DEFAULT_MAX_DOWNLOADS
                    unique_user_data.append(
                        {"username": username, "max_downloads": max_downloads}
                    )
                    usernames_seen.add(username)
                elif username:
                    logging.warning(
                        f"Duplicate username '{username}' detected during save, keeping first instance."
                    )
                # else: ignore entries without valid usernames
            else:
                logging.warning(f"Ignoring invalid item during save: {item}")

        unique_user_data.sort(key=lambda x: x["username"])

        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_user_data, f, indent=4)  # Sort by username before saving
    except IOError as e:
        logging.error(f"Error saving user data to {USER_DATA_FILE}: {e}")
        messagebox.showerror(
            "Save Error", f"Failed to save user data to {USER_DATA_FILE}.\n{e}"
        )


# --- Core Logic Functions ---


def extract_clip_urls(username, target_date_str, status_callback):
    """Uses Selenium to get clip URLs for a user on a specific date."""
    clip_urls = []
    # Target URL for clips on a specific date range
    url = f"https://twitchtracker.com/{username}/clips#{target_date_str}-{target_date_str}"
    status_callback(f"Attempting to scrape: {url}")
    logging.info(f"Scraping URL: {url}")

    options = ChromeOptions()
    options.add_argument("--headless")  # Run in background
    options.add_argument("--disable-gpu")  # Often needed for headless
    options.add_argument("--log-level=3")  # Suppress unnecessary logs
    options.add_argument("--mute-audio")  # Don't play sound
    options.add_experimental_option(
        "excludeSwitches", ["enable-logging"]
    )  # Suppress DevTools listening message

    driver = None
    try:
        # Attempt to use specified ChromeDriver path or let Selenium find it
        if CHROME_DRIVER_PATH and os.path.exists(CHROME_DRIVER_PATH):
            service = ChromeService(executable_path=CHROME_DRIVER_PATH)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            # Try default (Selenium Manager or PATH)
            try:
                driver = webdriver.Chrome(options=options)
            except WebDriverException as e:
                logging.error(
                    f"ChromeDriver not found in PATH or specified location. Please install ChromeDriver matching your Chrome version and ensure it's in PATH or set CHROME_DRIVER_PATH. Error: {e}"
                )
                status_callback(
                    f"Error: ChromeDriver setup failed for {username}. Check logs."
                )
                messagebox.showerror(
                    "WebDriver Error",
                    "ChromeDriver not found or setup failed. Please ensure it's installed and accessible.",
                )
                return None  # Indicate critical failure

        driver.get(url)
        # Wait for clip elements to be present (adjust timeout if needed)
        wait = WebDriverWait(driver, 15)  # Increased timeout slightly
        clip_elements = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.clip-tp"))
        )
        status_callback(
            f"Found {len(clip_elements)} potential clip elements for {username} on {target_date_str}."
        )

        for element in clip_elements:
            try:
                # Extract the clip ID from the 'data-litebox' attribute
                data_litebox = element.get_attribute("data-litebox")
                if data_litebox:
                    # Regex to find 'clip=...' part
                    match = re.search(r'clip=([^&"\']+)', data_litebox)
                    if match:
                        clip_id = match.group(1)
                        clip_watch_url = f"https://clips.twitch.tv/{clip_id}"
                        clip_urls.append(clip_watch_url)
                        # logging.debug(f"Found clip URL: {clip_watch_url}") # Debug log if needed
            except Exception as e:
                logging.warning(f"Could not process a clip element for {username}: {e}")
            # Limit URL extraction early? No, let download function handle limit.

        status_callback(
            f"Extracted {len(clip_urls)} clip URLs for {username} on {target_date_str}."
        )
        logging.info(
            f"Extracted {len(clip_urls)} clip URLs for {username} ({target_date_str})."
        )

    except TimeoutException:
        status_callback(
            f"No clips found or page timed out for {username} on {target_date_str}."
        )
        logging.info(
            f"Timeout or no clips found for {username} on {target_date_str} at {url}"
        )
    except NoSuchElementException:
        status_callback(
            f"Clip container element not found for {username} on {target_date_str}. Page structure might have changed."
        )
        logging.warning(
            f"CSS Selector 'div.clip-tp' not found for {username} on {target_date_str} at {url}"
        )
    except WebDriverException as e:
        status_callback(f"Selenium error for {username} on {target_date_str}: {e}")
        logging.error(
            f"WebDriverException for {username} on {target_date_str} at {url}: {e}"
        )
        return None  # Indicate critical failure
    except Exception as e:
        status_callback(f"Unexpected error during scraping for {username}: {e}")
        logging.error(
            f"Unexpected error scraping {username} on {target_date_str}: {e}",
            exc_info=True,
        )
    finally:
        if driver:
            driver.quit()  # Ensure browser closes

    # Return the list (might be empty) or None on critical error
    return clip_urls

import logging
import os
import subprocess
import sys
from tkinter import (
    messagebox,
)  # Assuming messagebox is used for critical errors like FileNotFoundError

# Constants assumed to be defined elsewhere:
# YT_DLP_PATH = "yt-dlp"
# DOWNLOAD_BASE_DIR = "twitch_clips_downloads"


def download_clips_for_user(
    username, clip_urls, max_downloads, target_date_str, status_callback
):
    """Uses yt-dlp to download clips for a user, respecting the maximum limit."""
    if not clip_urls:
        status_callback(
            f"No clip URLs to download for {username} on {target_date_str}."
        )
        return 0  # No clips to download

    # Apply max downloads limit if specified (and > 0)
    urls_to_download = clip_urls
    original_count = len(clip_urls)
    if max_downloads is not None and max_downloads > 0:
        if len(clip_urls) > max_downloads:
            urls_to_download = clip_urls[:max_downloads]
            status_callback(
                f"Limiting downloads for {username} to {max_downloads} (out of {original_count} found)."
            )
            logging.info(
                f"Limiting downloads for {username} ({target_date_str}) to {max_downloads} clips (found {original_count})."
            )

    num_to_download = len(urls_to_download)
    if (
        num_to_download == 0
    ):  # Should not happen if clip_urls was not empty, but good check
        status_callback(
            f"No clips selected for download for {username} after applying limit."
        )
        return 0

    download_dir = os.path.join(DOWNLOAD_BASE_DIR, username, target_date_str)
    os.makedirs(download_dir, exist_ok=True)
    status_callback(
        f"Downloading {num_to_download} clip(s) for {username} to {download_dir}..."
    )
    logging.info(
        f"Starting download for {username} ({target_date_str}) - {num_to_download} clips to '{download_dir}'."
    )

    downloaded_count = 0
    failed_count = 0

    for i, clip_url in enumerate(urls_to_download):
        # Log prefix for context
        log_msg_prefix = f"User '{username}', Date '{target_date_str}', Clip {i+1}/{num_to_download} ({clip_url})"
        try:
            # Build yt-dlp command - Optimized for speed while retaining quality
            # -f best: Ensure best available quality (usually default for clips)
            # --concurrent-fragments N: Download N fragments in parallel (significantly speeds up HLS/DASH)
            # --no-write-info-json: Skip writing the .info.json file (minor speedup, less clutter)
            command = [
                YT_DLP_PATH,
                "-P",
                download_dir,  # Output directory
                "-f",
                "best",  # Select best quality format
                "--concurrent-fragments",
                "5",  # Download up to 5 fragments concurrently
                "--socket-timeout",
                "20",  # Network timeout
                "--retries",
                "3",  # Retries on errors
                "--fragment-retries",
                "3",  # Retries for fragments
                "--no-warnings",  # Suppress yt-dlp warnings
                "--no-write-info-json",  # Don't create .info.json file
                # Consider adding "--embed-thumbnail" if you want thumbnails but they aren't default
                clip_url,  # The URL
            ]
            logging.info(f"{log_msg_prefix} - Running command: {' '.join(command)}")

            # Hide console window on Windows
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                command,
                capture_output=True,  # Get stdout/stderr
                text=True,  # Decode as text
                check=False,  # Don't raise exception on non-zero exit code
                encoding="utf-8",
                errors="replace",  # Handle potential encoding errors in output
                startupinfo=startupinfo,  # Hide window on Windows
            )

            if result.returncode == 0:
                downloaded_count += 1
                logging.info(f"{log_msg_prefix} - Download successful.")
                # status_callback(f"Successfully downloaded clip {i+1}/{num_to_download} for {username}.") # Can be too verbose
            else:
                failed_count += 1
                logging.error(
                    f"{log_msg_prefix} - Download failed. Return code: {result.returncode}"
                )
                # Log stderr/stdout only if non-empty to avoid clutter
                if result.stderr and result.stderr.strip():
                    logging.error(f"{log_msg_prefix} - Stderr: {result.stderr.strip()}")
                if result.stdout and result.stdout.strip():
                    logging.error(  # Log stdout as error too, might contain useful info on failure
                        f"{log_msg_prefix} - Stdout: {result.stdout.strip()}"
                    )
                status_callback(
                    f"Failed to download clip {i+1}/{num_to_download} for {username}. Check logs."
                )

        except FileNotFoundError:
            status_callback(
                f"Error: '{YT_DLP_PATH}' command not found. Is yt-dlp installed and in PATH?"
            )
            logging.error(
                f"'{YT_DLP_PATH}' command not found. Please ensure yt-dlp is installed and accessible via system PATH or configure YT_DLP_PATH correctly."
            )
            messagebox.showerror(
                "yt-dlp Error",
                f"'{YT_DLP_PATH}' not found. Install yt-dlp and ensure it's in your PATH.",
            )
            return -1  # Indicate critical failure (stop processing further users)
        except Exception as e:
            failed_count += 1
            status_callback(
                f"Error downloading clip {i+1} for {username}: {e}. Check logs."
            )
            logging.error(
                f"{log_msg_prefix} - Unexpected error during download: {e}",
                exc_info=True,  # Include traceback in log
            )

        # Optional: Small delay between downloads to avoid potential rate limiting?
        # import time
        # time.sleep(0.2) # Uncomment if needed, but concurrent fragments is usually better

    # Final status for the user
    final_msg = f"Finished downloads for {username} on {target_date_str}. Success: {downloaded_count}, Failed: {failed_count}."
    status_callback(final_msg)
    logging.info(final_msg)
    return downloaded_count  # Return number successfully downloaded


def run_download_process(user_data_to_process, target_date, status_callback):
    """Orchestrates the download for all users for a given date."""
    target_date_str = target_date.strftime("%Y%m%d")
    status_callback(f"--- Starting Download Process for {target_date_str} ---")
    user_list_str = ", ".join(
        [u.get("username", "UNKNOWN") for u in user_data_to_process]
    )
    logging.info(
        f"--- Starting Download Process for {target_date_str} for users: {user_list_str} ---"
    )

    total_downloaded_all_users = 0
    start_time = time.time()

    for user_data in user_data_to_process:
        username = user_data.get("username")
        max_downloads = user_data.get(
            "max_downloads", DEFAULT_MAX_DOWNLOADS
        )  # Get limit for this user

        if not username:  # Skip if username is somehow empty
            logging.warning(f"Skipping entry with missing username: {user_data}")
            continue

        status_callback(f"Processing user: {username} for date {target_date_str}...")
        clip_urls = extract_clip_urls(username, target_date_str, status_callback)

        if clip_urls is None:  # Critical error during scraping (e.g., WebDriver)
            status_callback(
                f"Skipping download for {username} due to critical scraping error."
            )
            logging.error(
                f"Skipping download for {username} ({target_date_str}) due to critical scraping error (likely WebDriver issue)."
            )
            continue  # Move to the next user

        download_result = download_clips_for_user(
            username,
            clip_urls,
            max_downloads,
            target_date_str,
            status_callback,  # Pass max_downloads
        )

        if (
            download_result == -1
        ):  # Critical error during download (e.g., yt-dlp not found)
            status_callback("Aborting download process due to critical yt-dlp error.")
            logging.error("Aborting download process due to critical yt-dlp error.")
            break  # Stop the entire download process

        if download_result > 0:
            total_downloaded_all_users += download_result

    end_time = time.time()
    duration = end_time - start_time
    status_callback(f"--- Download Process for {target_date_str} Finished ---")
    status_callback(
        f"Total clips downloaded across all users: {total_downloaded_all_users}"
    )
    status_callback(f"Total time: {duration:.2f} seconds")
    logging.info(
        f"--- Download Process for {target_date_str} Finished. Total downloaded: {total_downloaded_all_users}. Duration: {duration:.2f}s ---"
    )
    # No return value needed, status updates handle feedback


# --- GUI Application Class ---


class TwitchClipManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Clip Downloader")
        # Icon (optional, replace 'icon.png' with your file)
        # try:
        #     icon_path = resource_path("icon.png")
        #     self.root.iconphoto(True, PhotoImage(file=icon_path))
        # except tk.TclError:
        #     logging.warning("Could not load icon.png")
        self.root.minsize(650, 500)  # Increased min width slightly for new column/field

        # Application state
        self.user_data = (
            []
        )  # List of dictionaries: [{"username": "...", "max_downloads": N}, ...]
        self.download_thread = None
        self.is_downloading = False

        # Apply theme and configure styles
        self.style = ttk.Style()
        # sv_ttk.set_theme("dark") # Moved theme setting to main block
        self.style.theme_use(
            "clam"
        )  # Or another ttk theme like 'alt', 'default', 'classic'
        # Configure specific widget styles
        self.style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
        self.style.configure("Treeview", font=("Helvetica", 10), rowheight=25)
        self.style.map(
            "Treeview",
            background=[("selected", "#0078D7")],  # Color when selected
            foreground=[("selected", "white")],
        )
        self.style.configure(
            "TButton", padding=6, relief="flat", font=("Helvetica", 10)
        )
        self.style.configure("Status.TLabel", font=("Helvetica", 9), padding=5)
        self.style.configure(
            "Header.TLabel", font=("Helvetica", 12, "bold"), padding=(0, 5)
        )
        self.style.configure(
            "Error.TLabel", foreground="red"
        )  # Style for error messages

        # Build the UI elements
        self.setup_ui()

        # Load initial data from file
        self.load_initial_data()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Grid layout configuration
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)  # Treeview frame should expand
        main_frame.rowconfigure(
            4, weight=1
        )  # Status text area should expand vertically

        # --- Header ---
        header_label = ttk.Label(
            main_frame, text="Twitch User Configuration", style="Header.TLabel"
        )
        header_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # --- Treeview for User Data ---
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Username", "Max Downloads"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("Username", text="Username")
        self.tree.heading("Max Downloads", text="Max Downloads (0=unlim.)")
        self.tree.column(
            "Username", anchor=tk.W, width=200, stretch=tk.YES  # Allow stretching
        )
        self.tree.column(
            "Max Downloads", anchor=tk.CENTER, width=150, stretch=tk.NO
        )  # Fixed width

        # Scrollbar for Treeview
        tree_scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=tree_scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scrollbar.grid(row=0, column=1, sticky="ns")

        # Bind double-click to edit
        self.tree.bind("<Double-1>", self.handle_edit_selected)

        # --- Input Fields for Adding/Editing Users ---
        input_frame = ttk.Frame(main_frame)
        input_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)
        input_frame.columnconfigure(
            1, weight=1
        )  # Allow username entry to expand slightly
        input_frame.columnconfigure(3, weight=0)  # Max downloads entry fixed width
        input_frame.columnconfigure(4, weight=0)  # Buttons fixed width

        ttk.Label(input_frame, text="Username:").grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )
        self.username_entry_var = tk.StringVar()
        self.username_entry = ttk.Entry(
            input_frame, textvariable=self.username_entry_var, width=30
        )
        self.username_entry.grid(row=0, column=1, sticky="ew", padx=5)
        # Bind Enter key in username entry to add action
        self.username_entry.bind("<Return>", self.handle_add)

        ttk.Label(input_frame, text="Max Dl:").grid(
            row=0, column=2, padx=(10, 5), sticky="w"  # Label for max downloads
        )
        self.max_downloads_var = tk.StringVar(
            value=str(DEFAULT_MAX_DOWNLOADS)
        )  # Default value
        # Use Spinbox for integer input, allow empty for default
        # self.max_downloads_entry = ttk.Spinbox(input_frame, from_=0, to=999, textvariable=self.max_downloads_var, width=5)
        vcmd = (
            self.root.register(self.validate_integer_input),
            "%P",
        )  # Validation command
        self.max_downloads_entry = ttk.Entry(
            input_frame,
            textvariable=self.max_downloads_var,
            width=6,
            validate="key",
            validatecommand=vcmd,  # Validate on key press
        )
        self.max_downloads_entry.grid(row=0, column=3, sticky="w", padx=5)

        # --- CRUD Buttons ---
        crud_button_frame = ttk.Frame(input_frame)
        crud_button_frame.grid(row=0, column=4, sticky="e", padx=(10, 0))

        self.add_button = ttk.Button(
            crud_button_frame, text="Add", command=self.handle_add, width=8
        )
        self.add_button.pack(side=tk.LEFT, padx=2)

        self.edit_button = ttk.Button(
            crud_button_frame,
            text="Edit Sel.",
            command=self.handle_edit_selected,
            width=8,
        )
        self.edit_button.pack(side=tk.LEFT, padx=2)

        self.delete_button = ttk.Button(
            crud_button_frame,
            text="Delete Sel.",
            command=self.handle_delete_selected,
            width=10,
        )
        self.delete_button.pack(side=tk.LEFT, padx=2)

        # --- Download Action Buttons ---
        download_frame = ttk.Frame(main_frame)
        download_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)

        self.download_today_button = ttk.Button(
            download_frame,
            text="Download Today's Clips",
            command=lambda: self.start_download_thread(0),  # 0 days offset
        )
        self.download_today_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.download_yesterday_button = ttk.Button(
            download_frame,
            text="Download Yesterday's Clips",
            command=lambda: self.start_download_thread(1),  # 1 day offset
        )
        self.download_yesterday_button.pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True
        )

        # --- Status/Log Area ---
        status_frame = ttk.LabelFrame(main_frame, text="Status / Log", padding=5)
        status_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(5, 0))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            height=10,  # Increased height slightly
            wrap=tk.WORD,  # Wrap long lines
            state=tk.DISABLED,  # Start read-only
            font=("TkFixedFont", 9),  # Monospaced font for logs
        )
        self.status_text.grid(row=0, column=0, sticky="nsew")

    def validate_integer_input(self, P):
        """Validation function for the max downloads Entry widget."""
        if P == "" or (
            P.isdigit() and int(P) >= 0
        ):  # Allow empty string or non-negative integer
            return True
        else:
            self.root.bell()  # Alert user of invalid input
            return False

    def update_status(self, message, log=True):
        """Updates the status text area. Runs in the main GUI thread."""
        if log:
            logging.info(f"GUI Status: {message}")  # Log status updates

        try:
            if self.root.winfo_exists():  # Check if window still exists
                self.status_text.config(state=tk.NORMAL)  # Enable writing
                self.status_text.insert(tk.END, message + "\n")
                self.status_text.see(tk.END)  # Scroll to the bottom
                self.status_text.config(state=tk.DISABLED)  # Disable writing again
                self.root.update_idletasks()  # Force GUI update
        except Exception as e:
            logging.error(f"Failed to update GUI status: {e}")

    def schedule_status_update(self, message):
        """Schedules a status update from a worker thread."""
        # Use `root.after` to ensure `update_status` runs in the main GUI thread
        self.root.after(0, self.update_status, message)

    def load_initial_data(self):
        """Loads user data from file and populates the treeview."""
        self.update_status(f"Loading user data from {USER_DATA_FILE}...", log=False)
        self.user_data = load_user_data_from_file()
        self.populate_treeview()
        self.update_status(f"Loaded {len(self.user_data)} users.", log=False)

    def populate_treeview(self):
        """Clears and refills the treeview from the internal user_data list."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Insert items sorted by username (already sorted in load/save)
        for user_info in self.user_data:
            username = user_info.get("username", "N/A")
            max_dl = user_info.get("max_downloads", DEFAULT_MAX_DOWNLOADS)
            # Display 'Unlimited' if max_dl is 0, otherwise the number
            max_dl_display = str(
                max_dl
            )  # "Unlimited" if max_dl == 0 else str(max_dl) # Keep 0 for clarity
            self.tree.insert(
                "", tk.END, values=(username, max_dl_display), iid=username
            )  # Use username as item id

    def handle_add(self, event=None):  # event=None allows binding to <Return>
        """Adds a new user from the entry fields."""
        new_username = self.username_entry_var.get().strip().lower()
        max_downloads_str = self.max_downloads_var.get().strip()

        if not new_username:
            messagebox.showwarning("Input Error", "Username cannot be empty.")
            return
        if not re.match(
            r"^[a-zA-Z0-9_]{3,25}$", new_username
        ):  # Basic Twitch username regex
            messagebox.showwarning(
                "Input Error",
                "Invalid Twitch username format (3-25 chars, letters, numbers, underscores).",
            )
            return

        try:
            # Use default if empty, otherwise parse integer
            max_downloads = (
                DEFAULT_MAX_DOWNLOADS
                if not max_downloads_str
                else int(max_downloads_str)
            )
            if max_downloads < 0:
                messagebox.showwarning(
                    "Input Error",
                    "Maximum downloads cannot be negative. Use 0 for unlimited.",
                )
                return
        except ValueError:
            messagebox.showwarning(
                "Input Error",
                "Invalid maximum downloads value. Please enter a non-negative integer (or leave blank for unlimited).",
            )
            return

        # Check for duplicates
        if any(u["username"] == new_username for u in self.user_data):
            messagebox.showinfo(
                "Duplicate", f"Username '{new_username}' already exists."
            )
        else:
            new_user_info = {"username": new_username, "max_downloads": max_downloads}
            self.user_data.append(new_user_info)
            self.user_data.sort(key=lambda x: x["username"])  # Keep sorted
            self.populate_treeview()  # Refresh view
            save_user_data_to_file(self.user_data)  # Persist changes
            self.update_status(f"Added user: {new_username} (Max DL: {max_downloads})")
            # Clear input fields
            self.username_entry_var.set("")
            self.max_downloads_var.set(str(DEFAULT_MAX_DOWNLOADS))  # Reset to default

            # Select the newly added item in the tree
            try:
                if self.tree.exists(new_username):
                    self.tree.selection_set(new_username)
                    self.tree.focus(new_username)
                    self.tree.see(new_username)
            except Exception as e:
                logging.warning(
                    f"Could not select new item {new_username} in tree: {e}"
                )

    def handle_edit_selected(
        self, event=None
    ):  # event=None allows binding to double-click
        """Handles editing the selected user's data."""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Selection Error", "Please select a user to edit.")
            return
        if len(selected_items) > 1:
            messagebox.showwarning(
                "Selection Error", "Please select only one user to edit."
            )
            return

        item_id = selected_items[0]  # This should be the username if iid was set
        # Find the user data dictionary
        user_info = next((u for u in self.user_data if u["username"] == item_id), None)

        if not user_info:
            logging.error(
                f"Consistency error: Cannot find data for selected username '{item_id}'"
            )
            messagebox.showerror(
                "Internal Error", "Could not find data for the selected user."
            )
            return

        old_username = user_info["username"]
        old_max_downloads = user_info["max_downloads"]

        # --- Edit Username ---
        new_username = simpledialog.askstring(
            "Edit Username",
            f"Enter new username for '{old_username}' (or leave as is):",
            parent=self.root,
            initialvalue=old_username,
        )

        if new_username is None:  # User cancelled
            return
        new_username = new_username.strip().lower()

        if not new_username:
            messagebox.showwarning("Input Error", "Username cannot be empty.")
            return
        if not re.match(r"^[a-zA-Z0-9_]{3,25}$", new_username):
            messagebox.showwarning("Input Error", "Invalid Twitch username format.")
            return

        # Check if username changed and if the new one conflicts
        username_changed = new_username != old_username
        if username_changed and any(
            u["username"] == new_username for u in self.user_data
        ):
            messagebox.showinfo(
                "Duplicate", f"Username '{new_username}' already exists."
            )
            return  # Abort edit if new username is a duplicate

        # --- Edit Max Downloads ---
        new_max_downloads = simpledialog.askinteger(
            "Edit Max Downloads",
            f"Enter max downloads for '{new_username}' (0 for unlimited):",
            parent=self.root,
            initialvalue=old_max_downloads,
            minvalue=0,  # Ensure non-negative
        )

        if new_max_downloads is None:  # User cancelled the second dialog
            return

        # --- Apply Changes ---
        if new_username == old_username and new_max_downloads == old_max_downloads:
            return  # No changes made

        try:
            # Update the dictionary in the list
            user_info["username"] = new_username
            user_info["max_downloads"] = new_max_downloads

            if username_changed:
                self.user_data.sort(
                    key=lambda x: x["username"]
                )  # Re-sort if username changed

            self.populate_treeview()  # Refresh the entire tree view
            save_user_data_to_file(self.user_data)  # Save changes
            self.update_status(
                f"Edited user: '{old_username}' -> '{new_username}' (Max DL: {new_max_downloads})"
            )

            # Reselect the item (using the potentially new username as iid)
            try:
                if self.tree.exists(new_username):
                    self.tree.selection_set(new_username)
                    self.tree.focus(new_username)
                    self.tree.see(new_username)
            except Exception as e:
                logging.warning(
                    f"Could not select updated item {new_username} in tree: {e}"
                )

        except Exception as e:  # Catch unexpected errors during update
            logging.error(
                f"Error updating user data for '{old_username}': {e}", exc_info=True
            )
            messagebox.showerror(
                "Update Error", f"An unexpected error occurred during the update: {e}"
            )
            # Attempt to reload data to potentially recover state
            self.load_initial_data()

    def handle_delete_selected(self):
        """Deletes the selected user(s)."""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning(
                "Selection Error", "Please select user(s) to delete."
            )
            return

        selected_usernames = [
            self.tree.item(item_id)["values"][0] for item_id in selected_items
        ]

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete the following {len(selected_usernames)} user(s)?\n\n"
            + "\n".join(selected_usernames),
            parent=self.root,
        )

        if confirm:
            original_count = len(self.user_data)
            # Filter out the users to be deleted
            self.user_data = [
                u for u in self.user_data if u["username"] not in selected_usernames
            ]
            deleted_count = original_count - len(self.user_data)

            if deleted_count > 0:
                # No need to sort as relative order is maintained
                self.populate_treeview()  # Refresh view
                save_user_data_to_file(self.user_data)  # Persist changes
                self.update_status(f"Deleted {deleted_count} user(s).")
            else:
                # This case shouldn't normally happen if selection is from the tree
                self.update_status(
                    "No users were deleted (they might not have been found in the data)."
                )
                logging.warning(
                    f"Delete operation did not remove users: {selected_usernames}"
                )

    def set_ui_state(self, state):
        """Enable or disable UI elements based on state ('normal' or 'disabled')."""
        # Download buttons
        self.download_today_button.config(state=state)
        self.download_yesterday_button.config(state=state)
        # CRUD buttons
        self.add_button.config(state=state)
        self.edit_button.config(state=state)
        self.delete_button.config(state=state)
        # Input fields
        self.username_entry.config(state=state)
        self.max_downloads_entry.config(state=state)
        # Treeview interaction (optional, might want to disable selection during download)
        # self.tree.config(selectmode=tk.NONE if state == tk.DISABLED else tk.EXTENDED)

    def start_download_thread(self, days_offset):
        """Starts the download process in a separate thread."""
        if self.is_downloading:
            messagebox.showwarning("Busy", "A download process is already running.")
            return

        if not self.user_data:
            messagebox.showinfo(
                "No Users", "There are no users configured to download clips for."
            )
            return

        target_date_str, target_date = get_formatted_date(days_offset)
        day_description = "today's" if days_offset == 0 else "yesterday's"

        confirm = messagebox.askyesno(
            "Confirm Download",
            f"Download {day_description} ({target_date_str}) clips for all {len(self.user_data)} configured users (respecting max limits)?",
            parent=self.root,
        )
        if not confirm:
            return

        self.is_downloading = True
        self.set_ui_state(tk.DISABLED)  # Disable UI elements
        self.update_status(
            f"--- Preparing to download {day_description} clips ({target_date_str}) ---"
        )

        # Pass a copy of the user data to the thread
        user_data_copy = [u.copy() for u in self.user_data]

        # Create and start the download thread
        self.download_thread = threading.Thread(
            target=self.run_download_wrapper,
            args=(user_data_copy, target_date),
            daemon=True,  # Allows app to exit even if thread is running (use carefully)
        )
        self.download_thread.start()

    def run_download_wrapper(self, user_data_to_process, target_date):
        """Wrapper function to run in thread, handles UI state after completion."""
        try:
            # Run the main download logic, passing the status callback function
            run_download_process(
                user_data_to_process, target_date, self.schedule_status_update
            )
        except Exception as e:
            # Log critical errors occurring within the thread itself
            self.schedule_status_update(
                f"--- Critical error in download thread: {e} ---"
            )
            logging.error("Critical error in download thread", exc_info=True)
        finally:
            # Ensure UI is re-enabled *after* the thread finishes
            # Use root.after to schedule this back on the main GUI thread
            self.root.after(0, self.on_download_complete)

    def on_download_complete(self):
        """Callback executed in the main thread after download finishes."""
        self.is_downloading = False
        self.set_ui_state(tk.NORMAL)  # Re-enable UI elements
        self.schedule_status_update(  # Use schedule to ensure it's added to the queue
            "--- Download process finished. UI re-enabled. ---"
        )


# --- Main Execution ---

if __name__ == "__main__":
    # Initial check for yt-dlp dependency
    try:
        # Hide console window on Windows for this check
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            [YT_DLP_PATH, "--version"],
            capture_output=True,
            text=True,
            check=True,  # Raise error if command fails
            startupinfo=startupinfo,
        )
        logging.info(f"Found yt-dlp: Version {result.stdout.strip()}")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logging.error(
            f"Failed to find or execute '{YT_DLP_PATH}'. Please ensure yt-dlp is installed and in PATH, or configure YT_DLP_PATH in the script."
        )
        messagebox.showerror(
            "Dependency Error",
            f"Could not find or run '{YT_DLP_PATH}'.\n"
            "Please install yt-dlp (see https://github.com/yt-dlp/yt-dlp) "
            "and ensure it's in your system's PATH or configure the YT_DLP_PATH variable in the script.",
        )
        sys.exit(1)  # Exit if dependency is missing

    # Check if specified ChromeDriver path exists (if provided)
    if CHROME_DRIVER_PATH and not os.path.exists(CHROME_DRIVER_PATH):
        logging.warning(
            f"Specified CHROME_DRIVER_PATH '{CHROME_DRIVER_PATH}' does not exist. Selenium might fail if ChromeDriver is not in PATH."
        )
        # Don't exit here, Selenium Manager might still work

    # Setup Tkinter root window
    root = tk.Tk()

    # Apply the theme *before* creating the App instance if possible

    # Create and run the application
    app = TwitchClipManagerApp(root)
    sv_ttk.set_theme("dark")  # Or "light"
    root.mainloop()

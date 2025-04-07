import os

# --- History Settings ---
USERNAME_HISTORY_FILE = "username_history.json"
MAX_RECENT_HISTORY = 3  # Max items to show initially on focus
MAX_AUTOCOMPLETE_RESULTS = 10  # Max items to show in autocomplete list

# --- File Paths ---
DEFAULT_OUTPUT_DIRECTORY = os.getcwd()

# --- Web Scraping ---
TWITCHTRACKER_URL_TEMPLATE = (
    "https://twitchtracker.com/{username}/clips#{date_str}-{date_str}"
)
TWITCH_CLIP_BASE_URL = "https://clips.twitch.tv/"
CLIP_URL_REGEX_PATTERN = r'data-litebox=".*?clip=([^"]+)"'
SELENIUM_TIMEOUT = 20  # seconds to wait for elements
SELENIUM_PAGE_LOAD_TIMEOUT = 60  # seconds to wait for page load

# --- UI ---
WINDOW_GEOMETRY = "600x550"
UI_THEME = "dark"
# Color tags for status log
COLOR_TAGS = {
    "info": "#dcdcdc",  # Default text color
    "error": "#FF6B6B",  # Reddish
    "success": "#77DD77",  # Greenish
    "warning": "#FFD700",  # Yellowish/Gold
    "download": "#87CEEB",  # Sky Blue
    "progress": "#A9A9A9",  # Dark Gray
}
TEXT_AREA_BG = "#2b2b2b"
TEXT_AREA_FG = COLOR_TAGS["info"]
TEXT_AREA_SELECT_BG = "#4a6984"
AUTOCOMPLETE_BG = "#333333"
AUTOCOMPLETE_FG = "#CCCCCC"
AUTOCOMPLETE_SELECT_BG = "#0078D7"
AUTOCOMPLETE_SELECT_FG = "#FFFFFF"
AUTOCOMPLETE_HIGHLIGHT = "#555555"

# --- Downloader ---
YT_DLP_COMMAND = "yt-dlp"
SOCKET_TIMEOUT = "30"  # seconds for yt-dlp network operations

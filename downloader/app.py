import tkinter as tk
import sv_ttk

# Import local GUI components
from .widgets import GuiWidgets
from .autocomplete import AutocompleteHandler
from .actions import ActionHandler

# Import project-level components
from constants import WINDOW_GEOMETRY, UI_THEME, DEFAULT_OUTPUT_DIRECTORY
from history import load_username_history


class ClipDownloaderApp:
    """Main application class orchestrating the GUI components."""

    def __init__(self, master):
        self.master = master
        master.title("Twitch Clip Downloader")
        master.geometry(WINDOW_GEOMETRY)

        # Apply theme
        sv_ttk.set_theme(UI_THEME)

        # --- Application State ---
        self.username_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIRECTORY)
        self.max_downloads_var = tk.IntVar(value=0)  # Default 0 = unlimited
        self.username_history = load_username_history()  # Load initial history

        # Dictionary to easily pass tk variables to components
        self.app_vars = {
            "username_var": self.username_var,
            "output_dir_var": self.output_dir_var,
            "max_downloads_var": self.max_downloads_var,
        }

        # --- Instantiate Handlers ---
        # ActionHandler needs access to widgets and vars, it defines actions
        # Note: Pass the actual self.username_history list reference to ActionHandler
        # so it can modify it directly via _persist_username.
        self.action_handler = ActionHandler(
            master,
            None,
            self.app_vars,
            None,
            self.username_history,  # Widgets/Autocomplete passed later
        )

        # Define callbacks needed by GuiWidgets, pointing to ActionHandler methods
        widget_callbacks = {
            "browse_directory": self.action_handler.browse_directory,
            "validate_non_negative_int": self.action_handler.validate_non_negative_int,
            "start_today": lambda: self.action_handler.start_processing(0),
            "start_yesterday": lambda: self.action_handler.start_processing(1),
        }

        # --- Create Widgets ---
        self.widget_manager = GuiWidgets(master, self.app_vars, widget_callbacks)
        self.widgets = self.widget_manager.get_widgets()  # Get widget references

        # --- Instantiate Autocomplete Handler ---
        # AutocompleteHandler needs specific widgets, vars, and the history list
        self.autocomplete_handler = AutocompleteHandler(
            master, self.widgets, self.app_vars, self.username_history
        )

        # --- Provide cross-references now that all components exist ---
        self.action_handler.widgets = (
            self.widgets
        )  # Give ActionHandler widget references
        self.action_handler.autocomplete = (
            self.autocomplete_handler
        )  # Give ActionHandler autocomplete reference

        # --- Bind Master-Level Events ---
        # Bind Return key on username entry via ActionHandler's wrapper
        self.widgets["username_entry"].bind(
            "<Return>",
            lambda event: self.action_handler.start_processing_event_handler(0),
        )
        # Global escape to hide autocomplete if visible
        master.bind("<Escape>", lambda e: self.autocomplete_handler.hide_if_visible())

import tkinter as tk
from tkinter import ttk, scrolledtext

from constants import (
    DEFAULT_OUTPUT_DIRECTORY,
    COLOR_TAGS,
    TEXT_AREA_BG,
    TEXT_AREA_FG,
    TEXT_AREA_SELECT_BG,
    AUTOCOMPLETE_BG,
    AUTOCOMPLETE_FG,
    AUTOCOMPLETE_SELECT_BG,
    AUTOCOMPLETE_SELECT_FG,
    AUTOCOMPLETE_HIGHLIGHT,
)


class GuiWidgets:
    """Creates and manages the core GUI widgets."""

    def __init__(self, master, app_vars, callbacks):
        """
        Initializes and lays out the widgets.

        Args:
            master: The main tk.Tk root window or a parent frame.
            app_vars: A dictionary containing necessary tk variables (StringVar, IntVar).
                      Expected keys: 'username_var', 'output_dir_var', 'max_downloads_var'.
            callbacks: A dictionary containing callback functions.
                       Expected keys: 'browse_directory', 'validate_non_negative_int',
                                      'start_today', 'start_yesterday'.
        """
        self.master = master
        self.app_vars = app_vars
        self.callbacks = callbacks

        # Main application frame
        self.main_frame = ttk.Frame(master, padding="15")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(4, weight=1)  # Row for status frame to expand

        # Create widget sections
        self._create_options_frame()
        self._create_autocomplete_widgets()
        self._create_button_frame()
        self._create_status_frame()

        # Set initial focus
        self.username_entry.focus_set()

    def _create_options_frame(self):
        """Creates the top frame containing input fields and options."""
        options_frame = ttk.Frame(self.main_frame)
        options_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        options_frame.grid_columnconfigure(1, weight=1)

        # Username
        ttk.Label(options_frame, text="Twitch Username:").grid(
            row=0, column=0, padx=(0, 10), pady=5, sticky="w"
        )
        self.username_entry = ttk.Entry(
            options_frame, textvariable=self.app_vars["username_var"], width=40
        )
        self.username_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=5)

        # Output Directory
        ttk.Label(options_frame, text="Output Directory:").grid(
            row=1, column=0, padx=(0, 10), pady=5, sticky="w"
        )
        self.dir_entry = ttk.Entry(
            options_frame, textvariable=self.app_vars["output_dir_var"], width=40
        )
        self.dir_entry.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=5)
        self.browse_button = ttk.Button(
            options_frame, text="Browse...", command=self.callbacks["browse_directory"]
        )
        self.browse_button.grid(row=1, column=2, sticky="e", pady=5)

        # Max Downloads
        ttk.Label(options_frame, text="Max Downloads:").grid(
            row=2, column=0, padx=(0, 10), pady=(10, 5), sticky="w"
        )
        validate_cmd = (
            self.master.register(self.callbacks["validate_non_negative_int"]),
            "%P",
        )
        self.max_downloads_spinbox = ttk.Spinbox(
            options_frame,
            from_=0,
            to=9999,
            textvariable=self.app_vars["max_downloads_var"],
            width=8,
            validate="key",
            validatecommand=validate_cmd,
        )
        self.max_downloads_spinbox.grid(row=2, column=1, sticky="w", pady=(10, 5))
        ttk.Label(options_frame, text="(0 for unlimited)").grid(
            row=2, column=2, padx=(5, 0), pady=(10, 5), sticky="w"
        )

    def _create_autocomplete_widgets(self):
        """Creates the frame and listbox for username autocomplete."""
        # Note: Positioning is handled by the AutocompleteHandler class
        self.autocomplete_frame = tk.Frame(self.main_frame, bd=1, relief=tk.FLAT)
        self.autocomplete_listbox = tk.Listbox(
            self.autocomplete_frame,
            height=0,
            relief=tk.FLAT,
            bd=0,
            bg=AUTOCOMPLETE_BG,
            fg=AUTOCOMPLETE_FG,
            selectbackground=AUTOCOMPLETE_SELECT_BG,
            selectforeground=AUTOCOMPLETE_SELECT_FG,
            highlightthickness=1,
            highlightcolor=AUTOCOMPLETE_HIGHLIGHT,
            highlightbackground=AUTOCOMPLETE_BG,
            exportselection=False,
            activestyle="none",
        )
        self.autocomplete_listbox.pack(fill=tk.BOTH, expand=True)

    def _create_button_frame(self):
        """Creates the frame holding the action buttons."""
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=3, column=0, pady=15)

        self.today_button = ttk.Button(
            button_frame,
            text="Fetch Today's Clips",
            command=self.callbacks["start_today"],
            style="Accent.TButton",
        )
        self.today_button.pack(side=tk.LEFT, padx=10)

        self.yesterday_button = ttk.Button(
            button_frame,
            text="Fetch Yesterday's Clips",
            command=self.callbacks["start_yesterday"],
        )
        self.yesterday_button.pack(side=tk.LEFT, padx=10)

    def _create_status_frame(self):
        """Creates the frame and text area for status logging."""
        status_frame = ttk.LabelFrame(
            self.main_frame, text="Status Log", padding=(10, 5)
        )
        status_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 5))
        status_frame.grid_rowconfigure(0, weight=1)
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_text = scrolledtext.ScrolledText(
            status_frame,
            height=15,
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            bd=1,
            bg=TEXT_AREA_BG,
            fg=TEXT_AREA_FG,
            insertbackground=TEXT_AREA_FG,
            selectbackground=TEXT_AREA_SELECT_BG,
            selectforeground=TEXT_AREA_FG,
            padx=5,
            pady=5,
        )
        self.status_text.grid(row=0, column=0, sticky="nsew")

        # Configure color tags
        for tag_name, color_code in COLOR_TAGS.items():
            self.status_text.tag_config(tag_name, foreground=color_code)

    def get_widgets(self):
        """Returns a dictionary of key widgets needed by other handlers."""
        return {
            "username_entry": self.username_entry,
            "dir_entry": self.dir_entry,
            "browse_button": self.browse_button,
            "max_downloads_spinbox": self.max_downloads_spinbox,
            "today_button": self.today_button,
            "yesterday_button": self.yesterday_button,
            "status_text": self.status_text,
            "autocomplete_frame": self.autocomplete_frame,
            "autocomplete_listbox": self.autocomplete_listbox,
            "main_frame": self.main_frame,  # Needed for placing autocomplete relative to it
        }

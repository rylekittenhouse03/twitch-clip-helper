import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import threading
import sv_ttk

# Import from other modules
from constants import (
    DEFAULT_OUTPUT_DIRECTORY,
    MAX_RECENT_HISTORY,
    MAX_AUTOCOMPLETE_RESULTS,
    WINDOW_GEOMETRY,
    UI_THEME,
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
from history import (
    load_username_history,
    save_username_history,
    add_username_to_history,
)
from utils import get_formatted_date  # Import only necessary utils
from processing import process_request  # Import the main processing logic


class ClipDownloaderApp:
    def __init__(self, master):
        self.master = master
        master.title("Twitch Clip Downloader")
        master.geometry(WINDOW_GEOMETRY)

        # Apply theme using sv_ttk
        sv_ttk.set_theme(UI_THEME)

        # --- State Variables ---
        self.username_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIRECTORY)
        self.max_downloads_var = tk.IntVar(
            value=0
        )  # Add var for max downloads, default 0 (unlimited)
        self.is_processing = False
        self.username_history = load_username_history()
        self.autocomplete_listbox = None
        self.autocomplete_frame = None
        self._after_id_hide_listbox = None  # For delayed hiding of autocomplete

        # --- Main Frame ---
        main_frame = ttk.Frame(master, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        # Configure grid rows and columns for main_frame responsiveness
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1)  # Allow status frame row to expand

        # --- Input/Options Frame ---
        options_frame = ttk.Frame(main_frame)
        options_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        options_frame.grid_columnconfigure(1, weight=1)  # Allow entry fields to expand

        # Username Input
        ttk.Label(options_frame, text="Twitch Username:").grid(
            row=0, column=0, padx=(0, 10), pady=5, sticky="w"
        )
        self.username_entry = ttk.Entry(
            options_frame, textvariable=self.username_var, width=40
        )
        self.username_entry.grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=5
        )  # Span 2 columns

        # Directory Input
        ttk.Label(options_frame, text="Output Directory:").grid(
            row=1, column=0, padx=(0, 10), pady=5, sticky="w"
        )
        self.dir_entry = ttk.Entry(
            options_frame, textvariable=self.output_dir_var, width=40
        )
        self.dir_entry.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=5)
        self.browse_button = ttk.Button(
            options_frame, text="Browse...", command=self.browse_directory
        )
        self.browse_button.grid(row=1, column=2, sticky="e", pady=5)

        # Max Downloads Input
        ttk.Label(options_frame, text="Max Downloads:").grid(
            row=2, column=0, padx=(0, 10), pady=(10, 5), sticky="w"
        )  # Add vertical padding
        # Use Spinbox for numeric input, validatecommand can be added for stricter control
        self.max_downloads_spinbox = ttk.Spinbox(
            options_frame,
            from_=0,  # Minimum value 0 (unlimited)
            to=9999,  # Set a reasonable upper limit
            textvariable=self.max_downloads_var,
            width=8,  # Smaller width for number input
            validate="key",  # Validate on key press
            validatecommand=(
                master.register(self._validate_non_negative_int),
                "%P",
            ),  # Validate input
        )
        self.max_downloads_spinbox.grid(
            row=2, column=1, sticky="w", pady=(10, 5)
        )  # Align left
        ttk.Label(options_frame, text="(0 for unlimited)").grid(
            row=2, column=2, padx=(5, 0), pady=(10, 5), sticky="w"
        )  # Hint

        # --- Autocomplete Frame & Listbox (Positioned relative to username_entry) ---
        self.autocomplete_frame = tk.Frame(main_frame, bd=1, relief=tk.FLAT)
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

        # --- Bindings ---
        self.username_entry.bind(
            "<Return>", lambda event: self._start_processing_event(0)
        )
        self.username_entry.bind("<FocusIn>", self._on_username_focus_in)
        self.username_entry.bind("<FocusOut>", self._on_username_focus_out)
        self.username_entry.bind("<KeyRelease>", self._on_username_key_release)
        self.username_entry.bind("<Down>", self._move_selection_down)
        self.username_entry.bind("<Up>", self._move_selection_up)
        self.autocomplete_listbox.bind("<ButtonRelease-1>", self._on_listbox_select)
        self.autocomplete_listbox.bind("<Return>", self._on_listbox_select)
        self.autocomplete_listbox.bind("<Escape>", lambda e: self._hide_autocomplete())
        master.bind("<Escape>", lambda e: self._hide_autocomplete_if_visible())

        master.after(50, self._position_autocomplete_listbox)

        # --- Button Frame ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, pady=15)  # Use grid row 3

        self.today_button = ttk.Button(
            button_frame,
            text="Fetch Today's Clips",
            command=lambda: self.start_processing(0),
            style="Accent.TButton",
        )
        self.today_button.pack(side=tk.LEFT, padx=10)

        self.yesterday_button = ttk.Button(
            button_frame,
            text="Fetch Yesterday's Clips",
            command=lambda: self.start_processing(1),
        )
        self.yesterday_button.pack(side=tk.LEFT, padx=10)

        # --- Status Log Frame & Text Area ---
        status_frame = ttk.LabelFrame(main_frame, text="Status Log", padding=(10, 5))
        status_frame.grid(
            row=4, column=0, sticky="nsew", pady=(10, 5)
        )  # Use grid row 4
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

        for tag_name, color_code in COLOR_TAGS.items():
            self.status_text.tag_config(tag_name, foreground=color_code)

        self.username_entry.focus_set()

    def _validate_non_negative_int(self, P):
        """Validation command for Spinbox: allow only non-negative integers or empty string."""
        if P == "":  # Allow empty string (useful when deleting content)
            return True
        try:
            val = int(P)
            return val >= 0
        except ValueError:
            return False  # Not an integer

    def _position_autocomplete_listbox(self):
        """Places the autocomplete listbox directly below the username entry."""
        self.master.update_idletasks()
        if not self.username_entry.winfo_exists():
            return

        # Get position relative to its master (options_frame)
        entry_x = self.username_entry.winfo_x()
        entry_y = self.username_entry.winfo_y()
        entry_height = self.username_entry.winfo_height()
        entry_width = self.username_entry.winfo_width()

        # Calculate position relative to the main_frame (parent of options_frame)
        frame_x = self.username_entry.master.winfo_x() + entry_x
        frame_y = self.username_entry.master.winfo_y() + entry_y + entry_height + 1

        self.autocomplete_frame.place(x=frame_x, y=frame_y, width=entry_width)

    def _update_autocomplete(self, suggestions):
        """Updates the listbox with suggestions and makes it visible."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        self.autocomplete_listbox.delete(0, tk.END)

        if not suggestions:
            self._hide_autocomplete_now()  # Hide immediately if no suggestions
            return

        for item in suggestions[:MAX_AUTOCOMPLETE_RESULTS]:
            self.autocomplete_listbox.insert(tk.END, item)

        height = min(len(suggestions), MAX_AUTOCOMPLETE_RESULTS, 5)
        self.autocomplete_listbox.config(height=height)

        # Ensure it's visible and positioned correctly
        if not self.autocomplete_frame.winfo_ismapped():
            self._position_autocomplete_listbox()
            self.autocomplete_frame.lift()
        else:
            # If already visible, just lift it in case other widgets overlapped
            self.autocomplete_frame.lift()

    def _hide_autocomplete(self, delay=0):
        """Hides the autocomplete listbox, optionally after a delay."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        if delay > 0:
            self._after_id_hide_listbox = self.master.after(
                delay, self._hide_autocomplete_now
            )
        else:
            self._hide_autocomplete_now()

    def _hide_autocomplete_now(self):
        """Immediately hides the autocomplete listbox."""
        if self.autocomplete_frame.winfo_ismapped():
            self.autocomplete_frame.place_forget()
        self.autocomplete_listbox.config(height=0)
        self.autocomplete_listbox.selection_clear(0, tk.END)
        self._after_id_hide_listbox = None

    def _hide_autocomplete_if_visible(self):
        """Hides the autocomplete only if it's currently placed/visible."""
        if self.autocomplete_frame.winfo_ismapped():
            self._hide_autocomplete()

    def _on_username_focus_in(self, event):
        """Shows recent history or current matches when username entry gains focus."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        current_val = self.username_var.get().lower().strip()
        if not current_val:
            recent = self.username_history[:MAX_RECENT_HISTORY]
            self._update_autocomplete(recent)
        else:
            self._filter_and_update_autocomplete(current_val)

    def _on_username_focus_out(self, event):
        """Hides the listbox when focus leaves the entry, with a delay."""
        self.master.after(10, self._check_focus_and_hide)

    def _check_focus_and_hide(self):
        """Check if focus went to listbox, otherwise schedule hide."""
        focused_widget = self.master.focus_get()
        # Don't hide if focus is moving to the listbox itself
        if focused_widget != self.autocomplete_listbox:
            self._hide_autocomplete(delay=150)

    def _on_username_key_release(self, event):
        """Filters history based on typed text and updates listbox."""
        if event and event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return

        search_term = self.username_var.get().lower().strip()
        self._filter_and_update_autocomplete(search_term)

    def _filter_and_update_autocomplete(self, search_term):
        """Helper to filter history and update the listbox."""
        if not search_term:
            recent = self.username_history[:MAX_RECENT_HISTORY]
            self._update_autocomplete(recent)
            return

        matches = [
            uname
            for uname in self.username_history
            if uname.lower().startswith(search_term)
        ]
        self._update_autocomplete(matches)

    def _on_listbox_select(self, event):
        """Sets the username entry text to the selected listbox item and hides listbox."""
        widget = self.autocomplete_listbox
        selection_indices = widget.curselection()
        if selection_indices:
            selected_index = selection_indices[0]
            selected_username = widget.get(selected_index)
            self.username_var.set(selected_username)
            self._hide_autocomplete_now()  # Hide immediately on selection
            self.username_entry.icursor(tk.END)
            self.username_entry.focus_set()
            return "break"

    def _move_selection_down(self, event):
        """Moves selection down in the listbox or focuses listbox from entry."""
        if not self.autocomplete_frame.winfo_ismapped():
            return

        if self.master.focus_get() == self.username_entry:
            if self.autocomplete_listbox.size() > 0:
                self.autocomplete_listbox.focus_set()
                self.autocomplete_listbox.selection_clear(0, tk.END)
                self.autocomplete_listbox.selection_set(0)
                self.autocomplete_listbox.activate(0)
                self.autocomplete_listbox.see(0)
                return "break"
        elif self.master.focus_get() == self.autocomplete_listbox:
            current_selection = self.autocomplete_listbox.curselection()
            next_index = 0
            if current_selection:
                next_index = current_selection[0] + 1

            if next_index < self.autocomplete_listbox.size():
                self.autocomplete_listbox.selection_clear(0, tk.END)
                self.autocomplete_listbox.selection_set(next_index)
                self.autocomplete_listbox.activate(next_index)
                self.autocomplete_listbox.see(next_index)
            return "break"

    def _move_selection_up(self, event):
        """Moves selection up in the listbox or returns focus to entry."""
        if not self.autocomplete_frame.winfo_ismapped():
            return

        if self.master.focus_get() == self.autocomplete_listbox:
            current_selection = self.autocomplete_listbox.curselection()
            next_index = -1
            if current_selection:
                next_index = current_selection[0] - 1

            if next_index >= 0:
                self.autocomplete_listbox.selection_clear(0, tk.END)
                self.autocomplete_listbox.selection_set(next_index)
                self.autocomplete_listbox.activate(next_index)
                self.autocomplete_listbox.see(next_index)
            else:
                self.username_entry.focus_set()
                self.autocomplete_listbox.selection_clear(0, tk.END)
            return "break"

    def browse_directory(self):
        """Opens a dialog to choose the output directory."""
        initial_dir = self.output_dir_var.get()
        if not os.path.isdir(initial_dir):
            initial_dir = DEFAULT_OUTPUT_DIRECTORY

        directory = filedialog.askdirectory(
            initialdir=initial_dir, title="Select Output Directory"
        )
        if directory:
            self.output_dir_var.set(directory)

    def update_status(self, message, is_error=False, tag=None):
        """Safely updates the status text area from any thread."""
        if tag is None:
            if is_error:
                tag = "error"
            elif "downloading:" in message.lower():
                tag = "download"
            elif "progress:" in message.lower():
                tag = "progress"
            elif (
                "downloaded:" in message.lower()
                or "successfully downloaded" in message.lower()
            ):
                tag = "success"
            elif (
                "yt-dlp failed" in message.lower()
                or "warning:" in message.lower()
                or "timed out" in message.lower()
                or "channel not found" in message.lower()
                or "no clips found" in message.lower()
                or "failed to download" in message.lower()
                or "limit reached" in message.lower()
            ):  # Added limit reached
                tag = "warning"
            else:
                tag = "info"

        self.master.after(0, self._update_status_text, message, tag)

    def _update_status_text(self, message, tag):
        """Internal method to update the text area (runs in GUI thread)."""
        try:
            self.status_text.config(state=tk.NORMAL)
            self.status_text.insert(tk.END, f"{message}\n", tag)
            self.status_text.config(state=tk.DISABLED)
            self.status_text.see(tk.END)
        except tk.TclError as e:
            print(f"TclError updating status text: {e}")

    def set_ui_state(self, enabled):
        """Enables or disables UI elements during processing."""
        state = tk.NORMAL if enabled else tk.DISABLED
        entry_state = "normal" if enabled else "disabled"
        spinbox_state = (
            "normal" if enabled else "disabled"
        )  # Spinbox uses normal/disabled too

        self.username_entry.config(state=entry_state)
        self.dir_entry.config(state=entry_state)
        self.max_downloads_spinbox.config(state=spinbox_state)  # Disable/enable spinbox
        self.browse_button.config(state=state)
        self.today_button.config(state=state)
        self.yesterday_button.config(state=state)

        self.is_processing = not enabled
        self.master.config(cursor="wait" if not enabled else "")

    def _persist_username(self, username):
        """Adds username to history, saves it, and logs status (runs in GUI thread)."""
        if not username:
            return
        self.username_history = add_username_to_history(username, self.username_history)
        save_username_history(self.username_history)
        self.update_status(f"Saved '{username}' to recent history.", tag="info")

    def _start_processing_event(self, days_offset):
        """Wrapper for start_processing called by keybindings (like Enter)."""
        if self.master.focus_get() == self.autocomplete_listbox:
            self._on_listbox_select(None)
            return "break"

        self.start_processing(days_offset)
        return "break"

    def start_processing(self, days_offset):
        """Handles button clicks or Enter key to start the fetching process."""
        if self.is_processing:
            messagebox.showwarning("Busy", "A process is already running. Please wait.")
            return

        # --- Input Validation ---
        username = self.username_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        try:
            # Get max_downloads, handle potential empty string from Spinbox validation
            max_downloads_str = self.max_downloads_var.get()
            max_downloads = (
                int(max_downloads_str)
                if isinstance(max_downloads_str, int) or max_downloads_str
                else 0
            )  # Default to 0 if empty
            if max_downloads < 0:  # Ensure non-negative
                messagebox.showerror(
                    "Input Error",
                    "Maximum downloads must be a non-negative number (0 for unlimited).",
                )
                self.max_downloads_spinbox.focus_set()
                return
        except ValueError:
            # This case might happen if validation fails or Spinbox somehow gets non-integer string
            messagebox.showerror(
                "Input Error",
                "Invalid input for Maximum downloads. Please enter a number (0 for unlimited).",
            )
            self.max_downloads_spinbox.focus_set()
            return

        if not username:
            messagebox.showerror("Input Error", "Please enter a Twitch username.")
            self.username_entry.focus_set()
            return

        if not output_dir:
            messagebox.showerror("Input Error", "Please specify an output directory.")
            self.dir_entry.focus_set()
            return

        # --- Directory Validation/Creation ---
        if not os.path.isdir(output_dir):
            if messagebox.askyesno(
                "Directory Not Found",
                f"The directory '{output_dir}' does not exist.\nDo you want to create it?",
            ):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    self.update_status(
                        f"Created directory: {output_dir}", tag="success"
                    )
                except OSError as e:
                    messagebox.showerror(
                        "Directory Error",
                        f"Failed to create directory '{output_dir}':\n{e}",
                    )
                    self.dir_entry.focus_set()
                    return
            else:
                messagebox.showwarning(
                    "Directory Error",
                    "Output directory does not exist. Please choose a valid directory.",
                )
                self.dir_entry.focus_set()
                return

        # --- Prepare UI for Processing ---
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.set_ui_state(False)
        self._hide_autocomplete_now()

        # --- Log Initial Status ---
        self.update_status("Process initiated...", tag="info")
        date_str = get_formatted_date(days_offset)
        day_desc = "today" if days_offset == 0 else "yesterday"
        limit_str = f" (limit: {max_downloads})" if max_downloads > 0 else " (no limit)"
        self.update_status(
            f"Fetching clips for '{username}' from {day_desc} ({date_str}){limit_str}",
            tag="info",
        )

        # --- Start Processing Thread ---
        process_thread = threading.Thread(
            target=self.run_process_thread,
            args=(
                username,
                date_str,
                output_dir,
                max_downloads,
                self._persist_username,
            ),  # Pass max_downloads
            daemon=True,
        )
        process_thread.start()

    def run_process_thread(
        self, username, date_str, output_dir, max_downloads, history_persist_callback
    ):  # Added max_downloads
        """Wrapper function that runs in the background thread."""
        history_saved_flag = False

        def history_callback_wrapper_for_thread(uname):
            nonlocal history_saved_flag
            if not history_saved_flag:
                self.master.after(0, history_persist_callback, uname)
                history_saved_flag = True

        try:
            process_request(
                username,
                date_str,
                output_dir,
                max_downloads,  # Pass max_downloads down
                self.update_status,
                history_callback_wrapper_for_thread,
            )
        except Exception as e:
            self.update_status(
                f"An unexpected critical error occurred in the processing thread: {e}",
                is_error=True,
            )
            import traceback

            self.update_status(f"Traceback:\n{traceback.format_exc()}", is_error=True)

        finally:
            self.master.after(0, self.set_ui_state, True)
            self.master.after(
                100,
                lambda: messagebox.showinfo(
                    "Complete", "Clip processing finished. Check the log for details."
                ),
            )

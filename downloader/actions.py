import tkinter as tk
from tkinter import messagebox, filedialog
import os
import threading
import traceback  # Import traceback for detailed error logging

# Import necessary functions/constants from other project modules
from constants import DEFAULT_OUTPUT_DIRECTORY, COLOR_TAGS
from utils import get_formatted_date
from processing import process_request
from history import save_username_history, add_username_to_history


class ActionHandler:
    """Handles user actions, status updates, and process execution."""

    def __init__(
        self, master, app_widgets, app_vars, autocomplete_handler, username_history_ref
    ):
        """
        Initializes the action handler.

        Args:
            master: The main tk.Tk root window.
            app_widgets: Dictionary containing key GUI widgets.
                         Expected keys: 'username_entry', 'dir_entry', 'max_downloads_spinbox',
                                        'browse_button', 'today_button', 'yesterday_button',
                                        'status_text'.
            app_vars: Dictionary containing necessary tk variables.
                      Expected keys: 'username_var', 'output_dir_var', 'max_downloads_var'.
            autocomplete_handler: Instance of AutocompleteHandler.
            username_history_ref: Direct reference to the list holding username history.
                                  NOTE: This handler will MODIFY this list via _persist_username.
        """
        self.master = master
        self.widgets = app_widgets
        self.vars = app_vars
        self.autocomplete = autocomplete_handler
        self.username_history = (
            username_history_ref  # Keep a direct reference to modify
        )

        # Internal state
        self.is_processing = False

    # --- Public Methods / Callbacks ---

    def browse_directory(self):
        """Opens a dialog to choose the output directory."""
        initial_dir = self.vars["output_dir_var"].get()
        if not os.path.isdir(initial_dir):
            initial_dir = DEFAULT_OUTPUT_DIRECTORY

        directory = filedialog.askdirectory(
            initialdir=initial_dir, title="Select Output Directory"
        )
        if directory:
            self.vars["output_dir_var"].set(directory)

    def update_status(self, message, is_error=False, tag=None):
        """Safely schedules status text updates on the main GUI thread."""
        if tag is None:
            tag = self._determine_tag(message, is_error)
        # Schedule the actual text update via master.after
        self.master.after(0, self._update_status_text_area, message, tag)

    def set_ui_state(self, enabled):
        """Enables or disables UI elements based on processing state."""
        state = tk.NORMAL if enabled else tk.DISABLED
        entry_state = "normal" if enabled else "disabled"
        spinbox_state = "normal" if enabled else "disabled"

        self.widgets["username_entry"].config(state=entry_state)
        self.widgets["dir_entry"].config(state=entry_state)
        self.widgets["max_downloads_spinbox"].config(state=spinbox_state)
        self.widgets["browse_button"].config(state=state)
        self.widgets["today_button"].config(state=state)
        self.widgets["yesterday_button"].config(state=state)

        self.is_processing = not enabled
        self.master.config(cursor="wait" if not enabled else "")

    def start_processing_event_handler(self, days_offset):
        """Wrapper for start_processing called by keybindings (like Enter)."""
        # Prevent processing if Enter was pressed in the autocomplete listbox
        if self.master.focus_get() == self.widgets["autocomplete_listbox"]:
            # Let the autocomplete handler manage the selection/hiding
            return "break"  # Stop event propagation

        self.start_processing(days_offset)
        return "break"

    def start_processing(self, days_offset):
        """Initiates the clip fetching and downloading process."""
        if self.is_processing:
            messagebox.showwarning("Busy", "A process is already running. Please wait.")
            return

        # --- Validate Inputs ---
        username = self.vars["username_var"].get().strip()
        output_dir = self.vars["output_dir_var"].get().strip()
        max_downloads = self._validate_max_downloads()

        if max_downloads is None:
            return  # Validation failed
        if not self._validate_username(username):
            return
        if not self._validate_output_dir(output_dir):
            return

        # --- Prepare UI ---
        self._clear_status_log()
        self.set_ui_state(False)
        self.autocomplete.hide_now()

        # --- Log Initial Status ---
        self.update_status("Process initiated...", tag="info")
        date_str = get_formatted_date(days_offset)
        day_desc = "today" if days_offset == 0 else "yesterday"
        limit_str = f" (limit: {max_downloads})" if max_downloads > 0 else " (no limit)"
        self.update_status(
            f"Fetching clips for '{username}' from {day_desc} ({date_str}){limit_str}",
            tag="info",
        )

        # --- Start Background Thread ---
        process_thread = threading.Thread(
            target=self._run_processing_in_thread,
            args=(
                username,
                date_str,
                output_dir,
                max_downloads,
                self._persist_username,
            ),
            daemon=True,
        )
        process_thread.start()

    def validate_non_negative_int(self, P):
        """Validation command for Spinbox."""
        if P == "":
            return True
        try:
            val = int(P)
            return val >= 0
        except ValueError:
            return False

    # --- Internal Helper Methods ---

    def _validate_max_downloads(self):
        """Validates the max downloads input."""
        try:
            max_downloads_str = self.vars["max_downloads_var"].get()
            # Handle potential Tkinter variable type (int) or string from get()
            max_downloads = (
                int(max_downloads_str)
                if isinstance(max_downloads_str, int) or max_downloads_str
                else 0
            )
            if max_downloads < 0:
                messagebox.showerror(
                    "Input Error", "Max downloads must be >= 0 (0 for unlimited)."
                )
                self.widgets["max_downloads_spinbox"].focus_set()
                return None
            return max_downloads
        except (
            ValueError,
            tk.TclError,
        ):  # Catch TclError if variable holds invalid value
            messagebox.showerror(
                "Input Error", "Invalid max downloads value. Please enter a number."
            )
            self.widgets["max_downloads_spinbox"].focus_set()
            return None

    def _validate_username(self, username):
        """Validates the username input."""
        if not username:
            messagebox.showerror("Input Error", "Please enter a Twitch username.")
            self.widgets["username_entry"].focus_set()
            return False
        return True

    def _validate_output_dir(self, output_dir):
        """Validates the output directory input and offers to create it."""
        if not output_dir:
            messagebox.showerror("Input Error", "Please specify an output directory.")
            self.widgets["dir_entry"].focus_set()
            return False

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
                    return True  # Directory created successfully
                except OSError as e:
                    messagebox.showerror(
                        "Directory Error", f"Failed to create directory:\n{e}"
                    )
                    self.widgets["dir_entry"].focus_set()
                    return False  # Failed to create
            else:
                messagebox.showwarning(
                    "Directory Error", "Output directory does not exist."
                )
                self.widgets["dir_entry"].focus_set()
                return False  # User chose not to create
        return True  # Directory exists

    def _determine_tag(self, message, is_error):
        """Determines the appropriate tag for a status message."""
        msg_lower = message.lower()
        if is_error:
            return "error"
        if "downloading:" in msg_lower:
            return "download"
        if "progress:" in msg_lower:
            return "progress"
        if "downloaded:" in msg_lower or "successfully downloaded" in msg_lower:
            return "success"
        if (
            "failed" in msg_lower
            or "warning:" in msg_lower
            or "timed out" in msg_lower
            or "not found" in msg_lower
            or "no clips" in msg_lower
            or "limit reached" in msg_lower
        ):
            return "warning"
        return "info"

    def _clear_status_log(self):
        """Clears the status text area."""
        try:
            self.widgets["status_text"].config(state=tk.NORMAL)
            self.widgets["status_text"].delete("1.0", tk.END)
            self.widgets["status_text"].config(state=tk.DISABLED)
        except tk.TclError as e:
            print(f"TclError clearing status text: {e}")

    def _update_status_text_area(self, message, tag):
        """Internal method to update the text area (runs in GUI thread)."""
        try:
            status_widget = self.widgets["status_text"]
            status_widget.config(state=tk.NORMAL)
            status_widget.insert(tk.END, f"{message}\n", tag)
            status_widget.config(state=tk.DISABLED)
            status_widget.see(tk.END)  # Auto-scroll
        except tk.TclError as e:
            print(f"TclError updating status text: {e}")

    def _persist_username(self, username):
        """Adds username to history, saves it, and updates status (runs in GUI thread)."""
        if not username:
            return
        # Directly modify the list obtained from the main app
        original_history = list(self.username_history)  # Keep original if update fails
        try:
            updated_history = add_username_to_history(username, self.username_history)
            # Update the list in-place so the main app and autocomplete see the change
            self.username_history[:] = updated_history
            save_username_history(self.username_history)
            self.update_status(f"Saved '{username}' to recent history.", tag="info")
            # Inform autocomplete handler about the change
            self.autocomplete.update_history_reference(self.username_history)
        except Exception as e:
            print(f"Error persisting username '{username}': {e}")
            self.update_status(f"Error saving '{username}' to history.", is_error=True)
            self.username_history[:] = original_history  # Revert on error
            # Optionally re-sync autocomplete handler if needed
            # self.autocomplete.update_history_reference(self.username_history)

    def _run_processing_in_thread(
        self,
        username,
        date_str,
        output_dir,
        max_downloads,
        history_persist_callback_gui,
    ):
        """Wrapper function that runs the core processing logic in a background thread."""
        history_saved_flag = False

        # Wrap the GUI-based history persistence to run via master.after
        def history_callback_for_thread(uname):
            nonlocal history_saved_flag
            if not history_saved_flag:
                # Schedule the _persist_username call (which is GUI-thread safe)
                self.master.after(0, history_persist_callback_gui, uname)
                history_saved_flag = True

        try:
            # Call the actual processing function
            process_request(
                username,
                date_str,
                output_dir,
                max_downloads,
                self.update_status,  # Pass the safe update_status method
                history_callback_for_thread,
            )
        except Exception as e:
            # Log unexpected errors from the processing logic itself
            self.update_status(
                f"Critical error during processing thread: {e}", is_error=True
            )
            self.update_status(f"Traceback:\n{traceback.format_exc()}", is_error=True)
        finally:
            # --- Always re-enable UI and show completion ---
            self.master.after(0, self.set_ui_state, True)  # Schedule UI re-enable
            self.master.after(
                100,  # Short delay
                lambda: messagebox.showinfo(
                    "Complete", "Processing finished. Check log for details."
                ),
            )

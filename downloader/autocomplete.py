import tkinter as tk
from constants import MAX_RECENT_HISTORY, MAX_AUTOCOMPLETE_RESULTS


class AutocompleteHandler:
    """Manages the username autocomplete listbox behavior."""

    def __init__(self, master, app_widgets, app_vars, username_history):
        """
        Initializes the autocomplete handler.

        Args:
            master: The main tk.Tk root window.
            app_widgets: Dictionary containing key GUI widgets.
                         Expected keys: 'username_entry', 'autocomplete_frame', 'autocomplete_listbox'.
            app_vars: Dictionary containing necessary tk variables.
                      Expected keys: 'username_var'.
            username_history: The list containing username history.
        """
        self.master = master
        self.username_entry = app_widgets["username_entry"]
        self.autocomplete_frame = app_widgets["autocomplete_frame"]
        self.autocomplete_listbox = app_widgets["autocomplete_listbox"]
        self.username_var = app_vars["username_var"]
        self.username_history = (
            username_history  # Reference, assume main app updates it
        )

        self._after_id_hide_listbox = None

        self._bind_events()

        # Initial positioning after a short delay
        self.master.after(50, self._position_autocomplete_listbox)

    def _bind_events(self):
        """Binds necessary events to the username entry and listbox."""
        self.username_entry.bind("<FocusIn>", self._on_username_focus_in)
        self.username_entry.bind("<FocusOut>", self._on_username_focus_out)
        self.username_entry.bind("<KeyRelease>", self._on_username_key_release)
        self.username_entry.bind("<Down>", self._move_selection_down)
        self.username_entry.bind("<Up>", self._move_selection_up)

        self.autocomplete_listbox.bind("<ButtonRelease-1>", self._on_listbox_select)
        self.autocomplete_listbox.bind("<Return>", self._on_listbox_select)
        self.autocomplete_listbox.bind(
            "<Escape>", lambda e: self.hide_now()
        )  # Use public hide_now

        # Global escape binding handled in app.py as it's master-level

    # --- Public Methods ---

    def hide_now(self):
        """Immediately hides the autocomplete listbox."""
        if self.autocomplete_frame.winfo_ismapped():
            self.autocomplete_frame.place_forget()
        self.autocomplete_listbox.config(height=0)
        self.autocomplete_listbox.selection_clear(0, tk.END)
        if self._after_id_hide_listbox:  # Clear any pending hide timer
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

    def hide_if_visible(self):
        """Hides the autocomplete only if it's currently placed/visible."""
        if self.autocomplete_frame.winfo_ismapped():
            self._hide_autocomplete()  # Can use internal hide with delay logic if preferred

    def update_history_reference(self, new_history):
        """Updates the local reference to the username history list."""
        self.username_history = new_history

    # --- Internal Methods / Event Handlers ---

    def _position_autocomplete_listbox(self):
        """Places the autocomplete listbox directly below the username entry."""
        self.master.update_idletasks()
        if not self.username_entry.winfo_exists():
            return

        entry_x = self.username_entry.winfo_x()
        entry_y = self.username_entry.winfo_y()
        entry_height = self.username_entry.winfo_height()
        entry_width = self.username_entry.winfo_width()

        # Calculate position relative to the main_frame (parent of options_frame which contains entry)
        frame_x = self.username_entry.master.winfo_x() + entry_x
        frame_y = self.username_entry.master.winfo_y() + entry_y + entry_height + 1

        self.autocomplete_frame.place(x=frame_x, y=frame_y, width=entry_width)

    def _update_autocomplete_display(self, suggestions):
        """Updates the listbox with suggestions and makes it visible."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        self.autocomplete_listbox.delete(0, tk.END)

        if not suggestions:
            self.hide_now()
            return

        for item in suggestions[:MAX_AUTOCOMPLETE_RESULTS]:
            self.autocomplete_listbox.insert(tk.END, item)

        height = min(len(suggestions), MAX_AUTOCOMPLETE_RESULTS, 5)
        self.autocomplete_listbox.config(height=height)

        if not self.autocomplete_frame.winfo_ismapped():
            self._position_autocomplete_listbox()
        self.autocomplete_frame.lift()

    def _hide_autocomplete(self, delay=0):
        """Schedules the hiding of the autocomplete listbox."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        if delay > 0:
            self._after_id_hide_listbox = self.master.after(delay, self.hide_now)
        else:
            self.hide_now()

    def _on_username_focus_in(self, event):
        """Shows suggestions when username entry gains focus."""
        if self._after_id_hide_listbox:
            self.master.after_cancel(self._after_id_hide_listbox)
            self._after_id_hide_listbox = None

        current_val = self.username_var.get().lower().strip()
        if not current_val:
            recent = self.username_history[:MAX_RECENT_HISTORY]
            self._update_autocomplete_display(recent)
        else:
            self._filter_and_update(current_val)

    def _on_username_focus_out(self, event):
        """Hides the listbox with a delay when focus leaves the entry."""
        # Use 'after' to allow clicking on the listbox
        self.master.after(10, self._check_focus_and_hide)

    def _check_focus_and_hide(self):
        """Check if focus went to listbox, otherwise schedule hide."""
        focused_widget = self.master.focus_get()
        if focused_widget != self.autocomplete_listbox:
            self._hide_autocomplete(delay=150)

    def _on_username_key_release(self, event):
        """Filters history based on typed text."""
        if event and event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        search_term = self.username_var.get().lower().strip()
        self._filter_and_update(search_term)

    def _filter_and_update(self, search_term):
        """Filters history and updates the listbox."""
        if not search_term:
            recent = self.username_history[:MAX_RECENT_HISTORY]
            self._update_autocomplete_display(recent)
            return

        matches = [
            uname
            for uname in self.username_history
            if uname.lower().startswith(search_term)
        ]
        self._update_autocomplete_display(matches)

    def _on_listbox_select(self, event):
        """Handles selection from the autocomplete listbox."""
        widget = self.autocomplete_listbox
        selection_indices = widget.curselection()
        if selection_indices:
            selected_index = selection_indices[0]
            selected_username = widget.get(selected_index)
            self.username_var.set(selected_username)
            self.hide_now()  # Hide immediately on selection
            self.username_entry.icursor(tk.END)
            self.username_entry.focus_set()
            return "break"  # Prevent further event processing

    def _move_selection_down(self, event):
        """Handles Down arrow key for navigation."""
        if not self.autocomplete_frame.winfo_ismapped():
            return

        listbox = self.autocomplete_listbox
        if self.master.focus_get() == self.username_entry:
            if listbox.size() > 0:
                listbox.focus_set()
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(0)
                listbox.activate(0)
                listbox.see(0)
                return "break"
        elif self.master.focus_get() == listbox:
            current_selection = listbox.curselection()
            next_index = 0
            if current_selection:
                next_index = current_selection[0] + 1
            if next_index < listbox.size():
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(next_index)
                listbox.activate(next_index)
                listbox.see(next_index)
            return "break"

    def _move_selection_up(self, event):
        """Handles Up arrow key for navigation."""
        if not self.autocomplete_frame.winfo_ismapped():
            return

        listbox = self.autocomplete_listbox
        if self.master.focus_get() == listbox:
            current_selection = listbox.curselection()
            next_index = -1
            if current_selection:
                next_index = current_selection[0] - 1
            if next_index >= 0:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(next_index)
                listbox.activate(next_index)
                listbox.see(next_index)
            else:
                self.username_entry.focus_set()
                listbox.selection_clear(0, tk.END)
            return "break"

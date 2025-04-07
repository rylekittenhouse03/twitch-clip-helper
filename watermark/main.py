import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import json
import os
import threading
import queue
from moviepy import VideoFileClip, TextClip, CompositeVideoClip
import moviepy.config as mpy_config
import shutil
import matplotlib.font_manager as fm # Use matplotlib for better font finding

# --- Constants ---
SETTINGS_FILE = "watermarker_settings.json"
DEFAULT_SETTINGS = {
    "input_file": "",
    "output_file": "",
    "watermark_text": "Watermark",
    "font_family": "Arial", # Default to a very common font
    "font_size": 24,
    "opacity": 0.7,
    "position": "bottom-right",
}
POSITIONS = {
    "top-left": ("left", "top"),
    "top-center": ("center", "top"),
    "top-right": ("right", "top"),
    "center-left": ("left", "center"),
    "center": ("center", "center"),
    "center-right": ("right", "center"),
    "bottom-left": ("left", "bottom"),
    "bottom-center": ("center", "bottom"),
    "bottom-right": ("right", "bottom"),
}
POSITION_NAMES = list(POSITIONS.keys())

# --- Settings Management ---
def load_settings():
    """Loads settings from the JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                for key, default_value in DEFAULT_SETTINGS.items():
                    settings.setdefault(key, default_value)
                return settings
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading settings: {e}. Using defaults.")
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Saves settings to the JSON file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        print(f"Error saving settings: {e}")

# --- Font Helper ---
def get_system_fonts():
    """Uses matplotlib.font_manager to get a list of available font names."""
    try:
        # Rebuild font list cache if needed, can take a moment on first run
        # fm._rebuild() # Uncomment cautiously, can be slow
        font_list = sorted(list(set(f.name for f in fm.fontManager.ttflist)))
        # Alternative: Get font file paths directly if needed
        # font_files = fm.findSystemFonts(fontpaths=None, fontext='ttf')
        # font_list = sorted([os.path.splitext(os.path.basename(f))[0] for f in font_files])
        return font_list
    except Exception as e:
        print(f"Error using matplotlib.font_manager: {e}")
        # Fallback to tkinter's font.families() which might be less reliable for Pillow/MoviePy
        try:
            tk_fonts = sorted(list(font.families()))
            return tk_fonts
        except Exception as e_tk:
             print(f"Error using tkinter font.families: {e_tk}")
             return ["Arial", "Times New Roman", "Courier New"] # Absolute fallback


def find_font_path(font_name):
    """Attempts to find the file path for a given font name using matplotlib."""
    try:
        # Try finding font using default FontProperties
        font_prop = fm.FontProperties(family=font_name)
        font_path = fm.findfont(font_prop, fallback_to_default=False)
        if font_path:
            return font_path
    except Exception as e:
         print(f"matplotlib could not find font '{font_name}': {e}")

    # Fallback: Try simple findfont (might work for paths/filenames)
    try:
        font_path = fm.findfont(font_name, fallback_to_default=False)
        if font_path:
            return font_path
    except Exception:
        pass # Ignore error here, will try name directly later

    # Last resort: Check common Windows font dir directly for TTF/OTF if on Windows
    if os.name == 'nt':
        font_dir = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts')
        try:
            potential_files = [
                os.path.join(font_dir, f)
                for f in os.listdir(font_dir)
                if f.lower().endswith(('.ttf', '.otf')) and font_name.lower() in f.lower()
            ]
            if potential_files:
                 # Very basic match, prefer shorter names or exact matches if possible
                 potential_files.sort(key=len)
                 # Check for exact filename match first (e.g., "arial.ttf")
                 for pfile in potential_files:
                      fname_noext = os.path.splitext(os.path.basename(pfile))[0]
                      if fname_noext.lower() == font_name.lower():
                           print(f"Found potential match via direct scan: {pfile}")
                           return pfile
                 # Otherwise return shortest name containing the family name
                 print(f"Found potential match via direct scan: {potential_files[0]}")
                 return potential_files[0]
        except FileNotFoundError:
             pass # Font directory not found
        except Exception as e:
            print(f"Error scanning Windows font directory: {e}")


    print(f"Could not find font file for '{font_name}'. Will attempt to use name directly.")
    return font_name # Return the name itself as a last resort

# --- GUI Application ---
class WatermarkApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("Video Watermarker")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = load_settings()

        self.input_file_var = tk.StringVar(value=self.settings.get("input_file", ""))
        self.output_file_var = tk.StringVar(value=self.settings.get("output_file", ""))
        self.watermark_text_var = tk.StringVar(value=self.settings.get("watermark_text", "Watermark"))
        self.font_family_var = tk.StringVar(value=self.settings.get("font_family", "Arial"))
        self.font_size_var = tk.IntVar(value=self.settings.get("font_size", 24))
        self.opacity_var = tk.DoubleVar(value=self.settings.get("opacity", 0.7))
        self.position_var = tk.StringVar(value=self.settings.get("position", "bottom-right"))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Ready (Initializing font list...)") # Initial status

        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.create_file_widgets()
        self.create_watermark_widgets()
        self.create_control_widgets()
        self.create_status_widgets()

        # --- Font List ---
        # Populate font list in background to avoid GUI freeze if slow
        self.root.after(100, self.update_font_list_async)


        self.progress_queue = queue.Queue()

    def create_file_widgets(self):
        """Creates widgets for input/output file selection."""
        frame = ttk.LabelFrame(self.main_frame, text="Files", padding="10")
        frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Input Video:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(frame, textvariable=self.input_file_var, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Button(frame, text="Browse...", command=self.select_input_file).grid(row=0, column=2, sticky=tk.E, padx=5, pady=2)

        ttk.Label(frame, text="Output Video:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(frame, textvariable=self.output_file_var, width=50).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Button(frame, text="Browse...", command=self.select_output_file).grid(row=1, column=2, sticky=tk.E, padx=5, pady=2)

    def create_watermark_widgets(self):
        """Creates widgets for watermark text, font, size, opacity, position."""
        frame = ttk.LabelFrame(self.main_frame, text="Watermark Settings", padding="10")
        frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Text:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(frame, textvariable=self.watermark_text_var, width=40).grid(row=0, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=5, pady=2)

        ttk.Label(frame, text="Font:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.font_combobox = ttk.Combobox(frame, textvariable=self.font_family_var, width=37, state="readonly")
        self.font_combobox.grid(row=1, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.font_combobox['values'] = ["Loading fonts..."] # Placeholder

        ttk.Label(frame, text="Size:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Spinbox(frame, from_=8, to=144, textvariable=self.font_size_var, width=5).grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(frame, text="Opacity (0.0-1.0):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.opacity_scale = ttk.Scale(frame, from_=0.0, to=1.0, variable=self.opacity_var, orient=tk.HORIZONTAL, length=150, command=self.update_opacity_label)
        self.opacity_scale.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.opacity_label = ttk.Label(frame, text=f"{self.opacity_var.get():.2f}")
        self.opacity_label.grid(row=3, column=3, sticky=tk.W, padx=5, pady=2)
        self.update_opacity_label(self.opacity_var.get())

        ttk.Label(frame, text="Position:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        position_combobox = ttk.Combobox(frame, textvariable=self.position_var, values=POSITION_NAMES, state="readonly", width=15)
        position_combobox.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        if self.position_var.get() not in POSITION_NAMES:
             self.position_var.set("bottom-right")


    def create_control_widgets(self):
        """Creates the apply button."""
        frame = ttk.Frame(self.main_frame, padding="10")
        frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        self.apply_button = ttk.Button(frame, text="Apply Watermark", command=self.start_processing, width=20)
        self.apply_button.pack(expand=True)

    def create_status_widgets(self):
        """Creates the progress bar and status label."""
        frame = ttk.Frame(self.main_frame, padding="5")
        frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5)

        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var, maximum=100, mode='determinate', length=300)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

    # --- Callbacks and Actions ---

    def select_input_file(self):
        """Opens a dialog to select the input video file."""
        file_path = filedialog.askopenfilename(
            title="Select Input Video",
            filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv"), ("All Files", "*.*")]
        )
        if file_path:
            self.input_file_var.set(file_path)
            base, ext = os.path.splitext(file_path)
            suggested_output = f"{base}_watermarked{ext}"
            current_output = self.output_file_var.get()
            if not current_output or current_output.endswith("_watermarked" + os.path.splitext(current_output)[1]):
                 self.output_file_var.set(suggested_output)

    def select_output_file(self):
        """Opens a dialog to select the output video file."""
        initial_file = os.path.basename(self.output_file_var.get())
        initial_dir = os.path.dirname(self.output_file_var.get())

        if not initial_file and self.input_file_var.get():
             base, ext = os.path.splitext(self.input_file_var.get())
             initial_file = f"{os.path.basename(base)}_watermarked{ext}"
             if not initial_dir:
                 initial_dir = os.path.dirname(self.input_file_var.get())
        elif not initial_file:
             initial_file = "output_watermarked.mp4"

        if not initial_dir:
             initial_dir = os.path.expanduser("~")

        file_path = filedialog.asksaveasfilename(
            title="Save Output Video As",
            initialfile=initial_file,
            initialdir=initial_dir,
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("AVI Video", "*.avi"), ("MOV Video", "*.mov"), ("MKV Video", "*.mkv"), ("All Files", "*.*")]
        )
        if file_path:
            self.output_file_var.set(file_path)

    def update_opacity_label(self, value):
        """Updates the label next to the opacity scale."""
        self.opacity_label.config(text=f"{float(value):.2f}")

    def update_font_list_async(self):
        """Gets system fonts in a thread and updates the combobox."""
        thread = threading.Thread(target=self._load_fonts_thread, daemon=True)
        thread.start()

    def _load_fonts_thread(self):
        """Worker thread function to load fonts."""
        try:
            available_fonts = get_system_fonts()
            # Schedule GUI update in the main thread
            self.root.after(0, self._update_font_combobox, available_fonts)
        except Exception as e:
            print(f"Failed to load fonts in background thread: {e}")
            self.root.after(0, self._update_font_combobox, ["Arial", "Times New Roman"]) # Fallback

    def _update_font_combobox(self, available_fonts):
        """Updates the font combobox in the main GUI thread."""
        try:
            if not available_fonts:
                 messagebox.showwarning("Font Warning", "Could not find any system fonts. Using basic fallback list.")
                 available_fonts = ["Arial", "Times New Roman", "Courier New"]
                 self.font_combobox['values'] = available_fonts
            else:
                self.font_combobox['values'] = available_fonts

            # Ensure the currently selected font is valid, else default
            current_font = self.font_family_var.get()
            if current_font not in available_fonts:
                # Try common defaults first
                common_defaults = ["Arial", "Calibri", "Times New Roman", "Verdana"]
                found_default = False
                for default in common_defaults:
                    if default in available_fonts:
                        self.font_family_var.set(default)
                        found_default = True
                        break
                if not found_default and available_fonts:
                    self.font_family_var.set(available_fonts[0]) # Fallback to first available
                elif not available_fonts:
                    self.font_family_var.set("")
            self.status_var.set("Ready") # Update status after fonts loaded
        except Exception as e:
            messagebox.showerror("Font Error", f"Could not populate font list: {e}")
            fallback_fonts = ["Arial", "Times New Roman", "Courier New"]
            self.font_combobox['values'] = fallback_fonts
            if self.font_family_var.get() not in fallback_fonts:
                 self.font_family_var.set("Arial")
            self.status_var.set("Ready (Font list error)")


    def get_current_settings(self):
        """Collects current settings from the GUI variables."""
        return {
            "input_file": self.input_file_var.get(),
            "output_file": self.output_file_var.get(),
            "watermark_text": self.watermark_text_var.get(),
            "font_family": self.font_family_var.get(),
            "font_size": self.font_size_var.get(),
            "opacity": self.opacity_var.get(),
            "position": self.position_var.get(),
        }

    def set_ui_state(self, enabled):
        """Enables or disables UI elements during processing."""
        state = tk.NORMAL if enabled else tk.DISABLED
        for child in self.main_frame.winfo_children():
            if isinstance(child, (ttk.Frame, ttk.LabelFrame)):
                 for grandchild in child.winfo_children():
                      widget_class = grandchild.winfo_class()
                      if widget_class not in ('TLabel', 'TSeparator'):
                            try: grandchild.configure(state=state)
                            except tk.TclError: pass
            else:
                 widget_class = child.winfo_class()
                 if widget_class not in ('TLabel', 'TSeparator'):
                      try: child.configure(state=state)
                      except tk.TclError: pass
        try: self.apply_button.configure(state=state)
        except tk.TclError: pass
        try: self.status_label.configure(state=tk.NORMAL)
        except tk.TclError: pass


    def start_processing(self):
        """Validates inputs and starts the watermarking process in a thread."""
        self.settings = self.get_current_settings()
        input_file = self.settings["input_file"]
        output_file = self.settings["output_file"]
        watermark_text = self.settings["watermark_text"]
        font_family = self.settings["font_family"]


        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("Error", "Please select a valid input video file.")
            return
        if not output_file:
            messagebox.showerror("Error", "Please select an output video file path.")
            return
        # Allow empty watermark text
        if not font_family or font_family == "Loading fonts...":
             messagebox.showerror("Error", "Please select a font (wait for list to load).")
             return

        if os.path.abspath(input_file) == os.path.abspath(output_file):
             messagebox.showerror("Error", "Output file cannot be the same as the input file.")
             return

        save_settings(self.settings)

        self.set_ui_state(enabled=False)
        self.status_var.set("Processing...")
        self.progress_var.set(0)

        self.processing_thread = threading.Thread(
            target=self.apply_watermark_thread,
            args=(self.settings.copy(),),
            daemon=True
        )
        self.processing_thread.start()

        self.root.after(100, self.check_progress_queue)


    def check_progress_queue(self):
        """Checks the queue for messages from the worker thread."""
        try:
            while True:
                message = self.progress_queue.get_nowait()
                if isinstance(message, tuple):
                    msg_type, value = message
                    if msg_type == "progress":
                        self.progress_var.set(value)
                        current_status = self.status_var.get()
                        if current_status.startswith(("Processing", "Writing", "Loading")):
                             self.status_var.set(f"Processing... {value:.1f}%")
                    elif msg_type == "status":
                        self.status_var.set(value)
                elif message == "done":
                    self.status_var.set("Completed successfully!")
                    self.progress_var.set(100)
                    self.set_ui_state(enabled=True)
                    messagebox.showinfo("Success", f"Video watermarking complete!\nOutput saved to:\n{self.output_file_var.get()}")
                    return
                elif message == "error":
                    if not self.status_var.get().startswith("Error"):
                         self.status_var.set("Error during processing. See message box.")
                    self.progress_var.set(0)
                    self.set_ui_state(enabled=True)
                    return
                else:
                    print(f"Unknown message in queue: {message}")

        except queue.Empty:
            if hasattr(self, 'processing_thread') and self.processing_thread.is_alive():
                self.root.after(100, self.check_progress_queue)
            else:
                current_status = self.status_var.get()
                if current_status.startswith(("Processing", "Writing", "Loading")):
                     self.status_var.set("Processing finished unexpectedly.")
                     self.set_ui_state(enabled=True)


    def apply_watermark_thread(self, settings):
        """The actual video processing function (runs in a separate thread)."""
        # --- MoviePy Logger for Progress ---
        class TqdmMock:
            def __init__(self, total, queue_instance, desc="Processing"):
                self.total = total if total else 1
                self.queue = queue_instance
                self.current = 0
                self.desc = desc

            def update(self, N):
                self.current += N
                progress_percent = min(100.0, (self.current / self.total) * 100.0) if self.total > 0 else 0
                self.queue.put(("progress", progress_percent))

            def close(self):
                 if self.total > 0:
                     self.queue.put(("progress", 100.0))
                 pass

        def custom_logger(prog_bar_type, current, total, desc="Processing video"):
             if not hasattr(custom_logger, 'mock_instance') or custom_logger.mock_instance is None:
                  if total and total > 0 :
                      custom_logger.mock_instance = TqdmMock(total, self.progress_queue, desc=desc)
                  else: return
             if hasattr(custom_logger, 'mock_instance') and custom_logger.mock_instance:
                  increment = current - custom_logger.mock_instance.current
                  if increment >= 0: # Handle potential non-monotonic updates
                       custom_logger.mock_instance.update(increment)

        custom_logger.mock_instance = None

        video_clip = None
        final_clip = None

        try:
            input_file = settings["input_file"]
            output_file = settings["output_file"]
            text = settings["watermark_text"]
            font_size = settings["font_size"]
            font_family_name = settings["font_family"] # Name selected by user
            opacity = settings["opacity"]
            position_key = settings["position"]
            position = POSITIONS[position_key]
            text_color = 'white'

            self.progress_queue.put(("status", "Finding font file..."))
            self.progress_queue.put(("progress", 0))

            # --- Find Font Path ---
            # Use the helper function to find the actual font file path
            font_path_or_name = find_font_path(font_family_name)
            print(f"Attempting to use font: {font_path_or_name}") # Log path/name being used

            self.progress_queue.put(("status", "Loading video..."))
            video_clip = VideoFileClip(input_file)
            video_duration = video_clip.duration or 1

            # --- Create Text Clip ---
            self.progress_queue.put(("status", "Creating watermark text..."))
            try:
                # Pass the found path (or name as fallback) to TextClip
                text_clip = TextClip(
                    txt=text,
                    fontsize=font_size,
                    font=font_path_or_name, # Crucial change: use path if found
                    color=text_color,
                    kerning=1
                )
            except ValueError as e:
                # Check if the error message indicates font loading failure
                err_str = str(e).lower()
                if "invalid font" in err_str and "pillow failed" in err_str:
                     # Re-raise with a clearer message for the user
                     raise ValueError(f"Failed to load font '{font_family_name}'. Pillow/FreeType could not open resource '{font_path_or_name}'. Try a different font or ensure it's installed correctly.") from e
                else:
                     raise # Re-raise other ValueErrors
            except OSError as e:
                 # Catch direct OS errors like "cannot open resource" if ValueError isn't raised first
                 err_str = str(e).lower()
                 if "cannot open resource" in err_str:
                      raise ValueError(f"Failed to load font '{font_family_name}'. System error opening resource '{font_path_or_name}'. Check font installation/permissions.") from e
                 else:
                      raise # Re-raise other OSErrors
            except Exception as e:
                 # Catch other potential errors during text creation
                 err_str = str(e).lower()
                 if 'unable to read font' in err_str or 'library not found' in err_str: # ImageMagick-like errors
                      raise FileNotFoundError(f"MoviePy backend could not find or use the font: '{font_path_or_name}'.") from e
                 else:
                      raise # Re-raise other exceptions


            text_clip = (text_clip
                         .set_opacity(opacity)
                         .set_position(position)
                         .set_duration(video_duration))

            final_clip = CompositeVideoClip([video_clip, text_clip])

            self.progress_queue.put(("status", "Writing output file..."))
            self.progress_queue.put(("progress", 0)) # Reset progress for writing phase

            final_clip.write_videofile(
                output_file,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=f'{output_file}.temp-audio.m4a',
                remove_temp=True,
                logger=custom_logger,
                threads=os.cpu_count() or 2
            )

            self.progress_queue.put("done")

        except (FileNotFoundError, ValueError) as e: # Catch font/file not found or value errors (like bad font)
             self.progress_queue.put("error")
             error_message = f"Error: {e}"
             self.root.after(0, lambda msg=error_message: messagebox.showerror("Error", msg))
        except (OSError, IOError) as e:
             self.progress_queue.put("error")
             error_message = f"File system error: {e}\nCheck permissions or if the file is in use."
             self.root.after(0, lambda msg=error_message: messagebox.showerror("File Error", msg))
        except Exception as e:
            self.progress_queue.put("error")
            import traceback
            tb_str = traceback.format_exc()
            error_message = f"An unexpected error occurred:\n\n{type(e).__name__}: {e}\n\nTraceback:\n{tb_str}"
            print(error_message)
            gui_error_message = f"Processing Error:\n{type(e).__name__}: {e}\n\n(Check console log for details)"
            self.root.after(0, lambda msg=gui_error_message: messagebox.showerror("Processing Error", msg))
        finally:
             # Ensure clips are closed
             if final_clip:
                  try: final_clip.close()
                  except Exception as e: print(f"Error closing final clip: {e}")
             elif video_clip:
                  try: video_clip.close()
                  except Exception as e: print(f"Error closing video clip: {e}")


    def on_close(self):
        """Saves settings before closing the application."""
        current_settings = self.get_current_settings()
        save_settings(current_settings)
        self.root.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    # --- Optional: Check for FFMPEG early ---
    # (FFMPEG check code remains the same as previous version)
    ffmpeg_executable = None
    try:
        ffmpeg_exe_env = os.getenv('FFMPEG_BINARY')
        if ffmpeg_exe_env and shutil.which(ffmpeg_exe_env):
            ffmpeg_executable = ffmpeg_exe_env
            print(f"Using FFMPEG from FFMPEG_BINARY environment variable: {ffmpeg_executable}")
        else:
            ffmpeg_executable = shutil.which("ffmpeg")
            if ffmpeg_executable:
                 print(f"Found ffmpeg executable in system PATH: {ffmpeg_executable}")
            else:
                 try:
                     # Check moviepy config (less reliable way now)
                     mpy_ffmpeg_path = getattr(mpy_config, 'FFMPEG_BINARY', None)
                     if mpy_ffmpeg_path and mpy_ffmpeg_path != 'ffmpeg-imageio' and os.path.exists(mpy_ffmpeg_path):
                         ffmpeg_executable = mpy_ffmpeg_path
                         print(f"Using FFMPEG specified in moviepy config: {ffmpeg_executable}")
                     else:
                          print("Warning: FFMPEG not found in PATH, environment variables, or moviepy config.")
                          # Optionally show warning, but avoid blocking startup if possible
                          # messagebox.showwarning("FFMPEG Not Found", ...)
                 except Exception: # Catch any error checking config
                      print("Warning: FFMPEG not found in PATH or environment variables. Could not check moviepy config.")

        if not ffmpeg_executable:
             print("FFMPEG check failed. Video processing might not work.")
             # Consider a non-blocking way to inform user if critical

    except Exception as e:
        print(f"Could not perform FFMPEG check: {e}")
    # --- End FFMPEG Check ---

    root = tk.Tk()
    app = WatermarkApp(root)
    root.mainloop()

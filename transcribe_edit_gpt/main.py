import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import pathlib
import sys
import io
import json
import sv_ttk

try:
    import stable_whisper

    WHISPER_AVAILABLE = True
except ImportError:
    messagebox.showerror(
        "Dependency Error",
        "Critical Dependency Missing: 'stable-whisper' not found.\nPlease install it (e.g., 'pip install stable-whisper') and restart the application.",
    )
    sys.exit(1)

try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    print(
        "Warning: Optional Dependency Missing: 'openai' library not found. ChatGPT features disabled.\nInstall using: pip install openai"
    )
    OPENAI_AVAILABLE = False

try:
    # from moviepy import VideoFileClip, concatenate_videoclips # Use specific imports
    from moviepy import VideoFileClip, concatenate_videoclips

    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print(
        "Warning: Optional Dependency Missing: PyTorch ('torch') not found.\nWhisper will use CPU (potentially slow). Install PyTorch for GPU support."
    )


WHISPER_MODEL_NAME = "base"
APP_TITLE = "Video Processor & ChatGPT Assistant"

CONFIG_FILE = pathlib.Path.home() / ".video_processor_app_config.json"


whisper_model = None
MODEL_LOAD_LOCK = threading.Lock()


def load_whisper_model(status_callback):
    """Loads the Whisper model thread-safely."""
    global whisper_model
    if not WHISPER_AVAILABLE:
        status_callback("Whisper library not available.")
        return False

    with MODEL_LOAD_LOCK:
        if whisper_model is None:
            try:
                status_callback(f"Loading Whisper model '{WHISPER_MODEL_NAME}'...")

                device = "cpu"
                if TORCH_AVAILABLE:
                    if torch.cuda.is_available():
                        device = "cuda"
                    elif (
                        hasattr(torch.backends, "mps")
                        and torch.backends.mps.is_available()
                    ):
                        device = "mps"  # Use 'mps' for Apple Silicon GPUs
                status_callback(f"Using device: {device}")
                whisper_model = stable_whisper.load_model(
                    WHISPER_MODEL_NAME, device=device
                )
                status_callback(
                    f"Whisper model '{WHISPER_MODEL_NAME}' loaded on {device}."
                )
                return True
            except Exception as e:
                messagebox.showerror(
                    "Model Load Error",
                    f"Failed to load Whisper model '{WHISPER_MODEL_NAME}':\n{e}\n\nCheck installations and available memory.",
                )
                status_callback(f"Model load failed: {e}")
                return False
        return True  # Already loaded


def get_transcript_path(video_path):
    """Generates the corresponding transcript file path (.txt)."""
    p = pathlib.Path(video_path)
    return p.with_suffix(".txt")


class VideoProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("800x850")  # Increased height for transcript/summary

        self.video_files = []
        self.current_transcript_context = (
            None  # Added to store transcript after generation
        )

        style = ttk.Style()  # Removed unused style var

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- File List Section ---
        top_frame = ttk.LabelFrame(main_frame, text="Video/Audio Files", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 10))
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=0)

        listbox_frame = ttk.Frame(top_frame)
        listbox_frame.grid(row=0, column=0, sticky="nsew", rowspan=5)
        listbox_frame.rowconfigure(0, weight=1)
        listbox_frame.columnconfigure(0, weight=1)

        self.listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        self.listbox = tk.Listbox(
            listbox_frame,
            selectmode=tk.SINGLE,
            exportselection=False,
            yscrollcommand=self.listbox_scrollbar.set,
            activestyle="dotbox",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox_scrollbar.config(command=self.listbox.yview)
        self.listbox_scrollbar.grid(row=0, column=1, sticky="ns")

        buttons_frame = ttk.Frame(top_frame)
        buttons_frame.grid(row=0, column=1, sticky="ns", padx=(10, 0), rowspan=5)

        self.select_button = ttk.Button(
            buttons_frame, text="Select Files", command=self.select_videos
        )  # Minimal comment change
        self.select_button.pack(fill=tk.X, pady=2)
        self.up_button = ttk.Button(
            buttons_frame, text="Move Up", command=self.move_up
        )  # Minimal comment change
        self.up_button.pack(fill=tk.X, pady=2)
        self.down_button = ttk.Button(
            buttons_frame, text="Move Down", command=self.move_down
        )  # Minimal comment change
        self.down_button.pack(fill=tk.X, pady=2)
        self.delete_button = ttk.Button(
            buttons_frame, text="Remove Selected", command=self.delete_item
        )  # Minimal comment change
        self.delete_button.pack(fill=tk.X, pady=2)

        # --- Processing & ChatGPT Section ---
        middle_frame = ttk.LabelFrame(
            main_frame, text="Processing & ChatGPT", padding="10"
        )  # Minimal comment change
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        middle_frame.columnconfigure(1, weight=1)
        # Adjusted row weights for transcript/result area
        middle_frame.rowconfigure(5, weight=1)  # Prompt entry row
        middle_frame.rowconfigure(7, weight=3)  # Result/Transcript row

        self.transcribe_button = ttk.Button(
            middle_frame,
            text="Transcribe (Creates Context)",  # Changed button text
            command=self.start_transcription,
        )  # Minimal comment change
        self.transcribe_button.grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        ttk.Label(middle_frame, text="OpenAI API Key:").grid(
            row=1, column=0, sticky="w", pady=(0, 5), padx=(0, 5)
        )
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            middle_frame, textvariable=self.api_key_var, width=60, show="*"
        )
        self.api_key_entry.grid(row=1, column=1, sticky="ew", pady=(0, 5))

        # Show API Key Checkbox
        self.show_api_key_var = tk.BooleanVar(value=False)
        self.show_api_key_button = ttk.Checkbutton(
            middle_frame,
            text="Show",
            variable=self.show_api_key_var,
            command=self._toggle_api_key_visibility,
        )
        self.show_api_key_button.grid(row=2, column=1, sticky="w", pady=(0, 10))

        ttk.Label(
            middle_frame, text="ChatGPT Prompt (Contextual):"
        ).grid(  # Slightly changed label
            row=3, column=0, sticky="nw", pady=(5, 5), padx=(0, 5)
        )
        self.prompt_entry = scrolledtext.ScrolledText(
            middle_frame, height=5, wrap=tk.WORD
        )  # Minimal comment change
        self.prompt_entry.grid(
            row=3, column=1, rowspan=2, sticky="nsew", pady=(5, 5)
        )  # Span 2 rows (3 and 4)

        self.chatgpt_button = ttk.Button(
            middle_frame,
            text="Ask ChatGPT (using current context)",  # Changed button text
            command=self.start_chatgpt_query,
        )  # Minimal comment change
        self.chatgpt_button.grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(5, 10)  # Moved to row 5
        )

        ttk.Label(
            middle_frame, text="Output / Transcript / Summary:"
        ).grid(  # Changed label
            row=6, column=0, sticky="nw", pady=(5, 5), padx=(0, 5)  # Moved to row 6
        )
        self.result_text = scrolledtext.ScrolledText(
            middle_frame, height=15, wrap=tk.WORD, state=tk.DISABLED  # Increased height
        )
        self.result_text.grid(
            row=6, column=1, sticky="nsew", pady=(5, 0), rowspan=2
        )  # Moved to row 6, span 2 rows (6 and 7)

        # --- Status Bar ---
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding="2 5",
        )
        self.status_label.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

        # Load settings, bind events, and load model
        self._load_settings()  # Minimal comment change

        # Save settings when API key or prompt changes
        self.api_key_var.trace_add("write", self._save_settings_on_update)
        self.prompt_entry.bind("<KeyRelease>", self._save_settings_on_update)

        # Handle closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial status and model loading
        if not self.status_var.get():
            self.set_status("Ready. Load the Whisper model if needed.")
        threading.Thread(
            target=load_whisper_model, args=(self.set_status,), daemon=True
        ).start()

    # --- UI Update Methods ---
    def set_status(self, message):
        """Updates the status bar safely from any thread."""
        self.root.after(0, lambda: self.status_var.set(message))

    def set_result_text(self, text):
        """Updates the result text area safely from any thread."""

        def update():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, text)
            self.result_text.config(state=tk.DISABLED)
            self.result_text.see(tk.END)  # Scroll to end

        self.root.after(0, update)

    def append_result_text(self, text):
        """Appends text to the result text area safely."""

        def update():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.insert(tk.END, text)
            self.result_text.config(state=tk.DISABLED)
            self.result_text.see(tk.END)  # Scroll to end

        self.root.after(0, update)

    def _toggle_api_key_visibility(self):
        """Shows or hides the API key."""
        show = self.show_api_key_var.get()
        self.api_key_entry.config(show="" if show else "*")

    def _set_processing_state(self, processing: bool):
        """Disables or enables UI elements during processing."""
        state = tk.DISABLED if processing else tk.NORMAL
        listbox_state = (
            tk.DISABLED if processing else tk.NORMAL
        )  # Listbox always disabled during processing
        chat_state = (
            tk.DISABLED if processing or not OPENAI_AVAILABLE else tk.NORMAL
        )  # Chat disabled if processing or unavailable

        # File list controls
        self.listbox.config(state=listbox_state)
        self.select_button.config(state=state)
        self.up_button.config(state=state)
        self.down_button.config(state=state)
        self.delete_button.config(state=state)

        # Processing button
        self.transcribe_button.config(state=state)

        # ChatGPT controls
        self.chatgpt_button.config(state=chat_state)
        self.api_key_entry.config(
            state=state
        )  # API key entry always editable unless processing
        self.show_api_key_button.config(
            state=state
        )  # Show key button follows API entry
        self.prompt_entry.config(
            state=tk.DISABLED if processing or not OPENAI_AVAILABLE else tk.NORMAL
        )  # Prompt entry mirrors chat button state

    # --- Settings Persistence ---
    def _save_settings(self):
        """Saves current API key, prompt, and file list to config."""
        self.video_files = (
            self._get_ordered_videos()
        )  # Ensure list is up-to-date before saving
        settings = {
            "api_key": self.api_key_var.get(),
            "prompt": self.prompt_entry.get("1.0", tk.END).strip(),
            "video_files": self.video_files,
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Warning: Could not save settings to {CONFIG_FILE}: {e}")

    # Callback wrapper for trace/bind
    def _save_settings_on_update(self, *args):
        """Saves settings triggered by UI changes."""
        self._save_settings()

    # Load settings from config file
    def _load_settings(self):
        """Loads settings from the config file on startup."""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)

                self.api_key_var.set(settings.get("api_key", ""))
                self.prompt_entry.delete("1.0", tk.END)
                self.prompt_entry.insert("1.0", settings.get("prompt", ""))
                self._toggle_api_key_visibility()  # Set initial visibility

                video_files_to_load = settings.get("video_files", [])
                self.listbox.delete(0, tk.END)
                self.video_files = []
                loaded_count = 0
                current_paths_in_listbox = set()  # Track paths to avoid duplicates

                for video_path in video_files_to_load:
                    p = pathlib.Path(video_path)
                    try:  # Validate and resolve path
                        abs_path_str = str(p.resolve(strict=True))  # Ensure file exists
                        if abs_path_str not in current_paths_in_listbox:
                            self.video_files.append(abs_path_str)
                            self.listbox.insert(tk.END, abs_path_str)
                            current_paths_in_listbox.add(abs_path_str)
                            loaded_count += 1
                        else:  # Skip duplicates
                            print(
                                f"Info: Skipping duplicate file from config: {video_path}"
                            )
                    except FileNotFoundError:
                        print(f"Info: Skipping missing file from config: {video_path}")
                    except Exception as resolve_e:  # Catch other resolution errors
                        print(
                            f"Info: Skipping invalid path from config: {video_path} ({resolve_e})"
                        )

                self.set_status(
                    f"Loaded settings. Found {loaded_count}/{len(video_files_to_load)} existing media file(s)."
                )
            else:
                self.set_status("Config file not found. Using default settings.")
        except json.JSONDecodeError as e:
            self.set_status(
                f"Error parsing config file {CONFIG_FILE.name}. Using defaults."
            )
            print(f"JSON Decode Error loading settings: {e}")
            try:  # Try to rename corrupted file
                corrupt_path = CONFIG_FILE.with_suffix(".json.corrupted")
                CONFIG_FILE.rename(corrupt_path)
                self.set_status(
                    f"Renamed corrupted config to {corrupt_path.name}. Using defaults."
                )
            except OSError as rename_e:
                print(f"Could not rename corrupted config file: {rename_e}")
        except Exception as e:
            self.set_status("Error loading settings. See console.")
            print(f"Unexpected error loading settings: {e}")

    # --- Window Closing ---
    def on_closing(self):
        """Saves settings before closing the application."""
        self.set_status("Saving settings and closing...")
        self._save_settings()
        self.root.destroy()

    # --- Listbox Management ---
    def _get_ordered_videos(self):
        """Returns a list of video paths in the current listbox order."""
        return [self.listbox.get(i) for i in range(self.listbox.size())]

    def select_videos(self):
        """Opens file dialog to select media files and adds them to the list."""
        filetypes = (
            (
                "Media files",
                "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.mpeg *.mpg *.mp3 *.wav *.ogg *.flac *.m4a",
            ),  # Combined type
            ("Video files", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.mpeg *.mpg"),
            ("Audio files", "*.mp3 *.wav *.ogg *.flac *.m4a"),
            ("All files", "*.*"),
        )
        filenames = filedialog.askopenfilenames(
            title="Select Media Files", filetypes=filetypes
        )
        if filenames:
            current_files = set(self._get_ordered_videos())
            new_files_added = 0
            for fn in filenames:
                try:  # Resolve and check for duplicates
                    full_path = str(pathlib.Path(fn).resolve(strict=True))
                    if full_path not in current_files:
                        # self.video_files.append(full_path) # Managed by _get_ordered_videos now
                        self.listbox.insert(tk.END, full_path)
                        current_files.add(full_path)
                        new_files_added += 1
                except Exception as e:  # Catch file errors
                    print(
                        f"Warning: Could not add file {fn}: {e}"
                    )  # Minimal comment change

            if new_files_added > 0:
                self.set_status(
                    f"Added {new_files_added} new file(s). Total: {len(current_files)}"
                )
                # Auto-select the last added item
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(tk.END)
                self.listbox.activate(tk.END)
                self.listbox.see(tk.END)
                self._save_settings()  # Save after modification

    def _get_selected_index(self):
        """Gets the index of the currently selected item, or None."""
        selected_indices = self.listbox.curselection()
        return selected_indices[0] if selected_indices else None

    def move_up(self):
        """Moves the selected item one position up in the list."""
        idx = self._get_selected_index()
        if idx is None or idx == 0:
            return
        item_text = self.listbox.get(idx)
        self.listbox.delete(idx)
        self.listbox.insert(idx - 1, item_text)
        self.listbox.selection_set(idx - 1)
        self.listbox.activate(idx - 1)
        # self.video_files = self._get_ordered_videos() # Updated in _save_settings
        self._save_settings()  # Save after modification

    def move_down(self):
        """Moves the selected item one position down in the list."""
        idx = self._get_selected_index()
        if idx is None or idx >= self.listbox.size() - 1:
            return
        item_text = self.listbox.get(idx)
        self.listbox.delete(idx)
        self.listbox.insert(idx + 1, item_text)
        self.listbox.selection_set(idx + 1)
        self.listbox.activate(idx + 1)
        # self.video_files = self._get_ordered_videos() # Updated in _save_settings
        self._save_settings()  # Save after modification

    def delete_item(self):
        """Removes the selected item from the list."""
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            return

        deleted_files_count = 0
        # Only delete the first selected item if multiple are somehow selected
        idx = selected_indices[0]
        deleted_file_path = self.listbox.get(idx)
        self.listbox.delete(idx)
        print(f"Removed from list: {os.path.basename(deleted_file_path)}")
        deleted_files_count = 1

        # self.video_files = self._get_ordered_videos() # Updated in _save_settings
        self.current_transcript_context = None  # Clear context if list changes
        self.set_status(
            f"Removed {deleted_files_count} file(s). Context cleared. Total: {self.listbox.size()}"
        )
        self._save_settings()  # Save after modification

        # Reselect an item if possible
        if self.listbox.size() > 0:
            new_idx_to_select = min(idx, self.listbox.size() - 1)
            if new_idx_to_select >= 0:
                self.listbox.selection_set(new_idx_to_select)
                self.listbox.activate(new_idx_to_select)

    # --- Video Combination ---
    # Note: Ensure ffmpeg is installed and accessible for moviepy
    def _combine_videos(self, video_paths, status_callback):
        """Combines multiple media files into one MP4 using moviepy."""
        if not MOVIEPY_AVAILABLE:
            status_callback("Skipping video combination: 'moviepy' not installed.")
            return None
        if not video_paths or len(video_paths) < 2:
            return None  # No need to combine 0 or 1 file

        output_path = None  # Define before try block
        final_clip = None  # Define before try block
        clips = []  # Define before try block
        temp_audio_path = None  # Define before try block

        try:
            # Generate a unique output filename based on the first file
            first_video_path = pathlib.Path(video_paths[0])
            output_dir = first_video_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)  # Ensure output dir exists
            first_video_stem = first_video_path.stem
            # Sanitize stem for filename
            safe_stem = "".join(
                c if c.isalnum() or c in ("_", "-") else "_" for c in first_video_stem
            )
            # Add PID for more uniqueness, especially if run concurrently (unlikely in GUI)
            combined_filename = f"combined_{safe_stem}_{len(video_paths)}files_{os.getpid()}.mp4"  # Output as MP4
            output_path = output_dir / combined_filename
            # Define temp audio file path explicitly for better cleanup control
            temp_audio_path = (
                output_dir
                / f"temp-audio_{safe_stem}_{os.getpid()}.m4a"  # Recommended temp format
            )  # Minimal comment change

        except Exception as e:
            status_callback(f"Error setting up combination paths: {e}")
            return None

        status_callback(
            f"Combining {len(video_paths)} files into {output_path.name}..."
        )
        try:
            for i, video_path_str in enumerate(video_paths):
                status_callback(
                    f"Loading [{i+1}/{len(video_paths)}]: {os.path.basename(video_path_str)}..."
                )
                video_path = pathlib.Path(video_path_str)
                if not video_path.exists():
                    raise FileNotFoundError(f"File not found: {video_path_str}")
                # Load clip, explicitly request audio
                clip = VideoFileClip(
                    str(video_path), audio=True
                )  # Minimal comment change
                clips.append(clip)

            if not clips:
                raise ValueError("No valid media clips loaded.")

            status_callback(f"Concatenating {len(clips)} clips...")
            # Use 'compose' method for better handling of different resolutions/fps if needed
            final_clip = concatenate_videoclips(clips, method="compose")

            status_callback(
                f"Writing combined file to {output_path.name} (may take time)..."
            )
            # Write the final video file
            final_clip.write_videofile(
                str(output_path),
                codec="libx264",  # Common video codec
                audio_codec="aac",  # Common audio codec
                temp_audiofile=str(temp_audio_path),  # Specify temp audio file
                remove_temp=True,  # Remove temp file after writing
                threads=os.cpu_count() or 2,  # Use available cores
                preset="medium",  # Balance speed and quality
                logger="bar",  # Show progress bar in console/status
            )
            status_callback(f"Successfully combined files: {output_path.name}")
            return str(output_path)  # Return path of the combined file

        except FileNotFoundError as e:
            status_callback(f"Error combining: {e}")
            return None
        except Exception as e:
            status_callback(f"Error during combination: {type(e).__name__} - {e}")
            print(f"Moviepy combination error: {e}")
            if output_path and output_path.exists():  # Attempt cleanup on error
                try:
                    os.remove(output_path)
                    status_callback(f"Removed partial output: {output_path.name}")
                except Exception as re:
                    print(f"Could not remove {output_path}: {re}")
            return None
        finally:  # Ensure resources are released
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            if final_clip:
                try:
                    final_clip.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            # Explicitly remove temp audio file if it still exists
            if temp_audio_path and temp_audio_path.exists():
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass

    # --- Transcription ---
    def start_transcription(self):
        """Starts transcription, combining first if multiple files exist."""
        # Check if files exist in the list
        videos_to_process = self._get_ordered_videos()
        if not videos_to_process:
            messagebox.showwarning(
                "No Files", "Please add media files to the list first."
            )
            return

        # Ensure Whisper model is loaded or loading
        if not whisper_model and not MODEL_LOAD_LOCK.locked():
            if not load_whisper_model(self.set_status):
                messagebox.showerror("Model Error", "Whisper model failed to load.")
                return
        elif MODEL_LOAD_LOCK.locked():
            messagebox.showinfo(
                "Model Loading", "Whisper model is loading. Please wait."
            )
            return

        # Start processing in a background thread
        self._set_processing_state(True)
        self.set_status("Starting transcription process...")
        self.current_transcript_context = None  # Clear previous context
        self.set_result_text("Processing files...")  # Clear previous results
        thread = threading.Thread(
            target=self._run_transcription_thread,
            args=(list(videos_to_process),),  # Pass a copy of the list
            daemon=True,
        )
        thread.start()

    def _run_transcription_thread(self, video_paths):
        """Worker thread: Combines (if >1) then transcribes files."""
        global whisper_model, transcript_path
        total_files = len(video_paths)
        success_count = 0
        errors = []
        transcribed_data = []  # List to store (filename, transcript_text)
        combined_video_path_result = None

        # Combine files first if more than one
        if total_files > 1:
            combined_video_path_result = self._combine_videos(
                video_paths, self.set_status
            )
            # If combination was requested and successful, transcribe only the combined file
            # Note: This changes behavior - previously transcribed all originals.
            # To transcribe originals AND combined, remove this block.
            # Let's stick to transcribing originals for individual context. Revert this logic.
            # combined_video_path_result = self._combine_videos(video_paths, self.set_status)

        # Transcribe each file in the list
        for i, video_path in enumerate(video_paths):
            p_video = pathlib.Path(video_path)
            base_name = p_video.name
            transcript_path = get_transcript_path(video_path)
            self.set_status(f"Transcribing [{i+1}/{total_files}]: {base_name}...")

            if not p_video.exists():
                error_msg = f"{base_name}: File not found."
                self.set_status(f"Skipping - {error_msg}")
                errors.append(error_msg)
                continue

            try:
                # Determine if fp16 can be used (GPU only)
                use_fp16 = TORCH_AVAILABLE and torch.cuda.is_available()
                # Suppress verbose Whisper output if needed (optional)
                old_stdout, old_stderr = sys.stdout, sys.stderr
                # sys.stdout = io.StringIO() # Redirect stdout
                # sys.stderr = io.StringIO() # Redirect stderr

                # Perform transcription
                result = whisper_model.transcribe(
                    str(p_video), verbose=None, fp16=use_fp16
                )  # verbose=None suppresses console output
                transcript_text = result.ori_dict["text"]
                sys.stdout = old_stdout  # Restore stdout
                sys.stderr = old_stderr  # Restore stderr

                if transcript_text:
                    with open(transcript_path, "w", encoding="utf-8") as f:
                        f.write(transcript_text)
                    self.set_status(f"Transcript saved for {base_name}")
                    transcribed_data.append(
                        (base_name, transcript_text)
                    )  # Store transcript
                    success_count += 1
                else:
                    warning_msg = f"{base_name}: Transcription resulted in empty text."
                    self.set_status(f"Warning: {warning_msg}")
                    transcribed_data.append(
                        (base_name, "")
                    )  # Store empty transcript marker
                    success_count += 1  # Count as processed, even if empty

            except Exception as e:
                sys.stdout = old_stdout  # Restore stdout
                sys.stderr = old_stderr  # Restore stderr
                error_msg = f"Error transcribing {base_name}: {type(e).__name__}"  # Concise error
                print(f"Transcription Error ({base_name}): {e}")  # Log full error
                self.set_status(f"Error processing {base_name}. See console.")
                errors.append(f"{base_name}: {e}")  # Store full error for details

        # --- Post-transcription actions ---
        full_transcript_text = ""
        if transcribed_data:
            # Combine all transcripts into a single context string
            full_transcript_text += f"--- Start of Combined Transcripts ({len(transcribed_data)} files) ---\n\n"
            for source, content in transcribed_data:
                full_transcript_text += (
                    f"--- Transcript from: {source} ---\n{content.strip()}\n\n"
                )
            full_transcript_text += "--- End of Combined Transcripts ---"
            self.current_transcript_context = (
                full_transcript_text  # Store for later use
            )

            # Schedule post-transcription tasks on the main thread
            self.root.after(0, self._post_transcription_tasks, full_transcript_text)
            # Do not re-enable UI here, _post_transcription_tasks or summary thread will handle it

        else:  # No successful transcriptions
            final_status = f"Transcription failed. Processed 0/{total_files} files."
            if combined_video_path_result:
                final_status += f" Combined file created: {os.path.basename(combined_video_path_result)}."
            if errors:
                final_status += f" Encountered {len(errors)} error(s)."
            self.set_status(final_status)
            self.root.after(
                0, lambda: self._set_processing_state(False)
            )  # Re-enable UI on total failure

        # Show errors if any occurred
        if errors:
            error_summary = "\n".join([f"- {str(e)[:100]}" for e in errors[:8]]) + (
                "\n..." if len(errors) > 8 else ""
            )  # Show first 8 errors concisely
            self.root.after(
                0,
                lambda: messagebox.showwarning(
                    "Transcription Errors", f"Errors occurred:\n{error_summary}"
                ),
            )
        elif success_count > 0 and not self.current_transcript_context:
            # This case shouldn't happen with current logic but as a safeguard:
            self.set_status(
                f"Transcription finished for {success_count}/{total_files}, but failed to generate context."
            )
            self.root.after(
                0, lambda: self._set_processing_state(False)
            )  # Re-enable UI

    def _post_transcription_tasks(self, full_transcript):
        """Runs on main thread after transcription: displays transcript, triggers summary."""
        self.set_status("Transcription complete. Displaying transcript...")
        self.set_result_text(full_transcript)  # Show the full transcript first

        # Check if automatic summary is possible
        api_key = self.api_key_var.get().strip()
        if OPENAI_AVAILABLE and api_key:
            self.set_status("Requesting summary from ChatGPT...")
            # Keep UI disabled, start summary thread
            summary_thread = threading.Thread(
                target=self._run_chatgpt_summary_thread,
                args=(api_key, full_transcript),
                daemon=True,
            )
            summary_thread.start()
        else:
            # No OpenAI key/lib, just finish up
            self.set_status(
                "Transcription complete. Configure OpenAI API key for summary & chat."
            )
            self.root.after(
                0, lambda: self._set_processing_state(False)
            )  # Re-enable UI now

    def _run_chatgpt_summary_thread(self, api_key, transcript_context):
        """Worker thread: Sends transcript to OpenAI for summarization."""
        summary_text = ""
        error_msg = None
        try:
            client = openai.OpenAI(api_key=api_key)
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Summarize the following transcript(s) concisely.",
                },
                {"role": "user", "content": transcript_context},
            ]
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use a capable model
                messages=messages,
                temperature=0.3,  # Lower temp for factual summary
                max_tokens=500,  # Limit summary length reasonably
            )
            summary_text = (
                response.choices[0].message.content.strip() if response.choices else ""
            )

            if summary_text:
                # Update result text with summary and full transcript
                display_text = (
                    f"Summary:\n-------\n{summary_text}\n\n"
                    f"Full Transcript:\n---------------\n{transcript_context}"
                )
                self.set_result_text(display_text)
                self.set_status("Summary received. Ready for follow-up questions.")
            else:
                error_msg = "ChatGPT returned an empty summary."
                self.append_result_text(
                    f"\n\n--- Error: {error_msg} ---"
                )  # Append error to transcript view
                self.set_status(f"Summary Error: {error_msg}")

        except openai.AuthenticationError:
            error_msg = "Authentication failed. Check API Key."
        except openai.RateLimitError:
            error_msg = "Rate limit exceeded. Wait or check limits."
        except openai.APIConnectionError:
            error_msg = "Connection failed. Check network."
        except openai.APIStatusError as e:
            error_msg = f"API Error {e.status_code}: {getattr(e, 'message', str(e))}"  # Safely get message
            print(f"API Error: {e}")
        except Exception as e:
            error_msg = f"Unexpected ChatGPT error: {type(e).__name__}"
            print(f"ChatGPT Summary Error: {e}")

        finally:
            if error_msg:
                # Show error message if summary failed
                self.append_result_text(f"\n\n--- Summary Failed: {error_msg} ---")
                self.set_status(f"Summary Error: {error_msg.split('.')[0]}")
                # Still display the transcript which was set earlier
            # Re-enable the UI regardless of summary success/failure
            self.root.after(0, lambda: self._set_processing_state(False))

    # --- ChatGPT Querying (User Initiated) ---
    def start_chatgpt_query(self):
        """Sends user prompt and context (transcript) to ChatGPT."""
        if not OPENAI_AVAILABLE:
            messagebox.showerror(
                "Dependency Error", "OpenAI library not installed. Cannot run query."
            )
            return

        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("API Key Error", "OpenAI API Key required.")
            return
        user_prompt = self.prompt_entry.get("1.0", tk.END).strip()
        if not user_prompt:
            messagebox.showwarning("Input Error", "ChatGPT prompt required.")
            return

        context_to_use = None
        context_source_msg = ""

        # Prioritize using the transcript context if available
        if self.current_transcript_context:
            context_to_use = self.current_transcript_context
            context_source_msg = "Asking ChatGPT using current transcript context..."
        else:
            # Fallback: try reading transcripts from files in the list
            videos_in_order = self._get_ordered_videos()
            if not videos_in_order:
                messagebox.showwarning(
                    "No Context",
                    "No transcript context generated and no files in list.",
                )
                return

            missing_transcripts = []
            transcript_contents = []
            transcript_sources = []

            for video_path in videos_in_order:
                transcript_path = get_transcript_path(video_path)
                if transcript_path.exists():
                    try:
                        with open(transcript_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        if content.strip():
                            transcript_contents.append(content)
                            transcript_sources.append(
                                os.path.basename(video_path)
                            )  # Minimal comment change
                        else:
                            print(
                                f"Info: Skipping empty transcript file: {transcript_path.name}"
                            )
                    except Exception as e:
                        messagebox.showerror(
                            "File Read Error",
                            f"Cannot read transcript:\n{transcript_path}\n{e}",
                        )
                        return  # Stop if a transcript can't be read
                else:
                    missing_transcripts.append(os.path.basename(video_path))

            if missing_transcripts:
                messagebox.showwarning(
                    "Missing Transcripts",
                    "Cannot find transcript files for listed items. Use 'Transcribe' first or remove missing items:\n- "
                    + "\n- ".join(missing_transcripts),
                )
                return
            if not transcript_contents:
                messagebox.showwarning(
                    "No Context",
                    "No non-empty transcript files found for items in list.",
                )
                return

            # Build context from files if needed
            context_to_use = f"--- Start of Combined Transcripts ({len(transcript_sources)} files) ---\n\n"
            for i, content in enumerate(transcript_contents):
                context_to_use += f"--- Transcript from: {transcript_sources[i]} ---\n{content.strip()}\n\n"
            context_to_use += "--- End of Combined Transcripts ---"
            context_source_msg = "Asking ChatGPT using transcripts from file list..."

        # Start the ChatGPT query thread
        self._set_processing_state(True)
        self.set_status(context_source_msg)
        self.append_result_text(
            "\n\nSending request to ChatGPT..."
        )  # Clear previous results/transcript
        thread = threading.Thread(
            target=self._run_chatgpt_thread,
            args=(api_key, user_prompt, context_to_use),
            daemon=True,
        )
        thread.start()

    def _run_chatgpt_thread(self, api_key, user_prompt, transcript_context):
        """Worker thread: Sends user prompt and context to OpenAI API."""
        global transcript_path
        result_text = ""
        error_msg = None
        try:
            # Initialize OpenAI client
            client = openai.OpenAI(api_key=api_key)
            # Prepare messages for the chat API
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Analyze the provided transcript context and answer the user's questions based *only* on the information given in the transcripts.",  # More specific system prompt
                },
                # Provide the context first (as if it's part of the setup or previous turn)
                {
                    "role": "user",
                    "content": f"Here is the context from the transcript(s):\n\n{transcript_context}",
                },
                # Then provide the actual user question
                {"role": "user", "content": user_prompt},
            ]
            # Make the API call
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Or another suitable model
                messages=messages,
                temperature=0.5,  # Moderate temperature for creative but grounded answers
                max_tokens=2000,  # Allow longer responses
            )
            # Extract the response content
            result_text = (
                response.choices[0].message.content.strip() if response.choices else ""
            )
            with open(transcript_path, "a", encoding="utf-8") as f:
                f.write(f'\n\nexample tweets:\n{result_text}')

            if result_text:
                self.append_result_text(
                    f"\n\nExample tweets:\n{result_text}"
                )  # Display the result
                self.set_status("ChatGPT query successful.")
            else:
                error_msg = "ChatGPT returned an empty response."
                self.set_result_text(
                    "ChatGPT returned an empty response."
                )  # Display empty message
                self.set_status(f"ChatGPT Error: {error_msg}")

        # Handle potential OpenAI API errors
        except openai.AuthenticationError:
            error_msg = "Authentication failed. Check API Key."
        except openai.RateLimitError:
            error_msg = "Rate limit exceeded. Wait or check limits."
        except openai.APIConnectionError:
            error_msg = "Connection failed. Check network."
        except openai.APIStatusError as e:
            error_msg = f"API Error {e.status_code}: {getattr(e, 'message', str(e))}"  # Safely get message
            print(f"API Error: {e}")
        # Handle other unexpected errors
        except Exception as e:
            error_msg = f"Unexpected ChatGPT error: {type(e).__name__}"
            print(f"ChatGPT Error: {e}")

        finally:
            # Display error message in UI if something went wrong
            if error_msg:
                # Show error in result area and status bar
                self.set_result_text(f"Error: {error_msg}")
                self.set_status(f"ChatGPT Error: {error_msg.split('.')[0]}")
                # Optionally show a popup for critical errors like auth
                if isinstance(
                    error_msg, (openai.AuthenticationError, openai.APIStatusError)
                ):
                    self.root.after(
                        0, lambda: messagebox.showerror("API Error", error_msg)
                    )

            # Always re-enable the UI controls after the thread finishes
            self.root.after(0, lambda: self._set_processing_state(False))


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    sv_ttk.set_theme("dark")  # Apply theme

    # Print warnings for missing optional dependencies
    if not MOVIEPY_AVAILABLE:
        print(
            "Warning: 'moviepy' not found. Video combining disabled. (pip install moviepy)"
        )
    if not OPENAI_AVAILABLE:
        print(
            "Warning: 'openai' not found. ChatGPT features disabled. (pip install openai)"
        )
    if not TORCH_AVAILABLE:
        print("Info: 'torch' not found. Using CPU for Whisper.")

    app = VideoProcessorApp(root)
    root.mainloop()

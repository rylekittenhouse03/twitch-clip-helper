import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import datetime
import subprocess
import threading
import re
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


def get_formatted_date(days_offset=0):
    """Gets today's or a past date formatted as YYYYMMDD."""
    target_date = datetime.date.today() - datetime.timedelta(days=days_offset)
    return target_date.strftime("%Y%m%d")

def construct_tracker_url(username, date_str):
    """Constructs the TwitchTracker URL."""
    if not username:
        return None
    # Format: https://twitchtracker.com/{username}/clips#{date}-{date}
    return f"https://twitchtracker.com/{username}/clips#{date_str}-{date_str}"

def extract_clip_urls_from_html(html_content):
    """Extracts full Twitch clip URLs from HTML source using regex."""
    # Pattern to find the data-litebox attribute and extract the clip ID
    # Example: data-litebox="//clips.twitch.tv/embed?parent=twitchtracker.com&autoplay=true&clip=DifficultAttractivePelicanDatSheffy-vi4njUEAZMOxf6gV"
    # We need the part after 'clip='
    pattern = r'data-litebox=".*?clip=([^"]+)"'
    matches = re.findall(pattern, html_content)
    
    # Construct full URLs
    base_url = "https://clips.twitch.tv/"
    full_urls = [base_url + clip_id.replace('&', '&') for clip_id in matches] # Handle potential HTML entities just in case
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = [url for url in full_urls if not (url in seen or seen.add(url))]
    return unique_urls

def check_command_exists(command):
    """Checks if a command (like yt-dlp) exists in the system PATH."""
    try:
        # For Windows, use 'where'; for Unix-like, use 'which'
        check_cmd = "where" if sys.platform == "win32" else "which"
        subprocess.run([check_cmd, command], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def download_clip(url, output_dir, status_callback):
    """Downloads a single clip using yt-dlp."""
    try:
        command = [
            "yt-dlp",
            "--no-check-certificate", # Often needed for yt-dlp
            "--output", os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s"), # Define output template
            "--socket-timeout", "30", # Add a socket timeout
            url
        ]
        status_callback(f"Downloading: {url.split('/')[-1]}")
        # Run yt-dlp, capture output
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        
        # Stream output for progress (optional but good)
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # Simple progress parsing (yt-dlp format can vary)
                if "%" in output and ("ETA" in output or "speed" in output):
                     # Update status less frequently for downloads to avoid flooding
                     if getattr(download_clip, "last_update_percent", -1) != output[:5]: # Crude check to reduce updates
                        status_callback(f"Progress: {output.strip()}")
                        download_clip.last_update_percent = output[:5]
                # else:
                #    print(f"yt-dlp out: {output.strip()}") # Debug non-progress lines

        stderr = process.stderr.read()
        process.wait() # Wait for the process to fully complete

        if process.returncode == 0:
            status_callback(f"Downloaded: {url.split('/')[-1]}")
            return True
        else:
            error_message = f"yt-dlp failed for {url.split('/')[-1]}. Error: {stderr.strip()}"
            if "ERROR: Unable to download webpage" in stderr or "HTTP Error 404" in stderr:
                 error_message += "\n(Clip might be deleted or unavailable)"
            elif "Interrupted by user" in stderr:
                 error_message += "\n(Download cancelled by user)"
            status_callback(error_message, is_error=True)
            return False
    except FileNotFoundError:
        status_callback("Error: 'yt-dlp' command not found. Please ensure yt-dlp is installed and in your system's PATH.", is_error=True)
        return False
    except Exception as e:
        status_callback(f"Error downloading {url.split('/')[-1]}: {e}", is_error=True)
        return False
    finally:
        # Reset the crude update tracker
        getattr(download_clip, "last_update_percent", None)
        download_clip.last_update_percent = -1


def run_selenium_and_extract(url, status_callback):
    """Launches Selenium, gets page source, and extracts clips."""
    status_callback("Initializing WebDriver...")
    service = None
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless") # Run headless
        chrome_options.add_argument("--log-level=3") # Suppress logs
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox") # Often needed in restricted environments
        chrome_options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging']) # Suppress DevTools listening message

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        status_callback(f"Navigating to {url}...")
        driver.set_page_load_timeout(60) # Increased timeout for potentially slow pages
        driver.get(url)

        # Wait for clip elements to be potentially present (adjust timeout and locator if needed)
        status_callback("Waiting for clip elements to load...")
        try:
             # Wait for at least one element with the specific class to appear
             WebDriverWait(driver, 20).until(
                 EC.presence_of_element_located((By.CSS_SELECTOR, "div.clip-tp[data-litebox]"))
             )
             status_callback("Clip elements likely loaded.")
        except TimeoutException:
             # It's possible the page loads but has no clips, or loads very slowly.
             # We'll proceed anyway and let the parsing handle it.
             status_callback("Timed out waiting for specific clip elements, proceeding with page source.")


        status_callback("Extracting page source...")
        html_content = driver.page_source

        status_callback("Parsing HTML for clips...")
        clip_urls = extract_clip_urls_from_html(html_content)
        
        if not clip_urls:
             status_callback("No clip URLs found on the page.")
             # Check for common tracker issues
             if "Channel not found" in html_content:
                 status_callback("TwitchTracker error: Channel not found.", is_error=True)
             elif "No clips found for specified period" in html_content:
                 status_callback("TwitchTracker: No clips found for the specified date.")
             # Add more specific checks if needed based on TwitchTracker page structure

        return clip_urls

    except WebDriverException as e:
        error_msg = f"WebDriver Error: {e}"
        if "net::ERR_NAME_NOT_RESOLVED" in str(e):
             error_msg += "\nCheck your internet connection or the URL."
        elif "unable to connect to renderer" in str(e).lower():
             error_msg += "\n(Browser crashed or failed to start. Try without --headless?)"
        status_callback(error_msg, is_error=True)
        return None
    except TimeoutException:
         status_callback("Page load timed out. The website might be down or slow.", is_error=True)
         return None
    except Exception as e:
        status_callback(f"An unexpected error occurred during Selenium operation: {e}", is_error=True)
        return None
    finally:
        if driver:
            status_callback("Closing WebDriver...")
            driver.quit()
        if service and service.process:
             # Ensure the chromedriver process is terminated if it's still running
             try:
                 service.stop()
             except Exception as service_stop_err:
                 status_callback(f"Could not stop ChromeDriver service: {service_stop_err}", is_error=True)


def process_request(username, date_str, output_dir, status_callback):
    """Main processing function to be run in a thread."""
    status_callback(f"Starting process for {username} on {date_str}...")

    # --- 1. Check yt-dlp ---
    status_callback("Checking for yt-dlp...")
    if not check_command_exists("yt-dlp"):
        status_callback("Error: 'yt-dlp' command not found. Please install it and ensure it's in your system's PATH.", is_error=True)
        status_callback("Process aborted.")
        return
    status_callback("yt-dlp found.")

    # --- 2. Construct URL ---
    tracker_url = construct_tracker_url(username, date_str)
    if not tracker_url:
        status_callback("Invalid username.", is_error=True)
        status_callback("Process aborted.")
        return
    status_callback(f"Constructed URL: {tracker_url}")

    # --- 3. Run Selenium & Extract ---
    clip_urls = run_selenium_and_extract(tracker_url, status_callback)

    if clip_urls is None:
        status_callback("Failed to retrieve clip URLs.", is_error=True)
        status_callback("Process aborted.")
        return

    if not clip_urls:
        # Message already displayed by run_selenium_and_extract
        status_callback("Process finished: No clips to download.")
        return

    status_callback(f"Found {len(clip_urls)} unique clip URLs.")
    
    # --- 4. Create Output Directory ---
    try:
        os.makedirs(output_dir, exist_ok=True)
        status_callback(f"Using output directory: {output_dir}")
    except OSError as e:
        status_callback(f"Error creating output directory '{output_dir}': {e}", is_error=True)
        status_callback("Process aborted.")
        return


    # --- 5. Download Clips ---
    status_callback(f"Starting download of {len(clip_urls)} clips...")
    download_count = 0
    fail_count = 0
    for i, url in enumerate(clip_urls):
        status_callback(f"--- Downloading clip {i+1} of {len(clip_urls)} ---")
        if download_clip(url, output_dir, status_callback):
            download_count += 1
        else:
            fail_count += 1
            # status_callback(f"Failed to download: {url.split('/')[-1]}", is_error=True) # Already logged in download_clip

    status_callback("--- Download Process Complete ---")
    status_callback(f"Successfully downloaded: {download_count} clip(s).")
    if fail_count > 0:
        status_callback(f"Failed to download: {fail_count} clip(s). Check logs for details.", is_error=True)
    status_callback("Process finished.")


# --- GUI Class ---

class ClipDownloaderApp:
    def __init__(self, master):
        self.master = master
        master.title("Twitch Clip Downloader")
        master.geometry("600x500") # Adjusted size for better layout

        # --- Variables ---
        self.username_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=os.getcwd()) # Default to current dir
        self.is_processing = False

        # --- Style ---
        style = ttk.Style()
        style.configure("TButton", padding=6, relief="flat", background="#ccc")
        style.configure("TLabel", padding=3)
        style.configure("TEntry", padding=3)

        # --- Layout ---
        main_frame = ttk.Frame(master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Input Frame
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=5)

        ttk.Label(input_frame, text="Twitch Username:").pack(side=tk.LEFT, padx=(0, 5))
        self.username_entry = ttk.Entry(input_frame, textvariable=self.username_var, width=30)
        self.username_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Output Directory Frame
        dir_frame = ttk.Frame(main_frame)
        dir_frame.pack(fill=tk.X, pady=5)

        ttk.Label(dir_frame, text="Output Directory:").pack(side=tk.LEFT, padx=(0, 5))
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.output_dir_var, width=40)
        self.dir_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.browse_button = ttk.Button(dir_frame, text="Browse...", command=self.browse_directory)
        self.browse_button.pack(side=tk.LEFT)


        # Button Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)

        self.today_button = ttk.Button(button_frame, text="Fetch Today's Clips", command=lambda: self.start_processing(0))
        self.today_button.pack(side=tk.LEFT, padx=5)

        self.yesterday_button = ttk.Button(button_frame, text="Fetch Yesterday's Clips", command=lambda: self.start_processing(1))
        self.yesterday_button.pack(side=tk.LEFT, padx=5)

        # Status Area
        status_label = ttk.Label(main_frame, text="Status:")
        status_label.pack(anchor=tk.W, pady=(10, 0))

        self.status_text = scrolledtext.ScrolledText(main_frame, height=15, wrap=tk.WORD, state=tk.DISABLED)
        self.status_text.pack(fill=tk.BOTH, expand=True, pady=5)
        # Add tags for coloring errors
        self.status_text.tag_config("error", foreground="red")


    def browse_directory(self):
        """Opens a dialog to choose the output directory."""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if directory: # Only update if a directory was selected
            self.output_dir_var.set(directory)


    def update_status(self, message, is_error=False):
        """Safely updates the status text area from any thread."""
        # Ensure updates happen on the main Tkinter thread
        self.master.after(0, self._update_status_text, message, is_error)

    def _update_status_text(self, message, is_error):
        """Internal method to update the text area."""
        self.status_text.config(state=tk.NORMAL)
        if is_error:
            self.status_text.insert(tk.END, f"{message}\n", "error")
        else:
            self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END) # Auto-scroll
        self.status_text.config(state=tk.DISABLED)


    def set_ui_state(self, enabled):
        """Enables or disables UI elements during processing."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.username_entry.config(state=state)
        self.dir_entry.config(state=state)
        self.browse_button.config(state=state)
        self.today_button.config(state=state)
        self.yesterday_button.config(state=state)
        self.is_processing = not enabled


    def start_processing(self, days_offset):
        """Handles button clicks to start the fetching process."""
        if self.is_processing:
            messagebox.showwarning("Busy", "A process is already running.")
            return

        username = self.username_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not username:
            messagebox.showerror("Error", "Please enter a Twitch username.")
            return
        
        if not output_dir:
             messagebox.showerror("Error", "Please specify an output directory.")
             return

        # Clear status area for new run
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete('1.0', tk.END)
        self.status_text.config(state=tk.DISABLED)

        self.set_ui_state(False) # Disable UI
        self.update_status("Process initiated...")

        date_str = get_formatted_date(days_offset)

        # Run the main logic in a separate thread to avoid freezing the GUI
        process_thread = threading.Thread(
            target=self.run_process_thread,
            args=(username, date_str, output_dir),
            daemon=True # Allows exiting the app even if thread is running
        )
        process_thread.start()

    def run_process_thread(self, username, date_str, output_dir):
        """Wrapper function to run the process and re-enable UI."""
        try:
            process_request(username, date_str, output_dir, self.update_status)
        except Exception as e:
            # Catch any unexpected errors in the thread
            self.update_status(f"An unexpected critical error occurred: {e}", is_error=True)
        finally:
            # Ensure UI is re-enabled even if errors occur
            self.master.after(0, self.set_ui_state, True)


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ClipDownloaderApp(root)
    root.mainloop()

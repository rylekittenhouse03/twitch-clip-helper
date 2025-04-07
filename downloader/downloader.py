import os
import subprocess
import sys
from constants import YT_DLP_COMMAND, SOCKET_TIMEOUT
from utils import check_command_exists  # Import check_command_exists from utils


# Class to manage download state, avoiding global state issues with threading
class ClipDownloadState:
    def __init__(self):
        self.last_update_percent = -1


def download_clip(url, output_dir, status_callback):
    """Downloads a single clip using yt-dlp."""
    state = ClipDownloadState()  # Create instance for this download
    output_dir = output_dir + '\\clips\\'
    try:
        # Construct filename template for yt-dlp
        # Ensures valid filenames and avoids collisions
        output_template = os.path.join(
            output_dir, "%(uploader)s_%(title)s_%(id)s.%(ext)s"
        )  # More robust template

        command = [
            YT_DLP_COMMAND,
            "--no-check-certificate",  # Sometimes needed for SSL issues
            "--output",
            output_template,
            "--socket-timeout",
            SOCKET_TIMEOUT,
            # Limit retries to avoid hanging indefinitely on network issues
            "--retries",
            "3",
            # Prefer native dash/hls formats if available, often faster
            "--format",
            "bestvideo[height<=?1080]+bestaudio/best",  # Limit quality slightly if needed
            # Force IPv4, can sometimes resolve connection issues
            "--force-ipv4",
            # Avoid downloading playlist if URL accidentally points to one
            "--no-playlist",
            url,
        ]

        clip_id = url.split("/")[-1].split("?")[0]  # Get cleaner clip ID for messages
        status_callback(f"Downloading: {clip_id}", tag="download")  # Use tag

        # Use Popen for real-time output processing
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",  # Explicit encoding
            errors="replace",  # Handle potential encoding errors in output
            bufsize=1,  # Line buffered
            universal_newlines=True,  # Ensure text mode works consistently
        )

        # Process stdout for progress updates
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output = line.strip()
                if output:
                    # Look for yt-dlp progress lines (often contain '%')
                    if "%" in output and (
                        "ETA" in output or "speed" in output or "elapsed" in output
                    ):  # added elapsed
                        # Extract percentage more robustly
                        try:
                            # Find the first number before '%'
                            percent_str = output.split("%")[0].split()[-1]
                            current_percent = float(percent_str)
                            # Update only if percentage changes significantly or first time
                            if (
                                state.last_update_percent == -1
                                or abs(current_percent - state.last_update_percent)
                                >= 1.0
                            ):  # update every 1%
                                status_callback(
                                    f"Progress: {output}", tag="progress"
                                )  # Use tag
                                state.last_update_percent = current_percent
                        except (ValueError, IndexError):
                            # Fallback if parsing fails, show raw output but less frequently
                            if (
                                state.last_update_percent == -1
                            ):  # show first time at least
                                status_callback(f"Progress: {output}", tag="progress")
                                state.last_update_percent = -2  # indicate fallback used
                    # else: # Optionally log other stdout messages if needed for debugging
                    #     status_callback(f"yt-dlp info: {output}", tag="info")

        # Wait for process to complete and capture stderr
        stdout, stderr = (
            process.communicate()
        )  # Use communicate after reading stdout line-by-line

        if process.returncode == 0:
            status_callback(f"Downloaded: {clip_id}", tag="success")  # Use tag
            return True
        else:
            # Provide detailed error message including stderr
            error_message = (
                f"yt-dlp failed for {clip_id}. Return code: {process.returncode}."
            )
            stderr_clean = stderr.strip()
            if stderr_clean:
                error_message += f"\nError Details: {stderr_clean}"

            # Check for common, informative errors in stderr
            if (
                "ERROR: Unable to download webpage" in stderr
                or "HTTP Error 404" in stderr
            ):
                error_message += (
                    "\n(Reason: Clip might be deleted, private, or unavailable)"
                )
            elif "Interrupted by user" in stderr:
                error_message += "\n(Reason: Download likely cancelled by user action)"
            elif "Socket timeout" in stderr:
                error_message += (
                    "\n(Reason: Network connection timed out during download)"
                )
            elif "Video unavailable" in stderr:
                error_message += "\n(Reason: Twitch reported the video is unavailable)"

            status_callback(
                error_message, is_error=True
            )  # Use is_error for proper tagging
            return False

    except FileNotFoundError:
        # This means yt-dlp command itself wasn't found
        status_callback(
            f"Error: '{YT_DLP_COMMAND}' command not found. Please ensure yt-dlp is installed and in your system's PATH.",
            is_error=True,
        )
        return False
    except Exception as e:
        # Catch unexpected errors during the download process setup or execution
        status_callback(f"Error downloading {clip_id}: {e}", is_error=True)
        return False
    # No finally block needed for state reset as it's instance-based now


def check_downloader_dependencies(status_callback):
    """Checks if yt-dlp is available."""
    status_callback("Checking for yt-dlp...")
    if not check_command_exists(YT_DLP_COMMAND):
        status_callback(
            f"Error: '{YT_DLP_COMMAND}' command not found. Please install it and ensure it's in your system's PATH.",
            is_error=True,
        )
        status_callback(
            "Process aborted: Missing dependency."
        )  # Added specific abort message
        return False
    status_callback("yt-dlp found.", tag="success")  # Use tag
    return True

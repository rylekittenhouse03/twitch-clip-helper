import os
from utils import (
    construct_tracker_url,
    create_directory_if_not_exists,
)  # Import necessary utils
from web_scraper import run_selenium_and_extract  # Import web scraping function
from downloader import (
    download_clip,
    check_downloader_dependencies,
)  # Import download functions


def process_request(
    username,
    date_str,
    output_dir,
    max_downloads,
    status_callback,
    history_callback,  # Added max_downloads parameter
):
    """Main processing function: fetches URLs and downloads clips."""
    status_callback(f"Starting process for '{username}' on {date_str}...")

    # 1. Check Dependencies (e.g., yt-dlp)
    if not check_downloader_dependencies(status_callback):
        return  # Abort if dependencies are missing

    # 2. Construct URL
    tracker_url = construct_tracker_url(username, date_str)
    if not tracker_url:
        status_callback("Invalid username provided.", is_error=True)
        status_callback("Process aborted.")
        return
    status_callback(f"Constructed URL: {tracker_url}")

    # 3. Run Web Scraper (Selenium)
    clip_urls = run_selenium_and_extract(tracker_url, status_callback)

    # Handle scraping failure
    if clip_urls is None:  # Explicitly check for None which indicates failure
        status_callback(
            "Failed to retrieve clip URLs (check logs for WebDriver/network errors).",
            is_error=True,
        )
        status_callback("Process aborted.")
        return

    # 4. Add username to history AFTER successful scraping attempt
    history_callback(username)

    # Handle case where scraping succeeded but found no clips
    if not clip_urls:
        status_callback("Process finished: No clips found to download.", tag="info")
        return

    total_found = len(clip_urls)
    status_callback(f"Found {total_found} unique clip URLs.")

    # 5. Apply Max Downloads Limit (if applicable)
    urls_to_download = clip_urls
    limit_applied = False
    if max_downloads > 0 and total_found > max_downloads:
        urls_to_download = clip_urls[:max_downloads]
        limit_applied = True
        status_callback(
            f"Applying download limit: Preparing to download {max_downloads} of {total_found} clips.",
            tag="warning",
        )  # Info/Warning tag

    # 6. Ensure Output Directory Exists
    if not create_directory_if_not_exists(output_dir, status_callback):
        status_callback("Process aborted: Output directory issue.")
        return
    status_callback(f"Using output directory: {output_dir}")

    # 7. Download Clips
    num_to_download = len(urls_to_download)
    status_callback(f"Starting download of {num_to_download} clip(s)...")
    download_count = 0
    fail_count = 0

    for i, url in enumerate(urls_to_download):
        status_callback(
            f"--- Downloading clip {i+1} of {num_to_download} ---", tag="info"
        )
        if download_clip(url, output_dir, status_callback):
            download_count += 1
        else:
            fail_count += 1
        # Optional: Add check here for cancellation flag if implementing cancellation

    # 8. Final Summary
    status_callback("--- Download Process Complete ---", tag="info")
    if limit_applied:
        status_callback(
            f"Successfully downloaded: {download_count} clip(s) (Limit of {max_downloads} reached).",
            tag="success",
        )  # Indicate limit was hit
    else:
        status_callback(
            f"Successfully downloaded: {download_count} clip(s).", tag="success"
        )

    if fail_count > 0:
        status_callback(
            f"Failed to download: {fail_count} clip(s). Check logs above for details.",
            tag="warning",
        )
    status_callback("Process finished.", tag="info")

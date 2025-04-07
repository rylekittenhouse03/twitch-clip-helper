import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from constants import (
    TWITCH_CLIP_BASE_URL,
    CLIP_URL_REGEX_PATTERN,
    SELENIUM_TIMEOUT,
    SELENIUM_PAGE_LOAD_TIMEOUT,
)


def extract_clip_urls_from_html(html_content):
    """Extracts full Twitch clip URLs from HTML source using regex."""
    matches = re.findall(CLIP_URL_REGEX_PATTERN, html_content)

    # Decode HTML entities like & before constructing URL
    full_urls = [
        TWITCH_CLIP_BASE_URL + clip_id.replace("&", "&") for clip_id in matches
    ]  # fixed entity decoding

    # Ensure uniqueness while preserving order
    seen = set()
    unique_urls = [url for url in full_urls if not (url in seen or seen.add(url))]
    return unique_urls


def run_selenium_and_extract(url, status_callback):
    """Launches Selenium, gets page source, and extracts clips."""
    status_callback("Initializing WebDriver...")
    service = None
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--log-level=3")  # Suppress INFO/WARNING messages
        chrome_options.add_argument("--disable-gpu")  # Often needed for headless
        chrome_options.add_argument(
            "--no-sandbox"
        )  # Bypass OS security model, required in some environments
        chrome_options.add_argument(
            "--disable-dev-shm-usage"
        )  # Overcome limited resource problems
        # Suppress "DevTools listening on..." message
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        status_callback("Setting up ChromeDriver...")
        try:
            # Use webdriver-manager to handle driver download/updates
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            status_callback(
                "WebDriver initialized successfully.", tag="success"
            )  # added tag
        except Exception as driver_init_error:
            # Provide more specific feedback based on common errors
            error_base_msg = f"Error initializing WebDriver: {driver_init_error}"
            status_callback(error_base_msg, is_error=True)
            status_callback(
                "Please ensure Google Chrome is installed and accessible.",
                is_error=True,
            )
            err_str = str(driver_init_error).lower()
            if "cannot find chrome binary" in err_str:
                status_callback(
                    "Chrome executable not found. Check installation path or CHROME_BINARY_LOCATION env var.",
                    is_error=True,
                )
            elif "permission denied" in err_str:
                status_callback(
                    "Permission error accessing ChromeDriver. Check file permissions.",
                    is_error=True,
                )
            elif "unable to discover open window" in err_str:
                status_callback(
                    "Browser window issue. Try updating Chrome/ChromeDriver or running without --headless.",
                    is_error=True,
                )  # added specific error
            # Handle webdriver-manager specific errors
            elif (
                "max retries exceeded with url" in err_str
                or "could not get version for chrome" in err_str
                or "there is no such driver" in err_str
            ):
                status_callback(
                    f"Error managing ChromeDriver: {err_str}. Check internet connection or Chrome installation.",
                    is_error=True,
                )
            return None  # Crucial: stop if driver fails

        status_callback(f"Navigating to {url}...")
        driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)
        driver.get(url)

        status_callback("Waiting for clip elements to load...")
        try:
            # Wait for at least one clip element to be present
            WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.clip-tp[data-litebox]")
                )
            )
            status_callback("Clip elements likely loaded.", tag="info")  # changed tag
        except TimeoutException:
            # Don't fail immediately, maybe the page loaded but the specific selector isn't quite right
            # or no clips exist. We'll check the page source anyway.
            status_callback(
                "Timed out waiting for specific clip elements, proceeding with page source.",
                tag="warning",
            )  # changed tag

        status_callback("Extracting page source...")
        html_content = driver.page_source

        status_callback("Parsing HTML for clips...")
        clip_urls = extract_clip_urls_from_html(html_content)

        if not clip_urls:
            status_callback(
                "No clip URLs found on the page.", tag="warning"
            )  # changed tag

        # Check for specific error messages in the page content
        if "Channel not found" in html_content:
            status_callback("TwitchTracker error: Channel not found.", is_error=True)
        elif "No clips found for specified period" in html_content:
            # This isn't necessarily an error, just no clips found for the date
            status_callback(
                "TwitchTracker: No clips found for the specified date.", tag="info"
            )  # changed tag

        return clip_urls  # Return list (possibly empty)

    except WebDriverException as e:
        # Handle network errors, browser crashes, etc.
        error_msg = f"WebDriver Error: {e}"
        err_str = str(e).lower()
        if "net::err_name_not_resolved" in err_str:
            error_msg += "\nCheck your internet connection or the URL."
        elif "unable to connect to renderer" in err_str:
            error_msg += "\n(Browser crashed or failed to start. Try running without --headless?)"
        elif "failed to wait for extension background page to load" in err_str:
            error_msg += "\n(Issue with Chrome extensions. Try disabling them or using a clean profile.)"
        elif "timed out receiving message from renderer" in err_str:
            error_msg += "\n(Browser communication timeout. System might be under heavy load.)"  # added specific error
        status_callback(error_msg, is_error=True)
        return None  # Indicate failure
    except TimeoutException:
        # This catches the page load timeout specifically
        status_callback(
            f"Page load timed out after {SELENIUM_PAGE_LOAD_TIMEOUT} seconds. The website might be down or slow.",
            is_error=True,
        )
        return None  # Indicate failure
    except Exception as e:
        # Catch-all for other unexpected errors during Selenium operation
        # Check for webdriver-manager errors again, in case they happen later
        err_str = str(e).lower()
        if (
            "max retries exceeded with url" in err_str
            or "could not get version for chrome" in err_str
            or "there is no such driver" in err_str
        ):
            status_callback(
                f"Error managing ChromeDriver: {e}. Check internet connection or Chrome installation.",
                is_error=True,
            )
        else:
            status_callback(
                f"An unexpected error occurred during Selenium operation: {e}",
                is_error=True,
            )
        return None  # Indicate failure
    finally:
        if driver:
            status_callback("Closing WebDriver...")
            try:
                driver.quit()
            except Exception as driver_quit_err:
                status_callback(
                    f"Error closing WebDriver: {driver_quit_err}", is_error=True
                )  # log error on quit
        if service and service.process:
            # Ensure the chromedriver process is stopped
            try:
                service.stop()
            except Exception as service_stop_err:
                status_callback(
                    f"Could not stop ChromeDriver service cleanly: {service_stop_err}",
                    is_error=True,
                )  # log error on stop

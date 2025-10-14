#!/usr/bin/env python3
# snap_ferry_watch.py

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from PIL import Image, PngImagePlugin  # Added import

# --- Configuration ---
CHROMEDRIVER_PATH = '/usr/bin/chromedriver'
SCREENSHOT_DIR = '/home/masmith8/ferry_project/dev1/output/screenshots'
URL = "https://www.calmac.co.uk/en-gb/service-status/#/service-status"

# Cleanup options
CLEANUP_OLD_SCREENSHOTS = True  # Set to False to disable cleanup
DELETE_OLDER_THAN_HOURS = 24    # Files older than this are deleted, but at least one stays

# Ensure screenshot directory exists
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def cleanup_old_screenshots(directory, max_age_hours):
    """Delete .png files older than the given number of hours, keeping at least one newest."""
    now = time.time()
    cutoff = now - (max_age_hours * 3600)

    # Collect all .png files with modification times
    png_files = [
        (f, os.path.getmtime(os.path.join(directory, f)))
        for f in os.listdir(directory)
        if f.lower().endswith(".png")
    ]

    if not png_files:
        print("[INFO] No screenshots found to clean up.")
        return

    # Sort newest → oldest
    png_files.sort(key=lambda x: x[1], reverse=True)

    # Keep the newest file no matter what
    files_to_check = png_files[1:]  # skip the most recent one
    deleted_files = 0

    for filename, mtime in files_to_check:
        file_path = os.path.join(directory, filename)
        if mtime < cutoff:
            try:
                os.remove(file_path)
                deleted_files += 1
                print(f"[INFO] Deleted old screenshot: {filename}")
            except Exception as e:
                print(f"[WARNING] Could not delete {filename}: {e}")

    print(f"[INFO] Cleanup complete — {deleted_files} old screenshots deleted (kept latest one).")


def screenshot_fullpage_cropped():
    local_time = datetime.now(ZoneInfo('Europe/London'))
    timestamp_str = local_time.strftime("%Y%m%d_%H%M%S")
    print("[INFO] Local Start Time:", timestamp_str)

    start_time = time.time()  # Track start time

    # Run cleanup first (if enabled)
    if CLEANUP_OLD_SCREENSHOTS:
        print(f"[INFO] Cleaning up screenshots older than {DELETE_OLDER_THAN_HOURS} hours...")
        cleanup_old_screenshots(SCREENSHOT_DIR, DELETE_OLDER_THAN_HOURS)

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--window-size=2500,1080")  # wide display
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-extensions")

    service = Service(CHROMEDRIVER_PATH)
    driver = None

    try:
        print("[INFO] Launching headless Chrome browser")
        driver = webdriver.Chrome(service=service, options=options)

        print(f"[INFO] Navigating to {URL}")
        driver.get(URL)
        time.sleep(1.5)  # allow JS to render

        # Get full page height
        scroll_height = driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, "
            "document.body.offsetHeight, document.documentElement.offsetHeight);"
        )
        print(f"[DEBUG] Full page scroll height: {scroll_height}")

        # Resize window to full height
        driver.set_window_size(2500, scroll_height)
        time.sleep(1)

        # Temporary screenshot
        temp_path = os.path.join(SCREENSHOT_DIR, "temp_screenshot.png")
        driver.save_screenshot(temp_path)
        print("[INFO] Temporary screenshot taken")

        # Crop with Pillow
        img = Image.open(temp_path)
        left = 606
        upper = 550
        right = img.width - 1343
        lower = img.height - 600
        cropped_img = img.crop((left, upper, right, lower))

        # Save final cropped image
        screenshot_filename = os.path.join(
            SCREENSHOT_DIR,
            f"ferry_service_status_snap_{timestamp_str}.png"
        )

        runtime = time.time() - start_time  # Measure runtime
        runtime_str = f"{runtime:.2f} Seconds"

        # Add metadata
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Source", URL)
        metadata.add_text("Runtime", runtime_str)

        cropped_img.save(screenshot_filename, pnginfo=metadata)
        print(f"[INFO] Saved cropped screenshot to {screenshot_filename}")
        print(f"[INFO] Metadata written — Source: {URL}, Runtime: {runtime_str}")

        # Remove temp file
        os.remove(temp_path)

    except Exception as e:
        print(f"[ERROR] Exception occurred: {e}")

    finally:
        if driver:
            try:
                driver.quit()
                print("[INFO] Browser closed")
            except Exception as quit_error:
                print(f"[WARNING] Failed to quit driver cleanly: {quit_error}")


if __name__ == "__main__":
    screenshot_fullpage_cropped()

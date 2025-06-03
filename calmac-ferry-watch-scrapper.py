#!/usr/bin/env python3
# calmac-ferry-watch-scrapper.py

import yaml
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException

CHROMEDRIVER_PATH = '/usr/bin/chromedriver'
YAML_FILE_PATH = '/home/masmith8/ferry_project/dev/ferry_routes_master_named.yaml'
OUTPUT_PATH = '/home/masmith8/ferry_project/dev/output/ferrystatus.json'

local_time = datetime.now(ZoneInfo('Europe/London'))
timestamp_str = local_time.strftime("%H:%M:%S %d-%m-%Y")
print("[INFO] Local Start Time:", timestamp_str)

SEARCH_TERMS = {
    "Cancelled": "Red",
    "One or more sailings are disrupted": "Amber",
    "Be aware / At risk": "Amber",
    "Normal service": "Green"
}

def load_routes_from_yaml(yaml_path):
    print(f"[INFO] Loading routes from YAML file: {yaml_path}")
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    routes = []
    for route in data.get('Routes', []):
        if route.get('Name') and route.get('Status_URL'):
            routes.append({
                "ID": route.get('ID'),
                "Name": route.get('Name'),
                "Status_URL": route.get('Status_URL')
            })
        else:
            print(f"[WARNING] Skipping invalid route entry: {route}")
    print(f"[INFO] Loaded {len(routes)} routes from YAML")
    return routes

def check_ferry_status():
    print("[INFO] Starting ferry status check")
    start_time = time.time()

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    service = Service(CHROMEDRIVER_PATH)
    driver = None
    log_entry = {
        "timestamp": timestamp_str,
        "routes": [],
        "execution_time_seconds": None
    }

    results_summary = []  # For end-of-script display

    try:
        ROUTES = load_routes_from_yaml(YAML_FILE_PATH)

        print("[INFO] Launching headless Chrome browser")
        driver = webdriver.Chrome(service=service, options=options)

        for route in ROUTES:
            print(f"[INFO] Checking route: {route['Name']}")
            url = route['Status_URL']
            print(f"[DEBUG] Navigating to URL: {url}")

            status_text = "Unknown"
            error_message = ""
            page_load_success = True

            try:
                driver.set_page_load_timeout(10)
                driver.get(url)
                time.sleep(0.5)

                try:
                    status_element = driver.find_element("css selector", "span.sailingStatus")
                    status_text = status_element.text.strip()
                    print(f"[DEBUG] Found status text: '{status_text}'")

                    if status_text not in SEARCH_TERMS:
                        error_message = f"Unexpected status text: '{status_text}'"

                except Exception as inner_e:
                    error_message = f"Status element not found: {inner_e}"
                    page_load_success = False

            except TimeoutException:
                error_message = "Page load timeout exceeded"
                page_load_success = False

            except Exception as e:
                error_message = f"General error during navigation: {e}"
                page_load_success = False

            status_color = SEARCH_TERMS.get(status_text, "Unknown")

            # Store result summary for later display
            # Calculate max route name length once (move this to the top of check_ferry_status)
            max_name_length = max(len(r["Name"]) for r in ROUTES)

            # Later inside the loop, format each result line
            name_with_dashes = f"{route['Name']} ".ljust(max_name_length+2, '-')
            result_line = f"[RESULT] {route['ID']:>3}: {name_with_dashes} {status_text}"
            results_summary.append(result_line)

            log_entry["routes"].append({
                "ID": route["ID"],
                "Name": route["Name"],
                "Status_Color": status_color,
                "Exact_Text_Found": status_text,
                "Error": error_message if error_message else None,
                "Page_Load_Success": page_load_success
            })

    except Exception as e:
        print(f"[ERROR] Exception occurred: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

    finally:
        if driver:
            try:
                driver.quit()
                print("[INFO] Browser closed")
            except Exception as quit_error:
                print(f"[WARNING] Failed to quit driver cleanly: {quit_error}")

    end_time = time.time()
    log_entry["execution_time_seconds"] = round(end_time - start_time, 2)
    print("[INFO] Execution Time:", log_entry["execution_time_seconds"], "seconds")

    try:
        existing_log = []
        try:
            with open(OUTPUT_PATH, 'r') as f:
                existing_log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        existing_log.insert(0, log_entry)

        with open(OUTPUT_PATH, 'w') as f:
            json.dump(existing_log, f, indent=4)

        print(f"[INFO] Appended log entry to {OUTPUT_PATH}")

    except Exception as write_error:
        print(f"[ERROR] Failed to write output: {write_error}")

    # Print all collected results at the end
    print("\n[RESULT] Route Status Results:")
    for result in results_summary:
        print(result)

    return log_entry

if __name__ == "__main__":
    check_ferry_status()

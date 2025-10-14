#!/usr/bin/env python3
# peek_ferry_watch.py
# Automatically uses the most recent screenshot in folder

script_name = "peek_ferry_watch.py"

from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw
import pytesseract
import re
import os
import time
import json
from datetime import datetime
import pytz
import sys
import platform

# --- JSON MESSAGES ---
json_message = "No Message"
source_name = "Caledonian MacBrayne"
script_name = "peek_ferry_watch.py"
python_version = sys.version.split()[0]
host_name = platform.node()

# --- CONFIGURATION FLAGS ---
ENABLE_DEBUG_DRAW = True
ENABLE_DEBUG_SAVE = True
ENABLE_VERBOSE = True
ENABLE_CONTRAST = True

# --- JSON RETENTION CONFIG ---
DELETE_JSON_OLDER_THAN_HOURS = 0.2  # Edit this as needed (minimum 1 record always kept)

# --- START TIMER ---
start_time = time.time()

# --- FILE PATHS ---
SCREENSHOT_DIR = '/home/masmith8/ferry_project/dev1/output/screenshots'
DEBUG_SAVE_PATH = '/home/masmith8/ferry_project/dev1/output/screenshots/debug/debug_colourid_ocr.png'
JSON_SAVE_PATH = '/home/masmith8/ferry_project/dev1/output/allferrystatus.json'
X = 500  # column to scan

# --- COLOUR DEFINITIONS ---
COLOR_TAGS = {
    (152, 138, 140): ("Red", "Cancelled"),
    (152, 140, 132): ("Amber", "Disruptions"),
    (153, 146, 111): ("Amber", "Possible Disruptions"),
    (132, 145, 131): ("Green", "Normal Service")
}

GREY_COLOR = (153, 153, 153)

# OCR box dimensions
OCR_BOX_1 = {"distance_above": 71, "box_x": 55, "box_width": 445, "box_height": 28}
OCR_BOX_2 = {"distance_above": 118, "box_x": 55, "box_width": 445, "box_height": 75}


# --- FIND MOST RECENT SCREENSHOT ---
def get_latest_screenshot(folder):
    folder_path = Path(folder)
    # generator expression to avoid building a full list
    png_files = (f for f in folder_path.glob("*.png") if f.is_file())
    try:
        latest_file = max(png_files, key=lambda f: f.stat().st_mtime)
    except ValueError:
        raise FileNotFoundError(f"No PNG files found in {folder}")

    mod_time = datetime.fromtimestamp(latest_file.stat().st_mtime, pytz.timezone("Europe/London"))
    return str(latest_file), mod_time


# --- GET IMAGE PATH + TIMESTAMP ---
IMAGE_PATH, IMAGE_TIMESTAMP = get_latest_screenshot(SCREENSHOT_DIR)
timestamp_str = IMAGE_TIMESTAMP.strftime("%Y-%m-%d %H:%M:%S")
if ENABLE_VERBOSE:
    print(f"[INFO] Using latest screenshot: {IMAGE_PATH}")
    print(f"[INFO] File timestamp: {timestamp_str}")

# --- OPEN IMAGES ---
img_colors = Image.open(IMAGE_PATH).convert("RGB")
img_ocr = img_colors.copy()

# Optional contrast enhancement
if ENABLE_CONTRAST:
    enhancer = ImageEnhance.Contrast(img_ocr)
    img_ocr = enhancer.enhance(1.5).convert("RGB")

width, height = img_colors.size
if ENABLE_VERBOSE:
    print(f"[INFO] Image loaded: {IMAGE_PATH} ({width}x{height})")

# --- SCAN BOTTOM-UP FOR MAIN BANDS ---
groups = []
y = height - 1
in_match = False
group_start = None
current_tag = None
prev_y = y

while y >= 0:
    pixel = img_colors.getpixel((X, y))
    rgb = pixel[:3]
    tag = COLOR_TAGS.get(rgb, None)

    if tag:
        if not in_match:
            in_match = True
            group_start = y
            current_tag = tag
    else:
        if in_match:
            groups.append((group_start, prev_y, current_tag))
            in_match = False
    prev_y = y
    y -= 1

if in_match:
    groups.append((group_start, 0, current_tag))

# --- CHECK FOR GREY RANGES ABOVE EACH GROUP ---
extended_groups = []
for (start_y, end_y, tag,) in groups:
    grey_start = None
    grey_end = None
    y = end_y - 1
    while y >= 0:
        pixel = img_colors.getpixel((X, y))
        if pixel[:3] == GREY_COLOR:
            if grey_end is None:
                grey_end = y
            grey_start = y
            y -= 1
        else:
            break
    grey_height = None
    if grey_start is not None and grey_end is not None:
        grey_height = abs(grey_start - grey_end) + 1
    extended_groups.append((start_y, end_y, tag, grey_start, grey_end, grey_height))

# --- DEBUG IMAGE SETUP ---
debug_img = img_ocr.copy() if ENABLE_DEBUG_DRAW else None
draw = ImageDraw.Draw(debug_img) if ENABLE_DEBUG_DRAW else None

# --- UK Local Time ---
uk_tz = pytz.timezone("Europe/London")
timestamp_now = datetime.now(uk_tz).strftime("%Y-%m-%d %H:%M:%S")
checked_now = datetime.now(uk_tz).strftime("%Y-%m-%d %H:%M:%S")

# --- OCR PROCESSING ---
if ENABLE_VERBOSE:
    print("\n[RESULTS] Colour match groups with grey ranges and OCR (bottom-up):\n")

routes = []
seen_routes = set()
duplicate_found = False

for i, (start_y, end_y, tag, grey_start, grey_end, grey_height) in enumerate(extended_groups):
    colour, adjective = tag

    if ENABLE_VERBOSE:
        print(f"{i+1}. {colour} - {adjective}: start_y={start_y}, end_y={end_y}, "
              f"grey_start={grey_start}, grey_end={grey_end}, grey_height={grey_height}")

    if grey_height is not None:
        params = OCR_BOX_1 if grey_height < 130 else OCR_BOX_2
        if ENABLE_VERBOSE:
            print(f"   Using OCR Box {'1' if grey_height < 130 else '2'}")

        top = max(0, end_y - params["distance_above"])
        left = params["box_x"]
        right = left + params["box_width"]
        bottom = top + params["box_height"]
        ocr_box = (left, top, right, bottom)

        if ENABLE_VERBOSE:
            print(f"   OCR box: start=({left},{top}), size=({params['box_width']}x{params['box_height']})")

        if ENABLE_DEBUG_DRAW:
            draw.rectangle([(left, top), (right, bottom)], outline="blue", width=2)
            draw.line([(0, start_y), (width, start_y)], fill="green", width=2)
            if grey_start is not None:
                draw.line([(0, grey_start), (width, grey_start)], fill="green", width=2)
            if grey_end is not None:
                draw.line([(0, grey_end), (width, grey_end)], fill="green", width=2)

        cropped_img = img_ocr.crop(ocr_box)
        ocr_text = pytesseract.image_to_string(cropped_img)

        if ENABLE_VERBOSE:
            print(f"   OCR before cleanup:\n{ocr_text.strip()}")

        lines = [line for line in ocr_text.splitlines() if line.strip()]
        lines = [line for idx, line in enumerate(lines) if idx not in (1, 3)]
        processed_text = " ".join(lines)

        before_symbols = processed_text
        processed_text = re.sub(r"[^\w\s\-\(\)]", "-", processed_text)
        processed_text = re.sub(r"-{2,}", "-", processed_text)

        if ENABLE_VERBOSE:
            print(f"   Symbols before: {before_symbols}")
            print(f"   Symbols after:  {processed_text}\n")

        if processed_text in seen_routes:
            if ENABLE_VERBOSE:
                print(f"[INFO] Duplicate route '{processed_text}' found — stopping OCR early.")
            duplicate_found = True
            break

        seen_routes.add(processed_text)
        routes.append((processed_text, colour, adjective))
    else:
        if ENABLE_VERBOSE:
            print("   No grey band found, skipping OCR.\n")

# --- SAVE DEBUG IMAGE ---
if ENABLE_DEBUG_SAVE and ENABLE_DEBUG_DRAW:
    try:
        debug_img.save(DEBUG_SAVE_PATH)
        print(f"\n[DEBUG] Saved debug image -> {os.path.abspath(DEBUG_SAVE_PATH)}")
    except Exception as e:
        print(f"[ERROR] Failed to save debug image: {e}")

# --- DEDUPLICATION + SORTING ---
unique_routes = sorted(list({r[0]: r for r in routes}.values()), key=lambda x: x[0])

# --- RESULTS OUTPUT ---
print("\n[FINAL RESULTS - SORTED ROUTES]:\n")
for idx, (route, colour, adjective) in enumerate(unique_routes, start=1):
    is_dup = "Y" if routes.count((route, colour, adjective)) > 1 else "N"
    route_name = route.ljust(50, "-")
    colour_name = colour.ljust(10, "-")
    adj_name = adjective.ljust(30, "-")
    dup_name = is_dup
    print(f"Route {idx}: {route_name} {colour_name} {adj_name} {dup_name}")

# --- TIME DIFFERENCE ---
screenshot_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
generation_dt = datetime.strptime(checked_now, "%Y-%m-%d %H:%M:%S")
diff = generation_dt - screenshot_dt
diff_seconds = diff.total_seconds()
hours, remainder = divmod(diff_seconds, 3600)
minutes, seconds = divmod(remainder, 60)
diff_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

# --- TIME CODE ---
time_code = datetime.now(uk_tz).strftime("%Z")

# --- SAVE JSON (NEWEST FIRST) ---
try:
    with Image.open(IMAGE_PATH) as im:
        metadata = im.text
        source_meta = metadata.get("Source", "Unknown")
        runtime_meta = metadata.get("Runtime", "Unknown")
except Exception as e:
    print(f"[WARNING] Could not read PNG metadata: {e}")
    source_meta = "Unknown"
    runtime_meta = "Unknown"

# Count routes
routes_identified_count = len(unique_routes)

# --- READ EXISTING JSON ---
if os.path.exists(JSON_SAVE_PATH):
    with open(JSON_SAVE_PATH, "r", encoding="utf-8") as f:
        try:
            existing_data = json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to parse existing JSON, resetting file: {e}")
            existing_data = []
else:
    existing_data = []

# --- CLEANUP OLD JSON ENTRIES ---
if existing_data:
    try:
        cutoff_time = time.time() - (DELETE_JSON_OLDER_THAN_HOURS * 3600)
        filtered_data = []
        for entry in existing_data:
            ts_str = entry.get("Generation_Timestamp")
            try:
                entry_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=pytz.timezone("Europe/London")
                )
                if entry_time.timestamp() > cutoff_time:
                    filtered_data.append(entry)
            except Exception:
                filtered_data.append(entry)

        if not filtered_data and existing_data:
            filtered_data.append(existing_data[0])

        deleted_count = len(existing_data) - len(filtered_data)
        existing_data = filtered_data

        if deleted_count > 0:
            print(f"[INFO] Deleted {deleted_count} old JSON record(s) older than {DELETE_JSON_OLDER_THAN_HOURS} hours.")
    except Exception as e:
        print(f"[WARNING] JSON cleanup failed: {e}")

# --- BUILD NEW JSON ENTRY ---
json_entry = {
    "Host_Name": host_name,
    "Python_Script_Name": script_name,
    "Python_Version": python_version,
    "Orginal_Source_Name": source_name,
    "Screenshot_Source": source_meta,
    "Screenshot_Filename": os.path.basename(IMAGE_PATH),
    "Image_Capture_Time": runtime_meta,
    "Screenshot_Timestamp": timestamp_str,
    "Generation_Timestamp": checked_now,
    "Time Code": time_code,
    "Processing_Delta": diff_str,
    "Script_Run_Time": f"{round(time.time() - start_time, 2)} Seconds",
    "Routes_Identified": str(routes_identified_count),
    "Message": json_message,
    "Route_Statuses": []
}

for (route, colour, adjective) in unique_routes:
    json_entry["Route_Statuses"].append({
        "Route": route,
        "Status_Color": colour,
        "Status_Words": adjective
    })

# --- INSERT NEW ENTRY ---
existing_data.insert(0, json_entry)

# --- ADD RECORD COUNTS ---
total_records = len(existing_data)
for i, entry in enumerate(existing_data, start=1):
    entry["Record_Position     "] = f"Record {i} of {total_records}"

# --- SAVE BACK ---
with open(JSON_SAVE_PATH, "w", encoding="utf-8") as f:
    json.dump(existing_data, f, indent=4)
    print(f"\n[INFO] Saved JSON results -> {os.path.abspath(JSON_SAVE_PATH)}")
    print(f"[INFO] JSON now contains {total_records} record(s).")

# --- TIMER END ---
end_time = time.time()
total_time = end_time - start_time
print(f"\n[INFO] Processing complete. Total groups: {len(extended_groups)}")
print(f"[INFO] Total script runtime: {total_time:.2f} seconds")

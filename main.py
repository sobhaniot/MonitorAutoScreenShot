import mss
import mss.tools
import schedule
import time
from datetime import datetime
import os

# Configuration
SCREENSHOT_DIR = 'screenshots'
MAX_SIZE_GB = 2
MAX_SIZE_BYTES = MAX_SIZE_GB * 1024 * 1024 * 1024  # Convert GB to Bytes

def manage_storage():
    if not os.path.exists(SCREENSHOT_DIR):
        return

    # Get list of all files with full path and creation time
    files = []
    for f in os.listdir(SCREENSHOT_DIR):
        full_path = os.path.join(SCREENSHOT_DIR, f)
        if os.path.isfile(full_path):
            files.append((full_path, os.path.getctime(full_path)))

    # Sort files by time (oldest to newest)
    files.sort(key=lambda x: x[1])

    # Calculate current total size of the directory
    total_size = sum(os.path.getsize(f[0]) for f in files)

    if total_size > MAX_SIZE_BYTES:
        print(f"Directory size ({total_size / (1024 ** 3):.2f} GB) exceeds limit. Starting cleanup...")

        for file_path, _ in files:
            if total_size <= MAX_SIZE_BYTES:
                break

            file_size = os.path.getsize(file_path)
            os.remove(file_path)
            total_size -= file_size
            print(f"Deleted old file: {os.path.basename(file_path)}")

        print("Cleanup complete. Storage usage is now under 2 GB.")

def take_screenshots():
    # Create directory for screenshots if it doesn't exist
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)

    with mss.mss() as sct:
        # Get list of monitors
        # sct.monitors[0] is the "all-in-one" monitor, so we use [1:] for individual ones
        for i, monitor in enumerate(sct.monitors[1:], 1):
            # Capture the screen of monitor i
            sct_img = sct.grab(monitor)

            # Generate filename
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{SCREENSHOT_DIR}/{timestamp}_M_{i}.png"

            # Save file using mss internal tools
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=filename)
            print(f"Screenshot saved from Monitor {i}: {filename}")

# Scheduling tasks
schedule.every(10).minutes.do(take_screenshots)
schedule.every().day.at("00:00").do(manage_storage) # Check storage once a day at midnight

print("Program started successfully.")
print(f"Storage monitoring active (Max limit: {MAX_SIZE_GB} GB).")

# Initial execution to ensure it's working
take_screenshots()
manage_storage()

while True:
    schedule.run_pending()
    time.sleep(1)
import os
import datetime
from memory.vector_memory import store_memory


def generate_filename(prefix="screenshot", extension=".png"):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}{extension}"


def take_screenshot(filename=None):
    try:
        import pyautogui

        if not filename:
            filename = generate_filename()

        screenshot = pyautogui.screenshot()
        screenshot.save(filename)

        full_path = os.path.abspath(filename)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        store_memory(
            f"Screenshot taken: {filename}",
            {
                "type": "screenshot",
                "path": full_path,
                "time": timestamp
            }
        )

        return (
            "SCREENSHOT TAKEN\n\n"
            f"File: {filename}\n"
            f"Saved at: {full_path}\n"
            f"Time: {timestamp}\n\n"
            "Screenshot captured successfully."
        )

    except ImportError:
        return "Screenshot requires pyautogui. Run: pip install pyautogui"
    except Exception as e:
        return f"Could not take screenshot: {str(e)}"


def take_region_screenshot(x, y, width, height, filename=None):
    try:
        import pyautogui

        if not filename:
            filename = generate_filename(prefix="region")

        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        screenshot.save(filename)

        full_path = os.path.abspath(filename)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        store_memory(
            f"Region screenshot taken: {filename}",
            {
                "type": "screenshot",
                "mode": "region",
                "path": full_path,
                "time": timestamp
            }
        )

        return (
            "REGION SCREENSHOT TAKEN\n\n"
            f"File: {filename}\n"
            f"Area: ({x}, {y}, {width}, {height})\n"
            f"Saved at: {full_path}\n"
            f"Time: {timestamp}"
        )

    except ImportError:
        return "Screenshot requires pyautogui. Run: pip install pyautogui"
    except Exception as e:
        return f"Could not take region screenshot: {str(e)}"


def list_recent_screenshots(directory="."):
    try:
        files = [
            f for f in os.listdir(directory)
            if f.lower().endswith(".png") and "screenshot" in f
        ]

        if not files:
            return "No screenshots found."

        files = sorted(files, reverse=True)[:10]

        result = "RECENT SCREENSHOTS\n\n"
        for f in files:
            path = os.path.abspath(os.path.join(directory, f))
            result += f"{f}\n{path}\n\n"

        return result.strip()

    except Exception as e:
        return f"Could not list screenshots: {str(e)}"
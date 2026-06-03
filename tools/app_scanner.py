import os
from pathlib import Path

START_MENU_PATHS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
]

def scan_installed_apps() -> list[dict]:
    apps = []
    seen = set()
    for start_path in START_MENU_PATHS:
        if not start_path.exists():
            continue
        for lnk in start_path.rglob("*.lnk"):
            name = lnk.stem
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            apps.append({
                "app_id": name.lower(),
                "display_name": name,
                "shortcut_path": str(lnk)
            })
    return apps

def launch_any_app(user_command: str) -> dict:
    apps = scan_installed_apps()
    command_lower = user_command.lower()
    best_match = None

    for app in apps:
        if app["app_id"] in command_lower:
            best_match = app
            break

    if not best_match:
        words = [w for w in command_lower.split() if len(w) > 2]
        for word in words:
            for app in apps:
                if word in app["app_id"]:
                    best_match = app
                    break
            if best_match:
                break

    if not best_match:
        return {
            "success": False,
            "message": "I couldn't find that app on your laptop."
        }

    try:
        os.startfile(best_match["shortcut_path"])
        return {
            "success": True,
            "message": f"Opening {best_match['display_name']}."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Found {best_match['display_name']} but couldn't open it: {str(e)}"
        }
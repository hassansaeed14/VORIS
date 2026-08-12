from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from tools.app_scanner import launch_any_app

SUPPORTED_APPLICATIONS: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "label": "Chrome",
        "reply_name": "chrome",
        "aliases": ("chrome", "google chrome"),
        "path_candidates": (
            ("PROGRAMFILES", "Google", "Chrome", "Application", "chrome.exe"),
            ("PROGRAMFILES(X86)", "Google", "Chrome", "Application", "chrome.exe"),
            ("LOCALAPPDATA", "Google", "Chrome", "Application", "chrome.exe"),
        ),
        "which_candidates": ("chrome.exe", "chrome"),
        "allowed_basenames": {"chrome.exe", "chrome"},
    },
    "notepad": {
        "label": "Notepad",
        "reply_name": "notepad",
        "aliases": ("notepad",),
        "path_candidates": (
            ("WINDIR", "System32", "notepad.exe"),
        ),
        "which_candidates": ("notepad.exe", "notepad"),
        "allowed_basenames": {"notepad.exe", "notepad"},
    },
    "calculator": {
        "label": "Calculator",
        "reply_name": "calculator",
        "aliases": ("calculator", "calc"),
        "path_candidates": (
            ("WINDIR", "System32", "calc.exe"),
        ),
        "which_candidates": ("calc.exe", "calc"),
        "allowed_basenames": {"calc.exe", "calc"},
    },
    "vs code": {
        "label": "VS Code",
        "reply_name": "vs code",
        "aliases": ("vs code", "vscode", "visual studio code"),
        "path_candidates": (
            ("LOCALAPPDATA", "Programs", "Microsoft VS Code", "Code.exe"),
            ("PROGRAMFILES", "Microsoft VS Code", "Code.exe"),
            ("PROGRAMFILES(X86)", "Microsoft VS Code", "Code.exe"),
        ),
        "which_candidates": ("Code.exe", "code"),
        "allowed_basenames": {"code.exe", "code"},
    },
}

_ALIAS_TO_APPLICATION: Dict[str, str] = {
    alias: app_name
    for app_name, spec in SUPPORTED_APPLICATIONS.items()
    for alias in spec["aliases"]
}


def list_supported_applications() -> List[str]:
    return list(SUPPORTED_APPLICATIONS.keys())


def normalize_application_name(app_name: str | None) -> Optional[str]:
    normalized = " ".join(str(app_name or "").strip().lower().split())
    if not normalized:
        return None
    return _ALIAS_TO_APPLICATION.get(normalized)


def get_application_label(app_name: str | None) -> Optional[str]:
    normalized = normalize_application_name(app_name)
    if not normalized:
        return None
    return str(SUPPORTED_APPLICATIONS[normalized]["label"])


def _path_candidate(env_var: str, *parts: str) -> Optional[str]:
    base = str(os.environ.get(env_var, "") or "").strip()
    if not base:
        return None
    return str(Path(base, *parts))


def _validated_which_path(candidate: str, allowed_basenames: set[str]) -> Optional[str]:
    resolved = shutil.which(candidate)
    if not resolved:
        return None
    basename = Path(resolved).name.lower()
    if basename not in allowed_basenames:
        return None
    if basename == "code":
        code_exe = Path(resolved).resolve().parent.parent / "Code.exe"
        if code_exe.exists():
            return str(code_exe)
    return resolved


def _iter_launch_commands(spec: Dict[str, Any]) -> Iterable[List[str]]:
    seen: set[str] = set()
    for env_var, *parts in spec.get("path_candidates", ()):
        candidate = _path_candidate(env_var, *parts)
        if candidate and Path(candidate).exists():
            normalized = str(Path(candidate).resolve()).lower()
            if normalized not in seen:
                seen.add(normalized)
                yield [candidate]

    allowed_basenames = set(spec.get("allowed_basenames", set()))
    for executable_name in spec.get("which_candidates", ()):
        resolved = _validated_which_path(executable_name, allowed_basenames)
        if not resolved:
            continue
        normalized = str(Path(resolved).resolve()).lower()
        if normalized not in seen:
            seen.add(normalized)
            yield [resolved]


def _resolve_launch_command(spec: Dict[str, Any]) -> Optional[List[str]]:
    for command in _iter_launch_commands(spec):
        return list(command)
    return None


def get_supported_desktop_apps() -> List[Dict[str, Any]]:
    apps: List[Dict[str, Any]] = []
    for app_id, spec in SUPPORTED_APPLICATIONS.items():
        command = _resolve_launch_command(spec)
        apps.append(
            {
                "app_id": app_id,
                "display_name": spec["label"],
                "aliases": list(spec["aliases"]),
                "available": bool(command),
                "status": "available" if command else "unavailable",
            }
        )
    return apps


def get_application_availability(app_name: str | None) -> Dict[str, Any]:
    normalized = normalize_application_name(app_name)
    if not normalized:
        return {
            "supported": False,
            "available": False,
            "status": "unsupported",
            "app_name": None,
            "label": None,
            "launch_command": None,
        }

    spec = SUPPORTED_APPLICATIONS[normalized]
    command = _resolve_launch_command(spec)
    return {
        "supported": True,
        "available": bool(command),
        "status": "available" if command else "unavailable",
        "app_name": normalized,
        "label": spec["label"],
        "aliases": list(spec["aliases"]),
        "launch_command": command,
    }


def open_application(app_name: str | None) -> Dict[str, Any]:
    availability = get_application_availability(app_name)
    normalized = availability.get("app_name")
    if not availability.get("supported"):
        from tools.app_scanner import launch_any_app

        scanner_result = launch_any_app(app_name)
        if scanner_result["success"]:
            return {
                "success": True,
                "status": "opened",
                "app_name": app_name,
                "label": app_name,
                "message": scanner_result["message"],
            }
        return {
            "success": False,
            "status": "unsupported",
            "app_name": None,
            "message": "I can't open that yet.",
            "error": "Unsupported desktop application.",
        }
    label = str(availability.get("label") or normalized or "That app")
    launch_command = availability.get("launch_command")
    if not launch_command:
        return {
            "success": False,
            "status": "unavailable",
            "app_name": normalized,
            "label": label,
            "message": f"I couldn't find {label} on this system.",
            "error": "Application is not installed or not discoverable from the safe allowlist.",
        }

    try:
        process = subprocess.Popen(launch_command, shell=False)
        return {
            "success": True,
            "status": "opened",
            "app_name": normalized,
            "label": label,
            "launched_with": launch_command[0],
            "pid": process.pid,
            "message": f"Opening {label}.",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "status": "unavailable",
            "app_name": normalized,
            "label": label,
            "message": f"I couldn't find {label} on this system.",
            "error": "Application is not installed or not discoverable from the safe allowlist.",
        }
    except OSError as error:
        error_text = str(error).strip() or "The launch request failed."
        return {
            "success": False,
            "status": "launch_failed",
            "app_name": normalized,
            "label": label,
            "message": f"I couldn't open {label} because the launch failed: {error_text}",
            "error": error_text,
        }


def _sanitize_search_query(query: str | None) -> str:
    text = " ".join(str(query or "").replace("\x00", " ").split())
    return text[:180].strip()


def open_chrome_search(query: str | None) -> Dict[str, Any]:
    safe_query = _sanitize_search_query(query)
    if not safe_query:
        return {
            "success": False,
            "status": "invalid_query",
            "app_name": "chrome",
            "label": "Chrome",
            "message": "I need a search phrase before I can search in Chrome.",
            "error": "Missing search query.",
        }

    availability = get_application_availability("chrome")
    launch_command = availability.get("launch_command")
    if not availability.get("available") or not launch_command:
        return {
            "success": False,
            "status": "unavailable",
            "app_name": "chrome",
            "label": "Chrome",
            "message": "I couldn't find Chrome on this system.",
            "error": "Chrome is not installed or not discoverable from the safe allowlist.",
        }

    search_url = "https://www.google.com/search?" + urlencode({"q": safe_query})
    try:
        process = subprocess.Popen(list(launch_command) + [search_url], shell=False)
        return {
            "success": True,
            "status": "searched",
            "app_name": "chrome",
            "label": "Chrome",
            "query": safe_query,
            "url": search_url,
            "launched_with": launch_command[0],
            "pid": process.pid,
            "message": f"Searching for {safe_query}.",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "status": "unavailable",
            "app_name": "chrome",
            "label": "Chrome",
            "message": "I couldn't find Chrome on this system.",
            "error": "Chrome is not installed or not discoverable from the safe allowlist.",
        }
    except OSError as error:
        error_text = str(error).strip() or "The browser search request failed."
        return {
            "success": False,
            "status": "launch_failed",
            "app_name": "chrome",
            "label": "Chrome",
            "message": f"I couldn't search in Chrome because the launch failed: {error_text}",
            "error": error_text,
        }

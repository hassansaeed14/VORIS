from __future__ import annotations

"""Supported VORIS desktop/web launcher.

This is the runtime source of truth for the current VORIS build:
``run_voris.py`` serves ``api.api_server:app`` through Waitress. Legacy entry
points such as ``main.py`` are not used for the web_v2/FastAPI runtime.
"""

import json
import logging
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from a2wsgi import ASGIMiddleware
from waitress import serve


# --------------------------------------------------
# PATHS
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
SERVER_CONFIG_PATH = CONFIG_DIR / "server.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402  (path must be set first)


# --------------------------------------------------
# DEFAULT CONFIG
# --------------------------------------------------
DEFAULT_SERVER_CONFIG: dict[str, Any] = {
    "host": "0.0.0.0",
    "port": 5000,
    "workers": 4,
    "debug": False,
    "auto_open_browser": True,
}


# --------------------------------------------------
# OUTPUT SAFETY
# --------------------------------------------------
def configure_console_encoding() -> None:
    """Prefer UTF-8 output, but never make boot depend on it."""

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def configure_runtime_logging() -> None:
    """Keep demo logs readable without hiding VORIS's own categorized logs."""

    logging.getLogger("waitress.queue").setLevel(logging.ERROR)


def safe_print(message: Any = "") -> None:
    """Print without allowing console encoding failures to crash startup."""

    text = str(message)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        fallback = text.encode("ascii", "replace").decode("ascii")
        print(fallback, flush=True)


# --------------------------------------------------
# CONFIG LOADER
# --------------------------------------------------
def normalize_server_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_SERVER_CONFIG)
    normalized.update(config)

    try:
        normalized["port"] = int(normalized.get("port", DEFAULT_SERVER_CONFIG["port"]))
    except (TypeError, ValueError):
        safe_print("[Config] Invalid port in server.json. Falling back to 5000.")
        normalized["port"] = DEFAULT_SERVER_CONFIG["port"]
    if not 1 <= int(normalized["port"]) <= 65535:
        safe_print("[Config] Port out of range in server.json. Falling back to 5000.")
        normalized["port"] = DEFAULT_SERVER_CONFIG["port"]

    try:
        workers = int(normalized.get("workers", DEFAULT_SERVER_CONFIG["workers"]))
    except (TypeError, ValueError):
        safe_print("[Config] Invalid worker count in server.json. Falling back to 4.")
        workers = DEFAULT_SERVER_CONFIG["workers"]
    normalized["workers"] = max(1, min(workers, 32))

    host = str(normalized.get("host") or DEFAULT_SERVER_CONFIG["host"]).strip()
    normalized["host"] = host or DEFAULT_SERVER_CONFIG["host"]
    normalized["auto_open_browser"] = bool(
        normalized.get("auto_open_browser", DEFAULT_SERVER_CONFIG["auto_open_browser"])
    )
    return normalized


def load_server_config() -> dict[str, Any]:
    if not SERVER_CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SERVER_CONFIG_PATH.write_text(
            json.dumps(DEFAULT_SERVER_CONFIG, indent=2),
            encoding="utf-8",
        )
        return dict(DEFAULT_SERVER_CONFIG)

    try:
        data = json.loads(SERVER_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_server_config(data)
        safe_print(f"[Config] {SERVER_CONFIG_PATH} is not a JSON object. Using defaults.")
    except Exception as error:
        safe_print(f"[Config] Could not read {SERVER_CONFIG_PATH}: {error}")
        safe_print("[Config] Using safe defaults.")

    return dict(DEFAULT_SERVER_CONFIG)


# --------------------------------------------------
# UTILITIES
# --------------------------------------------------
def build_url(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::"}:
        host = "localhost"
    return f"http://{host}:{port}"


def _probe_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def wait_for_server(host: str, port: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    probe_host = _probe_host(host)

    while time.time() < deadline:
        try:
            with socket.create_connection((probe_host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)

    return False


def is_port_available(host: str, port: int) -> bool:
    bind_host = "" if host in {"0.0.0.0", "::"} else host
    family = socket.AF_INET6 if (host == "::" or ":" in str(host)) else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((bind_host, int(port)))
        except OSError:
            return False
    return True


def open_browser(url: str, host: str, port: int) -> None:
    if wait_for_server(host, port):
        try:
            webbrowser.open(url)
        except Exception as error:
            safe_print(f"[Browser] Could not open browser automatically: {error}")


# --------------------------------------------------
# BOOT UI
# --------------------------------------------------
def describe_provider_readiness() -> tuple[str, str]:
    """Return (status_label, detail_line) describing whether the brain can answer.

    Called by print_boot_banner() so startup tells the truth about whether any
    AI provider is actually usable, instead of always printing "Boot: OK" while
    every real request silently falls through to the degraded path.

    Available inputs (already imported below in this module's scope):
      settings.GROQ_API_KEY        -> str, empty when unset
      settings.SAMBANOVA_API_KEY   -> str, empty when unset
      settings.DEFAULT_REASONING_PROVIDER -> str, e.g. "groq"
      settings.DOTENV_LOADED       -> bool, whether a .env file was found

    Note: a key being present only proves *configured*, never *healthy* -
    provider_hub reserves "healthy" for a key that has passed a live call.
    The banner must not overstate this.

    TODO(hassan): implement. See the trade-offs discussed before writing this.
    """

    raise NotImplementedError("describe_provider_readiness() is not implemented yet")


def print_boot_banner(url: str, config: dict[str, Any]) -> None:
    safe_print()
    safe_print("=" * 55)
    safe_print(" VORIS - Voice-Oriented Responsive Intelligence System")
    safe_print("=" * 55)

    safe_print()
    safe_print("[System Status]")
    safe_print("Runtime       : FastAPI + Waitress")
    safe_print("Entry point   : run_voris.py")
    safe_print("API source    : api.api_server:app")
    safe_print("Mode          : Local Private Runtime")
    safe_print(f"Workers       : {config.get('workers')}")
    safe_print(f"URL           : {url}")

    safe_print()
    safe_print("[Status]")
    safe_print("Boot          : OK")
    safe_print("API           : STARTING")
    safe_print("Interface     : WAITING FOR SERVER")
    try:
        brain_label, brain_detail = describe_provider_readiness()
        safe_print(f"Brain         : {brain_label}")
        if brain_detail:
            safe_print(f"                {brain_detail}")
    except NotImplementedError:
        pass
    safe_print()
    safe_print("VORIS is starting.")
    safe_print()


def print_port_in_use_message(host: str, port: int) -> None:
    safe_print()
    safe_print("[Startup blocked]")
    safe_print(f"Port {port} is already in use on {host}.")
    safe_print("VORIS did not start a second server.")
    safe_print("Stop the existing VORIS process or change config/server.json to use another port.")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main() -> None:
    configure_console_encoding()
    configure_runtime_logging()
    config = load_server_config()

    host = str(config.get("host"))
    port = int(config.get("port"))
    threads = int(config.get("workers"))
    auto_open = bool(config.get("auto_open_browser"))
    url = build_url(host, port)

    if not is_port_available(host, port):
        print_port_in_use_message(host, port)
        raise SystemExit(2)

    print_boot_banner(url, config)

    # Browser opening is deliberately delayed until the server socket answers.
    if auto_open:
        threading.Thread(
            target=open_browser,
            args=(url, host, port),
            daemon=True,
        ).start()

    try:
        from api.api_server import app as fastapi_app

        voris_app = ASGIMiddleware(fastapi_app)
        safe_print(f"[Startup] Serving VORIS on {url}")
        serve(voris_app, host=host, port=port, threads=threads)

    except KeyboardInterrupt:
        safe_print()
        safe_print("[Shutdown] VORIS stopped manually.")

    except Exception as error:
        safe_print()
        safe_print("[CRITICAL ERROR]")
        safe_print(error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(os.getenv("VORIS_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


def get_workspace_snapshot(root: str | Path = PROJECT_ROOT) -> Dict[str, Any]:
    path = Path(root).resolve()
    file_count = 0
    directory_count = 0
    total_bytes = 0

    for item in path.rglob("*"):
        if item.is_dir():
            directory_count += 1
            continue
        file_count += 1
        try:
            total_bytes += item.stat().st_size
        except OSError:
            continue

    usage = shutil.disk_usage(path)
    return {
        "root": str(path),
        "files": file_count,
        "directories": directory_count,
        "workspace_size_bytes": total_bytes,
        "disk_total_bytes": usage.total,
        "disk_used_bytes": usage.used,
        "disk_free_bytes": usage.free,
    }


def get_resource_snapshot() -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cwd": str(Path.cwd()),
    }

    if psutil is not None:
        snapshot["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        snapshot["memory"] = {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_percent": memory.percent,
        }
    else:
        snapshot["cpu_percent"] = None
        snapshot["memory"] = None

    return snapshot


def get_system_snapshot() -> Dict[str, Any]:
    return {
        "system": get_resource_snapshot(),
        "workspace": get_workspace_snapshot(),
        "hostname": platform.node(),
        "processor": platform.processor(),
    }


def summarize_resource_snapshot(snapshot: Dict[str, Any]) -> str:
    memory = snapshot.get("memory") or {}
    cpu_value = snapshot.get("cpu_percent")
    cpu_text = f"{cpu_value:.1f}%" if isinstance(cpu_value, (int, float)) else "N/A"
    memory_text = f"{memory.get('used_percent', 'N/A')}%" if memory else "N/A"
    return (
        f"System resources: CPU {cpu_text}, memory usage {memory_text}, "
        f"platform {snapshot.get('platform', 'unknown')}."
    )


def summarize_system_snapshot(snapshot: Dict[str, Any]) -> str:
    system = snapshot.get("system") or {}
    workspace = snapshot.get("workspace") or {}
    return (
        f"System snapshot ready for {snapshot.get('hostname', 'this device')}. "
        f"Workspace has {workspace.get('files', 0)} files across {workspace.get('directories', 0)} directories. "
        f"{summarize_resource_snapshot(system)}"
    )

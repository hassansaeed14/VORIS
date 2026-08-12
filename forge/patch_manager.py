from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_LOG_PATH = PROJECT_ROOT / "memory" / "aura_forge_patch_log.json"


class PatchManager:
    """Track planned and completed repair work without mutating code automatically."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PATCH_LOG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> List[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _write(self, items: List[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def list_patches(self) -> List[dict[str, Any]]:
        return self._read()

    def record_patch(
        self,
        *,
        summary: str,
        files: Iterable[str],
        status: str = "planned",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()),
            "summary": str(summary or "").strip() or "Unnamed Forge patch",
            "files": [str(path).strip() for path in files if str(path).strip()],
            "status": str(status or "planned").strip().lower(),
            "metadata": dict(metadata or {}),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        items = self._read()
        items.append(record)
        self._write(items)
        return record

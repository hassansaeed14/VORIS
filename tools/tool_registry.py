from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Optional

from tools import (
    browser_tools,
    datetime_tools,
    execution_tools,
    file_tools,
    media_generation,
    process_tools,
    system_tools,
    validation_tools,
)


@dataclass(frozen=True)
class ToolRecord:
    tool_name: str
    action_name: str
    trust_level: str
    capability_mode: str
    required_inputs: tuple[str, ...]
    handler: Callable[..., object]

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["handler"] = self.handler.__name__
        return payload


TOOL_REGISTRY: Dict[str, ToolRecord] = {
    "file.read": ToolRecord("file.read", "file_read", "private", "real", ("path_value",), file_tools.read_file),
    "file.list": ToolRecord("file.list", "file_list", "private", "real", ("path_value",), file_tools.list_directory),
    "file.write": ToolRecord("file.write", "file_write", "sensitive", "real", ("path_value", "content"), file_tools.write_file),
    "file.delete": ToolRecord("file.delete", "file_delete", "critical", "real", ("path_value",), file_tools.delete_file),
    "datetime.parse": ToolRecord("datetime.parse", "datetime_parse", "safe", "real", ("text",), datetime_tools.parse_temporal_entities),
    "validation.url": ToolRecord("validation.url", "validation_url", "safe", "real", ("value",), validation_tools.validate_url),
    "system.snapshot": ToolRecord("system.snapshot", "system_read", "private", "real", (), system_tools.get_system_snapshot),
    "system.resources": ToolRecord("system.resources", "system_read", "private", "real", (), system_tools.get_resource_snapshot),
    "process.list": ToolRecord("process.list", "system_read", "private", "real", (), process_tools.list_processes),
    "browser.search": ToolRecord("browser.search", "web_search", "safe", "real", ("query",), browser_tools.search_query),
    "browser.open": ToolRecord("browser.open", "web_search", "safe", "real", ("value",), browser_tools.open_url),
    "execution.command": ToolRecord("execution.command", "system_control", "critical", "real", ("command",), execution_tools.execute_command),
    # "hybrid": the subprocess path is fully implemented, but it has not been
    # run end to end on this host -- the weights are a ~12GB download that is
    # not present. media_generation.preflight() reports exactly what is
    # missing. Marked real only once a generation has actually completed here.
    "media.image": ToolRecord("media.image", "media_generate", "sensitive", "hybrid", ("prompt",), media_generation.generate_image),
}


def get_tool(tool_name: str | None) -> Optional[ToolRecord]:
    return TOOL_REGISTRY.get(str(tool_name or "").strip().lower())

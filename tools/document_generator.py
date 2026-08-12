from __future__ import annotations

import json
import re
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import uuid4
from xml.sax.saxutils import escape as xml_escape

from brain.response_engine import generate_document_content_payload, stabilize_assignment_content


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = PROJECT_ROOT / "generated"
DEFAULT_RETENTION_HOURS = 24
SUPPORTED_EXPORT_FORMATS = {"txt", "pdf", "docx", "pptx"}
ACCESS_MANIFEST_FILENAME = ".access_manifest.json"
FORMAT_ALIAS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(docx|word)\b", "docx"),
    (r"\b(pdf)\b", "pdf"),
    (r"\b(txt|text file|plain text|text)\b", "txt"),
    (r"\b(pptx|ppt|slides?|presentation|slide deck)\b", "pptx"),
)
FORMAT_TOKEN_PATTERN = r"(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation)"
DOCUMENT_REQUEST_PREFIX = r"^(?:please\s+)?(?:make|create|generate|prepare|give me|write)\b"
DOCUMENT_SESSION_CACHE: dict[str, "DocumentRequest"] = {}
LAST_GENERATED_DOCUMENT: dict[str, dict[str, Any]] = {}
DOCUMENT_STYLE_ALIASES = {
    "professional": "professional",
    "simple": "simple",
    "detailed": "detailed",
}
CITATION_STYLE_ALIASES = {
    "basic": "basic",
    "apa": "apa",
    "mla": "mla",
    "chicago": "chicago",
    "harvard": "harvard",
    "ieee": "ieee",
}


@dataclass(slots=True)
class DocumentRequest:
    document_type: str
    topic: str
    export_format: str
    page_target: Optional[int] = None
    requested_formats: tuple[str, ...] = ("txt",)
    style: str = "professional"
    include_references: bool = False
    citation_style: Optional[str] = None


@dataclass(slots=True)
class DocumentSection:
    title: str
    lines: list[str]
    level: int = 1


@dataclass(slots=True)
class DocumentLayout:
    title: str
    subtitle: str
    topic: str
    document_type: str
    page_target: Optional[int]
    metadata_lines: list[str]
    sections: list[DocumentSection]
    preview_text: str
    style: str = "professional"
    include_references: bool = False
    citation_style: Optional[str] = None


@dataclass(slots=True)
class DocumentSlide:
    title: str
    bullets: list[str]
    notes: str = ""
    is_title_slide: bool = False


def ensure_generated_dir() -> Path:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    return GENERATED_DIR


def _access_manifest_path() -> Path:
    return ensure_generated_dir() / ACCESS_MANIFEST_FILENAME


def _load_access_manifest() -> dict[str, dict[str, Any]]:
    path = _access_manifest_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    manifest: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, dict):
            manifest[key] = dict(value)
    return manifest


def _save_access_manifest(payload: dict[str, dict[str, Any]]) -> None:
    path = _access_manifest_path()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _prune_access_manifest(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pruned: dict[str, dict[str, Any]] = {}
    directory = ensure_generated_dir()
    for file_name, metadata in payload.items():
        if not isinstance(file_name, str) or not isinstance(metadata, dict):
            continue
        candidate = directory / file_name
        if candidate.is_file():
            pruned[file_name] = dict(metadata)
    return pruned


def cleanup_generated_documents(*, max_age_hours: int = DEFAULT_RETENTION_HOURS) -> int:
    directory = ensure_generated_dir()
    deleted = 0
    cutoff = datetime.now() - timedelta(hours=max(1, int(max_age_hours)))
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.name == ACCESS_MANIFEST_FILENAME:
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                deleted += 1
        except Exception:
            continue
    try:
        manifest = _prune_access_manifest(_load_access_manifest())
        _save_access_manifest(manifest)
    except Exception:
        pass
    return deleted


def normalize_document_format(value: str | None) -> str:
    normalized = str(value or "txt").strip().lower()
    aliases = {
        "text": "txt",
        "word": "docx",
        "ppt": "pptx",
        "slides": "pptx",
        "presentation": "pptx",
        ".txt": "txt",
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError("format must be one of: txt, pdf, docx, pptx")
    return normalized


def normalize_document_formats(values: Optional[Iterable[str] | str]) -> tuple[str, ...]:
    if values is None:
        return ("txt",)
    if isinstance(values, str):
        items = [part for part in re.split(r"[,/|+]", values) if part.strip()]
        if not items:
            items = [values]
    else:
        items = list(values)

    normalized: list[str] = []
    for item in items:
        format_name = normalize_document_format(str(item))
        if format_name not in normalized:
            normalized.append(format_name)
    return tuple(normalized or ["txt"])


def normalize_document_style(value: Optional[str]) -> str:
    normalized = str(value or "professional").strip().lower()
    return DOCUMENT_STYLE_ALIASES.get(normalized, "professional")


def normalize_citation_style(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return CITATION_STYLE_ALIASES.get(normalized)


def _normalize_topic(value: str) -> str:
    topic = str(value or "").strip()
    topic = re.sub(r"\s+", " ", topic)
    if re.search(r"\b(?:notes|assignment|document|essay|report|page|pages|download|format|style)\b", topic, flags=re.IGNORECASE):
        anchor_matches = list(re.finditer(r"\b(?:on|about|regarding)\s+(.+)$", topic, flags=re.IGNORECASE))
        if anchor_matches:
            topic = anchor_matches[-1].group(1).strip()
        else:
            for_match = re.search(r"\b(?:notes|assignment|document|essay|report)\s+for\s+(.+)$", topic, flags=re.IGNORECASE)
            if for_match:
                topic = for_match.group(1).strip()
    topic = re.sub(r"^(?:please\s+)?(?:make|create|generate|prepare|give me|write)\s+", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^(?:a|an|the)\s+", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^(?:at\s+least\s+|minimum\s+|at\s+most\s+|maximum\s+|around\s+|about\s+)?\d{1,2}\s*(?:page|pages)\b\s*", "", topic, flags=re.IGNORECASE)
    topic = re.sub(
        r"^(?:(?:at\s+least\s+|minimum\s+|around\s+|about\s+)?\d{1,2}\s*(?:page|pages)\s+)?"
        r"(?:notes|assignment|document|essay|report)\s*(?:on|about|for)?\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"^(?:on|about|for)\s+", "", topic, flags=re.IGNORECASE)
    # Strip comma + command phrases: ", write at least 7 pages in professional format..."
    topic = re.sub(r"\s*,\s+(?:write|make|create|format|generate|add|include|prepare|produce|use)\b.*$", "", topic, flags=re.IGNORECASE)
    # Strip "in detail" intensifier (filler phrase)
    topic = re.sub(r"\s+in\s+detail\b", "", topic, flags=re.IGNORECASE)
    # Strip page counts with qualifiers like "at least 7 pages"
    topic = re.sub(r"\s+(?:at\s+least\s+|minimum\s+|at\s+most\s+|maximum\s+|around\s+|about\s+)?\d{1,2}\s*(?:page|pages)\b[^,]*", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+\d{1,2}\s*(?:page|pages)\b", "", topic, flags=re.IGNORECASE)
    # Strip "in a professional/formal/academic format/style"
    topic = re.sub(r"\s+in\s+(?:a\s+)?(?:professional|simple|detailed|formal|academic|standard)\s+(?:format|style|manner|way|tone)\b.*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+(?:professional|simple|detailed|formal|academic|standard)\s+(?:format|style|manner|way|tone)\b.*$", "", topic, flags=re.IGNORECASE)
    # Strip delivery phrases including "give me its download link"
    topic = re.sub(
        r"\s+(?:and\s+)?(?:give|send|get|provide|email|share)\s+(?:me\s+)?(?:its\s+|a\s+|an\s+|the\s+)?(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation|file|link|download)\b.*$",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    # Strip "and give me ..." variants
    topic = re.sub(
        r"\s+(?:and|then|also)\s+(?:give|send|get|provide|email|share)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation|file|link|download)\b.*$",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"\s+(?:in|as)\s+(?:pdf|docx|word|txt|text|pptx|ppt)\b$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation)\b$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+(?:in|as)\s+(?:professional|simple|detailed)\b$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(
        r"\s+(?:and|also|with)\s+(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation)(?:\s+(?:and|also)\s+(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation))*$",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(
        r"\s+(?:and|also|with)\s+(?:also\s+)?(?:pdf|docx|word|txt|text|pptx|ppt|slides?|presentation)\b.*$",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"\s+(?:download\s+)?link\b.*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+with\s+(?:references|citation|citations|bibliography|works cited)\b.*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+(?:and|also|with)$", "", topic, flags=re.IGNORECASE)
    return topic.strip(" .,!?:;-")


def _parse_page_target(text: str) -> Optional[int]:
    match = re.search(r"\b(\d{1,2})\s*(?:page|pages)\b", str(text or "").lower())
    if not match:
        return None
    pages = int(match.group(1))
    return max(1, min(pages, 20))


def _parse_document_style(text: str, *, document_type: Optional[str] = None) -> str:
    lowered = str(text or "").lower()
    for style_name in ("detailed", "simple", "professional"):
        if re.search(rf"\b{style_name}\b", lowered):
            return style_name
    if document_type == "notes":
        return "simple"
    return "professional"


def _parse_citation_style(text: str) -> Optional[str]:
    lowered = str(text or "").lower()
    for style_name in ("apa", "mla", "chicago", "harvard", "ieee", "basic"):
        if re.search(rf"\b{style_name}\b", lowered):
            return style_name
    return None


def _parse_include_references(text: str) -> bool:
    lowered = str(text or "").lower()
    return bool(
        re.search(r"\b(reference|references|bibliography|works cited|citations?)\b", lowered)
        or _parse_citation_style(lowered)
    )


def _collect_format_matches(text: str) -> list[tuple[int, str]]:
    lowered = str(text or "").lower()
    matches: list[tuple[int, str]] = []
    for pattern, format_name in FORMAT_ALIAS_PATTERNS:
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            matches.append((match.start(), format_name))
    matches.sort(key=lambda item: item[0])
    deduped: list[str] = []
    for _, format_name in matches:
        if format_name not in deduped:
            deduped.append(format_name)
    return [(index, name) for index, name in enumerate(deduped)]


def _parse_requested_formats(
    text: str,
    *,
    document_type: Optional[str] = None,
    include_default_document: bool = True,
) -> tuple[str, ...]:
    lowered = str(text or "").lower()
    matched_formats = [format_name for _, format_name in _collect_format_matches(lowered)]
    if "pptx" in matched_formats:
        non_slide_formats = [name for name in matched_formats if name != "pptx"]
        if (
            include_default_document
            and document_type in {"notes", "assignment"}
            and not non_slide_formats
            and re.search(r"\b(and|also)\b", lowered)
        ):
            matched_formats = ["txt", "pptx"]
    return normalize_document_formats(matched_formats or ["txt"])


def _normalize_session_id(session_id: Optional[str]) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(session_id or "").strip())
    normalized = normalized[:120].strip("-")
    return normalized or "default"


def _download_access_url(file_name: str, access_token: Optional[str]) -> str:
    token = str(access_token or "").strip()
    if not token:
        return f"/downloads/{file_name}"
    return f"/downloads/{file_name}?access={token}"


def _update_generated_access_links(
    generated: dict[str, Any],
    access_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if not generated:
        return generated

    artifacts = generated.get("artifacts") or {}
    for format_name, artifact in list(artifacts.items()):
        if not isinstance(artifact, dict):
            continue
        access_entry = access_map.get(str(artifact.get("file_name") or ""))
        if access_entry:
            artifact["download_url"] = access_entry["download_url"]
            artifact["access_token"] = access_entry["access_token"]
            artifact["access_scope"] = access_entry["access_scope"]
            artifacts[format_name] = artifact

    primary_entry = access_map.get(str(generated.get("file_name") or ""))
    if primary_entry:
        generated["download_url"] = primary_entry["download_url"]
        generated["access_token"] = primary_entry["access_token"]
        generated["access_scope"] = primary_entry["access_scope"]

    updated_files = []
    for file_entry in generated.get("files") or []:
        if not isinstance(file_entry, dict):
            updated_files.append(file_entry)
            continue
        access_entry = access_map.get(str(file_entry.get("file_name") or ""))
        if access_entry:
            updated_files.append(
                {
                    **file_entry,
                    "download_url": access_entry["download_url"],
                    "access_scope": access_entry["access_scope"],
                }
            )
        else:
            updated_files.append(file_entry)
    generated["files"] = updated_files

    format_links: dict[str, str] = {}
    for format_name, link in dict(generated.get("format_links") or {}).items():
        artifact = artifacts.get(format_name) if isinstance(artifacts, dict) else None
        access_entry = access_map.get(str((artifact or {}).get("file_name") or ""))
        format_links[format_name] = access_entry["download_url"] if access_entry else link
    generated["format_links"] = format_links
    generated["alternate_format_links"] = {
        format_name: url
        for format_name, url in format_links.items()
        if format_name != generated.get("format")
    }
    generated["document_delivery"] = _build_document_delivery_payload(generated)
    return generated


def secure_generated_document_access(
    generated: dict[str, Any],
    *,
    owner_session_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> dict[str, Any]:
    if not generated or not generated.get("success"):
        return generated

    normalized_user_id = str(owner_user_id or "").strip() or None
    normalized_session_id = _normalize_session_id(owner_session_id) if owner_session_id else None
    access_scope = "authenticated_user" if normalized_user_id else ("browser_session" if normalized_session_id else "local_link")

    manifest = _prune_access_manifest(_load_access_manifest())
    access_map: dict[str, dict[str, str]] = {}

    artifacts = generated.get("artifacts") or {}
    for artifact in artifacts.values():
        if not isinstance(artifact, dict):
            continue
        file_name = str(artifact.get("file_name") or "").strip()
        if not file_name:
            continue
        access_token = uuid4().hex
        manifest[file_name] = {
            "file_name": file_name,
            "owner_session_id": normalized_session_id,
            "owner_user_id": normalized_user_id,
            "access_token": access_token,
            "access_scope": access_scope,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        }
        access_map[file_name] = {
            "download_url": _download_access_url(file_name, access_token),
            "access_token": access_token,
            "access_scope": access_scope,
        }

    _save_access_manifest(manifest)
    return _update_generated_access_links(generated, access_map)


def resolve_generated_download_access(
    file_name: str,
    *,
    access_token: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    safe_name = Path(str(file_name or "")).name
    if not safe_name or safe_name != str(file_name or ""):
        return {"allowed": False, "status": "invalid", "reason": "Download link is invalid."}

    manifest = _prune_access_manifest(_load_access_manifest())
    if manifest != _load_access_manifest():
        _save_access_manifest(manifest)

    record = manifest.get(safe_name)
    file_path = ensure_generated_dir() / safe_name
    if not record or not file_path.is_file():
        return {
            "allowed": False,
            "status": "missing",
            "reason": "This document is no longer available. Generate it again if you still need it.",
        }

    normalized_user_id = str(user_id or "").strip() or None
    normalized_session_id = _normalize_session_id(session_id) if session_id else None
    expected_token = str(record.get("access_token") or "").strip()
    provided_token = str(access_token or "").strip()
    owner_user_id = str(record.get("owner_user_id") or "").strip() or None
    owner_session_id = str(record.get("owner_session_id") or "").strip() or None
    access_scope = str(record.get("access_scope") or "").strip() or "local_link"

    allowed = False
    reason = "Download access denied."

    if owner_user_id:
        if normalized_user_id and normalized_user_id == owner_user_id:
            allowed = True
        else:
            reason = "Sign in with the account that generated this document."
    elif owner_session_id:
        if normalized_session_id and normalized_session_id == owner_session_id and provided_token and provided_token == expected_token:
            allowed = True
        else:
            reason = "Open this download from the same browser session that generated it."
    else:
        if provided_token and provided_token == expected_token:
            allowed = True
        else:
            reason = "This local download link has expired or is missing its access token."

    if not allowed:
        return {"allowed": False, "status": "forbidden", "reason": reason, "access_scope": access_scope}

    return {
        "allowed": True,
        "status": "ok",
        "file_name": safe_name,
        "file_path": str(file_path),
        "content_type_hint": file_path.suffix.lower(),
        "access_scope": access_scope,
    }


def _make_document_request(
    document_type: str,
    topic: str,
    *,
    requested_formats: Optional[Iterable[str] | str] = None,
    page_target: Optional[int] = None,
    style: Optional[str] = None,
    include_references: bool = False,
    citation_style: Optional[str] = None,
) -> DocumentRequest:
    normalized_formats = normalize_document_formats(requested_formats)
    normalized_citation_style = normalize_citation_style(citation_style)
    return DocumentRequest(
        str(document_type or "").strip().lower(),
        _normalize_topic(topic),
        normalized_formats[0],
        page_target=page_target,
        requested_formats=normalized_formats,
        style=normalize_document_style(style),
        include_references=bool(include_references or normalized_citation_style),
        citation_style=normalized_citation_style,
    )


def remember_document_request(session_id: Optional[str], request: DocumentRequest) -> None:
    if request is None:
        return
    DOCUMENT_SESSION_CACHE[_normalize_session_id(session_id)] = request


def remember_generated_document(session_id: Optional[str], generated: dict[str, Any]) -> None:
    if not generated:
        return
    LAST_GENERATED_DOCUMENT[_normalize_session_id(session_id)] = dict(generated)


def get_last_generated_document(session_id: Optional[str]) -> Optional[dict[str, Any]]:
    return LAST_GENERATED_DOCUMENT.get(_normalize_session_id(session_id))


_RETRIEVAL_TRIGGER_PATTERNS: tuple[str, ...] = (
    r"\b(?:download|send|share)\s+(?:me\s+)?(?:the\s+)?(?:file|link|pdf|docx|doc|txt|pptx|ppt|slides?|presentation|document|it|again)\b",
    r"\b(?:pdf|docx|doc|txt|pptx|ppt|slides?|presentation|document|file|download)\s+(?:link|file)\b",
    r"\bthe\s+(?:pdf|docx|doc|txt|pptx|ppt|slides?|presentation|document|link|file)\b",
    r"\b(?:give|get|grab|fetch)\s+(?:me\s+)?(?:the\s+)?(?:file|link|pdf|docx|doc|txt|pptx|ppt|slides?|presentation|document|download)\b",
    r"\bwhere(?:\s+is)?\s+(?:the\s+)?(?:file|link|pdf|docx|doc|txt|pptx|ppt|slides?|presentation|document)\b",
    r"\bshow\s+(?:me\s+)?(?:the\s+)?(?:preview|file|link|document)\b",
    r"\bpreview(?:\s+(?:it|please|again|the\s+document))?\b",
    r"\bsend\s+(?:it|again|file|me|me\s+the\s+file)\b",
    r"\bcan\s+you\s+(?:send|share|give|resend)\b",
    r"\bresend\s+(?:it|the\s+link|the\s+file|please)?\b",
)


def detect_document_retrieval_followup(text: str) -> Optional[dict[str, Any]]:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return None
    if detect_document_request(text) is not None:
        return None
    matched = any(re.search(pattern, lowered) for pattern in _RETRIEVAL_TRIGGER_PATTERNS)
    if not matched:
        return None
    requested_format: Optional[str] = None
    for pattern, fmt in FORMAT_ALIAS_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            requested_format = fmt
            break
    wants_preview = bool(re.search(r"\bpreview\b", lowered))
    return {
        "requested_format": requested_format,
        "wants_preview": wants_preview,
    }


def resolve_document_retrieval_followup(
    text: str,
    *,
    session_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    intent = detect_document_retrieval_followup(text)
    if intent is None:
        return None
    cached = get_last_generated_document(session_id)
    if not cached:
        return None

    requested_format = intent.get("requested_format")
    wants_preview = bool(intent.get("wants_preview"))
    artifacts = cached.get("artifacts") or {}
    format_links: dict[str, str] = dict(cached.get("format_links") or {})
    primary_format = str(cached.get("format") or cached.get("primary_format") or "txt").lower()

    if requested_format and requested_format in artifacts:
        chosen_format = requested_format
        artifact = artifacts[requested_format]
        file_name = artifact.get("file_name", cached.get("file_name", ""))
        file_path = artifact.get("file_path", cached.get("file_path", ""))
        download_url = artifact.get("download_url", cached.get("download_url", ""))
    elif requested_format and requested_format in format_links:
        chosen_format = requested_format
        file_name = cached.get("file_name", "")
        file_path = cached.get("file_path", "")
        download_url = format_links[requested_format]
    else:
        chosen_format = primary_format
        file_name = cached.get("file_name", "")
        file_path = cached.get("file_path", "")
        download_url = cached.get("download_url", "")

    alternate_format_links = {
        fmt: link
        for fmt, link in format_links.items()
        if fmt != chosen_format
    }

    doc_type = str(cached.get("document_type") or "document").lower()
    doc_label = "notes" if doc_type == "notes" else ("assignment" if doc_type == "assignment" else doc_type)
    fmt_upper = str(chosen_format).upper()
    if wants_preview and cached.get("preview_text"):
        message = f"Here is the preview of your {doc_label}. The {fmt_upper} link is ready below."
    elif requested_format:
        message = f"Here is your {fmt_upper} link."
    else:
        message = f"Here is your {doc_label} download link."

    result = dict(cached)
    result["format"] = chosen_format
    result["primary_format"] = chosen_format
    result["file_name"] = file_name
    result["file_path"] = file_path
    result["download_url"] = download_url
    result["format_links"] = format_links
    result["alternate_format_links"] = alternate_format_links
    result["message"] = message
    result["retrieval_followup"] = True
    result["document_delivery"] = _build_document_delivery_payload(result)
    return result


def _detect_followup_request_controls(text: str) -> dict[str, Any]:
    lowered = str(text or "").strip().lower()
    matched_formats = [format_name for _, format_name in _collect_format_matches(lowered)]
    requested_formats = tuple(matched_formats)
    style_match = next((style_name for style_name in ("detailed", "simple", "professional") if re.search(rf"\b{style_name}\b", lowered)), None)
    page_target = _parse_page_target(lowered)
    citation_style = _parse_citation_style(lowered)
    include_references = _parse_include_references(lowered)

    stripped = lowered
    stripped = re.sub(r"^(?:please\s+)?", "", stripped)
    stripped = re.sub(r"\b(?:also|and|as|in|export|download|save|it|version|make|give|me|another|format)\b", " ", stripped)
    stripped = re.sub(r"\b(?:professional|simple|detailed)\b", " ", stripped)
    stripped = re.sub(r"\b(?:reference|references|bibliography|works cited|citations?)\b", " ", stripped)
    stripped = re.sub(r"\b(?:apa|mla|chicago|harvard|ieee|basic)\b", " ", stripped)
    stripped = re.sub(r"\b\d{1,2}\s*(?:page|pages)\b", " ", stripped)
    for pattern, _ in FORMAT_ALIAS_PATTERNS:
        stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    return {
        "requested_formats": normalize_document_formats(requested_formats) if requested_formats else (),
        "style": normalize_document_style(style_match) if style_match else None,
        "page_target": page_target,
        "include_references": include_references,
        "citation_style": normalize_citation_style(citation_style),
        "looks_like_followup": bool(
            requested_formats
            or page_target is not None
            or include_references
            or citation_style is not None
            or style_match is not None
        ) and not stripped,
    }


def detect_document_request(text: str) -> Optional[DocumentRequest]:
    normalized = str(text or "").strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    page_target = _parse_page_target(lowered)
    request_shape = bool(
        re.match(DOCUMENT_REQUEST_PREFIX, lowered, flags=re.IGNORECASE)
        or re.match(rf"^(?:{FORMAT_TOKEN_PATTERN})\s+(?:notes|assignment)\b", lowered, flags=re.IGNORECASE)
        or re.match(r"^(?:notes|assignment)\b", lowered, flags=re.IGNORECASE)
    )
    if not request_shape:
        return None

    explicit_type: Optional[str] = None
    if re.search(r"\bnotes\b", lowered):
        explicit_type = "notes"
    elif re.search(r"\bassignment\b", lowered):
        explicit_type = "assignment"
    elif page_target is not None and re.search(r"\b(?:on|about|for)\b", lowered):
        explicit_type = "assignment"

    if explicit_type is None:
        return None

    topic_match = re.search(r"\b(?:on|about|for)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not topic_match:
        return None

    topic = _normalize_topic(topic_match.group(1))
    if topic:
        return _make_document_request(
            explicit_type,
            topic,
            requested_formats=_parse_requested_formats(lowered, document_type=explicit_type),
            page_target=page_target,
            style=_parse_document_style(lowered, document_type=explicit_type),
            include_references=_parse_include_references(lowered),
            citation_style=_parse_citation_style(lowered),
        )

    return None


def resolve_document_request(text: str, *, session_id: Optional[str] = None) -> Optional[DocumentRequest]:
    direct_request = detect_document_request(text)
    if direct_request is not None:
        remember_document_request(session_id, direct_request)
        return direct_request

    followup_controls = _detect_followup_request_controls(text)
    if not followup_controls.get("looks_like_followup"):
        return None

    previous_request = DOCUMENT_SESSION_CACHE.get(_normalize_session_id(session_id))
    if previous_request is None:
        return None

    followup_request = _make_document_request(
        previous_request.document_type,
        previous_request.topic,
        requested_formats=followup_controls.get("requested_formats") or previous_request.requested_formats,
        page_target=followup_controls.get("page_target") or previous_request.page_target,
        style=followup_controls.get("style") or previous_request.style,
        include_references=bool(followup_controls.get("include_references") or previous_request.include_references),
        citation_style=followup_controls.get("citation_style") or previous_request.citation_style,
    )
    remember_document_request(session_id, followup_request)
    return followup_request


def _smart_title_case(text: str) -> str:
    tokens = re.split(r"(\s+)", str(text or "").strip())
    formatted: list[str] = []
    acronym_words = {"ai", "ml", "nlp", "llm", "api", "iot"}
    for token in tokens:
        if not token or token.isspace():
            formatted.append(token)
            continue
        if token.lower() in acronym_words or (token.isupper() and len(token) <= 5):
            formatted.append(token)
        else:
            formatted.append(token[:1].upper() + token[1:].lower())
    return "".join(formatted).strip()


def _normalize_body_line(line: str) -> str:
    normalized = str(line or "").replace("\u2022", "- ").replace("â€¢", "- ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _deduplicate_content(content: str) -> str:
    """Remove near-duplicate sentences and lines, preserving section headings."""
    lines = str(content or "").splitlines()
    seen_normalized: set[str] = set()
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        norm = re.sub(r"\s+", " ", stripped.lower().strip(".-– "))
        if _looks_like_heading(stripped) or stripped.startswith("-"):
            if norm not in seen_normalized:
                seen_normalized.add(norm)
                result.append(line)
        else:
            if norm not in seen_normalized:
                seen_normalized.add(norm)
                result.append(line)
    return "\n".join(result)


def _build_title(document_type: str, topic: str) -> str:
    _ = document_type
    return _smart_title_case(topic)


def _build_subtitle(document_type: str) -> str:
    return "Study Notes" if document_type == "notes" else "Professional Assignment"


def _normalize_section_title(title: str) -> str:
    candidate = _normalize_body_line(title).strip("# ").strip()
    candidate = re.sub(r"^[0-9]+[.)]\s*", "", candidate)
    candidate = candidate.rstrip(":")
    lowered = candidate.lower()
    title_aliases = {
        "background": "Background / History",
        "background and history": "Background / History",
        "background / history": "Background / History",
        "background and context": "Background / History",
        "technical background and context": "Background / History",
        "comparison context": "Background / History",
        "historical development": "Background / History",
        "history": "Background / History",
        "key criteria and core differences": "Core Concepts",
        "architecture and mechanism": "Core Concepts",
        "how it works": "Core Concepts",
        "applications and use cases": "Applications",
        "best-fit use cases": "Applications",
        "case studies and practical examples": "Applications",
        "advantages and importance": "Advantages",
        "relative strengths": "Advantages",
        "challenges": "Limitations",
        "challenges and limitations": "Limitations",
        "tradeoffs and limitations": "Limitations",
    }
    if lowered in title_aliases:
        return title_aliases[lowered]
    return _smart_title_case(candidate or "Section")


def _looks_like_heading(line: str) -> bool:
    candidate = _normalize_body_line(line).strip("# ").strip()
    if not candidate or len(candidate) > 90:
        return False
    if candidate.startswith(("-", "*")):
        return False
    if candidate.endswith((".", "!", "?")):
        return False
    return any(character.isalpha() for character in candidate)


def _append_default_summary_sections(document_type: str, sections: list[DocumentSection], topic: str) -> list[DocumentSection]:
    normalized_titles = {section.title.strip().lower() for section in sections}
    if document_type == "notes" and "summary" not in normalized_titles:
        sections.append(
            DocumentSection(
                "Summary",
                [
                    f"- Review the main definition, structure, and importance of {topic}.",
                    "- Revisit the key ideas, practical examples, and common limitations before final revision.",
                    "- Use this summary as a quick recap before discussion, revision, or assessment.",
                ],
            )
        )
    if document_type == "assignment" and "conclusion" not in normalized_titles:
        sections.append(
            DocumentSection(
                "Conclusion",
                [
                    f"In conclusion, {topic.title()} occupies a significant place in academic and professional study, valued for its capacity to address complex challenges with systematic analysis.",
                    f"Its historical development, core concepts, practical applications, and known limitations together form a complete picture of why {topic} continues to attract serious scholarly and applied attention.",
                ],
            )
        )
    return sections


def _merge_duplicate_sections(sections: list[DocumentSection]) -> list[DocumentSection]:
    merged: list[DocumentSection] = []
    title_index: dict[str, int] = {}
    for section in sections:
        key = section.title.strip().lower()
        if key in title_index:
            merged[title_index[key]].lines.extend(section.lines)
            continue
        title_index[key] = len(merged)
        merged.append(section)
    return merged


def _strengthen_assignment_sections(sections: list[DocumentSection], topic: str) -> list[DocumentSection]:
    strengthened: list[DocumentSection] = []
    for section in sections:
        lines = list(section.lines)
        if section.title.strip().lower() == "conclusion":
            closing_line = (
                f"Overall, {topic.title()} remains important because it connects foundational understanding with practical impact, future relevance, and informed decision-making."
            )
            if not any(closing_line.lower() in str(line).lower() for line in lines):
                lines.append(closing_line)
        strengthened.append(DocumentSection(section.title, lines, section.level))
    return strengthened


def _enforce_assignment_section_order(sections: list[DocumentSection]) -> list[DocumentSection]:
    """Guarantee assignment body sections render in the canonical academic order."""
    if not sections:
        return sections
    canonical_order = [
        "Introduction",
        "Background / History",
        "Core Concepts",
        "Applications",
        "Advantages",
        "Limitations",
        "Conclusion",
    ]
    canonical_lookup = {title.lower(): index for index, title in enumerate(canonical_order)}
    ordered: list[DocumentSection] = []
    extras: list[DocumentSection] = []
    by_title: dict[str, DocumentSection] = {}

    for section in sections:
        normalized_title = _normalize_section_title(section.title)
        key = normalized_title.lower()
        normalized_section = DocumentSection(normalized_title, list(section.lines), section.level)
        if key in canonical_lookup:
            if key in by_title:
                by_title[key].lines.extend(normalized_section.lines)
            else:
                by_title[key] = normalized_section
        else:
            extras.append(normalized_section)

    for title in canonical_order:
        section = by_title.get(title.lower())
        if section:
            ordered.append(section)

    return [*ordered, *extras]


def _parse_document_sections(document_type: str, topic: str, content: str) -> list[DocumentSection]:
    cleaned_content = str(content or "").replace("\r\n", "\n").strip()
    sections: list[DocumentSection] = []

    for raw_line in cleaned_content.splitlines():
        line = _normalize_body_line(raw_line)
        if not line:
            continue
        if _looks_like_heading(line):
            sections.append(DocumentSection(title=_normalize_section_title(line), lines=[]))
            continue
        if sections:
            sections[-1].lines.append(line)
            continue
        sections.append(
            DocumentSection(
                title="Overview" if document_type == "notes" else "Introduction",
                lines=[line],
            )
        )

    sections = _append_default_summary_sections(document_type, sections, topic)
    if document_type == "assignment":
        sections = _merge_duplicate_sections(sections)
        sections = _enforce_assignment_section_order(sections)
        sections = _strengthen_assignment_sections(sections, topic)
    return sections


def _build_references_section(topic: str, citation_style: Optional[str]) -> DocumentSection:
    normalized_style = normalize_citation_style(citation_style) or "basic"
    heading = "References" if normalized_style == "basic" else f"References ({normalized_style.upper()} Style)"
    lines = [
        f"- Use verified academic books, peer-reviewed articles, or institutional reports related to {_smart_title_case(topic)}.",
        "- Keep the reference list consistent in author, year, title, and source formatting.",
        f"- For {heading.lower()}, replace these guidance lines with course-approved sources before final submission.",
    ]
    return DocumentSection(heading, lines)


def _build_metadata_lines(
    document_type: str,
    topic: str,
    page_target: Optional[int],
    *,
    style: str = "professional",
    include_references: bool = False,
    citation_style: Optional[str] = None,
) -> list[str]:
    label = "Notes" if document_type == "notes" else "Assignment"
    metadata = [
        f"Type: {label}",
        f"Topic: {_smart_title_case(topic)}",
        f"Style: {normalize_document_style(style).title()}",
            "Prepared by: VORIS",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    if page_target:
        metadata.append(f"Requested length: Approximately {page_target} pages")
    if include_references:
        citation_label = normalize_citation_style(citation_style) or "basic"
        metadata.append(f"References: Included ({citation_label.upper()} style)")
    return metadata


def _build_preview_text(document_type: str, sections: list[DocumentSection]) -> str:
    first_section = next((section for section in sections if section.lines), None)
    if first_section is None:
        return "Preview unavailable."

    preview_parts: list[str] = []
    max_lines = 3 if document_type == "notes" else 2
    for line in first_section.lines:
        cleaned = re.sub(r"^(?:[-*]\s*)", "", _normalize_body_line(line)).strip()
        if cleaned:
            preview_parts.append(cleaned)
        if len(" ".join(preview_parts)) >= 220 or len(preview_parts) >= max_lines:
            break

    preview_body = " ".join(preview_parts).strip()
    if len(preview_body) > 240:
        preview_body = preview_body[:237].rsplit(" ", 1)[0].rstrip(" ,.;:") + "..."

    return f"{first_section.title}: {preview_body}" if preview_body else first_section.title


def _build_document_layout(
    document_type: str,
    topic: str,
    content: str,
    page_target: Optional[int],
    *,
    style: Optional[str] = None,
    include_references: bool = False,
    citation_style: Optional[str] = None,
) -> DocumentLayout:
    normalized_type = str(document_type or "").strip().lower()
    sections = _parse_document_sections(normalized_type, topic, content)
    if include_references and not any(section.title.strip().lower().startswith("references") for section in sections):
        sections.append(_build_references_section(topic, citation_style))
    return DocumentLayout(
        title=_build_title(normalized_type, topic),
        subtitle=_build_subtitle(normalized_type),
        topic=_smart_title_case(topic),
        document_type=normalized_type,
        page_target=page_target,
        metadata_lines=_build_metadata_lines(
            normalized_type,
            topic,
            page_target,
            style=normalize_document_style(style),
            include_references=include_references,
            citation_style=citation_style,
        ),
        sections=sections,
        preview_text=_build_preview_text(normalized_type, sections),
        style=normalize_document_style(style),
        include_references=include_references,
        citation_style=normalize_citation_style(citation_style),
    )


def _section_heading_text(layout: DocumentLayout, index: int, section: DocumentSection) -> str:
    heading = _normalize_section_title(section.title)
    if layout.document_type == "assignment":
        return f"{index}. {heading}"
    return heading.upper()


def _wrap_paragraph(text: str, *, width: int, initial_indent: str = "", subsequent_indent: str = "") -> list[str]:
    return textwrap.wrap(
        str(text or ""),
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [initial_indent.rstrip() or str(text or "")]


def _build_txt_document(layout: DocumentLayout) -> str:
    lines: list[str] = [
        layout.title.upper(),
        "=" * len(layout.title),
        layout.subtitle,
        "",
    ]

    if layout.document_type == "assignment":
        lines.extend(
            [
                f"Topic: {layout.topic}",
            "Prepared by: VORIS",
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ]
        )
        if layout.page_target:
            lines.append(f"Target length: Approximately {layout.page_target} pages")
        lines.extend(["", "-" * 78])
    else:
        lines.extend(["DOCUMENT DETAILS", "----------------"])
        lines.extend(f"- {item}" for item in layout.metadata_lines)

    for index, section in enumerate(layout.sections, start=1):
        heading = _section_heading_text(layout, index, section)
        lines.extend(["", heading, "-" * len(heading)])
        for line in section.lines:
            stripped = _normalize_body_line(line)
            if not stripped:
                continue
            if stripped.startswith(("-", "*")):
                bullet_text = re.sub(r"^(?:[-*]\s*)", "", stripped).strip()
                lines.extend(
                    _wrap_paragraph(
                        bullet_text,
                        width=90,
                        initial_indent="- ",
                        subsequent_indent="  ",
                    )
                )
            else:
                lines.extend(_wrap_paragraph(stripped, width=92))
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()

    return "\n".join(lines).strip() + "\n"


def _wrap_export_lines(text: str, *, width: int, initial_indent: str = "", subsequent_indent: str = "") -> list[str]:
    wrapped: list[str] = []
    for raw_line in str(text or "").splitlines():
        if not raw_line.strip():
            wrapped.append("")
            continue
        wrapped.extend(
            _wrap_paragraph(
                raw_line,
                width=width,
                initial_indent=initial_indent,
                subsequent_indent=subsequent_indent,
            )
        )
    return wrapped


def _iter_render_blocks(layout: DocumentLayout) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    if layout.document_type == "assignment":
        blocks.append({"kind": "title", "text": layout.title})
        blocks.append({"kind": "subtitle", "text": layout.subtitle})
        blocks.append({"kind": "cover_meta", "text": f"Topic: {layout.topic}"})
        blocks.append({"kind": "cover_meta", "text": "Prepared by VORIS"})
        blocks.append({"kind": "cover_meta", "text": f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}"})
    if layout.page_target:
            blocks.append({"kind": "cover_meta", "text": f"Requested length: Approximately {layout.page_target} pages"})
            blocks.append({"kind": "page_break", "text": ""})
    else:
        blocks.extend(
            [
                {"kind": "title", "text": layout.title},
                {"kind": "subtitle", "text": layout.subtitle},
                {"kind": "spacer", "text": ""},
                {"kind": "meta_heading", "text": "Document Details"},
            ]
        )
        blocks.extend({"kind": "meta_bullet", "text": item} for item in layout.metadata_lines)
        blocks.append({"kind": "spacer", "text": ""})

    for index, section in enumerate(layout.sections, start=1):
        blocks.append({"kind": "heading", "text": _section_heading_text(layout, index, section)})
        for line in section.lines:
            stripped = _normalize_body_line(line)
            if not stripped:
                continue
            if stripped.startswith(("-", "*")):
                blocks.append({"kind": "bullet", "text": re.sub(r"^(?:[-*]\s*)", "", stripped).strip()})
            else:
                blocks.append({"kind": "paragraph", "text": stripped})
        blocks.append({"kind": "spacer", "text": ""})

    while blocks and blocks[-1]["kind"] in {"spacer", "page_break"}:
        blocks.pop()
    return blocks


def _write_txt(path: Path, layout: DocumentLayout) -> None:
    path.write_text(_build_txt_document(layout), encoding="utf-8")


def _pdf_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_text_x(text: str, style: dict[str, Any]) -> int:
    if style.get("align") == "center":
        estimated_width = min(480, int(len(str(text or "")) * float(style.get("size", 12)) * 0.5))
        return max(64, int((612 - estimated_width) / 2))
    return int(style.get("x", 64))


def _build_pdf_bytes(layout: DocumentLayout) -> bytes:
    style_map: dict[str, dict[str, Any]] = {
        "title": {"font": "F2", "size": 24, "leading": 34, "width": 38, "align": "center"},
        "subtitle": {"font": "F1", "size": 13, "leading": 22, "width": 56, "align": "center"},
        "cover_meta": {"font": "F1", "size": 11, "leading": 18, "width": 62, "align": "center"},
        "meta_heading": {"font": "F2", "size": 12, "leading": 18, "width": 66, "x": 64},
        "meta_bullet": {"font": "F1", "size": 10, "leading": 16, "width": 74, "x": 82},
        "heading": {"font": "F2", "size": 15, "leading": 24, "width": 64, "x": 64},
        "paragraph": {"font": "F1", "size": 11, "leading": 18, "width": 86, "x": 64},
        "bullet": {"font": "F1", "size": 11, "leading": 18, "width": 80, "x": 84},
    }

    rendered_lines: list[dict[str, Any]] = []
    for block in _iter_render_blocks(layout):
        kind = block["kind"]
        if kind == "spacer":
            rendered_lines.append({"kind": "spacer", "height": 14})
            continue
        if kind == "page_break":
            rendered_lines.append({"kind": "page_break"})
            continue
        style = style_map[kind]
        if kind in {"meta_bullet", "bullet"}:
            wrapped = _wrap_export_lines(
                block["text"],
                width=style["width"],
                initial_indent="- ",
                subsequent_indent="  ",
            )
        else:
            wrapped = _wrap_export_lines(block["text"], width=style["width"])
        for line in wrapped:
            if not line:
                rendered_lines.append({"kind": "spacer", "height": 12})
                continue
            rendered_lines.append({**style, "kind": kind, "text": line, "x": _pdf_text_x(line, style)})

    pages: list[list[dict[str, Any]]] = [[]]
    current_y = 744
    bottom_margin = 64
    for entry in rendered_lines:
        if entry["kind"] == "page_break":
            if pages[-1]:
                pages.append([])
            current_y = 744
            continue
        if entry["kind"] == "spacer":
            current_y -= int(entry["height"])
            if current_y <= bottom_margin:
                pages.append([])
                current_y = 744
            continue
        line_height = int(entry["leading"])
        if current_y - line_height <= bottom_margin:
            pages.append([])
            current_y = 744
        pages[-1].append({**entry, "y": current_y})
        current_y -= line_height

    pages = [page for page in pages if page] or [[]]

    objects: list[bytes] = []
    regular_font_number = 3
    bold_font_number = 4
    page_object_numbers: list[int] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [] /Count 0 >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    for page_lines in pages:
        stream_lines = ["BT"]
        for line in page_lines:
            stream_lines.append(f"/{line['font']} {line['size']} Tf")
            stream_lines.append(f"1 0 0 1 {line['x']} {line['y']} Tm")
            stream_lines.append(f"({_pdf_escape(line['text'])}) Tj")
        stream_lines.append("ET")
        stream_data = "\n".join(stream_lines).encode("utf-8")
        content_object_number = len(objects) + 1
        objects.append(f"<< /Length {len(stream_data)} >>\nstream\n".encode("utf-8") + stream_data + b"\nendstream")

        page_object_number = len(objects) + 1
        page_payload = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {regular_font_number} 0 R /F2 {bold_font_number} 0 R >> >> "
            f"/Contents {content_object_number} 0 R >>"
        ).encode("utf-8")
        objects.append(page_payload)
        page_object_numbers.append(page_object_number)

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("utf-8")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("utf-8"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("utf-8")
    )
    return bytes(pdf)


def _write_pdf(path: Path, layout: DocumentLayout) -> None:
    path.write_bytes(_build_pdf_bytes(layout))


def _docx_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="320"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="38"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle">
    <w:name w:val="Subtitle"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="220"/></w:pPr>
    <w:rPr><w:i/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="DocumentMeta">
    <w:name w:val="DocumentMeta"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="140"/></w:pPr>
    <w:rPr><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="MetaHeading">
    <w:name w:val="MetaHeading"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="140" w:after="100"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="30"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyText">
    <w:name w:val="Body Text"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:after="180"/></w:pPr>
    <w:rPr><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph">
    <w:name w:val="List Paragraph"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:ind w:left="720" w:hanging="360"/><w:spacing w:after="140"/></w:pPr>
    <w:rPr><w:sz w:val="22"/></w:rPr>
  </w:style>
</w:styles>"""


def _docx_paragraph_xml(text: str, kind: str = "paragraph") -> str:
    escaped = xml_escape(str(text or ""))
    style_map = {
        "title": ("Title", escaped),
        "subtitle": ("Subtitle", escaped),
        "cover_meta": ("DocumentMeta", escaped),
        "meta_heading": ("MetaHeading", escaped),
        "meta_bullet": ("ListParagraph", f"&#8226; {escaped}"),
        "heading": ("Heading1", escaped),
        "bullet": ("ListParagraph", f"&#8226; {escaped}"),
        "paragraph": ("BodyText", escaped),
    }
    style_id, display_text = style_map.get(kind, style_map["paragraph"])
    return (
        "<w:p>"
        "<w:pPr>"
        f"<w:pStyle w:val=\"{style_id}\"/>"
        "</w:pPr>"
        "<w:r>"
        "<w:t xml:space=\"preserve\">"
        f"{display_text}"
        "</w:t></w:r>"
        "</w:p>"
    )


def _docx_page_break_xml() -> str:
    return "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"


def _write_docx(path: Path, layout: DocumentLayout) -> None:
    paragraphs: list[str] = []
    for block in _iter_render_blocks(layout):
        if block["kind"] == "spacer":
            continue
        if block["kind"] == "page_break":
            paragraphs.append(_docx_page_break_xml())
            continue
        paragraphs.append(_docx_paragraph_xml(block["text"], block["kind"]))

    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" mc:Ignorable=\"w14 wp14\">"
        "<w:body>"
        f"{''.join(paragraphs)}"
        "<w:sectPr><w:pgSz w:w=\"12240\" w:h=\"15840\"/><w:pgMar w:top=\"1260\" w:right=\"1260\" "
        "w:bottom=\"1260\" w:left=\"1260\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/></w:sectPr>"
        "</w:body>"
        "</w:document>"
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{xml_escape(layout.title)}</dc:title>
        <dc:creator>VORIS</dc:creator>
        <cp:lastModifiedBy>VORIS</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}Z</dcterms:created>
</cp:coreProperties>"""

    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
        <Application>VORIS</Application>
</Properties>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", _docx_styles_xml())
        archive.writestr("word/_rels/document.xml.rels", document_rels)


def _truncate_slide_text(text: str, limit: int) -> str:
    candidate = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(candidate) <= limit:
        return candidate
    return candidate[: limit - 3].rsplit(" ", 1)[0].rstrip(" ,.;:") + "..."


def _extract_slide_bullets_from_line(line: str, *, style: str) -> list[str]:
    cleaned = _normalize_body_line(line)
    if not cleaned:
        return []
    if cleaned.startswith(("-", "*")):
        bullet = re.sub(r"^(?:[-*]\s*)", "", cleaned).strip()
        return [_truncate_slide_text(bullet, 128 if style == "detailed" else 110)]

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]
    if not sentences:
        sentences = [cleaned]
    limit = 145 if style == "detailed" else 125 if style == "professional" else 105
    return [_truncate_slide_text(sentence, limit) for sentence in sentences[:2]]


def _build_slide_deck(layout: DocumentLayout) -> list[DocumentSlide]:
    style = normalize_document_style(layout.style)
    max_bullets = 6 if style == "detailed" else 5 if style == "professional" else 4
    slides: list[DocumentSlide] = [
        DocumentSlide(
            title=layout.title,
            bullets=[
                layout.subtitle,
                f"Topic: {layout.topic}",
                *( [f"Target length: ~{layout.page_target} pages"] if layout.page_target else [] ),
                *( [f"References: {normalize_citation_style(layout.citation_style).upper()} style"] if layout.include_references and normalize_citation_style(layout.citation_style) else [] ),
            ],
            notes=layout.preview_text,
            is_title_slide=True,
        )
    ]

    for section in layout.sections:
        bullet_pool: list[str] = []
        for line in section.lines:
            bullet_pool.extend(_extract_slide_bullets_from_line(line, style=style))
        bullet_pool = [bullet for bullet in bullet_pool if bullet]
        if not bullet_pool:
            bullet_pool = [f"Key points related to {section.title}."]
        for index in range(0, len(bullet_pool), max_bullets):
            chunk = bullet_pool[index : index + max_bullets]
            title = section.title if index == 0 else f"{section.title} (Continued)"
            slides.append(DocumentSlide(title=title, bullets=chunk, notes=" ".join(chunk[:2])))
    return slides


def _pptx_text_paragraph_xml(text: str, *, level: int = 0, centered: bool = False, bold: bool = False, size: int = 2200) -> str:
    escaped = xml_escape(str(text or ""))
    alignment = '<a:pPr algn="ctr"/>' if centered and level == 0 else f'<a:pPr lvl="{level}"><a:buChar char="•"/></a:pPr>'
    if centered:
        alignment = '<a:pPr algn="ctr"/>'
    bold_attr = ' b="1"' if bold else ""
    return (
        "<a:p>"
        f"{alignment}"
        f"<a:r><a:rPr lang=\"en-US\" sz=\"{size}\"{bold_attr}/><a:t>{escaped}</a:t></a:r>"
        "<a:endParaRPr lang=\"en-US\"/>"
        "</a:p>"
    )


def _pptx_shape_xml(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs_xml: str) -> str:
    return (
        "<p:sp>"
        "<p:nvSpPr>"
        f"<p:cNvPr id=\"{shape_id}\" name=\"{xml_escape(name)}\"/>"
        "<p:cNvSpPr txBox=\"1\"/>"
        "<p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f"<a:xfrm><a:off x=\"{x}\" y=\"{y}\"/><a:ext cx=\"{cx}\" cy=\"{cy}\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom>"
        "</p:spPr>"
        "<p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>"
        f"{paragraphs_xml}"
        "</p:txBody>"
        "</p:sp>"
    )


def _build_pptx_slide_xml(slide: DocumentSlide) -> str:
    if slide.is_title_slide:
        title_paragraphs = _pptx_text_paragraph_xml(slide.title, centered=True, bold=True, size=3000)
        subtitle_paragraphs = "".join(
            _pptx_text_paragraph_xml(bullet, centered=True, size=1800)
            for bullet in slide.bullets
            if bullet
        )
        body_shapes = [
            _pptx_shape_xml(2, "Title", 685800, 914400, 7772400, 1066800, title_paragraphs),
            _pptx_shape_xml(3, "Subtitle", 1143000, 2438400, 6858000, 1828800, subtitle_paragraphs or _pptx_text_paragraph_xml("", centered=True)),
        ]
    else:
        title_paragraphs = _pptx_text_paragraph_xml(slide.title, bold=True, size=2400)
        bullet_paragraphs = "".join(
            _pptx_text_paragraph_xml(bullet, level=0, size=1800)
            for bullet in slide.bullets
            if bullet
        ) or _pptx_text_paragraph_xml("Key points unavailable.", level=0, size=1800)
        body_shapes = [
            _pptx_shape_xml(2, "Title", 457200, 304800, 8229600, 685800, title_paragraphs),
            _pptx_shape_xml(3, "Content", 685800, 1371600, 7772400, 4419600, bullet_paragraphs),
        ]

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">"
        "<p:cSld><p:spTree>"
        "<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
        "<p:grpSpPr>"
        "<a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm>"
        "</p:grpSpPr>"
        f"{''.join(body_shapes)}"
        "</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>"
        "</p:sld>"
    )


def _pptx_content_types(slide_count: int) -> str:
    slide_overrides = "".join(
        f"<Override PartName=\"/ppt/slides/slide{index}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/>"
        for index in range(1, slide_count + 1)
    )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/ppt/presentation.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml\"/>"
        "<Override PartName=\"/ppt/slideMasters/slideMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml\"/>"
        "<Override PartName=\"/ppt/slideLayouts/slideLayout1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml\"/>"
        "<Override PartName=\"/ppt/theme/theme1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.theme+xml\"/>"
        f"{slide_overrides}"
        "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
        "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
        "</Types>"
    )


def _write_pptx(path: Path, layout: DocumentLayout) -> None:
    slides = _build_slide_deck(layout)
    slide_count = len(slides)

    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    slide_rel_entries = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    ]
    slide_id_entries = []
    for index in range(1, slide_count + 1):
        relationship_id = index + 1
        slide_rel_entries.append(
            f'<Relationship Id="rId{relationship_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>'
        )
        slide_id_entries.append(f'<p:sldId id="{255 + index}" r:id="rId{relationship_id}"/>')

    presentation_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<p:presentation xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">"
        "<p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst>"
        f"<p:sldIdLst>{''.join(slide_id_entries)}</p:sldIdLst>"
        "<p:sldSz cx=\"9144000\" cy=\"6858000\"/>"
        "<p:notesSz cx=\"6858000\" cy=\"9144000\"/>"
        "</p:presentation>"
    )

    presentation_rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        f"{''.join(slide_rel_entries)}"
        "</Relationships>"
    )

    slide_master_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:cSld name="VORIS Master">
    <p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle/>
    <p:bodyStyle/>
    <p:otherStyle/>
  </p:txStyles>
</p:sldMaster>"""

    slide_master_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""

    slide_layout_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="titleAndContent" preserve="1">
  <p:cSld name="Title and Content">
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""

    slide_layout_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""

    theme_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="VORIS Theme">
  <a:themeElements>
          <a:clrScheme name="VORIS">
      <a:dk1><a:srgbClr val="111827"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="1F2937"/></a:dk2>
      <a:lt2><a:srgbClr val="F3F4F6"/></a:lt2>
      <a:accent1><a:srgbClr val="3B82F6"/></a:accent1>
      <a:accent2><a:srgbClr val="0F766E"/></a:accent2>
      <a:accent3><a:srgbClr val="7C3AED"/></a:accent3>
      <a:accent4><a:srgbClr val="D97706"/></a:accent4>
      <a:accent5><a:srgbClr val="DC2626"/></a:accent5>
      <a:accent6><a:srgbClr val="059669"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink>
      <a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
          <a:fontScheme name="VORIS Fonts">
      <a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
          <a:fmtScheme name="VORIS Format">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle/></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>"""

    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{xml_escape(layout.title)}</dc:title>
        <dc:creator>VORIS</dc:creator>
        <cp:lastModifiedBy>VORIS</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}Z</dcterms:created>
</cp:coreProperties>"""

    app_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
        <Application>VORIS</Application>
  <Slides>{slide_count}</Slides>
  <PresentationFormat>On-screen Show (4:3)</PresentationFormat>
</Properties>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _pptx_content_types(slide_count))
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("ppt/presentation.xml", presentation_xml)
        archive.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        archive.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml)
        archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels)
        archive.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml)
        archive.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels)
        archive.writestr("ppt/theme/theme1.xml", theme_xml)
        for index, slide in enumerate(slides, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", _build_pptx_slide_xml(slide))
            archive.writestr(
                f"ppt/slides/_rels/slide{index}.xml.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""",
            )


def _build_topic_label(topic: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", str(topic or ""))
    if not words:
        return "Document"

    stop_words = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    meaningful = [word for word in words if word.lower() not in stop_words] or words
    if len(meaningful) >= 2:
        acronym = "".join(word[0].upper() for word in meaningful[:4])
        if 2 <= len(acronym) <= 5:
            return acronym
    if len(meaningful) == 1:
        return meaningful[0][:18].title()
    combined = "".join(word[:1].upper() + word[1:].lower() for word in meaningful[:2])
    return combined[:22] or "Document"


def _build_output_bundle(document_type: str, topic: str) -> dict[str, tuple[Path, str]]:
    directory = ensure_generated_dir()
    topic_label = _build_topic_label(topic)
    type_label = "Notes" if document_type == "notes" else "Assignment"
    base_name = f"{topic_label}-{type_label}"
    candidate_name = base_name
    while any(
        (
            directory
            / (
                f"{candidate_name}-Slides.pptx"
                if export_format == "pptx"
                else f"{candidate_name}.{export_format}"
            )
        ).exists()
        for export_format in SUPPORTED_EXPORT_FORMATS
    ):
        candidate_name = f"{base_name}-{uuid4().hex[:4].upper()}"
    return {
        export_format: (
            directory / (f"{candidate_name}-Slides.pptx" if export_format == "pptx" else f"{candidate_name}.{export_format}"),
            f"{candidate_name}-Slides.pptx" if export_format == "pptx" else f"{candidate_name}.{export_format}",
        )
        for export_format in sorted(SUPPORTED_EXPORT_FORMATS)
    }


def _delivery_message(document_type: str, requested_formats: Iterable[str]) -> str:
    normalized_formats = tuple(normalize_document_formats(tuple(requested_formats)))
    includes_slides = "pptx" in normalized_formats
    includes_documents = any(format_name in {"txt", "pdf", "docx"} for format_name in normalized_formats)
    if includes_slides and includes_documents:
        return "Done. Your document set is ready."
    if includes_slides:
        return "Done. Your presentation is ready."
    if document_type == "notes":
        return "Done. Your notes are ready."
    return "Done. Your assignment is ready."


def _build_document_delivery_payload(generated: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "kind": "document_delivery",
        "delivery_message": generated["message"],
        "title": generated["title"],
        "subtitle": generated["subtitle"],
        "document_type": generated["document_type"],
        "format": generated["format"],
        "file_name": generated["file_name"],
        "download_url": generated["download_url"],
        "page_target": generated.get("page_target"),
        "topic": generated["topic"],
        "preview_text": generated.get("preview_text"),
        "style": generated.get("style"),
        "include_references": generated.get("include_references"),
        "citation_style": generated.get("citation_style"),
        "access_scope": generated.get("access_scope"),
        "requested_formats": list(generated.get("requested_formats") or []),
        "primary_format": generated.get("primary_format") or generated["format"],
        "files": list(generated.get("files") or []),
        "alternate_format_links": dict(generated.get("alternate_format_links") or {}),
        "format_links": dict(generated.get("format_links") or {}),
        "available_formats": list(generated.get("available_formats") or []),
    }


_MIN_WORDS_PER_PAGE = 180


def _warn_low_word_count(content: str, document_type: str, page_target: Optional[int]) -> None:
    word_count = len(content.split())
    pages = page_target or (2 if document_type == "assignment" else 1)
    minimum = pages * _MIN_WORDS_PER_PAGE
    if word_count < minimum:
        print(
            f"[DOCGEN] Low word count warning: {word_count} words for "
            f"{pages}-page {document_type} (minimum {minimum}). "
            f"Topic may be too narrow or LLM output was truncated."
        )


def _is_unclear_document_request(text: str) -> bool:
    """Return True when the text looks like a document request but has no extractable topic."""
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    has_shape = bool(
        re.match(DOCUMENT_REQUEST_PREFIX, lowered, flags=re.IGNORECASE)
        or re.match(rf"^(?:{FORMAT_TOKEN_PATTERN})\s+(?:notes|assignment)\b", lowered, flags=re.IGNORECASE)
        or re.match(r"^(?:notes|assignment)\b", lowered, flags=re.IGNORECASE)
    )
    if not has_shape:
        return False
    has_type = bool(re.search(r"\b(?:notes|assignment)\b", lowered))
    if not has_type:
        return False
    has_topic = bool(re.search(r"\b(?:on|about|for)\s+\S", lowered))
    return not has_topic


def generate_document(
    document_type: str,
    topic: str,
    export_format: str = "txt",
    *,
    formats: Optional[Iterable[str] | str] = None,
    page_target: Optional[int] = None,
    style: Optional[str] = None,
    include_references: bool = False,
    citation_style: Optional[str] = None,
    prebuilt_content: Optional[str] = None,
) -> dict[str, Any]:
    normalized_type = str(document_type or "").strip().lower()
    if normalized_type not in {"notes", "assignment"}:
        raise ValueError("type must be either 'notes' or 'assignment'")

    normalized_topic = _normalize_topic(topic)
    if not normalized_topic:
        raise ValueError("topic is required")

    requested_formats = normalize_document_formats(formats or [export_format])
    normalized_format = requested_formats[0]
    normalized_style = normalize_document_style(style)
    normalized_citation_style = normalize_citation_style(citation_style)
    include_references = bool(include_references or normalized_citation_style)
    cleanup_generated_documents()

    if str(prebuilt_content or "").strip():
        content = str(prebuilt_content or "").strip()
        content_payload = {
            "provider": "local",
            "model": "transformer",
            "source": "transformed_source",
            "degraded": False,
            "providers_tried": [],
        }
    else:
        content_payload = generate_document_content_payload(
            normalized_type,
            normalized_topic,
            page_target=page_target,
            style=normalized_style,
            include_references=include_references,
            citation_style=normalized_citation_style,
        )
        content = _deduplicate_content(str(content_payload.get("content") or "").strip())
        if not content:
            raise RuntimeError("Document generation returned empty content.")
    if normalized_type == "assignment":
        content = stabilize_assignment_content(
            content,
            normalized_topic,
            page_target=page_target,
            style=normalized_style,
            include_references=include_references,
            citation_style=normalized_citation_style,
        )
    else:
        content = _deduplicate_content(content)
    _warn_low_word_count(content, normalized_type, page_target)

    layout = _build_document_layout(
        normalized_type,
        normalized_topic,
        content,
        page_target,
        style=normalized_style,
        include_references=include_references,
        citation_style=normalized_citation_style,
    )
    output_bundle = _build_output_bundle(normalized_type, normalized_topic)
    artifacts: dict[str, dict[str, str]] = {}

    for format_name, (output_path, filename) in output_bundle.items():
        if format_name == "txt":
            _write_txt(output_path, layout)
        elif format_name == "pdf":
            _write_pdf(output_path, layout)
        elif format_name == "docx":
            _write_docx(output_path, layout)
        else:
            _write_pptx(output_path, layout)
        artifacts[format_name] = {
            "file_name": filename,
            "file_path": str(output_path),
            "download_url": f"/downloads/{filename}",
        }

    ordered_formats = [normalized_format, *[name for name in sorted(SUPPORTED_EXPORT_FORMATS) if name != normalized_format]]
    primary_artifact = artifacts[normalized_format]
    format_links = {format_name: artifacts[format_name]["download_url"] for format_name in ordered_formats}
    alternate_format_links = {
        format_name: format_links[format_name]
        for format_name in ordered_formats
        if format_name != normalized_format
    }
    requested_file_entries = [
        {
            "format": format_name,
            "file_name": artifacts[format_name]["file_name"],
            "file_path": artifacts[format_name]["file_path"],
            "download_url": artifacts[format_name]["download_url"],
            "primary": format_name == normalized_format,
        }
        for format_name in requested_formats
    ]

    generated = {
        "success": True,
        "document_type": normalized_type,
        "topic": normalized_topic,
        "format": normalized_format,
        "primary_format": normalized_format,
        "requested_formats": list(requested_formats),
        "page_target": page_target,
        "style": normalized_style,
        "include_references": include_references,
        "citation_style": normalized_citation_style,
        "title": layout.title,
        "subtitle": layout.subtitle,
        "preview_text": layout.preview_text,
        "file_name": primary_artifact["file_name"],
        "file_path": primary_artifact["file_path"],
        "download_url": primary_artifact["download_url"],
        "available_formats": ordered_formats,
        "format_links": format_links,
        "alternate_format_links": alternate_format_links,
        "files": requested_file_entries,
        "artifacts": artifacts,
        "content": content,
        "provider": content_payload.get("provider"),
        "model": content_payload.get("model"),
        "source": content_payload.get("source"),
        "degraded": bool(content_payload.get("degraded", False)),
        "providers_tried": list(content_payload.get("providers_tried") or []),
        "message": _delivery_message(normalized_type, requested_formats),
    }
    generated["document_delivery"] = _build_document_delivery_payload(generated)
    return generated

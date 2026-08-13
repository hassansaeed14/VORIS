from __future__ import annotations

import hashlib
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


# "pollinations" is first because it is the only adapter with a verified
# implementation below. The other two remain listed but deliberately report
# adapter_missing rather than pretending to work.
SUPPORTED_IMAGE_PROVIDERS = ("pollinations", "openai", "stable_diffusion_local")
IMPLEMENTED_IMAGE_PROVIDERS = ("pollinations",)
DEFAULT_IMAGE_SIZE = "1024x1024"
MAX_PROMPT_CHARS = 1200

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_IMAGE_DIR = PROJECT_ROOT / "generated" / "images"
IMAGE_URL_PREFIX = "/generated-images"
POLLINATIONS_TIMEOUT = 90

IMAGE_REQUEST_RE = re.compile(
    r"\b(?:generate|create|make|draw|produce)\b.{0,90}\b(?:image|picture|illustration|artwork|logo|poster|visual)\b"
    r"|\b(?:image|picture|illustration|artwork|logo|poster|visual)\s+of\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ImageProviderStatus:
    provider: str
    configured: bool
    available: bool
    status: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "available": self.available,
            "status": self.status,
            "reason": self.reason,
        }


def detect_image_generation_request(text: str) -> bool:
    return bool(IMAGE_REQUEST_RE.search(str(text or "").strip()))


def _pollinations_key() -> str:
    return os.getenv("POLLINATIONS_API_KEY", "").strip()


def _configured_provider() -> str:
    """Which provider to use.

    An explicit VORIS_IMAGE_PROVIDER (or the pre-rename AURA_ name) always
    wins. Otherwise Pollinations is selected automatically when its key is
    present, so a working key needs no second setting to become active.
    """

    explicit = (
        os.getenv("VORIS_IMAGE_PROVIDER")
        or os.getenv("AURA_IMAGE_PROVIDER")
        or ""
    ).strip().lower()
    if explicit in SUPPORTED_IMAGE_PROVIDERS:
        return explicit
    if _pollinations_key():
        return "pollinations"
    return ""


def _sanitize_prompt(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", str(prompt or "")).strip()
    return normalized[:MAX_PROMPT_CHARS]


def normalize_image_size(size: Optional[str]) -> str:
    normalized = str(size or DEFAULT_IMAGE_SIZE).strip().lower()
    if re.fullmatch(r"\d{2,4}x\d{2,4}", normalized):
        return normalized
    return DEFAULT_IMAGE_SIZE


def get_image_generation_status() -> dict[str, Any]:
    provider = _configured_provider()
    if not provider:
        status = ImageProviderStatus(
            provider="none",
            configured=False,
            available=False,
            status="not_configured",
            reason="No image generation provider is configured.",
        )
        return {
            **status.as_dict(),
            "supported_providers": list(SUPPORTED_IMAGE_PROVIDERS),
        }

    if provider == "pollinations":
        has_key = bool(_pollinations_key())
        status = ImageProviderStatus(
            provider="pollinations",
            configured=has_key,
            available=has_key,
            status="ready" if has_key else "missing_key",
            reason=(
                "Pollinations is ready."
                if has_key
                else "Pollinations needs POLLINATIONS_API_KEY in your .env file."
            ),
        )
        return {
            **status.as_dict(),
            "supported_providers": list(SUPPORTED_IMAGE_PROVIDERS),
            "implemented_providers": list(IMPLEMENTED_IMAGE_PROVIDERS),
        }

    # Listed but not implemented. Never flipped to available without a real,
    # verified generation call behind it.
    status = ImageProviderStatus(
        provider=provider,
        configured=True,
        available=False,
        status="adapter_missing",
        reason=f"{provider} is configured, but no verified image generation adapter is active yet.",
    )
    return {
        **status.as_dict(),
        "supported_providers": list(SUPPORTED_IMAGE_PROVIDERS),
        "implemented_providers": list(IMPLEMENTED_IMAGE_PROVIDERS),
    }


def _call_pollinations(prompt: str, size: str) -> dict[str, Any]:
    """Fetch one image and store it under generated/images.

    Returns {"ok": True, "image_url": ...} or {"ok": False, "status": ...}.
    Never raises: every failure path is reported, so callers can stay honest
    about what happened instead of surfacing a stack trace.
    """

    key = _pollinations_key()
    if not key:
        return {"ok": False, "status": "missing_key",
                "error": "POLLINATIONS_API_KEY is not set."}

    width, _, height = size.partition("x")
    url = (
        f"https://gen.pollinations.ai/image/{quote(prompt)}"
        f"?model=flux&width={width}&height={height}&nologo=true&key={quote(key)}"
    )
    request = urllib.request.Request(
        url, headers={"User-Agent": "VORIS/1.0 image-generation"}
    )

    try:
        with urllib.request.urlopen(request, timeout=POLLINATIONS_TIMEOUT) as response:
            code = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if code != 200 or not content_type.startswith("image/"):
                return {"ok": False, "status": "provider_failed",
                        "error": f"Pollinations returned {code} {content_type}".strip()}
            payload = response.read()
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        return {
            "ok": False,
            "status": "payment_required" if code == 402 else "provider_failed",
            "error": f"Pollinations returned HTTP {code}",
        }
    except Exception as exc:  # network, DNS, timeout
        return {"ok": False, "status": "provider_failed", "error": str(exc)}

    if not payload:
        return {"ok": False, "status": "provider_failed",
                "error": "Pollinations returned an empty image."}

    if "jpeg" in content_type or "jpg" in content_type:
        extension = ".jpg"
    elif "webp" in content_type:
        extension = ".webp"
    else:
        extension = ".png"

    stamp = hashlib.sha256(f"{prompt}:{time.time()}".encode("utf-8")).hexdigest()[:20]
    GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_IMAGE_DIR / f"pollinations-{stamp}{extension}"
    out.write_bytes(payload)
    return {"ok": True, "image_url": f"{IMAGE_URL_PREFIX}/{out.name}",
            "bytes": len(payload)}


def generate_image(prompt: str, style: Optional[str] = None, size: Optional[str] = None) -> dict[str, Any]:
    cleaned_prompt = _sanitize_prompt(prompt)
    provider_status = get_image_generation_status()
    normalized_size = normalize_image_size(size)
    normalized_style = str(style or "").strip().lower() or None

    if not cleaned_prompt:
        return {
            "success": False,
            "status": "invalid_prompt",
            "provider": provider_status["provider"],
            "prompt": "",
            "style": normalized_style,
            "size": normalized_size,
            "message": "Please describe the image you want generated.",
            "error": "empty_prompt",
            "images": [],
        }

    if not provider_status.get("available"):
        return {
            "success": False,
            "status": provider_status.get("status") or "not_configured",
            "provider": provider_status.get("provider") or "none",
            "prompt": cleaned_prompt,
            "style": normalized_style,
            "size": normalized_size,
            "message": (
                "Image generation is not configured yet. I can prepare the prompt architecture, "
                "but I will not fake an image output."
            ),
            "error": provider_status.get("reason"),
            "images": [],
            "provider_status": provider_status,
        }

    provider = provider_status.get("provider")

    if provider == "pollinations":
        styled_prompt = f"{cleaned_prompt}, {normalized_style}" if normalized_style else cleaned_prompt
        result = _call_pollinations(styled_prompt, normalized_size)

        if result.get("ok"):
            return {
                "success": True,
                "status": "ok",
                "provider": "pollinations",
                "prompt": cleaned_prompt,
                "style": normalized_style,
                "size": normalized_size,
                "message": "Image ready.",
                "error": None,
                "image_url": result["image_url"],
                "images": [{"url": result["image_url"], "size": normalized_size}],
                "provider_status": provider_status,
            }

        status = result.get("status") or "provider_failed"
        if status == "payment_required":
            message = (
                "Pollinations rejected the request because that key has no remaining "
                "balance. Add credits or use a different POLLINATIONS_API_KEY."
            )
        elif status == "missing_key":
            message = "Add POLLINATIONS_API_KEY to your .env file, then restart VORIS."
        else:
            message = "Pollinations did not return an image this time. Try again in a moment."

        return {
            "success": False,
            "status": status,
            "provider": "pollinations",
            "prompt": cleaned_prompt,
            "style": normalized_style,
            "size": normalized_size,
            "message": message,
            "error": result.get("error"),
            "images": [],
            "provider_status": provider_status,
        }

    return {
        "success": False,
        "status": "adapter_missing",
        "provider": provider,
        "prompt": cleaned_prompt,
        "style": normalized_style,
        "size": normalized_size,
        "message": "Image generation provider is configured, but the verified adapter is not implemented yet.",
        "error": "adapter_missing",
        "images": [],
        "provider_status": provider_status,
    }


"""Provider diagnostics for VORIS.

Answers one question: *why* is the brain degraded?

Run from the project root:

    python tools/provider_doctor.py

Prints masked diagnostics only. It never prints an API key, and it never
writes one anywhere. Safe to share the output.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _mask(value: str) -> str:
    """Describe a secret without revealing it."""

    if not value:
        return "MISSING"
    if len(value) < 12:
        return f"present but suspiciously short (len={len(value)})"
    return f"present (len={len(value)}, starts '{value[:4]}…', ends '…{value[-2:]}')"


def _check_dotenv() -> None:
    print("=" * 62)
    print("1. .env DISCOVERY")
    print("=" * 62)

    cwd = Path.cwd()
    print(f"current working directory : {cwd}")
    print(f"project root              : {PROJECT_ROOT}")

    root_env = PROJECT_ROOT / ".env"
    cwd_env = cwd / ".env"

    print(f".env at project root      : {'FOUND' if root_env.exists() else 'MISSING'}")
    if cwd != PROJECT_ROOT:
        print(f".env at cwd               : {'FOUND' if cwd_env.exists() else 'MISSING'}")
        print(
            "  NOTE: settings.py calls load_dotenv() with no path, which searches\n"
            "  upward from the CWD. Since you are not running from the project root,\n"
            "  the project .env may not be loaded. Re-run from the project root."
        )

    if root_env.exists():
        try:
            keys = [
                line.split("=", 1)[0].strip()
                for line in root_env.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.strip() and not line.strip().startswith("#") and "=" in line
            ]
            print(f"keys defined in .env      : {', '.join(keys) if keys else '(none)'}")
        except Exception as error:  # pragma: no cover - diagnostic only
            print(f"could not read .env       : {error}")


def _check_settings() -> None:
    print()
    print("=" * 62)
    print("2. KEYS AS SETTINGS ACTUALLY RESOLVED THEM")
    print("=" * 62)

    from config import settings

    print(f"GROQ_API_KEY              : {_mask(settings.GROQ_API_KEY)}")
    print(f"SAMBANOVA_API_KEY         : {_mask(settings.SAMBANOVA_API_KEY)}")
    print(f"DEFAULT_REASONING_PROVIDER: {settings.DEFAULT_REASONING_PROVIDER}")
    print(f"PROVIDER_PRIORITY         : {', '.join(settings.PROVIDER_PRIORITY)}")

    bundle = os.getenv("VORIS_API_BUNDLE_PATH") or os.getenv("AURA_API_BUNDLE_PATH") or ""
    if bundle:
        print(f"API bundle file override  : {bundle}")
        print(
            "  WARNING: a bundle file takes precedence over .env values in\n"
            "  _env_or_bundle(). A stale key in that file will silently win."
        )


def _check_live() -> None:
    print()
    print("=" * 62)
    print("3. LIVE PROVIDER CALLS (the only thing that proves 'healthy')")
    print("=" * 62)

    from brain.provider_hub import provider_hub

    from config import settings

    candidates = [p for p in settings.PROVIDER_PRIORITY if p in {"groq", "sambanova"}]
    probe = [{"role": "user", "content": "Reply with exactly: OK"}]

    for provider in candidates:
        print(f"\n-- {provider} --")
        try:
            result = provider_hub.generate_with_provider(
                provider, probe, max_tokens=16, temperature=0.0
            )
            text = str(result.get("text") or "").strip()
            print(f"  result : SUCCESS")
            print(f"  model  : {result.get('model')}")
            print(f"  reply  : {text[:60]!r}")
        except Exception as error:
            name = type(error).__name__
            detail = str(error)
            print(f"  result : FAILED ({name})")
            print(f"  detail : {detail[:200]}")
            low = detail.lower()
            if "connection" in low or "getaddrinfo" in low or "timed out" in low:
                print("  meaning: network/DNS problem or blocked egress - not a bad key.")
            elif "401" in low or "invalid" in low or "auth" in low:
                print("  meaning: the key was rejected. Regenerate it at the provider.")
            elif "429" in low or "rate" in low:
                print("  meaning: key is VALID but rate limited right now.")
            elif "not configured" in low:
                print("  meaning: no key reached settings. See sections 1 and 2 above.")


def main() -> int:
    print("VORIS provider doctor - no secrets are printed\n")
    _check_dotenv()
    _check_settings()
    _check_live()
    print()
    print("=" * 62)
    print("Done. This output is safe to share.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

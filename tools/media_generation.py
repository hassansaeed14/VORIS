"""Local media generation for VORIS.

Image generation runs stable-diffusion.cpp (MIT) as a *subprocess*, never as a
Python import. That is the same aggregation boundary used for Piper TTS: the
binary's licence does not reach into this process, and a native crash cannot
take the API server down with it.

Licensing is a hard constraint here, not a preference. VORIS is heading toward
a source-available commercial licence, so:

  - ComfyUI (GPL-3.0) and AUTOMATIC1111 (AGPL-3.0) are not used at all.
  - The backend is leejet/stable-diffusion.cpp, MIT.
  - Weights are FLUX.1-schnell (Apache-2.0) only. FLUX.1-dev is
    non-commercial and must not be substituted. The VAE is the trap: the
    schnell and dev repos both ship a file called `ae.safetensors`, and only
    the schnell copy is Apache-2.0. See docs/MODEL_LICENSES.md.

Video generation is NOT implemented. See generate_video() for the measured
hardware reason rather than a placeholder that pretends otherwise.

Weights live outside the repository in models/ (gitignored). A Flux checkpoint
plus its text encoders is roughly 12GB, so preflight() reports exactly what is
missing and the command to fetch it, instead of failing mid-generation.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Weights and binaries are deliberately outside the repo and gitignored.
MODELS_DIR = Path(os.environ.get("VORIS_MODELS_DIR") or (PROJECT_ROOT / "models"))
GENERATED_MEDIA_DIR = PROJECT_ROOT / "generated" / "media"
MEDIA_URL_PREFIX = "/generated-media"

# stable-diffusion.cpp binary. Windows ships sd.exe; POSIX builds ship sd.
SD_BINARY_NAME = "sd.exe" if platform.system() == "Windows" else "sd"
SD_BINARY = Path(os.environ.get("VORIS_SD_BINARY") or (MODELS_DIR / "bin" / SD_BINARY_NAME))

# FLUX.1-schnell is Apache-2.0 and needs only ~4 steps, which is what makes it
# viable on a CPU at all. Every entry here is recorded in MODEL_LICENSES.md.
REQUIRED_MODELS: tuple[dict[str, str], ...] = (
    {
        "key": "diffusion_model",
        "filename": "flux1-schnell-Q4_K.gguf",
        "approx_size": "6.8 GB",
        "repo": "city96/FLUX.1-schnell-gguf",
        "licence": "Apache-2.0",
    },
    {
        "key": "vae",
        "filename": "ae.safetensors",
        "approx_size": "335 MB",
        "repo": "black-forest-labs/FLUX.1-schnell",
        "licence": "Apache-2.0",
    },
    {
        "key": "clip_l",
        "filename": "clip_l.safetensors",
        "approx_size": "246 MB",
        "repo": "comfyanonymous/flux_text_encoders",
        "licence": "Apache-2.0",
    },
    {
        "key": "t5xxl",
        "filename": "t5xxl_fp8_e4m3fn.safetensors",
        "approx_size": "4.9 GB",
        "repo": "comfyanonymous/flux_text_encoders",
        "licence": "Apache-2.0",
    },
)

DEFAULT_STEPS = 4          # schnell is distilled for 4; more does not help
DEFAULT_SIZE = 512
MAX_SIZE = 1024
GENERATION_TIMEOUT_SECONDS = int(os.environ.get("VORIS_SD_TIMEOUT") or 1800)


# --------------------------------------------------------------- preflight

def model_path(filename: str) -> Path:
    return MODELS_DIR / "flux" / filename


def preflight() -> Dict[str, Any]:
    """Report what is missing before anything long-running starts.

    Generation takes minutes on this class of hardware, so discovering a
    missing 6.8GB file at the end of it is the wrong time to find out.
    """
    missing_models = [m for m in REQUIRED_MODELS if not model_path(m["filename"]).is_file()]
    binary_present = SD_BINARY.is_file() or bool(shutil.which(SD_BINARY_NAME))

    problems: List[str] = []
    if not binary_present:
        problems.append(f"stable-diffusion.cpp binary not found at {SD_BINARY}")
    for model in missing_models:
        problems.append(f"missing {model['filename']} ({model['approx_size']})")

    return {
        "ok": not problems,
        "status": "ready" if not problems else "not_installed",
        "binary": str(SD_BINARY),
        "binary_present": binary_present,
        "models_dir": str(MODELS_DIR),
        "missing": [m["filename"] for m in missing_models],
        "problems": problems,
        "install_hint": install_hint() if problems else "",
    }


def install_hint() -> str:
    """The exact commands to make this subsystem work, not a vague pointer."""
    lines = [
        "# 1. stable-diffusion.cpp (MIT) -- prebuilt release binary",
        f"#    place it at: {SD_BINARY}",
        "#    https://github.com/leejet/stable-diffusion.cpp/releases",
        "",
        "# 2. FLUX.1-schnell weights (Apache-2.0). ~12 GB total.",
        "pip install -e \".[media]\"",
    ]
    for model in REQUIRED_MODELS:
        lines.append(
            f"huggingface-cli download {model['repo']} {model['filename']} "
            f"--local-dir \"{MODELS_DIR / 'flux'}\""
        )
    lines.append("")
    lines.append("# FLUX.1-dev is NOT interchangeable here -- it is non-commercial.")
    return "\n".join(lines)


# ------------------------------------------------------------------- jobs

@dataclass
class MediaJob:
    """A single generation. Held in memory only; not durable across restarts."""

    job_id: str
    kind: str
    prompt: str
    status: str = "queued"          # queued | running | done | failed
    progress: float = 0.0           # 0..1, parsed from the backend's output
    message: str = ""
    file_path: str = ""
    url: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "prompt": self.prompt,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "file_path": self.file_path,
            "url": self.url,
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
        }


_JOBS: Dict[str, MediaJob] = {}
_JOBS_LOCK = threading.Lock()
_MAX_TRACKED_JOBS = 50


def _remember(job: MediaJob) -> None:
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job
        if len(_JOBS) > _MAX_TRACKED_JOBS:
            oldest = sorted(_JOBS.values(), key=lambda j: j.started_at)[: len(_JOBS) - _MAX_TRACKED_JOBS]
            for stale in oldest:
                _JOBS.pop(stale.job_id, None)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        job = _JOBS.get(str(job_id or "").strip())
        return job.to_dict() if job else None


def list_jobs() -> List[Dict[str, Any]]:
    with _JOBS_LOCK:
        return [j.to_dict() for j in sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)]


# -------------------------------------------------------------- generation

def _sanitize_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").split())[:600]


def _clamp_size(size: Optional[int]) -> int:
    try:
        value = int(size or DEFAULT_SIZE)
    except (TypeError, ValueError):
        return DEFAULT_SIZE
    value = max(256, min(value, MAX_SIZE))
    return value - (value % 64)          # the model requires a multiple of 64


def _parse_progress(line: str) -> Optional[float]:
    """stable-diffusion.cpp prints steps as `|===>   | 2/4 - 3.10s/it`."""
    if "/" not in line:
        return None
    for token in line.replace("|", " ").split():
        if "/" in token:
            head, _, tail = token.partition("/")
            if head.strip().isdigit() and tail.strip().isdigit():
                done, total = int(head), int(tail)
                if total > 0:
                    return min(done / total, 1.0)
    return None


def _run_generation(job: MediaJob, size: int, steps: int, seed: int) -> None:
    """Run the backend to completion. Executes on a worker thread."""
    GENERATED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GENERATED_MEDIA_DIR / f"{job.job_id}.png"

    binary = str(SD_BINARY) if SD_BINARY.is_file() else (shutil.which(SD_BINARY_NAME) or str(SD_BINARY))
    command = [
        binary,
        "--diffusion-model", str(model_path("flux1-schnell-Q4_K.gguf")),
        "--vae", str(model_path("ae.safetensors")),
        "--clip_l", str(model_path("clip_l.safetensors")),
        "--t5xxl", str(model_path("t5xxl_fp8_e4m3fn.safetensors")),
        "-p", job.prompt,
        "--cfg-scale", "1.0",        # schnell is distilled; CFG must stay at 1
        "--sampling-method", "euler",
        "--steps", str(steps),
        "-W", str(size), "-H", str(size),
        "-s", str(seed),
        "-o", str(out_path),
    ]

    job.status = "running"
    job.message = "loading model"

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            cwd=str(PROJECT_ROOT),
        )
    except OSError as exc:
        job.status = "failed"
        job.error = f"could not start the image backend: {exc}"
        job.finished_at = time.time()
        return

    deadline = time.time() + GENERATION_TIMEOUT_SECONDS
    tail: List[str] = []
    try:
        for line in process.stdout or []:
            line = line.strip()
            if line:
                tail.append(line)
                del tail[:-20]
                fraction = _parse_progress(line)
                if fraction is not None:
                    job.progress = fraction
                    job.message = f"sampling {int(fraction * 100)}%"
            if time.time() > deadline:
                process.kill()
                job.status = "failed"
                job.error = f"generation exceeded {GENERATION_TIMEOUT_SECONDS}s and was stopped"
                job.finished_at = time.time()
                return
        process.wait(timeout=60)
    except Exception as exc:  # noqa: BLE001 - a worker thread must not die silently
        process.kill()
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = time.time()
        return

    job.finished_at = time.time()
    if process.returncode != 0 or not out_path.is_file():
        job.status = "failed"
        job.error = f"backend exited {process.returncode}: " + " | ".join(tail[-3:])
        return

    job.status = "done"
    job.progress = 1.0
    job.message = f"generated in {job.elapsed_seconds}s"
    job.file_path = str(out_path)
    job.url = f"{MEDIA_URL_PREFIX}/{out_path.name}"


def generate_image(
    prompt: str,
    size: Optional[int] = None,
    steps: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Start an image generation and return a job id immediately.

    Generation takes minutes on CPU, so this never blocks the caller. Poll
    get_job(job_id) for progress.
    """
    cleaned = _sanitize_prompt(prompt)
    if not cleaned:
        return {"ok": False, "status": "invalid_prompt",
                "message": "Describe the image you want generated."}

    check = preflight()
    if not check["ok"]:
        return {
            "ok": False,
            "status": "not_installed",
            "message": "Local image generation is not installed yet.",
            "problems": check["problems"],
            "install_hint": check["install_hint"],
        }

    job = MediaJob(job_id=f"img-{uuid.uuid4().hex[:12]}", kind="image", prompt=cleaned)
    _remember(job)

    worker = threading.Thread(
        target=_run_generation,
        args=(job, _clamp_size(size), max(1, min(int(steps or DEFAULT_STEPS), 20)),
              int(seed if seed is not None else -1)),
        name=f"media-{job.job_id}",
        daemon=True,
    )
    worker.start()

    return {"ok": True, "status": "queued", "job_id": job.job_id,
            "message": "Generation started.", "poll": f"/api/media/jobs/{job.job_id}"}


def generate_video(prompt: str, **_kwargs: Any) -> Dict[str, Any]:
    """Not implemented, and deliberately not faked.

    Wan2.2 and LTX-Video (both Apache-2.0, so licence-clean) are CUDA-first
    and want roughly 12-24GB of VRAM. The target machine is an Intel Iris Xe
    integrated GPU with 2GB dedicated, sharing 15.6GB of system RAM, and no
    CUDA device. A CPU fallback exists in principle but a few seconds of video
    is hours of compute there, which is not a feature.

    This returns an honest unavailable result rather than queueing something
    that would OOM or never finish.
    """
    return {
        "ok": False,
        "status": "unsupported_hardware",
        "message": (
            "Local video generation is not available on this machine. "
            "It needs a CUDA GPU with at least 12GB of VRAM; this host has "
            "Intel Iris Xe integrated graphics and no CUDA device."
        ),
        "prompt": _sanitize_prompt(prompt),
        "required": "CUDA GPU, >=12GB VRAM",
        "detected": "Intel Iris Xe Graphics (integrated, no CUDA)",
    }


def get_media_generation_status() -> Dict[str, Any]:
    """Capability report for the provider/telemetry surface."""
    check = preflight()
    return {
        "image": {
            "backend": "stable-diffusion.cpp (MIT, subprocess)",
            "model": "FLUX.1-schnell (Apache-2.0)",
            "available": check["ok"],
            "status": check["status"],
            "missing": check["missing"],
        },
        "video": {
            "backend": "none",
            "available": False,
            "status": "unsupported_hardware",
            "reason": "no CUDA device; Intel Iris Xe integrated graphics",
        },
    }

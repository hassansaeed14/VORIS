# VORIS System Audit

Audit date: 2026-05-08

This audit summarizes the current repository truth after stabilization phases. It is not a marketing document.

## Executive Summary

VORIS is a serious Level 3 / early Level 4 JARVIS-style assistant prototype. It has a real backend, modern interface, document engine, scoped memory, safe action layers, voice scaffolding, OCR safety checks, and a broad test suite.

VORIS is not a real Level 5 JARVIS assistant. Voice is dependency-based, screen understanding is OCR-level, automation is intentionally narrow, provider reliability depends on configured services, and daily-use reliability still needs hardening.

## Runtime

Status: REAL

Evidence:

- `run_voris.py` is the supported launcher.
- `api/api_server.py` is the live FastAPI API.
- Health endpoints exist for session, assistant runtime, desktop apps, and system health.

Limitations:

- Windows runtime still needs careful port and dependency handling.
- Legacy files may remain for history and should not be treated as live launch paths.

## API

Status: REAL

Evidence:

- `/api/chat` routes normal requests.
- `/api/generate/document` supports document generation.
- `/api/desktop/apps` reports supported app availability.
- Voice runtime endpoints report honest status.

Limitations:

- Some behavior depends on local environment and configured provider keys.

## Auth / User System

Status: REAL

Evidence:

- Login, registration, forgot-password, logout, and session endpoints are wired.
- `web_v2` reflects public versus authenticated state.

Limitations:

- This is local-development auth, not hardened enterprise identity.

## Document Generation

Status: REAL

Evidence:

- Notes and assignments can be generated.
- PDF, DOCX, TXT, and PPTX outputs are supported.
- Document delivery returns file links and preview metadata.

Limitations:

- Long-form academic depth, references, and page-length fidelity still need polishing.

## Content Transformation

Status: HYBRID

Evidence:

- The document system can reuse extracted or supplied content.
- Some media/file paths are dependency-based.

Limitations:

- YouTube, image, and complex file transformation depend on optional extractors and are not uniformly production-stable.

## UI / web_v2

Status: REAL

Evidence:

- Chat-first shell loads.
- Orb state binding, message controls, document cards, action cards, profile panel, and voice status are wired.

Limitations:

- Demo polish is good but not final product polish.
- Some advanced controls are intentionally hidden or labeled when unavailable.

## Orb / Voice

Status: HYBRID

Evidence:

- Browser push-to-talk uses browser SpeechRecognition when supported.
- Browser speechSynthesis can speak responses.
- Desktop voice runtime exposes status/start/stop/interrupt endpoints.

Limitations:

- Desktop wake/listen/respond loop is dependency-based and disabled by default for production safety unless explicitly enabled.
- This is not yet reliable always-available voice.

## Security / Trust

Status: REAL

Evidence:

- Safe, private, sensitive, and critical classifications exist.
- Sensitive automation requires confirmation.
- Critical actions are blocked or require stronger verification flow.
- File access, document ownership, rate limits, and action safety were hardened in prior phases.

Limitations:

- Production security review is still required before public deployment.

## Providers

Status: HYBRID

Evidence:

- Provider hub tracks configured/unverified/healthy/degraded/rate-limited/auth-failed/unavailable states.
- Degraded fallback avoids empty responses.

Limitations:

- Local reliability depends heavily on valid keys and provider availability. Groq is the live primary until a SAMBANOVA_API_KEY is configured, at which point SambaNova takes routing priority.
- Configured providers are not guaranteed healthy.

## Memory / Personalization

Status: HYBRID

Evidence:

- Memory is scoped by public session versus authenticated user.
- Identity extraction is restricted to explicit signals.

Limitations:

- Long-term preference recall is still conservative and needs more real-world validation.

## Agents

Status: HYBRID

Evidence:

- Agents are tagged as real, hybrid, or placeholder.
- Placeholder agents should not be chat-routable.

Limitations:

- Some agents remain wrappers or thin routing layers rather than autonomous systems.

## Automation

Status: HYBRID

Evidence:

- Desktop app launching is whitelist-only.
- Browser actions use controlled URL/search flows.
- OS automation wrappers are permission-gated and app-limited.

Limitations:

- Automation remains fragile around window focus, local app availability, and environment differences.

## Local Media Generation

Status: HYBRID

Evidence:

- `tools/media_generation.py` invokes stable-diffusion.cpp (MIT) as a subprocess, never as a Python import, matching the Piper TTS aggregation boundary.
- Weights are FLUX.1-schnell only (Apache-2.0). Every file and its licence URL is recorded in `docs/MODEL_LICENSES.md`, including the `ae.safetensors` filename collision with the non-commercial FLUX.1-dev VAE.
- `preflight()` reports each missing file with its size and the exact `huggingface-cli` command, so a missing 6.8GB weight is reported before generation rather than after.
- Generation returns a job id immediately and runs on a worker thread; progress is polled at `/api/media/job`. Verified: preflight, the not-installed path, and the video refusal all return correctly on this host.
- Registered as the agent tool `media.image` with `capability_mode = "hybrid"`.

Limitations:

- **No image has been generated on this machine.** The subprocess path is implemented but unexercised end to end: the backend binary is absent (no C/C++ toolchain is installed to build it) and the weights are a ~12GB download that has not been made. There are therefore **no measured generation times**. This is why the status is HYBRID and not REAL; it moves to REAL only after a generation completes here and the timing is recorded.
- Expected performance is an estimate, not a measurement. The target host is an Intel Iris Xe integrated GPU with no CUDA device, 15.6GB of shared system RAM, and a 13th-gen i7-1360P. FLUX.1-schnell at Q4 with a fp8 T5 encoder should fit, but on a CPU backend a 512x512 4-step image is expected to take minutes, not seconds.
- **Video generation is not implemented and will not run on this hardware.** Wan2.2 and LTX-Video are both licence-clean (Apache-2.0) but are CUDA-first and want roughly 12-24GB of VRAM. `generate_video()` returns an explicit `unsupported_hardware` result naming the requirement and what was detected, rather than queueing a job that would exhaust memory or never finish. It is deliberately not registered as an agent tool, so it adds no capability row to the UI.
- Progress is polled rather than pushed. This codebase has no WebSocket; adding one solely for progress would have been new plumbing for a job measured in minutes.
- Jobs are held in memory and capped at 50. They do not survive a restart.

## Screen Awareness

Status: HYBRID

Evidence:

- Screenshot capture and OCR safety checks exist.
- Sensitive screen terms can block actions.

Limitations:

- This is OCR-level awareness, not robust computer vision.

## Tests

Status: REAL

Evidence:

- The local unittest suite contains more than 250 tests.
- Recent stable milestone reported 293 passing tests.

Limitations:

- Live voice, OS automation, and provider behavior still need manual environment verification.

## Experimental / Not Fully Verified

- Desktop wake-word reliability.
- OCR quality across different displays and apps.
- Long multi-step workflows involving screen context.
- Provider failover under real rate-limit pressure.
- Packaged desktop distribution.

## Provider Truth

Groq is the practical primary live provider when configured and healthy; SambaNova automatically takes priority once SAMBANOVA_API_KEY is set. Gemini, OpenAI, Ollama, or other paths should be treated as configured/unverified, degraded, or unavailable unless real checks prove otherwise.

## Voice Truth

Browser push-to-talk is useful but browser-dependent. Desktop voice is scaffolding plus guarded runtime support; it is not yet a polished always-available voice assistant.

## Automation Truth

VORIS can run narrow controlled actions. It should not be marketed as broad computer control.


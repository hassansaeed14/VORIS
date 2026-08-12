# Changelog

All notable VORIS changes are summarized here. This changelog favors verified capability over hype.

## Current Stable Milestone - 2026-05-08

### Added / Stabilized

- `run_voris.py` confirmed as the supported launcher.
- FastAPI backend and `web_v2` interface stabilized for local demo flows.
- Auth flows wired for register, login, forgot password, session state, and logout.
- Public/authenticated state made more truthful in the UI.
- Scoped memory and identity rules added to reduce stale-name and cross-user leakage.
- Provider health states improved beyond config-only status.
- Response fallback behavior improved to avoid empty or weak replies.
- Document system expanded and polished for assignments, notes, PDF, DOCX, TXT, and PPTX.
- Direct document delivery cards and preview metadata added.
- Desktop control layer added with whitelist-only app launching.
- Controlled browser actions added for safe search/URL flows.
- OS automation wrappers added behind confirmation and app/window safety checks.
- Screen capture and OCR safety layer added for pre-action validation.
- Browser push-to-talk and desktop voice runtime status endpoints added.
- Orb state binding, copy/speak controls, action plan cards, and profile/status UI improved.
- System trace object added for request observability.
- Production hardening reduced noisy logs and avoided unsafe desktop voice autostart.

### Tests

- Recent full local unittest run reported 293 passing tests.
- Syntax checks cover Python runtime/API files and `web_v2` JavaScript.

### Known Limitations

- VORIS is not production-ready.
- VORIS is not Level 5 real JARVIS.
- Desktop voice requires local dependencies and explicit opt-in.
- Screen awareness remains OCR-level.
- Automation is intentionally narrow and can be fragile around focus/window state.
- Provider reliability depends on configured external services.
- Long-form document depth and references still need polish.

## Earlier Milestones

- Initial terminal assistant evolved into VORIS.
- Web interface introduced and later replaced by `web_v2`.
- Document generation introduced.
- Trust model and security foundations introduced.
- Memory and provider systems introduced.
- Action planning, desktop control, automation, and screen awareness were added gradually under safety constraints.


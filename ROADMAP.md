# VORIS Roadmap

This roadmap is intentionally conservative. VORIS should become more capable only when existing systems are real, stable, and safe.

## Completed Milestones

- FastAPI runtime with `run_voris.py` as the supported launcher.
- `web_v2` chat-first interface with VORIS orb presence.
- Auth routes for login, register, forgot password, session state, and logout.
- Scoped memory and identity safeguards.
- Provider routing, health status, and degraded response handling.
- Document generation and delivery for notes, assignments, PDF, DOCX, TXT, and PPTX.
- Desktop app launcher with whitelist-only app support.
- Controlled browser actions for deterministic URL/search flows.
- Permission-gated OS automation wrappers.
- Screen capture and OCR-based pre-action safety checks.
- Browser push-to-talk and desktop voice runtime scaffolding.
- Security/trust model for safe, private, sensitive, and critical actions.
- Broad test coverage with more than 250 tests in the local suite.

## Current Focus

VORIS is being stabilized from a Level 3 JARVIS-style prototype toward an early Level 4 near-JARVIS system.

Current priorities:

1. Runtime reliability on Windows.
2. Memory and identity isolation.
3. Desktop voice reliability.
4. Provider reliability and truthful health.
5. Document quality polish.
6. Screen awareness and automation robustness.
7. UI/orb/demo polish.

## Upcoming Phases

### Phase 1 - Runtime and Reliability Hardening

- Keep `run_voris.py` as the single supported launcher.
- Ensure UTF-8 safe console output.
- Detect port conflicts clearly.
- Keep startup, health checks, and shutdown predictable.

### Phase 2 - Memory and Identity Isolation

- Prevent stale names and cross-session memory leakage.
- Separate public session memory from authenticated user memory.
- Store only explicit identity and preference signals.

### Phase 3 - Desktop Voice Reliability

- Stabilize desktop voice state machine.
- Verify microphone, STT, TTS, wake phrase, and interruption.
- Keep status honest when dependencies are missing.

### Phase 4 - Provider Reliability

- Track real health, rate limits, auth failures, and timeouts.
- Skip known-bad providers during cooldown.
- Improve useful degraded replies without pretending live model success.

### Phase 5 - Document Intelligence Final Polish

- Strengthen assignment structure and page-length consistency.
- Improve academic references and formatting.
- Reduce generic filler and repeated phrases.

### Phase 6 - Screen Understanding Upgrade

- Improve OCR confidence filtering.
- Better detect input fields, search bars, buttons, and editor regions.
- Keep actions blocked when context is unsafe or uncertain.

### Phase 7 - Automation Robustness

- Prevent duplicate execution.
- Improve active-window validation.
- Improve interruption and failure recovery.
- Keep automation narrow, transparent, and permission-gated.

### Phase 8 - UI / Orb / Experience Polish

- Make orb state changes smoother and truthful.
- Improve action plan cards and safety messaging.
- Polish copy/speak controls and document cards.

### Phase 9 - Agent Truth and Capability Expansion

- Keep real, hybrid, and placeholder agents clearly tagged.
- Route only to real or meaningful hybrid agents.
- Build fewer stronger agents instead of many thin wrappers.

### Phase 10 - Product and Demo Packaging

- Add screenshots, demo script, architecture docs, and release notes.
- Prepare a clean tagged milestone.
- Keep the demo honest about experimental areas.

## Future Advanced Work

- Packaged desktop app with signed installer.
- Stronger always-available desktop voice loop.
- Better local speech recognition and interruption handling.
- Vision model integration for richer screen understanding.
- Research-backed document generation with citations.
- More reliable provider redundancy.
- Stronger long-term personalization.

## Intentionally Delayed

- Unrestricted OS control.
- Arbitrary shell execution.
- Autonomous payment, banking, password, or account-security actions.
- Blind clicking or screen-based control without verification.
- Large agent marketplace claims.
- Fake always-on voice behavior.


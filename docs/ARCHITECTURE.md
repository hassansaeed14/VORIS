# VORIS Architecture

## Runtime Source of Truth

Supported launcher:

```text
run_voris.py
```

Live API:

```text
api/api_server.py
```

Current interface:

```text
interface/web_v2/
```

Legacy files may remain for history, but new development should use the paths above unless a future migration explicitly changes them.

## Request Flow

```text
Browser / Voice / API input
  -> FastAPI route
  -> session and identity resolution
  -> trust classification
  -> intent routing
  -> provider/document/action/automation path
  -> response shaping
  -> trace and memory update
  -> UI delivery
```

## Main Subsystems

### API

Routes chat, auth, documents, voice status, desktop apps, action plans, and health checks.

### Brain

Owns runtime orchestration, providers, response shaping, trace, and high-level routing.

### Security

Enforces trust levels, sessions, approvals, critical blocking, and rate limits.

### Memory

Stores session/user context with scoped identity rules.

### Tools

Implements document generation, desktop app launching, browser actions, OS automation wrappers, and screen capture/OCR.

### Voice

Contains desktop voice runtime scaffolding plus speech hooks. Browser voice lives mostly in `web_v2`.

### UI

`web_v2` renders chat, orb state, document cards, action plans, profile state, and voice controls.

## Safety Boundaries

- No arbitrary shell execution.
- No unrestricted pyautogui access.
- No blind clicking.
- No secret background listening.
- No unsafe critical action execution.
- No placeholder agent routing through chat.

## Capability Levels

- REAL: usable and tested locally.
- HYBRID: partly real but dependency-based or limited.
- PLACEHOLDER: not normal-routable.
- BROKEN: known failing.


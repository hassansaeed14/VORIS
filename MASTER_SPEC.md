# VORIS Master Spec

## Mission

VORIS exists to become a truthful, safe, local-first personal assistant system. The goal is not to look powerful; the goal is to make real capabilities dependable.

VORIS is currently a Level 3 / early Level 4 JARVIS-style assistant prototype. It should move toward Level 4 by hardening voice, memory, screen awareness, provider reliability, automation robustness, and user experience.

## Core Principles

- Truth over hype.
- Real execution over simulated claims.
- Safety before autonomy.
- Smaller dependable systems before broader features.
- UI must match backend truth.
- No hidden or silent control.
- No fake always-on assistant behavior.
- Unsupported features must be unavailable, disabled, or clearly labeled.

## Core Pipeline

```text
Perceive -> Understand -> Decide -> Act -> Reflect -> Improve
```

### Perceive

Accept text, browser voice input, desktop voice input where available, files, screen context, and API requests.

### Understand

Resolve user identity, session scope, intent, trust level, and relevant memory.

### Decide

Choose the correct path: chat, document, action plan, desktop control, browser action, OS automation, blocked action, or degraded response.

### Act

Execute only through allowlisted tools and permission-aware controllers.

### Reflect

Return a coherent response, update trace data, and store memory only when safe and explicit.

### Improve

Use tests, logs, audits, and demo feedback to harden real behavior.

## Architecture

- `run_voris.py` - supported launcher.
- `api/api_server.py` - live API and web serving.
- `brain/runtime_core.py` - core routing and execution.
- `brain/response_engine.py` - response shaping and document flow.
- `brain/provider_hub.py` - provider health and routing.
- `brain/system_trace.py` - per-request trace structure.
- `security/` - trust, session, approval, and rate-limit logic.
- `memory/` - scoped user/session memory.
- `tools/` - document generation, desktop control, browser actions, OS automation, screen capture.
- `voice/` - desktop voice runtime and speech hooks.
- `interface/web_v2/` - current interface.
- `tests/` - regression and behavior tests.

## Module Responsibilities

### Runtime

Keep routing deterministic and observable. Do not let fallback paths hide real failures.

### Providers

Track real health. Configured keys alone must not mean healthy.

### Documents

Generate structured deliverables, export files, and return clean delivery metadata.

### Automation

Execute only allowlisted actions. Require confirmation for sensitive control.

### Screen Awareness

Observe before acting. OCR can support safety checks but must not be treated as full vision.

### Voice

Never claim always-on listening unless the desktop voice runtime is actually enabled and active.

### UI

Display assistant state, document cards, action plans, and permission prompts truthfully.

## Trust Model

- `safe` - can proceed automatically.
- `private` - requires user/session context care.
- `sensitive` - requires explicit confirmation.
- `critical` - blocked or requires stronger verification.

Critical actions include passwords, banking, payments, destructive file actions, purchases, account/security changes, and credential handling.

## Capability Classification Rule

Every major capability should be classified as:

- `REAL` - wired, tested, and usable in normal local conditions.
- `HYBRID` - partly real but dependency-based or limited.
- `PLACEHOLDER` - present in code/UI but not reliable enough to route to.
- `BROKEN` - known failing behavior.

Placeholder capabilities must not be advertised as real.

## No Fake Autonomy Rule

VORIS must not pretend to:

- listen in the background when it is not listening;
- understand the screen beyond available OCR/context;
- launch unsupported apps;
- control the system without user approval;
- complete provider-backed tasks when providers failed;
- remember facts that are not stored for the current user/session.


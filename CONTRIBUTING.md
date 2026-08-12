# Contributing to VORIS

Thank you for helping improve VORIS. This project values truthful, tested progress over flashy claims.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python run_aura.py
```

Open:

```text
http://127.0.0.1:5000/
```

## Testing

Before submitting changes, run:

```powershell
python -m py_compile run_aura.py api\api_server.py
node --check interface\web_v2\app.js
node --check interface\web_v2\auth.js
python -m unittest discover -s tests -p "test_*.py"
```

Run targeted tests for the area you changed.

## Coding Standards

- Keep changes narrow and purposeful.
- Do not modify unrelated systems.
- Preserve safety checks.
- Prefer clear, deterministic routing over hidden magic.
- Keep UI text truthful.
- Add tests when behavior changes.
- Do not commit generated documents, logs, secrets, memory state, or local artifacts.

## No Fake Features Rule

If a feature is not implemented, do not show it as working.

Use one of:

- disabled control;
- beta label;
- clear unavailable message;
- placeholder classification outside normal routing.

## No Unsafe Automation Rule

Do not add:

- arbitrary shell execution;
- unrestricted keyboard/mouse control;
- blind clicking;
- automation of passwords, payments, banking, purchases, deletion, or account/security changes.

Sensitive automation must require confirmation and must be interruptible.

## Pull Request Checklist

- The change is scoped.
- Tests pass.
- UI labels match backend reality.
- No secrets or generated artifacts are staged.
- New capabilities are classified as real, hybrid, placeholder, or experimental.
- Safety behavior is documented when relevant.


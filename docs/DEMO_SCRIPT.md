# VORIS Demo Script

Use this script for controlled teacher/demo presentations. Do not demo unsafe or unsupported claims.

## Setup

1. Start VORIS:

```powershell
python run_voris.py
```

2. Open:

```text
http://127.0.0.1:5000/
```

3. Confirm the health check if needed:

```powershell
python tools/health_check.py
```

## Best Demo Flow

### 1. Normal Chat

Prompt:

```text
hello
```

Show:

- chat response;
- orb state changes;
- copy/speak controls.

### 2. Simple Explanation

Prompt:

```text
explain artificial intelligence simply
```

Show:

- clear response;
- no fake claims.

### 3. Document Generation

Prompt:

```text
write a 3 page assignment on climate change as a PDF
```

Show:

- document card;
- preview;
- direct download link.

### 4. Browser Action

Prompt:

```text
open chrome and search AI trends
```

Show:

- action plan;
- safe external action result.

### 5. Permission-Gated Automation

Prompt:

```text
open notepad and type hello
```

Show:

- approval request;
- safety warning;
- result after approval if the local environment supports it.

### 6. Critical Block

Prompt:

```text
type my password into this page
```

Show:

- blocked critical/sensitive behavior;
- safety model.

## Avoid Demoing

- Banking or payment workflows.
- Password entry.
- Deleting files.
- Unsupported app launching.
- Always-on voice unless the desktop voice runtime has been explicitly enabled and verified.
- Claims of full screen understanding.

## Honest Closing Line

VORIS is not finished or real JARVIS yet. It is a Level 3 / early Level 4 assistant prototype with real controlled capabilities and a safety-first roadmap.


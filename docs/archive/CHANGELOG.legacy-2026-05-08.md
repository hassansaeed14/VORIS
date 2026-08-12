# CHANGELOG

All notable changes to **AURA — Autonomous Universal Responsive Assistant** are documented here.

This project follows a **reality-first development model**:
only working or verified changes are recorded.

---

# [v1.0-dev] — 2026-04-10

## 🚀 Added

### Core System

* Private local runtime using **FastAPI + Waitress**
* Stable `/api/chat` execution path with structured response contract
* Multi-provider routing foundation (Groq, Gemini, OpenAI fallback-ready)

### Document Engine (Phase 1)

* Notes and assignment generation system
* Multi-format export:

  * `.txt`
  * `.pdf`
  * `.docx`
* File delivery system with direct download endpoints (`/downloads/...`)
* Preview text support for generated documents
* Chat-integrated document routing (natural prompts → file generation)

### Memory & Persistence

* SQLite-backed chat history with session tracking
* Structured local memory system
* Initial vector memory integration (experimental)

### Security Foundation

* Authentication system
* Session handling
* Trust-based action model (safe / private / sensitive / critical)

### Interface

* Web-based assistant interface
* Real-time chat flow integration
* Document preview and download UI support

### Testing

* Unit tests for:

  * runtime core
  * response engine
  * document generation

---

## ⚠️ Known Limitations

* Provider reliability not yet stable (quota / fallback issues)
* Vector memory requires repair and validation
* Voice system partially implemented (browser-first)
* Some agents are wrapper-based, not deep integrations
* UI still lacks full “assistant OS” feel
* Runtime drift exists across legacy layers

---

# [v0.19]

## Added

* Improved structured memory recording
* Better context persistence handling

---

# [v0.18]

## Added

* Private runtime with:

  * authentication
  * voice infrastructure
  * agent bus system

---

# [v0.17]

## Improved

* Agent routing behavior
* UI interaction flow

---

# [v0.16]

## Stabilized

* Security system
* Session handling reliability

---

# [v0.15]

## Added

* Self-improvement agent (early AURA Forge concept)

---

# [v0.14]

## Added

* Major system integration pass
* Core modules connected into unified runtime

---

# [v0.13]

## Improved

* Integration layer between agents and backend

---

# [v0.12]

## Updated

* Core agent system improvements
* Better capability structuring

---

# [v0.10]

## Added

* Conversation memory
* UI themes
* Voice control basics

---

# [v0.9]

## Added

* Vector memory (initial version)
* Improved response generation

---

# [v0.8]

## Added

* Voice selection support

---

# [v0.7]

## Added

* Urdu language support

---

# [v0.6]

## Improved

* UI experience
* Chat history handling

---

# [v0.5]

## Added

* First web interface

---

# [v0.4]

## Added

* Study agent
* Coding agent

---

# [v0.3]

## Changed

* Project renamed to **AURA**
* Introduced voice input/output

---

# [v0.2]

## Added

* Voice output
* Basic memory system

---

# [v0.1]

## Initial Release

* Terminal-based assistant (Hey Goku)
* Basic command handling

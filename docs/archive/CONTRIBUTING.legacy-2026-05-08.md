# Contributing to AURA

## Autonomous Universal Responsive Assistant

Thank you for contributing to AURA.

This is **not a typical open-source project**.
AURA is a system-level AI assistant with strict design and behavior rules.

Contributions must respect the system’s **reality-first doctrine**.

---

# 🧠 Core Principles (Mandatory)

All contributions must follow:

* **Reality over hype**
* **No fake capability claims**
* **Working over advertised**
* **Verified over assumed**
* **Security is never optional**
* **UI must reflect backend truth**
* **Execution must be real, not implied**

If a feature is incomplete, it must be clearly labeled.

---

# ⚙️ Development Setup

1. Clone the repository
2. Create a Python virtual environment
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure `.env`
5. Run AURA locally
6. Verify the system is working before making changes

---

# 🌿 Branch Naming Convention

Use structured naming:

* `fix/...` → bug fixes
* `feat/...` → new features
* `refactor/...` → internal improvements
* `docs/...` → documentation changes
* `test/...` → test-related changes

Example:

```bash
feat/document-generation-pdf
```

---

# 🔄 Pull Request Rules

Every PR must:

* Be **focused and minimal**
* Clearly explain:

  * what changed
  * why it changed
* List all affected files
* Mention:

  * risks
  * limitations
* Update documentation if behavior changes
* Include tests when logic is modified

---

# 🧪 Quality Gate (Required)

Before submitting a PR, ALL of the following must pass:

* Code runs without errors
* Tests pass
* No broken endpoints
* No fake or placeholder behavior introduced
* No UI overclaiming
* Documentation matches real system behavior

---

# 🚫 What is NOT allowed

Do NOT:

* Add fake “AI” features
* Simulate execution without real backend logic
* Hardcode outputs pretending to be intelligent
* Bypass the trust model
* Add UI features without backend support
* Introduce silent failures or hidden fallbacks

---

# 🔐 Security Rules

* Never bypass authentication or session checks
* Never skip trust-level enforcement
* Critical actions must always require verification
* Do not expose sensitive data

---

# 🧠 System Awareness

Before contributing, understand:

* AURA is a **JARVIS-style system**, not a chatbot
* The **brain → agents → tools → execution** pipeline must remain intact
* Document generation, routing, and delivery systems must not break
* All outputs must remain **real and verifiable**

---

# 🧩 Contribution Scope

Good contributions include:

* improving stability
* fixing broken behavior
* enhancing response quality
* strengthening system integrity
* improving document generation
* improving routing or execution

---

# 🛑 Final Rule

If a change makes AURA *look* more capable without actually making it more capable:

❌ Do not implement it.

AURA grows through **real capability**, not illusion.

---

# 👨‍💻 Maintainer

Hassan Saeed

Building a real assistant system — not a demo.

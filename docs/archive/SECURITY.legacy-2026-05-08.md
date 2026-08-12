# SECURITY POLICY

## AURA — Autonomous Universal Responsive Assistant

AURA is a **private-first AI assistant system**.

Security is a core system layer, not an optional feature.

---

# 🚨 Reporting a Vulnerability

Do **NOT** open public issues for security vulnerabilities.

Report privately with:

* affected component
* steps to reproduce
* potential impact
* suggested fix (if available)

All reports are treated seriously and reviewed before disclosure.

---

# 🔐 Security Principles

AURA follows strict security rules:

* **Security must be real, not cosmetic**
* **Execution must be guarded, not assumed safe**
* **Access must be verified, not trusted by default**
* **Sensitive actions must require explicit approval**

---

# 🧠 Trust Model

All actions in AURA are categorized:

* **safe** → auto allow
* **private** → user confirmation required
* **sensitive** → session-level approval required
* **critical** → verification code + PIN required

These rules must be enforced at execution level.

---

# 📱 Critical Action Protection (Planned / In Progress)

For critical operations, AURA will require:

* phone number verification
* one-time password (OTP)
* optional PIN confirmation
* expiration window (e.g., 120 seconds)

Examples of critical actions:

* password changes
* purchases or payments
* external account modifications
* sensitive data exposure

If verification fails or expires:
→ action is **automatically cancelled**

---

# 🔍 Sensitive System Areas

Special attention is required for:

* authentication system
* session management
* permission enforcement
* trust-level routing
* memory access and storage
* document generation outputs
* external API integrations
* execution pipelines

---

# ⚠️ Security Requirements for Contributors

All contributions must:

* respect the trust model
* never bypass verification layers
* never expose private data
* never simulate security checks
* avoid storing secrets in code

---

# 🚫 Forbidden Practices

Do NOT:

* hardcode credentials or tokens
* bypass authentication or session checks
* skip permission validation
* expose internal system data
* fake secure behavior in UI

---

# 🧠 Data Privacy

AURA is designed as:

* local-first
* private by default
* minimal external exposure

User data must:

* remain protected
* not be shared without explicit permission
* not be logged unnecessarily

---

# 🛡️ Execution Safety

No action is considered safe unless:

* it passes the trust model
* it is verified at runtime
* it is explicitly allowed

---

# 📊 Security Philosophy

AURA does not assume safety.

AURA enforces safety through:

* verification
* controlled execution
* explicit user approval

---

# 🛑 Final Rule

If a feature appears secure but is not actually enforced:

❌ It must not be shipped.

Security in AURA is defined by **real protection**, not appearance.

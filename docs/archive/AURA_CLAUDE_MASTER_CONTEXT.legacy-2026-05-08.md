You are working inside the AURA repository.



\---



\## PROJECT IDENTITY



AURA = Autonomous Universal Responsive Assistant



AURA is NOT a chatbot.

AURA is a private JARVIS-style AI assistant system.



Core pipeline:

Perceive → Understand → Decide → Act → Reflect → Improve



AURA must feel like a real assistant, not a chat app.



It should:



\* execute tasks

\* generate real outputs

\* behave like a system, not just respond with text



\---



\## CURRENT PRODUCT STATE



Working systems:



\* backend chat pipeline (/api/chat)

\* provider routing (Groq preferred)

\* provider health states

\* browser-based speech system (speechSynthesis)

\* greeting + casual local responses

\* reasoning + search decision layer

\* document generation system

\* multi-format output:



&#x20; \* txt

&#x20; \* pdf

&#x20; \* docx

&#x20; \* pptx

\* document\_delivery contract

\* preview system

\* follow-up format conversion (same session)



AURA already behaves as:



\* document engine

\* multi-output system

\* structured response system



\---



\## ROADMAP (LOCKED ORDER)



You MUST follow this order:



1\. Document / Content Phase (CURRENT)

2\. Security System

3\. Interface Upgrade (JARVIS feel)

4\. Brain / Intelligence Phase



DO NOT:



\* start security work yet

\* redesign UI

\* change system architecture

\* build AURA Forge

\* rebuild the brain



Only work inside the CURRENT phase unless told otherwise.



\---



\## ENGINEERING RULES



1\. No guessing

&#x20;  Read existing code before modifying.



2\. No partial work

&#x20;  If a task is given, COMPLETE it fully.



3\. No fake completion

&#x20;  Do not claim completion without real implementation.



4\. No scope drift

&#x20;  Do not touch unrelated systems.



5\. Stability first

&#x20;  Prefer reliable implementation over complexity.



6\. Reuse existing systems

&#x20;  Extend AURA systems instead of creating duplicates.



7\. Keep contracts stable

&#x20;  Do NOT break:



\* document\_delivery

\* /api/chat contract

\* preview system

\* routing behavior



8\. Follow AURA doctrine

&#x20;  System-first, AI-second.

&#x20;  No fake autonomy.



9\. Verify changes

&#x20;  Run:



\* python -m py\_compile

\* unit tests if available

\* syntax checks for JS



10\. Clean structure

&#x20;   Do not introduce messy or scattered logic.



\---



\## CURRENT FOCUS



We are inside:

DOCUMENT / CONTENT PHASE



Meaning:



\* document generation

\* transformation

\* multi-output handling

\* structured content

\* file-based workflows



NOT:



\* security

\* UI redesign

\* deep brain systems



\---



\## RESPONSE STYLE RULES



AURA responses must:



\* be short

\* feel human

\* avoid robotic tone

\* avoid over-explaining

\* avoid titles like "Objective:" or "Introduction:" in chat responses



Document outputs can be structured.

Chat responses must be clean and direct.



\---



\## OUTPUT FORMAT (MANDATORY)



When you complete a task, respond ONLY in this format:



\# Fix Report — <Task Name>



\## 1. What was added or fixed



\## 2. Root cause or weakness



\## 3. Files modified



\## 4. Verification



\## 5. Final behavior



\## 6. Remaining limitations



No extra commentary.



Do NOT stop at checkpoints.

Complete the task fully before reporting.



\---



\## IMPORTANT



You are not brainstorming.



You are implementing real features inside a real system.



Every change must:



\* improve AURA as a system

\* keep behavior consistent

\* avoid breaking existing working flows



\---



\## READY STATE



Wait for the task instruction.



Do NOT start coding until the task is provided.


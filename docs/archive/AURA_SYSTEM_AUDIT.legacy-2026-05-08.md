# AURA SYSTEM AUDIT

Audit date: 2026-04-10
Project root: `D:\HeyGoku`
Audit method: source-file review plus live runtime and test checks

This document replaces the previous master spec. It is a reality-based audit of the current repository, not a wishlist.

## 1. Project Identity

Name:
- AURA - Autonomous Universal Responsive Assistant

Current version label:
- `v1.0-dev`

Vision:
- A private JARVIS-style AI operating system that can understand, route, act, remember, and improve through real execution paths.

What AURA is:
- A multi-view AI OS interface and backend runtime.
- Not a generic chatbot.
- Not a pure prompt wrapper.
- A hybrid system that mixes deterministic parsing, local state, agent routing, security policy, and provider-backed language generation.

Core pipeline:
- Perceive -> Understand -> Decide -> Act -> Reflect -> Improve

Current truth:
- The pipeline exists in code.
- Some stages are real and dependable.
- Some stages are only partially connected.
- The default live brain path is presently unstable because provider readiness is overstated and the configured Groq key is failing at runtime.

## 2. Current Architecture

### Runtime Flow

Primary live runtime:
- `AURA.bat` -> `run_aura.py` -> Waitress -> `a2wsgi.ASGIMiddleware` -> `api/api_server.py` -> `brain/*` -> `agents/*`, `memory/*`, `security/*`, `voice/*` -> `interface/web/*`

Legacy secondary runtime:
- `main.py` still exposes a separate Flask `/api/chat` path and CLI loop, but it is not the private web runtime launched by `run_aura.py`.

Connection map:
- `interface/web/app.js` calls `api/api_server.py`
- `api/api_server.py` prepares requests with `brain/understanding_engine.py`, `brain/intent_engine.py`, and `brain/decision_engine.py`
- `brain/core_ai.py` and `brain/runtime_core.py` execute the request
- `agents/registry.py` and `agents/agent_fabric.py` expose most agent behaviors
- `memory/*` stores chat history, working memory, semantic memory, episodic memory, and vector fallback state
- `security/*` enforces auth, sessions, rate limits, whitelist access, confirmation code, PIN, and trust evaluation
- `voice/*` handles STT, TTS, wake word, audio inspection, and frontend voice status

### Generated And Non-Architectural Artifacts

Present on disk but not first-class architecture:
- `__pycache__/` folders across the repo: generated Python bytecode
- many root `tmp*` folders: temporary artifacts from earlier runs
- `memory/vector_store/*`: Chroma runtime data files and journals
- `audit_source_inventory.json`: audit helper file, not runtime architecture
- `screenshot_20260408_230303.png`: image artifact, not runtime architecture

Not present:
- `desktop/` does not exist

### Root Files

- `.env` - current environment file; only `GROQ_API_KEY` is present
- `.gitignore` - git ignore rules
- `AURA.bat` - one-click Windows launcher for the local private instance
- `AURA_MASTER_SPEC.md` - this human-readable audit/spec
- `dev_log.txt` - local development notes/artifact
- `main.py` - legacy Flask + CLI entrypoint with duplicate `/api/chat`
- `requirements.txt` - Python dependency list
- `run_aura.py` - Waitress-based launcher for the FastAPI app
- `start_aura.bat` - Windows startup helper
- `start_aura.sh` - Unix startup helper

### `brain/`

- `brain/capability_registry.py` - combines config and live agent registry into a capability inventory
- `brain/command_splitter.py` - splits messy multi-command input into ordered tasks
- `brain/confidence_engine.py` - wraps intent scoring and ambiguity signals
- `brain/context_manager.py` - maintains short-term conversational context
- `brain/core_ai.py` - high-level JARVIS-style brain wrapper, context window, direct Groq fallback, reasoning trace assembly
- `brain/core_ai_backup.py` - stale backup copy of old brain logic
- `brain/core_ai_backup2.py` - second stale backup copy of old brain logic
- `brain/decision_engine.py` - converts detected intent into routing/action decisions
- `brain/entity_parser.py` - extracts times, files, URLs, currencies, languages, usernames, and topics
- `brain/intent_engine.py` - rule-based intent detection and confidence scoring
- `brain/intent_engine_backup.py` - stale backup of earlier intent logic
- `brain/memory_extractor.py` - decides which interaction data is worth storing
- `brain/orchestrator.py` - older master orchestrator with direct Groq usage and legacy memory calls
- `brain/planner.py` - generates ordered plan steps and readiness summaries
- `brain/provider_hub.py` - provider selection and provider status reporting for Groq, OpenAI, Claude, Gemini, and Ollama
- `brain/reflection_engine.py` - records execution reflections and learning signals
- `brain/response_engine.py` - provider-backed response generation and generic fallback message
- `brain/runtime_core.py` - main runtime execution path used by the API; routes requests to capabilities and agents
- `brain/understanding_engine.py` - cleans input, expands shorthand, corrects messy phrasing, and normalizes user text
- `brain/understanding_engine_backup.py` - stale backup of earlier understanding logic
### `agents/`

Shared agent infrastructure:
- `agents/__init__.py` - package marker
- `agents/agent_bus.py` - lightweight event bus and direct request bridge between agents
- `agents/agent_fabric.py` - shared generated-agent runtime; 192 wrapper files delegate here
- `agents/agent_registry.py` - singleton registry for live agent instances
- `agents/context.py` - `AURAContext` object passed through agent workflows
- `agents/registry.py` - static metadata catalog for all advertised agents

Bespoke agent groups:
- `agents/autonomous/coding_agent.py`, `debug_agent.py`, `executor.py`, `planner_agent.py`, `tool_selector.py` - autonomous planning, code, debug, execution, and tool-selection helpers
- `agents/cognitive/cognitive_core.py`, `planner_core.py`, `reasoning_core.py`, `memory_core.py`, `evaluator_core.py`, `evolution_core.py` - experimental cognitive cores; explicitly placeholder in the registry
- `agents/core/__init__.py`, `language_agent.py`, `orchestrator.py`, `reasoning_agent.py`, `self_improvement_agent.py` - older core agent implementations
- `agents/integration/__init__.py`, `browser_agent.py`, `currency_agent.py`, `dictionary_agent.py`, `email_agent.py`, `joke_agent.py`, `math_agent.py`, `news_agent.py`, `password_agent.py`, `quote_agent.py`, `reminder_agent.py`, `translation_agent.py`, `weather_agent.py`, `web_search_agent.py`, `youtube_agent.py` - concrete integration/productivity helpers used by the runtime
- `agents/memory/__init__.py`, `episodic_memory.py`, `learning_agent.py`, `memory_cleanup.py`, `memory_controller.py`, `memory_index.py`, `memory_stats.py`, `semantic_memory.py`, `working_memory.py` - memory-facing agents bound to local stores
- `agents/productivity/__init__.py`, `coding_agent.py`, `content_writer_agent.py`, `cover_letter_agent.py`, `email_writer_agent.py`, `fitness_agent.py`, `grammar_agent.py`, `quiz_agent.py`, `research_agent.py`, `resume_agent.py`, `study_agent.py`, `summarizer_agent.py`, `task_agent.py` - concrete productivity helpers
- `agents/productivity/calendar_agent.py`, `goal_agent.py`, `notes_agent.py` - generated wrappers over shared fabric, not bespoke calendar/goal/notes engines
- `agents/system/__init__.py`, `file_agent.py`, `screenshot_agent.py` - concrete system helpers
- `agents/system/app_control_agent.py`, `backup_agent.py`, `cleanup_agent.py`, `download_manager_agent.py`, `file_organizer_agent.py`, `resource_monitor_agent.py`, `system_info_agent.py` - generated system wrappers
- `agents/security/auth_agent.py`, `permission_agent.py`, `pin_agent.py` - generated security wrappers

Generated wrapper directories:
- `agents/advanced/*.py` - generated hybrid advanced-agent wrappers: `automation_designer_agent.py`, `behavior_analysis_agent.py`, `code_architect_agent.py`, `daily_planner_agent.py`, `debate_agent.py`, `debug_agent.py`, `decision_breakdown_agent.py`, `decision_coach_agent.py`, `digital_twin_agent.py`, `execution_optimizer_agent.py`, `explainer_agent.py`, `future_planner_agent.py`, `goal_breakdown_agent.py`, `habit_engine_agent.py`, `habit_optimizer_agent.py`, `idea_generator_agent.py`, `learning_path_agent.py`, `life_assistant_agent.py`, `long_term_planner_agent.py`, `mental_model_agent.py`, `negotiation_agent.py`, `opportunity_scanner_agent.py`, `persona_agent.py`, `prediction_agent.py`, `risk_analyzer_agent.py`, `simulation_agent.py`, `social_simulator_agent.py`, `startup_agent.py`, `strategy_agent.py`, `system_designer_agent.py`, `system_reflection_agent.py`, `teaching_agent.py`, `weekly_review_agent.py`, `workflow_agent.py`
- `agents/aura_core/*.py` - generated AURA-core wrappers: `autonomy_monitor_agent.py`, `capability_growth_agent.py`, `learning_evolution_agent.py`, `mistake_analysis_agent.py`, `self_improvement_agent.py`, `trust_monitor_agent.py`
- `agents/business/*.py` - generated business wrappers: `ad_copy_agent.py`, `business_plan_agent.py`, `client_outreach_agent.py`, `cold_email_agent.py`, `competitor_analysis_agent.py`, `crm_agent.py`, `customer_support_agent.py`, `lead_generation_agent.py`, `market_research_agent.py`, `sales_script_agent.py`, `seo_agent.py`, `social_media_manager_agent.py`
- `agents/creative/*.py` - generated creative wrappers: `character_builder_agent.py`, `comic_creator_agent.py`, `dialogue_generator_agent.py`, `narration_agent.py`, `plot_twist_agent.py`, `screenplay_agent.py`, `script_writer_agent.py`, `story_editor_agent.py`, `story_generator_agent.py`, `world_builder_agent.py`
- `agents/data/*.py` - generated data wrappers: `analytics_agent.py`, `budget_planner_agent.py`, `csv_processor_agent.py`, `dashboard_report_agent.py`, `data_cleaning_agent.py`, `data_entry_agent.py`, `excel_sheet_agent.py`, `financial_model_agent.py`, `invoice_tracker_agent.py`, `spreadsheet_builder_agent.py`
- `agents/design/*.py` - generated design wrappers: `banner_design_agent.py`, `brand_identity_agent.py`, `brochure_design_agent.py`, `canva_design_agent.py`, `design_system_agent.py`, `figma_design_agent.py`, `flyer_design_agent.py`, `graphic_design_agent.py`, `logo_design_agent.py`, `poster_design_agent.py`, `presentation_design_agent.py`, `prototype_agent.py`, `social_media_design_agent.py`, `thumbnail_design_agent.py`, `uiux_design_agent.py`, `wireframe_agent.py`
- `agents/documents/*.py` - generated document wrappers: `assignment_writer_agent.py`, `certificate_creator_agent.py`, `contract_writer_agent.py`, `cover_letter_writer_agent.py`, `docx_formatter_agent.py`, `ebook_creator_agent.py`, `form_builder_agent.py`, `invoice_creator_agent.py`, `pdf_creator_agent.py`, `pitch_deck_agent.py`, `proposal_writer_agent.py`, `report_writer_agent.py`, `research_paper_agent.py`, `resume_designer_agent.py`, `word_creator_agent.py`
- `agents/elite/*.py` - generated elite wrappers: `context_switch_agent.py`, `conversation_coach_agent.py`, `decision_simulator_agent.py`, `digital_memory_replay_agent.py`, `energy_tracker_agent.py`, `environment_control_agent.py`, `focus_mode_agent.py`, `interruption_manager_agent.py`, `lie_detection_agent.py`, `micro_task_agent.py`, `personal_analytics_agent.py`, `productivity_audit_agent.py`, `reverse_engineering_agent.py`, `time_blocking_agent.py`
- `agents/experimental/*.py` - generated placeholder experimental wrappers: `alternate_reality_agent.py`, `dream_simulator_agent.py`, `imagination_engine_agent.py`, `life_simulation_agent.py`, `personality_clone_agent.py`, `scenario_engine_agent.py`, `story_to_video_agent.py`, `time_travel_scenario_agent.py`
- `agents/intelligence/*.py` - generated wrappers: `audience_analyzer_agent.py`, `claude_agent.py`, `content_optimizer_agent.py`, `content_strategy_agent.py`, `gemini_agent.py`, `groq_agent.py`, `model_router_agent.py`, `ollama_agent.py`, `openai_agent.py`, `reasoning_agent.py`, `research_agent.py`, `summarizer_agent.py`, `trend_analyzer_agent.py`, `virality_predictor_agent.py`
- `agents/media/*.py` - generated media wrappers: `animation_agent.py`, `cartoon_image_generator_agent.py`, `cartoon_video_creator_agent.py`, `dubbing_agent.py`, `image_editor_agent.py`, `image_generator_agent.py`, `meme_generator_agent.py`, `reel_creator_agent.py`, `shorts_creator_agent.py`, `subtitle_generator_agent.py`, `thumbnail_generator_agent.py`, `video_editor_agent.py`, `video_generator_agent.py`, `voice_clone_agent.py`
- `agents/web/*.py` - generated web wrappers: `blog_website_agent.py`, `dashboard_ui_agent.py`, `ecommerce_website_agent.py`, `frontend_builder_agent.py`, `html_css_agent.py`, `landing_page_agent.py`, `portfolio_website_agent.py`, `react_ui_agent.py`, `responsive_design_agent.py`, `web_design_agent.py`, `web_redesign_agent.py`, `website_audit_agent.py`, `wordpress_design_agent.py`

Agent tests:
- `agents/tests/test_password_agent.py` - password-agent tests
- `agents/tests/test_reminder_agent.py` - reminder-agent tests
- `agents/tests/test_translation_agent.py` - translation-agent tests
- `agents/tests/test_youtube_agent.py` - YouTube-agent tests

### `memory/`

- `memory/aura_history.db` - SQLite chat history database
- `memory/aura_improvement_log.json` - improvement/reflection log
- `memory/aura_learning.json` - learning state storage
- `memory/chat_history.json` - legacy JSON chat history store
- `memory/chat_history.py` - SQLite-backed chat history component
- `memory/episodic_memory.json` - persisted episodic memory data
- `memory/episodic_memory.py` - episodic event store
- `memory/knowledge_base.py` - older knowledge-base helper still used by legacy orchestrator paths
- `memory/memory_cleanup.py` - deduplication and cleanup helpers
- `memory/memory_controller.py` - routes extracted memory into working, semantic, episodic, and vector targets
- `memory/memory_index.py` - memory search/index helpers
- `memory/memory_manager.py` - legacy memory manager overlapping with the newer structured memory layer
- `memory/memory_stats.py` - storage counts, recent activity, and health metrics
- `memory/permissions.json` - stored permission state artifact
- `memory/pin_state.json` - PIN configuration and lock state
- `memory/security_audit.jsonl` - audit log artifact
- `memory/semantic_memory.json` - semantic fact store
- `memory/semantic_memory.py` - semantic memory logic
- `memory/sqlite_journal_memory_test.db` - SQLite probe/test artifact
- `memory/sqlite_journal_off_test.db` - SQLite probe/test artifact
- `memory/sqlite_probe.tmp` - SQLite probe artifact
- `memory/user_memory.json` - older user-memory artifact
- `memory/users.json` - user account store with mixed legacy and current schemas
- `memory/vector_memory.py` - Chroma-backed vector memory with fallback JSON mode
- `memory/vector_store_fallback.json` - fallback vector-memory store
- `memory/voice_settings.json` - stored voice settings artifact
- `memory/working_memory.json` - working memory state
- `memory/working_memory.py` - working memory logic

Generated runtime data:
- `memory/vector_store/chroma.sqlite3`, `chroma.sqlite3-journal`, and UUID shard files - Chroma runtime storage, currently affected by disk I/O issues
### `api/`

- `api/api_server.py` - live FastAPI server, page routes, auth endpoints, chat endpoints, history endpoints, admin endpoints, security endpoints, voice endpoints, system-status endpoints
- `api/auth.py` - legacy auth bridge around `security.auth_manager`

### `interface/web/`

- `interface/web/admin.html` - admin dashboard shell
- `interface/web/app.js` - main frontend controller for chat, history, settings, tasks, voice, orb states, admin hooks, and API calls
- `interface/web/aura.html` - primary multi-view application shell
- `interface/web/index.html` - simple root HTML entry
- `interface/web/login.html` - login screen
- `interface/web/register.html` - legacy register page; runtime redirects registration to login-only private flow
- `interface/web/setup.html` - first-run owner setup page
- `interface/web/styles.css` - shared visual system, panels, orb states, and responsive layout

### `voice/`

- `voice/audio_manager.py` - audio device inspection and helpers
- `voice/mic_handler.py` - microphone helper functions
- `voice/noise_filter.py` - transcript cleaning and noise filtering
- `voice/speech_to_text.py` - local STT using `speech_recognition`
- `voice/text_to_speech.py` - local TTS using `pyttsx3`
- `voice/voice_config.py` - voice settings model and persistence helpers
- `voice/voice_controller.py` - voice status aggregation plus API-facing helpers
- `voice/voice_manager.py` - speech formatting, voice profile resolution, browser voice selection metadata
- `voice/voice_pipeline.py` - wake-word aware voice pipeline into the runtime
- `voice/wake_word.py` - wake-word detection

### `config/`

- `config/agent_registry.py` - intent-to-agent routing config
- `config/limits_config.py` - safety and size limits
- `config/logging_config.py` - logging defaults
- `config/master_spec.py` - machine-readable spec snapshot; currently stale
- `config/memory_config.py` - memory limits and thresholds
- `config/permissions_config.py` - trust labels and action classifications
- `config/server.json` - runtime host/port/debug/workers settings
- `config/settings.py` - provider keys, model defaults, personality strings
- `config/system_modes.py` - UI/runtime mode definitions
- `config/user_profile.json` - preferred name, title, voice profile, speech defaults
- `config/voice_profiles.json` - jarvis/friday/neutral/Urdu voice profile metadata

### `security/`

- `security/.secret.key` - local encryption key artifact
- `security/access_control.py` - whitelist access, invite/revoke, rate limits, action evaluation
- `security/audit_logger.py` - structured audit logging
- `security/auth_manager.py` - owner setup, invited registration, login, auth cookies, and user lifecycle
- `security/confirmation_system.py` - confirmation-code hashing and verification
- `security/encryption_utils.py` - local encryption helpers
- `security/lock_manager.py` - lock/unlock state handling
- `security/permission_engine.py` - older permission helper layer kept alongside newer trust/access layers
- `security/pin_manager.py` - PIN setup, verify, lockout
- `security/rate_limits.json` - persisted auth rate-limit state
- `security/security_config.py` - security constants and file paths
- `security/session_manager.py` - login sessions and session approvals
- `security/sessions.json` - persisted session data
- `security/trust_engine.py` - trust model evaluation and permission payload builders
- `security/whitelist.json` - encrypted whitelist store

Security tests:
- `security/tests/test_access_control.py`
- `security/tests/test_agent_routing.py`
- `security/tests/test_audit_logger.py`
- `security/tests/test_auth_manager.py`
- `security/tests/test_brain_flow.py`
- `security/tests/test_decision_engine.py`
- `security/tests/test_encryption_utils.py`
- `security/tests/test_end_to_end.py`
- `security/tests/test_intent_engine.py`
- `security/tests/test_lock_manager.py`
- `security/tests/test_memory_controller.py`
- `security/tests/test_permission_engine.py`
- `security/tests/test_pin_manager.py`
- `security/tests/test_session_manager.py`
- `security/tests/test_tool_execution.py`
- `security/tests/test_trust_engine.py`

### `tools/`

- `tools/browser_tools.py` - browser helpers
- `tools/datetime_tools.py` - date/time parsing helpers
- `tools/execution_tools.py` - bounded command execution helpers
- `tools/file_tools.py` - file manipulation helpers
- `tools/network_tools.py` - network request helpers
- `tools/process_tools.py` - process/app helpers
- `tools/system_tools.py` - system status helpers
- `tools/tool_guard.py` - shared guarded execution wrapper
- `tools/tool_registry.py` - tool catalog
- `tools/validation_tools.py` - shared validators

### `tests/`

- `tests/test_agent_registry.py` - agent registry checks
- `tests/test_agent_routing.py` - routing behavior checks
- `tests/test_brain_flow.py` - core brain flow checks
- `tests/test_decision_engine.py` - decision-engine checks
- `tests/test_end_to_end.py` - main end-to-end smoke checks
- `tests/test_intent_engine.py` - intent-engine checks
- `tests/test_master_spec.py` - spec/doctrine checks
- `tests/test_memory_controller.py` - memory-controller checks
- `tests/test_provider_hub.py` - provider-hub checks
- `tests/test_runtime_core.py` - runtime-core checks
- `tests/test_tool_execution.py` - tool execution checks
- `tests/test_vector_memory.py` - vector memory fallback checks

## 3. What Is Fully Working

These items were verified from live code and runtime behavior, not assumed:

- The local private web launcher path works: `AURA.bat` -> `run_aura.py` -> Waitress -> FastAPI on `http://localhost:5000`.
- The main web application pages exist and are served: setup, login, admin, and multi-view app shells.
- The frontend chat composer posts real JSON to `/api/chat`, shows the user message immediately, shows a thinking state, and surfaces real backend errors.
- SQLite chat history is real and persists across restarts through `memory/chat_history.py` and `memory/aura_history.db`.
- `GET /api/history`, `DELETE /api/history`, and `GET /api/sessions` are wired and currently return real local data.
- Local structured memory stores are real: working, semantic, episodic, memory stats, and memory controller all exist and are backed by files in `memory/`.
- Agent catalog and capability summaries are real: `agents/registry.py` reports 256 agents and `brain/capability_registry.py` reports routed capabilities.
- The primary test suite passes: `tests/` ran `37` tests successfully.
- The dedicated agent test suite passes: `agents/tests/` ran `5` tests successfully.
- The private-access owner account and whitelist data exist locally, and first-run setup is no longer required on this machine.

## 4. What Is Partially Built

- The main brain pipeline exists end to end, but reliable live language generation is not dependable because the configured Groq key is failing and the provider hub does not verify readiness with a real request.
- Voice is hybrid rather than complete:
  - backend STT is real through `speech_recognition`
  - browser speech input fallback is real in the frontend
  - backend TTS exists in code through `pyttsx3`
  - backend TTS is currently unavailable on this machine
  - ElevenLabs is not wired at all
- The security stack is real in code, but not fully stable:
  - access control, confirmation code, PIN, rate limiting, auth sessions, and whitelist logic exist
  - the security test suite currently fails because auth/session tests still target old symbols
- The agent ecosystem is broad but mostly generated:
  - 192 agent files are thin wrappers over `agents/agent_fabric.py`
  - many names imply deeper integrations than the shared fabric actually provides
- The UI is much stronger than earlier versions, but some intelligence, autonomy, and provider surfaces still depend on partial telemetry or over-optimistic backend status.
- Vector memory exists in code, but it is not operating as a healthy vector database today; it is running in fallback mode.
- Multiple runtime layers still coexist:
  - FastAPI in `api/api_server.py`
  - legacy Flask/CLI in `main.py`
  - older orchestrator and backup brain files in `brain/`
- The machine-readable spec in `config/master_spec.py` exists, but it no longer matches current reality.
## 5. What Is Broken Right Now

### Critical

- `D:\HeyGoku\.env:1` plus `D:\HeyGoku\brain\core_ai.py:203-220`
  - The only configured provider key is Groq, and the live Groq path is failing with a `401 invalid_api_key` error. This blocks dependable real replies through the default brain.

- `D:\HeyGoku\memory\vector_memory.py:145-155`
  - Vector memory is degraded to fallback JSON because Chroma reports `disk I/O error`. Semantic/vector retrieval is not healthy.

### High

- `D:\HeyGoku\brain\provider_hub.py:72-90`
  - Provider status marks a provider as available when a key or base URL exists. It does not perform a real health check, so `/api/providers` can overclaim readiness.

- `D:\HeyGoku\security\tests\test_auth_manager.py:15`
  - The test still patches `security.auth_manager.login_user`, but `security/auth_manager.py` no longer exposes that symbol.

- `D:\HeyGoku\security\tests\test_session_manager.py:12`
  - The test still patches `security.session_manager.SESSION_FILE`, but `security/session_manager.py` imports `SESSIONS_FILE` from config and no longer has `SESSION_FILE`.

- `D:\HeyGoku\security\tests\test_end_to_end.py:13`
  - The end-to-end security smoke test has the same outdated `SESSION_FILE` assumption.

- `D:\HeyGoku\brain\runtime_core.py:66` and `D:\HeyGoku\brain\runtime_core.py:551-597`
  - The main runtime builds permission payloads directly from `security.trust_engine`, but it does not route all execution through `tools/tool_guard.py`.

- `D:\HeyGoku\agents\agent_fabric.py:757-766`
  - The shared fabric performs selective direct access checks itself rather than going through a single universal tool-execution gate.

### Medium

- `D:\HeyGoku\config\master_spec.py:31`
  - The machine-readable spec still says `terminal_first_workflow`, which no longer matches the private web launcher model.

- `D:\HeyGoku\config\master_spec.py:160-161`
  - The machine-readable spec still says the PIN system and locked chats are not built, but the codebase now includes `pin_manager.py` and `lock_manager.py`.

- `D:\HeyGoku\main.py:35`
  - A second `/api/chat` route still exists in the legacy Flask entrypoint, which creates maintenance drift from the live FastAPI route.

- `D:\HeyGoku\api\api_server.py:1391-1421`
  - Dead legacy agent-catalog code remains in the live API module.

### Low

- `D:\HeyGoku\interface\web\app.js:1108`
  - `closeActiveChatStream()` is a dead leftover after SSE streaming was removed.

- `D:\HeyGoku\interface\web\app.js:2404-2406`
  - `getStreamAgentLabel(...)` is dead leftover logic from the removed streaming path.

- `D:\HeyGoku\memory\users.json:2-11`
  - The users store contains mixed legacy and current schemas, which increases migration risk.

- Root `tmp*` folders and scattered runtime artifacts should be cleaned once the core system is stable.

## 6. What Is Placeholder Or Fake

These are the parts that still over-promise or are explicitly non-real:

- `D:\HeyGoku\agents\registry.py:111-116`
  - The six cognitive-core agents are explicitly marked `placeholder` and `experimental`.

- `D:\HeyGoku\agents\agent_fabric.py:108-113`
  - The entire `experimental` agent family is intentionally placeholder and says it must be connected before stronger claims.

- 192 generated wrapper agents across `agents/advanced`, `agents/aura_core`, `agents/business`, `agents/creative`, `agents/data`, `agents/design`, `agents/documents`, `agents/elite`, `agents/experimental`, `agents/intelligence`, `agents/media`, and `agents/web`
  - These are real files, but most are not bespoke implementations.
  - They delegate to one shared fabric.
  - Many produce plans, briefs, drafts, or structured guidance rather than full external execution implied by their names.

- Provider readiness reporting is partially fake today:
  - `brain/provider_hub.py` currently treats configuration as availability.
  - That means the UI and API can claim a provider is ready before any successful live call has happened.

- Duplicate legacy memory layers:
  - `memory/knowledge_base.py` and `memory/memory_manager.py` still coexist beside the newer structured memory system.
  - This creates the appearance of one unified memory layer when the codebase actually has overlapping implementations.

These items must be fixed before any honest `v1.0` release.

## 7. API Inventory

Only `GROQ_API_KEY` is present in `.env` today. The rest of the requested provider stack is not yet configured.

| API | Status | Used In | Current Reality | Needs To Be Wired To |
| --- | --- | --- | --- | --- |
| GROQ (`llama-3.3-70b-versatile`) | broken | `.env`, `config/settings.py`, `brain/provider_hub.py`, `brain/core_ai.py`, `brain/orchestrator.py`, several older agent modules | Code path exists, but live auth is failing with `401 invalid_api_key` | Valid key rotation, live health checks, and stable routing in `provider_hub` / `response_engine` |
| GEMINI (`gemini-2.5-flash` / code currently defaults to `gemini-2.5-pro`) | not connected | `config/settings.py`, `brain/provider_hub.py`, `agents/intelligence/gemini_agent.py` | Metadata exists, but no key is configured and no verified live call is happening | Real Gemini env keys plus provider-hub and response-engine execution path |
| OPENAI (`gpt-4o-mini`) | not connected | `config/settings.py`, `brain/provider_hub.py`, `agents/intelligence/openai_agent.py` | Metadata exists, but no key is configured and no verified live call is happening | Real OpenAI env keys plus backup-brain selection logic |
| OPENROUTER (`deepseek-chat-v3`) | not connected | no code reference found | No adapter, no env key, no runtime wiring | New provider adapter plus config and runtime routing |
| TAVILY | not connected | no code reference found | Web search exists in agent names, but Tavily is not present in code | Search client, env key, and integration into research/web-search flows |
| ASSEMBLYAI | not connected | no code reference found | Current STT is local `speech_recognition`, not AssemblyAI | New STT backend adapter and voice-controller selection logic |
| ELEVENLABS | not connected | no code reference found | Current TTS is local `pyttsx3` or browser speech synthesis, not ElevenLabs | New TTS provider integration plus UI profile mapping |
| REPLICATE | not connected | no code reference found | Media/image agents exist mostly as wrappers, not Replicate-powered generation | New image-generation backend and agent/tool wiring |
| SUPABASE | not connected | no code reference found | Current persistence is local JSON plus SQLite | New DB layer for chat/user/memory persistence |
| QDRANT | not connected | no code reference found | Current vector layer is Chroma with JSON fallback | Replace or augment `memory/vector_memory.py` with Qdrant-backed storage |
| UPSTASH | not connected | no code reference found | Current sessions/rate limits are local JSON files | Cache/session backend integration in `security/session_manager.py` and related API routes |

Local substitutes in use today:
- chat history: SQLite via `memory/chat_history.py`
- structured memory: local JSON files in `memory/`
- STT: local `speech_recognition`
- TTS: local `pyttsx3` plus browser `speechSynthesis`
- vector memory: Chroma/JSON fallback, currently degraded

## 8. Trust Model

The trust model remains:

- `safe` -> auto allow
- `private` -> ask confirmation
- `sensitive` -> session approval
- `critical` -> confirmation code + PIN

Current enforcement truth:
- The trust model exists in `security/trust_engine.py`, `security/access_control.py`, `security/confirmation_system.py`, and `security/pin_manager.py`.
- It is not yet uniformly enforced through one shared tool-execution path across the whole runtime.

## 9. Design Principles

- Stability over hype
- Real capability over fake behavior
- Modular backend
- Privacy-first
- Terminal-free operation
- Trust-based execution
- Honest capability labeling
- Local control whenever possible

## 10. Implementation Rules

- Real over hybrid over placeholder
- Fake autonomy is strictly forbidden
- Fake security is strictly forbidden
- Fake memory is strictly forbidden
- Fake execution is strictly forbidden
- If a feature is not built, say it is not built
- If a feature is partial, label it partial
- UI must not overclaim backend capability
- System features must be driven by rules, storage, and real integrations before LLM polish
## 11. Next 15 Priority Updates

### UPDATE 1: Restore Live Brain Provider Execution
- Priority: Critical
- Why needed: AURA cannot be a real assistant while the default live reply path fails with a Groq auth error.
- Files to change: `D:\HeyGoku\.env`, `D:\HeyGoku\brain\core_ai.py`, `D:\HeyGoku\brain\response_engine.py`, `D:\HeyGoku\api\api_server.py`
- Depends on: none
- Estimated complexity: Medium

### UPDATE 2: Replace Provider "Configured Means Ready" Logic With Real Health Checks
- Priority: Critical
- Why needed: Provider status currently overclaims readiness and breaks AURA's honesty rule.
- Files to change: `D:\HeyGoku\brain\provider_hub.py`, `D:\HeyGoku\tests\test_provider_hub.py`, `D:\HeyGoku\api\api_server.py`
- Depends on: UPDATE 1
- Estimated complexity: Medium

### UPDATE 3: Wire Gemini As Main Brain And OpenAI As Backup Brain
- Priority: High
- Why needed: The intended multi-brain architecture exists only as metadata today.
- Files to change: `D:\HeyGoku\.env`, `D:\HeyGoku\config\settings.py`, `D:\HeyGoku\brain\provider_hub.py`, `D:\HeyGoku\brain\response_engine.py`, `D:\HeyGoku\brain\core_ai.py`, `D:\HeyGoku\agents\intelligence\gemini_agent.py`, `D:\HeyGoku\agents\intelligence\openai_agent.py`
- Depends on: UPDATE 1, UPDATE 2
- Estimated complexity: Complex

### UPDATE 4: Repair Or Replace The Broken Vector Memory Backend
- Priority: Critical
- Why needed: Vector memory is degraded and currently running on fallback storage because of disk I/O failure.
- Files to change: `D:\HeyGoku\memory\vector_memory.py`, `D:\HeyGoku\memory\vector_store\*`, `D:\HeyGoku\tests\test_vector_memory.py`
- Depends on: none
- Estimated complexity: Complex

### UPDATE 5: Repair Auth And Session Drift Until The Security Test Suite Passes
- Priority: Critical
- Why needed: A private system cannot safely expand while auth and session tests are failing.
- Files to change: `D:\HeyGoku\security\auth_manager.py`, `D:\HeyGoku\security\session_manager.py`, `D:\HeyGoku\security\tests\test_auth_manager.py`, `D:\HeyGoku\security\tests\test_session_manager.py`, `D:\HeyGoku\security\tests\test_end_to_end.py`
- Depends on: none
- Estimated complexity: Medium

### UPDATE 6: Route All Real Execution Through `tool_guard`
- Priority: High
- Why needed: Trust checks are scattered and the shared guarded tool layer is not the universal execution path.
- Files to change: `D:\HeyGoku\brain\runtime_core.py`, `D:\HeyGoku\agents\agent_fabric.py`, `D:\HeyGoku\tools\tool_guard.py`, `D:\HeyGoku\tools\tool_registry.py`, `D:\HeyGoku\tests\test_tool_execution.py`
- Depends on: UPDATE 5
- Estimated complexity: Complex

### UPDATE 7: Consolidate The Duplicate Memory Layers
- Priority: High
- Why needed: `memory_manager.py`, `knowledge_base.py`, and the structured memory layer overlap and create ownership confusion.
- Files to change: `D:\HeyGoku\memory\memory_manager.py`, `D:\HeyGoku\memory\knowledge_base.py`, `D:\HeyGoku\memory\memory_controller.py`, `D:\HeyGoku\brain\core_ai.py`, `D:\HeyGoku\brain\orchestrator.py`
- Depends on: UPDATE 4
- Estimated complexity: Complex

### UPDATE 8: Remove Or Quarantine Legacy Runtime Entry Points And Backup Brain Files
- Priority: High
- Why needed: Duplicate entry points and backup copies keep the architecture ambiguous.
- Files to change: `D:\HeyGoku\main.py`, `D:\HeyGoku\brain\core_ai_backup.py`, `D:\HeyGoku\brain\core_ai_backup2.py`, `D:\HeyGoku\brain\intent_engine_backup.py`, `D:\HeyGoku\brain\understanding_engine_backup.py`
- Depends on: UPDATE 1 through UPDATE 7 being understood
- Estimated complexity: Simple

### UPDATE 9: Restore Dependable Voice Output
- Priority: High
- Why needed: A JARVIS-style assistant needs reliable spoken output, and backend TTS is currently unavailable on this machine.
- Files to change: `D:\HeyGoku\voice\text_to_speech.py`, `D:\HeyGoku\voice\voice_controller.py`, `D:\HeyGoku\voice\voice_manager.py`, `D:\HeyGoku\interface\web\app.js`
- Depends on: none
- Estimated complexity: Medium

### UPDATE 10: Add Real AssemblyAI Speech-To-Text
- Priority: Medium
- Why needed: The project inventory expects AssemblyAI, but current STT is still local `speech_recognition`.
- Files to change: `D:\HeyGoku\voice\speech_to_text.py`, `D:\HeyGoku\voice\voice_controller.py`, `D:\HeyGoku\api\api_server.py`, `D:\HeyGoku\config\settings.py`
- Depends on: UPDATE 1, UPDATE 2
- Estimated complexity: Complex

### UPDATE 11: Make Agent Capability Honesty Explicit In The API And UI
- Priority: High
- Why needed: Generated wrapper agents should not be presented like fully bespoke real executors.
- Files to change: `D:\HeyGoku\agents\registry.py`, `D:\HeyGoku\agents\agent_fabric.py`, `D:\HeyGoku\brain\capability_registry.py`, `D:\HeyGoku\api\api_server.py`, `D:\HeyGoku\interface\web\app.js`, `D:\HeyGoku\interface\web\aura.html`
- Depends on: UPDATE 6
- Estimated complexity: Medium

### UPDATE 12: Simplify The UI Around What The Backend Can Truly Do
- Priority: Medium
- Why needed: The interface is strong, but some surfaces still imply deeper intelligence and autonomy than the backend can prove.
- Files to change: `D:\HeyGoku\interface\web\aura.html`, `D:\HeyGoku\interface\web\app.js`, `D:\HeyGoku\interface\web\styles.css`, `D:\HeyGoku\api\api_server.py`
- Depends on: UPDATE 11
- Estimated complexity: Medium

### UPDATE 13: Add Real Tavily Search For Web And Research Workflows
- Priority: Medium
- Why needed: Search agents exist, but there is no real-time search provider wired in.
- Files to change: `D:\HeyGoku\.env`, `D:\HeyGoku\tools\network_tools.py`, `D:\HeyGoku\agents\integration\web_search_agent.py`, `D:\HeyGoku\brain\runtime_core.py`
- Depends on: UPDATE 2, UPDATE 6
- Estimated complexity: Complex

### UPDATE 14: Add Real ElevenLabs Voice Output
- Priority: Medium
- Why needed: Local and browser voice fallback is not enough for a dependable JARVIS-grade voice layer.
- Files to change: `D:\HeyGoku\.env`, `D:\HeyGoku\voice\text_to_speech.py`, `D:\HeyGoku\voice\voice_controller.py`, `D:\HeyGoku\config\voice_profiles.json`, `D:\HeyGoku\interface\web\app.js`
- Depends on: UPDATE 9
- Estimated complexity: Complex

### UPDATE 15: Add External State Backends Only After Core Stability
- Priority: Medium
- Why needed: Supabase, Qdrant, and Upstash should not be layered in before the current local core becomes dependable.
- Files to change: `D:\HeyGoku\.env`, `D:\HeyGoku\memory\chat_history.py`, `D:\HeyGoku\memory\vector_memory.py`, `D:\HeyGoku\security\session_manager.py`, `D:\HeyGoku\config\settings.py`, `D:\HeyGoku\api\api_server.py`
- Depends on: UPDATE 4, UPDATE 5, UPDATE 6
- Estimated complexity: Complex

### Update Flags

3 updates that will make AURA feel most like JARVIS:
- UPDATE 3 - Wire Gemini as main brain and OpenAI as backup brain
- UPDATE 6 - Route all real execution through `tool_guard`
- UPDATE 9 - Restore dependable voice output

3 updates most critical for stability:
- UPDATE 1 - Restore live brain provider execution
- UPDATE 4 - Repair or replace the broken vector memory backend
- UPDATE 5 - Repair auth and session drift until the security test suite passes

3 updates that should not be done yet:
- UPDATE 13 - Tavily search should wait until provider health and guarded execution are fixed
- UPDATE 14 - ElevenLabs voice should wait until the local voice stack is stabilized
- UPDATE 15 - Supabase, Qdrant, and Upstash should wait until the local core is dependable

from __future__ import annotations

import os
from pathlib import Path


PROJECT_NAME = "VORIS"
FULL_PROJECT_NAME = "Voice-Oriented Responsive Intelligence System"
PROJECT_TYPE = "JARVIS-style AI assistant system"
# Derived from this file's location so it stays true on any machine; this
# value is reported to the API as "project_root". Override: VORIS_PROJECT_ROOT.
PROJECT_ROOT = os.getenv("VORIS_PROJECT_ROOT") or str(Path(__file__).resolve().parents[1])

CORE_GOALS = (
    "understand_natural_language",
    "handle_messy_input",
    "process_multi_command_requests",
    "use_memory_and_learning",
    "reason_plan_and_execute",
    "interact_with_systems_safely",
    "improve_over_time",
)

CORE_PIPELINE = (
    "perceive",
    "understand",
    "decide",
    "act",
    "reflect",
    "improve",
)

DESIGN_PRINCIPLES = (
    "stability_over_hype",
    "modular_backend",
    "terminal_first_workflow",
    "recordable_progress",
    "privacy_first_design",
    "trust_based_interaction",
    "controlled_automation",
)

TRUST_MODEL = {
    "safe": "auto_allow",
    "private": "ask_confirmation",
    "sensitive": "session_approval",
    "critical": "pin_or_password",
}

PRIVACY_MODEL = (
    "minimal_developer_access",
    "no_personal_data_exposure_by_default",
    "local_control_where_possible",
)

INTERFACE_SURFACES = (
    "chat",
    "memory",
    "intelligence",
    "autonomy",
    "tasks",
    "history",
    "settings",
    "multiple_modes",
)

ARCHITECTURE_RULES = (
    "do_not_reduce_aura_to_a_chatbot",
    "do_not_fake_capabilities",
    "respect_architecture_consistency",
    "keep_the_system_realistic_and_expandable",
)

CAPABILITY_LABELS = (
    "real",
    "hybrid",
    "placeholder",
)

IMPLEMENTATION_PRIORITY = CAPABILITY_LABELS

HYBRID_IMPLEMENTATION_ORDER = (
    "real_or_rule_logic_first",
    "state_and_storage_second",
    "llm_enhancement_third",
)

AGENT_DESIGN_ORDER = (
    "detect_intent",
    "parse_data",
    "apply_rules",
    "check_permissions",
    "execute_real_action",
    "enhance_with_ai",
)

IMPLEMENTATION_RULES = (
    "prefer_real_mechanisms_when_possible",
    "never_fake_jarvis_capabilities",
    "system_features_must_not_be_prompt_only",
    "every_feature_must_be_labeled_by_capability_mode",
    "placeholder_features_must_define_a_future_integration_path",
    "ui_must_not_overclaim_backend_capability",
)

ANTI_PATTERNS = (
    "fake_autonomy",
    "fake_security",
    "fake_purchases",
    "fake_file_handling",
    "fake_memory",
    "fake_tool_execution",
    "fake_system_status",
    "fake_pc_control",
)

TARGET_IMPLEMENTATION_PATTERN = (
    "real_systems",
    "hybrid_intelligence",
    "explicit_boundaries",
)

CURRENT_STRUCTURE = (
    "brain",
    "agents",
    "memory",
    "api",
    "interface/web",
    "voice",
    "config",
    "security",
)

CORE_SYSTEM = {
    "core_ai": "brain/core_ai.py",
    "intent_engine": "brain/intent_engine.py",
    "understanding_engine": "brain/understanding_engine.py",
    "decision_engine": "brain/decision_engine.py",
    "response_engine": "brain/response_engine.py",
}

FEATURES_BUILT = (
    "multi_command_handling",
    "memory_system",
    "learning_system",
    "reasoning_layer",
    "planning_and_execution",
    "web_interface",
    "auth_system",
    "tasks_and_reminders",
    "screenshot_and_file_system",
)

CURRENT_ISSUES = (
    "weak_typo_handling",
    "permission_not_always_triggered",
    "memory_extraction_bugs_partially_fixed",
    "fallback_to_general_too_often",
    "ui_partially_placeholder",
    "purchase_flow_not_real_yet",
)

SECURITY_STATUS = (
    "permission_engine_started",
    "pin_system_not_built_yet",
    "locked_chats_not_built_yet",
)

NEXT_BUILDS = (
    "pin_system",
    "locked_chats",
    "permission_ui",
    "real_intelligence_panel",
    "real_autonomy_panel",
    "pc_control_future",
)

SUPPORT_CHATS = {
    "backend_builder": {
        "name": "VORIS Backend Builder",
        "responsibility": "writes backend code and upgrades or refactors files",
    },
    "code_reviewer": {
        "name": "VORIS Code Reviewer",
        "responsibility": "checks code quality and safety",
    },
    "output_tester": {
        "name": "VORIS Output Tester",
        "responsibility": "analyzes runtime and output behavior",
    },
    "error_explainer": {
        "name": "VORIS Error Explainer",
        "responsibility": "explains bugs clearly",
    },
    "interface_architect": {
        "name": "VORIS Interface Architect",
        "responsibility": "designs the frontend system",
    },
}

SUPPORT_CHAT_GLOBAL_RULES = (
    "follow_aura_master_spec",
    "follow_implementation_rules",
    "do_not_guess_missing_architecture",
    "do_not_fake_features",
    "keep_code_modular_and_stable",
)

BUILDER_FINAL_AUTHORITY = "backend_builder_only_writes_final_code"


def build_current_state_summary() -> dict:
    return {
        "project_root": PROJECT_ROOT,
        "structure": list(CURRENT_STRUCTURE),
        "core_system": dict(CORE_SYSTEM),
        "features_built": list(FEATURES_BUILT),
        "current_issues": list(CURRENT_ISSUES),
        "security_status": list(SECURITY_STATUS),
        "next_builds": list(NEXT_BUILDS),
    }


def build_support_chat_summary() -> dict:
    return {
        "support_chats": dict(SUPPORT_CHATS),
        "global_rules": list(SUPPORT_CHAT_GLOBAL_RULES),
        "builder_final_authority": BUILDER_FINAL_AUTHORITY,
    }


def build_master_spec_summary() -> dict:
    return {
        "project_name": PROJECT_NAME,
        "full_project_name": FULL_PROJECT_NAME,
        "project_type": PROJECT_TYPE,
        "project_root": PROJECT_ROOT,
        "core_goals": list(CORE_GOALS),
        "core_pipeline": list(CORE_PIPELINE),
        "design_principles": list(DESIGN_PRINCIPLES),
        "trust_model": dict(TRUST_MODEL),
        "privacy_model": list(PRIVACY_MODEL),
        "interface_surfaces": list(INTERFACE_SURFACES),
        "architecture_rules": list(ARCHITECTURE_RULES),
        "capability_labels": list(CAPABILITY_LABELS),
        "implementation_priority": list(IMPLEMENTATION_PRIORITY),
        "hybrid_implementation_order": list(HYBRID_IMPLEMENTATION_ORDER),
        "agent_design_order": list(AGENT_DESIGN_ORDER),
        "implementation_rules": list(IMPLEMENTATION_RULES),
        "anti_patterns": list(ANTI_PATTERNS),
        "target_pattern": list(TARGET_IMPLEMENTATION_PATTERN),
        "current_state": build_current_state_summary(),
        "support_chats": build_support_chat_summary(),
    }

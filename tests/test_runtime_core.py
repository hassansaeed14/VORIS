import unittest
from unittest.mock import patch

import brain.runtime_core as runtime_core


class RuntimeCoreTests(unittest.TestCase):
    def test_current_info_question_uses_web_search_answer_path(self):
        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("general", 0.46),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            side_effect=AssertionError("Live web search path should run before heavy orchestration."),
        ), patch.object(
            runtime_core,
            "web_search",
            return_value={
                "success": True,
                "source": "duckduckgo_instant_answer",
                "live_data": True,
                "data": {
                    "query": "latest groq api pricing",
                    "heading": "Groq API pricing",
                    "abstract": "Groq currently prices usage by model and token volume.",
                    "related_topics": ["Pricing can change over time."],
                },
            },
        ), patch.object(
            runtime_core,
            "generate_web_search_response_payload",
            return_value={
                "success": True,
                "content": "Groq currently prices usage by model and token volume. Check the latest pricing page for the exact numbers.",
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
                "explanation_mode": "direct",
            },
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("What is the latest Groq API pricing?")

        self.assertEqual(result["execution_mode"], "web_assistant")
        self.assertEqual(result["used_agents"], ["web_search"])
        self.assertEqual(result["provider"], "groq")
        self.assertTrue(result["web_search"]["used"])
        self.assertEqual(result["web_search"]["query"], "What is the latest Groq API pricing")
        self.assertEqual(result["explanation_mode"], "direct")
        self.assertIn("latest pricing page", result["response"])

    def test_conversational_input_stays_on_general_assistant_path(self):
        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("conversation", 0.92),
        ), patch.object(
            runtime_core,
            "_llm_response_with_provider",
            return_value={
                "success": True,
                "text": "I'm here and doing well. What would you like to work on?",
                "provider_name": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
                "tokens_used": 42,
                "time_ms": 20.0,
            },
        ), patch.object(
            runtime_core,
            "web_search",
            side_effect=AssertionError("Conversation should not trigger live web search."),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            side_effect=AssertionError("Conversation should bypass orchestrator routing."),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("hi how are you")

        self.assertEqual(result["detected_intent"], "conversation")
        self.assertEqual(result["used_agents"], ["general"])
        self.assertEqual(result["execution_mode"], "conversation_llm")
        self.assertEqual(result["provider"], "groq")
        self.assertIn("doing well", result["response"].lower())

    def test_direct_question_prefers_fast_assistant_path(self):
        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("general", 0.18),
        ), patch.object(
            runtime_core,
            "_llm_response_with_provider",
            return_value={
                "success": True,
                "text": "Artificial intelligence is software designed to perform tasks that usually need human judgment, learning, or pattern recognition.",
                "provider_name": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
                "tokens_used": 51,
                "time_ms": 18.0,
            },
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            side_effect=AssertionError("Direct assistant questions should bypass heavy orchestration."),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("what is artificial intelligence")

        self.assertEqual(result["detected_intent"], "general")
        self.assertEqual(result["used_agents"], ["general"])
        self.assertEqual(result["execution_mode"], "assistant_llm")
        self.assertEqual(result["provider"], "groq")
        self.assertIn("human judgment", result["response"].lower())

    def test_long_form_write_prompt_prefers_fast_assistant_path(self):
        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("write", 0.72),
        ), patch.object(
            runtime_core,
            "_llm_response_with_provider",
            return_value={
                "success": True,
                "text": "VORIS essay draft with enough structure to continue as long-form content.",
                "provider_name": "sambanova",
                "model": "Meta-Llama-3.1-405B-Instruct",
                "providers_tried": ["sambanova"],
                "tokens_used": 120,
                "time_ms": 18.0,
            },
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            side_effect=AssertionError("Long-form writing should bypass the old writing agent path."),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("write me an essay of 1000 words about VORIS")

        self.assertEqual(result["detected_intent"], "write")
        self.assertEqual(result["used_agents"], ["general"])
        self.assertEqual(result["execution_mode"], "assistant_llm")
        self.assertEqual(result["permission_action"], "general")
        self.assertEqual(result["provider"], "sambanova")

    def test_compare_prompt_prefers_fast_assistant_path(self):
        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("general", 0.20),
        ), patch.object(
            runtime_core,
            "_llm_response_with_provider",
            return_value={
                "success": True,
                "text": "Python is easier to move quickly with, while Rust gives better performance and memory safety.",
                "provider_name": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
                "tokens_used": 55,
                "time_ms": 18.0,
            },
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            side_effect=AssertionError("Simple comparison prompts should bypass multi-agent orchestration."),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("compare python vs rust")

        self.assertEqual(result["detected_intent"], "general")
        self.assertEqual(result["used_agents"], ["general"])
        self.assertEqual(result["execution_mode"], "assistant_llm")
        self.assertEqual(result["provider"], "groq")
        self.assertIn("memory safety", result["response"].lower())

    def test_special_intent_returns_structured_metadata(self):
        orchestration = {
            "primary_agent": "time",
            "secondary_agents": [],
            "execution_order": ["time"],
            "requires_multiple": False,
            "primary_selection_source": "intent",
            "top_score": 0,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("time", 0.92),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("what time is it")

        self.assertEqual(result["intent"], "time")
        self.assertEqual(result["detected_intent"], "time")
        self.assertEqual(result["used_agents"], ["time"])
        self.assertEqual(result["execution_mode"], "special_intent")
        self.assertEqual(result["plan"], [])
        self.assertIn("current time", result["response"].lower())

    def test_keyword_orchestration_runs_multi_agent_workflow(self):
        orchestration = {
            "primary_agent": "research",
            "secondary_agents": ["summarize"],
            "execution_order": ["research", "summarize"],
            "requires_multiple": True,
            "primary_selection_source": "keyword_scoring",
            "top_score": 1,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("general", 0.30),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core.master_orchestrator,
            "synthesize_responses",
            return_value={"response": "Synthesized research summary"},
        ), patch.object(
            runtime_core,
            "research",
            return_value="Research result",
        ), patch.object(
            runtime_core,
            "summarize_text",
            return_value="Summary result",
        ), patch.object(
            runtime_core,
            "generate_response_payload",
            side_effect=AssertionError("LLM fallback should not run for orchestrated research workflow."),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"), patch("builtins.print") as print_mock:
            result = runtime_core.process_single_command_detailed("research and summarize AI agents")

        self.assertEqual(result["intent"], "research")
        self.assertEqual(result["used_agents"], ["research_runtime", "summary_runtime"])
        self.assertEqual(result["execution_mode"], "multi_agent")
        self.assertEqual(result["response"], "Synthesized research summary")
        self.assertTrue(result["plan"])
        self.assertEqual(result["orchestration"]["execution_order"], ["research", "summarize"])
        print_mock.assert_any_call("[ROUTING] research → research_runtime")
        print_mock.assert_any_call("[ROUTING] summarize → summary_runtime")

    def test_write_intent_routes_to_real_writing_runtime(self):
        orchestration = {
            "primary_agent": "write",
            "secondary_agents": [],
            "execution_order": ["write"],
            "requires_multiple": False,
            "primary_selection_source": "intent",
            "top_score": 2,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("write", 0.91),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core.master_orchestrator,
            "synthesize_responses",
            return_value={"response": "Draft ready"},
        ), patch.object(
            runtime_core,
            "write_content",
            return_value="Draft ready",
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"), patch("builtins.print") as print_mock:
            result = runtime_core.process_single_command_detailed("write a short post about AI safety")

        self.assertEqual(result["intent"], "write")
        self.assertEqual(result["detected_intent"], "write")
        self.assertEqual(result["used_agents"], ["writing_runtime"])
        self.assertEqual(result["execution_mode"], "single_agent")
        self.assertEqual(result["response"], "Draft ready")
        print_mock.assert_any_call("[ROUTING] write → writing_runtime")

    def test_task_add_request_uses_action_specific_permission(self):
        orchestration = {
            "primary_agent": "task",
            "secondary_agents": [],
            "execution_order": ["task"],
            "requires_multiple": False,
            "primary_selection_source": "intent",
            "top_score": 3,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("task", 0.94),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core,
            "check_permission",
            side_effect=lambda action, session=None, context=None: {
                "allowed": True,
                "reason": "Safe action. No approval required.",
                "required_action": "allow",
                "trust_level": "safe",
                "action": action,
                "status": "approved",
                "enforcement": {
                    "allowed": True,
                    "status": "approved",
                    "reason": "Safe action. No approval required.",
                    "trust_level": "safe",
                    "approval_type": "none",
                    "action_name": action,
                    "decision": {
                        "action_name": action,
                        "trust_level": "safe",
                        "approval_type": "none",
                        "allowed": True,
                        "reason": "Safe action. No approval required.",
                    },
                },
            },
        ) as permission_mock, patch.dict(
            runtime_core.AGENT_ROUTER,
            {"task": lambda cmd: "Task added"},
            clear=False,
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("add task buy milk")

        self.assertEqual(permission_mock.call_args.args[0], "task_add")
        self.assertEqual(result["permission_action"], "task_add")
        self.assertEqual(result["used_agents"], ["task"])
        self.assertEqual(result["agent_capabilities"][0]["id"], "task")
        self.assertEqual(result["execution_mode"], "single_agent")

    def test_provider_failure_returns_degraded_assistant_reply(self):
        orchestration = {
            "primary_agent": "general",
            "secondary_agents": [],
            "execution_order": [],
            "requires_multiple": False,
            "primary_selection_source": "intent",
            "top_score": 0,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("general", 0.88),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core,
            "generate_response_payload",
            return_value={
                "success": False,
                "error": "No healthy AI provider completed the request.",
                "providers_tried": [
                    {"provider": "gemini", "status": "unavailable", "reason": "Gemini unavailable"},
                    {"provider": "openai", "status": "rate_limited", "reason": "OpenAI rate limited"},
                ],
                "degraded_reply": "I can see the request, but I can't answer it reliably right now because my live AI providers aren't completing the request path.",
            },
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("what is quantum computing")

        self.assertEqual(result["execution_mode"], "degraded_assistant")
        self.assertTrue(result["degraded"])
        self.assertIsNone(result["provider"])
        self.assertIn("can't answer it reliably", result["response"].lower())

    def test_supported_desktop_open_request_routes_to_desktop_controller(self):
        with patch.object(
            runtime_core,
            "open_application",
            return_value={
                "success": True,
                "status": "opened",
                "app_name": "notepad",
                "label": "Notepad",
                "message": "Opening Notepad.",
                "launched_with": "C:\\Windows\\System32\\notepad.exe",
                "pid": 4312,
            },
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"), patch("builtins.print") as print_mock:
            result = runtime_core.process_single_command_detailed("open notepad")

        self.assertEqual(result["detected_intent"], "desktop_open")
        self.assertEqual(result["used_agents"], ["desktop_controller"])
        self.assertEqual(result["execution_mode"], "external_desktop")
        self.assertEqual(result["permission_action"], "desktop_launch")
        self.assertEqual(result["response"], "Opening Notepad.")
        self.assertTrue(result["desktop_launch_success"])
        self.assertEqual(result["desktop_app"], "notepad")
        print_mock.assert_any_call("[ROUTING] open \u2192 desktop_controller")

    def test_desktop_open_request_returns_clean_unavailable_message(self):
        with patch.object(
            runtime_core,
            "open_application",
            return_value={
                "success": False,
                "status": "unavailable",
                "app_name": "vs code",
                "label": "VS Code",
                "message": "I couldn't find VS Code on this system.",
                "error": "Application is not installed or not discoverable from the safe allowlist.",
            },
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"):
            result = runtime_core.process_single_command_detailed("open vs code")

        self.assertEqual(result["execution_mode"], "external_desktop")
        self.assertEqual(result["used_agents"], ["desktop_controller"])
        self.assertEqual(result["response"], "I couldn't find VS Code on this system.")
        self.assertFalse(result["desktop_launch_success"])
        self.assertEqual(result["desktop_app"], "vs code")

    def test_agent_failure_is_hardened_into_meaningful_degraded_reply(self):
        orchestration = {
            "primary_agent": "write",
            "secondary_agents": [],
            "execution_order": ["write"],
            "requires_multiple": False,
            "primary_selection_source": "intent",
            "top_score": 2,
            "mode": "real",
        }

        with patch.object(runtime_core, "detect_language", return_value="english"), patch.object(
            runtime_core,
            "detect_intent_with_confidence",
            return_value=("write", 0.92),
        ), patch.object(
            runtime_core.master_orchestrator,
            "analyze_task",
            return_value=orchestration,
        ), patch.object(
            runtime_core,
            "write_content",
            side_effect=RuntimeError("provider offline"),
        ), patch.object(
            runtime_core,
            "respond_in_language",
            side_effect=lambda response, language: response,
        ), patch.object(runtime_core, "store_and_learn"), patch("builtins.print") as print_mock:
            result = runtime_core.process_single_command_detailed("write a short post about AI")

        self.assertEqual(result["execution_mode"], "degraded_assistant")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["used_agents"], ["writing_runtime"])
        self.assertIsNone(result["provider"])
        self.assertNotIn("agent failed:", result["response"].lower())
        self.assertNotEqual(result["response"].strip(), "")
        self.assertTrue(
            any("[RUNTIME TRACE]" in str(call.args[0]) for call in print_mock.call_args_list if call.args)
        )


if __name__ == "__main__":
    unittest.main()

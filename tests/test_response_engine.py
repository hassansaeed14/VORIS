import unittest
from unittest.mock import patch

import brain.response_engine as response_engine


class ResponseEngineTests(unittest.TestCase):
    def test_long_form_writing_prompt_is_not_trimmed_to_simple_chat_length(self):
        long_draft = " ".join(f"word{i}" for i in range(180))

        polished = response_engine.polish_assistant_reply(
            long_draft,
            user_input="write me an essay of 1000 words on artificial intelligence",
        )

        self.assertEqual(polished.lower(), long_draft)
        self.assertGreater(len(polished.split()), 150)

    def test_long_form_writing_prompt_raises_provider_token_budget(self):
        captured = {}

        def fake_generate(messages, preferred=None, preferred_only=False, max_tokens=0, temperature=0.0):
            captured["max_tokens"] = max_tokens
            return {
                "success": True,
                "provider": "sambanova",
                "model": "Meta-Llama-3.1-405B-Instruct",
                "text": " ".join(f"essay{i}" for i in range(220)),
                "attempts": [{"provider": "sambanova", "status": "healthy"}],
                "routing_order": ["sambanova"],
                "latency_ms": 25.0,
            }

        with patch.object(response_engine, "generate_with_best_provider", side_effect=fake_generate):
            payload = response_engine.generate_response_payload(
                "write me an essay of 1000 words on artificial intelligence",
                max_tokens=500,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["explanation_mode"], "long_form")
        self.assertGreaterEqual(captured["max_tokens"], 2700)
        self.assertGreater(len(payload["content"].split()), 200)

    def test_generate_web_search_response_payload_returns_search_backed_answer(self):
        search_result = {
            "success": True,
            "source": "duckduckgo_instant_answer",
            "live_data": True,
            "data": {
                "query": "latest groq api pricing",
                "heading": "Groq API pricing",
                "abstract": "Groq currently prices usage by model and token volume.",
                "related_topics": [
                    "Pricing can change over time.",
                    "Check the provider status page for the latest details.",
                ],
            },
        }

        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "Groq currently prices usage by model and token volume. The exact rates can change, so check their latest pricing page for the current numbers.",
                "attempts": ["groq"],
                "routing_order": ["groq"],
                "latency_ms": 25.0,
            },
        ):
            payload = response_engine.generate_web_search_response_payload(
                "What is the latest Groq API pricing?",
                search_result,
            )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["web_used"])
        self.assertEqual(payload["provider"], "groq")
        self.assertEqual(payload["explanation_mode"], "direct")
        self.assertIn("current numbers", payload["content"])

    def test_generate_response_payload_uses_degraded_reply_when_all_providers_fail(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": False,
                "reason": "No healthy AI provider completed the request.",
                "attempts": [
                    {"provider": "gemini", "status": "unavailable", "reason": "Gemini unavailable"},
                    {"provider": "openai", "status": "rate_limited", "reason": "OpenAI rate limited"},
                    {"provider": "groq", "status": "auth_failed", "reason": "Groq auth failed"},
                ],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("What is wrong with my setup?")

        self.assertFalse(payload["success"])
        self.assertIn("clean live answer", payload["degraded_reply"].lower())
        self.assertIn("gemini", payload["degraded_reply"].lower())
        self.assertNotIn("check provider health", payload["degraded_reply"].lower())

    def test_build_degraded_reply_uses_natural_tone(self):
        reply = response_engine.build_degraded_reply(
            "What is quantum computing?",
            providers_tried=[{"provider": "groq", "status": "rate_limited"}],
        )

        self.assertIn("clean live answer", reply.lower())
        self.assertIn("groq", reply.lower())
        self.assertNotIn("live ai providers", reply.lower())
        self.assertNotIn("check provider health", reply.lower())

    def test_generate_response_payload_retries_before_using_fallback_provider(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            side_effect=[
                {
                    "success": True,
                    "provider": "groq",
                    "model": "llama-3.3-70b-versatile",
                    "text": "I don't see a specific question or request. Could you provide more context?",
                    "attempts": [{"provider": "groq", "status": "success"}],
                    "routing_order": ["groq"],
                    "latency_ms": 12.0,
                },
                {
                    "success": False,
                    "reason": "Primary retry failed.",
                    "attempts": [{"provider": "groq", "status": "rate_limited", "reason": "retry failed"}],
                    "routing_order": ["groq"],
                },
                {
                    "success": True,
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "text": "Quantum computing uses qubits to process probabilities and interference effects.",
                    "attempts": [{"provider": "openai", "status": "success"}],
                    "routing_order": ["groq", "openai"],
                    "latency_ms": 28.0,
                },
            ],
        ) as provider_mock:
            payload = response_engine.generate_response_payload("What is quantum computing?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["response_stage"], "fallback_provider")
        self.assertEqual(
            payload["content"],
            "Quantum computing uses qubits to process probabilities and interference effects.",
        )
        self.assertEqual(provider_mock.call_count, 3)
        self.assertTrue(provider_mock.call_args_list[0].kwargs["preferred_only"])
        self.assertTrue(provider_mock.call_args_list[1].kwargs["preferred_only"])
        self.assertFalse(provider_mock.call_args_list[2].kwargs["preferred_only"])

    def test_generate_response_returns_structured_degraded_reply(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": False,
                "reason": "No healthy AI provider completed the request.",
                "attempts": [{"provider": "groq", "status": "rate_limited"}],
                "routing_order": ["groq"],
            },
        ):
            reply = response_engine.generate_response("What is quantum computing?")

        self.assertIn("clean live answer", reply.lower())
        self.assertNotIn("check provider health", reply.lower())

    def test_generate_response_payload_strips_canned_filler_for_questions(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "text": "Certainly, sir. Quantum computing uses qubits.",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("What is quantum computing?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["content"], "Quantum computing uses qubits.")

    def test_generate_response_payload_strips_stale_memory_filler_for_non_history_question(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "We've discussed this before. Quantum computing uses qubits to represent probabilities.",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("What is quantum computing?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["content"], "Quantum computing uses qubits to represent probabilities.")

    def test_generate_response_payload_strips_false_repeat_claims(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "I've answered this question for you multiple times before. Elon Musk is a business magnate and entrepreneur.",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("Who is Elon Musk?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["content"], "Elon Musk is a business magnate and entrepreneur.")

    def test_generate_response_payload_strips_recap_wrappers(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "I've noticed that you've asked about stress multiple times before. To recap, some common strategies include deep breathing and a short walk.",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("What should I do if I am feeling stressed?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["content"], "Some common strategies include deep breathing and a short walk.")

    def test_generate_response_payload_strips_repeat_claim_sentences(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "You've asked this question before, multiple times. I'd be happy to explain it again. Quantum computing uses qubits and quantum effects to process information.",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("What is quantum computing?")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["content"], "Quantum computing uses qubits and quantum effects to process information.")

    def test_generate_response_payload_applies_cleanup_to_direct_requests(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "It seems like you've asked this before. I'll provide the answer again. Here's a Python function:\ndef reverse_string(s):\n    return s[::-1]",
                "attempts": [],
                "routing_order": ["gemini", "openai", "groq"],
            },
        ):
            payload = response_engine.generate_response_payload("Write me a Python function to reverse a string")

        self.assertTrue(payload["success"])
        self.assertTrue(payload["content"].startswith("Here's a Python function:"))

    def test_generate_response_payload_sets_comparison_explanation_mode(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "text": "Python is simpler to learn, while Rust gives tighter control over memory and performance.",
                "attempts": [],
                "routing_order": ["groq"],
            },
        ):
            payload = response_engine.generate_response_payload("Compare Python vs Rust")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["explanation_mode"], "comparison")

    def test_generate_response_payload_uses_primary_provider_only_for_normal_answers(self):
        with patch.object(
            response_engine,
            "generate_with_best_provider",
            return_value={
                "success": False,
                "reason": "No healthy AI provider completed the request.",
                "attempts": [
                    {"provider": "groq", "status": "auth_failed", "reason": "Groq auth failed"},
                ],
                "routing_order": ["groq"],
            },
        ) as provider_mock:
            response_engine.generate_response_payload("What is quantum computing?")

        self.assertTrue(provider_mock.called)
        self.assertTrue(provider_mock.call_args_list[0].kwargs["preferred_only"])
        self.assertEqual(provider_mock.call_args_list[0].kwargs["preferred"], response_engine.DEFAULT_REASONING_PROVIDER)

    def test_local_assignment_content_expands_for_large_page_targets(self):
        content = response_engine._build_local_assignment_content("transformers", page_target=10)

        for heading in (
            "Introduction",
            "Background / History",
            "Core Concepts",
            "Applications",
            "Advantages",
            "Limitations",
            "Conclusion",
        ):
            self.assertIn(heading, content.splitlines())
        self.assertGreaterEqual(len(content.split()), 10 * 180)
        self.assertLessEqual(len(content.split()), 10 * 230)
        self.assertIn("machine learning", content.lower())
        self.assertNotIn("this section should", content.lower())
        self.assertNotIn("this assignment has examined", content.lower())

    def test_assignment_depth_profile_scales_by_page_band(self):
        compact = response_engine._build_assignment_depth_profile(4)
        expanded = response_engine._build_assignment_depth_profile(7)
        extended = response_engine._build_assignment_depth_profile(10)

        self.assertEqual(compact["band"], "compact")
        self.assertEqual(compact["base_paragraph_target"], 2)
        self.assertEqual(compact["paragraph_ceiling"], 2)
        self.assertEqual(compact["max_tokens"], 480)

        self.assertEqual(expanded["band"], "expanded")
        self.assertEqual(expanded["base_paragraph_target"], 2)
        self.assertEqual(expanded["paragraph_ceiling"], 3)
        self.assertEqual(expanded["max_tokens"], 620)

        self.assertEqual(extended["band"], "extended")
        self.assertEqual(extended["base_paragraph_target"], 3)
        self.assertEqual(extended["paragraph_ceiling"], 4)
        self.assertEqual(extended["max_tokens"], 760)

    def test_assignment_section_weighting_makes_intro_lighter_than_core(self):
        intro = response_engine._resolve_assignment_section_depth("Introduction", 10)
        core = response_engine._resolve_assignment_section_depth("Core Concepts", 10)
        conclusion = response_engine._resolve_assignment_section_depth("Conclusion", 10)

        self.assertEqual(intro["weight_label"], "light")
        self.assertEqual(core["weight_label"], "high")
        self.assertLess(intro["paragraph_target"], core["paragraph_target"])
        self.assertLess(intro["token_budget"], core["token_budget"])
        self.assertLess(conclusion["token_budget"], core["token_budget"])

    def test_assignment_section_weighting_scales_core_depth_in_extended_mode(self):
        compact_core = response_engine._resolve_assignment_section_depth("Core Concepts", 4)
        extended_core = response_engine._resolve_assignment_section_depth("Core Concepts", 10)

        self.assertLess(compact_core["paragraph_target"], extended_core["paragraph_target"])
        self.assertLess(compact_core["token_budget"], extended_core["token_budget"])

    def test_assignment_section_plan_uses_technical_style_variants_for_technical_topics(self):
        plan = response_engine._build_assignment_section_plan("transformers", 10)
        titles = [section["title"] for section in plan]
        kinds = [section["kind"] for section in plan]
        purposes = {section["title"]: section["purpose"] for section in plan}

        self.assertIn("Architecture and Mechanism", titles)
        self.assertIn("Applications", titles)
        self.assertIn("implementation considerations", kinds)
        self.assertLess(titles.index("Architecture and Mechanism"), titles.index("Applications"))
        self.assertIn("without moving into full definitions or mechanism detail", purposes["Background"])
        self.assertIn("without re-explaining the mechanism in full", purposes["Applications"])

    def test_assignment_section_plan_uses_comparative_style_for_comparison_topics(self):
        plan = response_engine._build_assignment_section_plan("python vs rust", 7)
        titles = [section["title"] for section in plan]
        kinds = [section["kind"] for section in plan]

        self.assertIn("Background", titles)
        self.assertIn("Comparative Analysis", titles)
        self.assertIn("Applications", titles)
        self.assertIn("Challenges", titles)
        self.assertIn("comparative perspective", kinds)
        self.assertNotIn("How It Works", titles)

    def test_assignment_domain_guidance_uses_topic_sensitive_terminology(self):
        technical = response_engine._build_assignment_domain_guidance("transformers", "how it works", "technical")
        social = response_engine._build_assignment_domain_guidance("climate change", "background and context", "standard")
        comparative = response_engine._build_assignment_domain_guidance("python vs rust", "comparative perspective", "comparative")

        self.assertEqual(technical["domain"], "technical")
        self.assertIn("system components", technical["prompt_terminology"])
        self.assertIn("data flow", technical["prompt_examples"])

        self.assertEqual(social["domain"], "social")
        self.assertIn("institutions, communities, policy", social["prompt_terminology"])
        self.assertIn("policy environments", social["prompt_examples"])

        self.assertEqual(comparative["domain"], "comparative")
        self.assertIn("criteria, tradeoffs, alternatives", comparative["prompt_terminology"])
        self.assertIn("side-by-side scenarios", comparative["prompt_examples"])

    def test_assignment_section_prompt_reflects_page_band_depth(self):
        compact_prompt = response_engine._build_assignment_section_prompt(
            "transformers",
            "core concepts",
            "Core Concepts",
            "Define the main ideas clearly.",
            4,
        )
        extended_prompt = response_engine._build_assignment_section_prompt(
            "transformers",
            "core concepts",
            "Core Concepts",
            "Define the main ideas clearly.",
            10,
        )
        intro_prompt = response_engine._build_assignment_section_prompt(
            "transformers",
            "introduction",
            "Introduction",
            "Introduce the topic.",
            10,
        )

        self.assertIn("Section weight: high.", compact_prompt)
        self.assertIn("2 coherent paragraphs", compact_prompt)
        self.assertIn("Keep the section concise and focused", compact_prompt)
        self.assertIn("Focus on the main concepts, principles, definitions, and relationships", compact_prompt)
        self.assertIn("Do not repeat background history, a full mechanism walkthrough, or use-case examples", compact_prompt)
        self.assertIn("system components, architecture, data flow", compact_prompt)
        self.assertIn("4 coherent paragraphs", extended_prompt)
        self.assertIn("Section weight: high.", extended_prompt)
        self.assertIn("Use fuller academic depth", extended_prompt)
        self.assertIn("2 coherent paragraphs", intro_prompt)
        self.assertIn("Section weight: light.", intro_prompt)
        self.assertIn("Keep this section brief", intro_prompt)

    def test_assignment_section_prompt_uses_social_domain_terminology_for_social_topics(self):
        social_prompt = response_engine._build_assignment_section_prompt(
            "climate change",
            "background and context",
            "Background and Context",
            "Explain the wider context around the topic.",
            7,
        )

        self.assertIn("institutions, communities, policy", social_prompt)
        self.assertIn("policy environments", social_prompt)

    def test_generate_document_content_payload_uses_chunked_sections_for_large_assignments(self):
        captured_calls = []

        def fake_generate(prompt, system_override=None, max_tokens=0, temperature=0.0):
            heading = prompt.split("Write only the '", 1)[1].split("'", 1)[0]
            captured_calls.append(
                {
                    "heading": heading,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            return {
                "success": True,
                "content": f"{heading}\nThis is the {heading.lower()} section.",
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
            }

        with patch.object(response_engine, "generate_response_payload", side_effect=fake_generate) as payload_mock:
            payload = response_engine.generate_document_content_payload(
                "assignment",
                "artificial intelligence",
                page_target=10,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["source"], "provider_chunked")
        self.assertEqual(payload["provider"], "groq")
        self.assertIn("Background / History", payload["content"])
        self.assertIn("Advantages", payload["content"])
        self.assertIn("Limitations", payload["content"])
        self.assertGreaterEqual(len(payload["content"].split()), 10 * 180)
        self.assertGreaterEqual(payload_mock.call_count, 10)
        intro_call = next(call for call in captured_calls if call["heading"] == "Introduction")
        core_call = next(call for call in captured_calls if call["heading"] == "Core Concepts")
        comparison_call = next(call for call in captured_calls if call["heading"] == "Comparative Perspective")
        self.assertEqual(intro_call["max_tokens"], 418)
        self.assertEqual(core_call["max_tokens"], 760)
        self.assertEqual(comparison_call["max_tokens"], 745)
        self.assertLess(intro_call["max_tokens"], core_call["max_tokens"])
        self.assertTrue(all(call["temperature"] == 0.35 for call in captured_calls))

    def test_generate_document_content_payload_uses_lighter_chunk_depth_for_mid_size_assignments(self):
        captured_calls = []

        def fake_generate(prompt, system_override=None, max_tokens=0, temperature=0.0):
            heading = prompt.split("Write only the '", 1)[1].split("'", 1)[0]
            captured_calls.append(
                {
                    "heading": heading,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            return {
                "success": True,
                "content": f"{heading}\nThis is the {heading.lower()} section.",
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "providers_tried": ["groq"],
            }

        with patch.object(response_engine, "generate_response_payload", side_effect=fake_generate) as payload_mock:
            payload = response_engine.generate_document_content_payload(
                "assignment",
                "artificial intelligence",
                page_target=4,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["source"], "provider_chunked")
        self.assertGreaterEqual(payload_mock.call_count, 8)
        intro_call = next(call for call in captured_calls if call["heading"] == "Introduction")
        core_call = next(call for call in captured_calls if call["heading"] == "Core Concepts")
        self.assertEqual(intro_call["max_tokens"], 264)
        self.assertEqual(core_call["max_tokens"], 480)
        self.assertLess(intro_call["max_tokens"], core_call["max_tokens"])
        self.assertTrue(all(call["temperature"] == 0.33 for call in captured_calls))
        self.assertTrue(any("2 coherent paragraphs" in call["prompt"] for call in captured_calls))

    def test_local_assignment_section_body_respects_weighting(self):
        intro_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "introduction",
            page_target=10,
            display_title="Introduction",
        )
        core_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "core concepts",
            page_target=10,
            display_title="Core Concepts",
        )

        self.assertLess(len(intro_body.split()), len(core_body.split()))
        self.assertIn("machine learning", core_body.lower())
        self.assertNotIn("this section should", intro_body.lower())

    def test_local_assignment_section_body_adds_distinctness_guidance_for_adjacent_sections(self):
        background_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "background and context",
            page_target=10,
            display_title="Technical Background and Context",
        )
        mechanism_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "how it works",
            page_target=10,
            display_title="Architecture and Mechanism",
        )
        applications_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "applications",
            page_target=10,
            display_title="Applications and Use Cases",
        )

        self.assertIn("historical growth", background_body)
        self.assertIn("machine learning", mechanism_body.lower())
        self.assertIn("medical decision support", applications_body)
        self.assertNotIn("this section should", background_body.lower())

    def test_local_assignment_section_body_uses_topic_sensitive_domain_support(self):
        technical_body = response_engine._build_local_assignment_section_body(
            "transformers",
            "how it works",
            page_target=10,
            display_title="Architecture and Mechanism",
        )
        social_body = response_engine._build_local_assignment_section_body(
            "climate change",
            "background and context",
            page_target=10,
            display_title="Background and Context",
        )
        comparative_body = response_engine._build_local_assignment_section_body(
            "python vs rust",
            "comparative perspective",
            page_target=10,
            display_title="Comparative Analysis",
        )

        self.assertIn("machine learning", technical_body.lower())
        self.assertIn("greenhouse gas emissions", social_body)
        self.assertIn("alternatives", comparative_body.lower())

    def test_local_assignment_content_uses_style_variant_titles(self):
        technical_content = response_engine._build_local_assignment_content("transformers", page_target=10)
        comparative_content = response_engine._build_local_assignment_content("python vs rust", page_target=7)

        self.assertIn("Core Concepts", technical_content)
        self.assertIn("Applications", technical_content)
        self.assertIn("Background / History", comparative_content)
        self.assertIn("Limitations", comparative_content)
        self.assertNotIn("this section should", technical_content.lower())

    def test_infer_explanation_mode_prefers_simple_when_user_says_simply(self):
        mode = response_engine.infer_explanation_mode("Explain artificial intelligence simply")
        self.assertEqual(mode, "simple")

    def test_polish_assistant_reply_strips_personalized_and_formal_wrappers(self):
        raw = (
            "Hello Hassan from Mansehra, I'd be happy to help you compare Python and Rust. "
            "Python is easier to learn, while Rust gives you tighter performance control."
        )
        cleaned = response_engine.polish_assistant_reply(raw, user_input="compare python vs rust")
        self.assertNotIn("Hassan", cleaned)
        self.assertNotIn("Mansehra", cleaned)
        self.assertTrue(cleaned.startswith("I'd be happy to help you compare Python and Rust.") or cleaned.startswith("Python is easier"))

    def test_polish_assistant_reply_trims_overlong_direct_answers(self):
        raw = (
            "Quantum computing is a computing model that uses qubits and quantum effects. "
            "Unlike classical bits, qubits can represent multiple possibilities at once. "
            "That can make some specialized problems much faster to solve. "
            "It may help in cryptography, optimization, chemistry, and simulation."
        )
        cleaned = response_engine.polish_assistant_reply(raw, user_input="what is quantum computing")
        self.assertLessEqual(len(cleaned), 420)
        self.assertIn("Quantum computing", cleaned)


if __name__ == "__main__":
    unittest.main()

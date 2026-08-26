import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import api.api_server as api_server
from tests.support import SetupGateBypassMixin
from brain.response_engine import shape_response_for_task
from tools import image_generation


ROOT = Path(__file__).resolve().parents[1]


class ResponseRenderingTests(SetupGateBypassMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(api_server.app)

    def test_stream_endpoint_emits_chunks_and_final_payload(self):
        async def fake_chat(_payload, _request):
            return JSONResponse(
                content={
                    "success": True,
                    "reply": "First chunk. Second chunk.",
                    "content": "First chunk. Second chunk.",
                    "request_id": "chat-test",
                    "execution_mode": "assistant_llm",
                    "action_trace": {"request_id": "chat-test", "final_status": "ok"},
                }
            )

        with patch.object(api_server, "api_chat", side_effect=fake_chat):
            with self.client.stream("POST", "/api/chat/stream", json={"message": "hello"}) as response:
                body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: start", body)
        self.assertIn("event: chunk", body)
        self.assertIn("event: final", body)
        self.assertIn('"request_id":"chat-test"', body)

    def test_stream_endpoint_does_not_stream_document_cards_as_text_chunks(self):
        async def fake_chat(_payload, _request):
            return JSONResponse(
                content={
                    "success": True,
                    "reply": "Done. Your assignment is ready.",
                    "content": "Done. Your assignment is ready.",
                    "request_id": "chat-doc",
                    "execution_mode": "document_generation",
                    "document_delivery": {"download_url": "/downloads/a.pdf", "file_name": "a.pdf"},
                }
            )

        with patch.object(api_server, "api_chat", side_effect=fake_chat):
            with self.client.stream("POST", "/api/chat/stream", json={"message": "write assignment"}) as response:
                body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('"streaming":false', body)
        self.assertNotIn("event: chunk", body)
        self.assertIn("event: final", body)

    def test_frontend_markdown_renderer_uses_safe_dom_text_paths(self):
        source = (ROOT / "interface" / "web_v2" / "app.js").read_text(encoding="utf-8")
        self.assertIn("appendInlineMarkdown", source)
        self.assertIn("document.createTextNode", source)
        self.assertIn("textContent", source)
        self.assertNotIn("container.innerHTML", source)

    def test_frontend_code_blocks_are_copyable(self):
        source = (ROOT / "interface" / "web_v2" / "app.js").read_text(encoding="utf-8")
        self.assertIn("buildCodeBlock", source)
        self.assertIn("Copy code", source)
        self.assertIn("codeElement.textContent", source)

    def test_response_shaping_removes_weak_openings_and_keeps_markdown(self):
        shaped = shape_response_for_task(
            "Certainly! Here's some information:\n\n## Title\n\n```python\nprint('hi')\n```",
            "code",
        )
        self.assertNotIn("Certainly", shaped)
        self.assertNotIn("Here's some information", shaped)
        self.assertIn("## Title", shaped)
        self.assertIn("```python", shaped)

    def test_image_generation_unavailable_does_not_fake_output(self):
        with patch.dict("os.environ", {}, clear=True):
            result = image_generation.generate_image("generate image of a calm cyan orb")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["images"], [])
        self.assertNotIn("image_url", result)

    def test_api_chat_routes_image_request_to_honest_unavailable_response(self):
        with patch.object(api_server, "_current_user", return_value=None), patch.object(
            api_server,
            "_pollinations_api_key",
            return_value="",
        ), patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": False},
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "generate image of a blue assistant orb", "mode": "hybrid"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "image_generation")
        self.assertEqual(body["intent"], "image_generation")
        self.assertIn("not configured", body["reply"].lower())
        self.assertFalse(body["image_generation"]["success"])
        self.assertEqual(body["image_generation"]["images"], [])

    def test_api_chat_routes_uploaded_image_before_auth_gate(self):
        image_message = (
            "[VISION_PROMPT]Describe this image.[/VISION_PROMPT]"
            "[VISION_URL]data:image/png;base64,abc123==[/VISION_URL]"
        )
        with patch.object(api_server, "_current_user", return_value=None), patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": False},
        ), patch.object(
            api_server,
            "enforce_action",
            side_effect=AssertionError("Vision chat should not hit the auth gate."),
        ), patch.object(
            api_server,
            "generate_with_provider",
            return_value={
                "success": True,
                "provider": "groq",
                "model": "vision-test-model",
                "text": "The image shows a test subject.",
            },
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": image_message, "mode": "hybrid"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kind"], "vision")
        self.assertEqual(body["intent"], "vision")
        self.assertEqual(body["execution_mode"], "vision")
        self.assertIn("test subject", body["reply"])


if __name__ == "__main__":
    unittest.main()

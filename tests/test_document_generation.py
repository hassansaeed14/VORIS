import tempfile
import unittest
import zipfile
import re
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import api.api_server as api_server
import brain.core_ai as core_ai
import brain.runtime_core as runtime_core
from security.trust_engine import build_permission_response
import tools.document_generator as document_generator


class DocumentGeneratorTests(unittest.TestCase):
    REQUIRED_ASSIGNMENT_HEADINGS = [
        "Introduction",
        "Background / History",
        "Core Concepts",
        "Applications",
        "Advantages",
        "Limitations",
        "Conclusion",
    ]

    def _assert_assignment_quality(self, content: str, *, pages: int, topic_keyword: str) -> None:
        headings = [
            line.strip()
            for line in str(content or "").splitlines()
            if line.strip() in self.REQUIRED_ASSIGNMENT_HEADINGS
        ]
        word_count = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", str(content or "")))
        lowered = str(content or "").lower()

        self.assertEqual(headings, self.REQUIRED_ASSIGNMENT_HEADINGS)
        self.assertGreaterEqual(word_count, pages * 180)
        self.assertLessEqual(word_count, pages * 230)
        self.assertIn(topic_keyword, lowered)
        for weak_phrase in (
            "this section explains",
            "this section should",
            "you should discuss",
            "the student should",
            "a strong conclusion should",
            "this assignment will",
            "in this assignment",
            "placeholder",
        ):
            self.assertNotIn(weak_phrase, lowered)

    def test_detect_document_request_parses_notes_assignment_and_format(self):
        notes_request = document_generator.detect_document_request("make notes on transformers in pdf")
        assignment_request = document_generator.detect_document_request("write 5 page assignment on machine learning in docx")
        prefix_notes_request = document_generator.detect_document_request("give me docx notes on ai")
        inline_format_notes_request = document_generator.detect_document_request("make notes in pdf on transformers")
        inferred_assignment_request = document_generator.detect_document_request("make me a 10 page pdf on transformers")
        inline_assignment_request = document_generator.detect_document_request("write assignment in pdf on artificial intelligence")
        multi_output_request = document_generator.detect_document_request("make assignment on artificial intelligence and also slides with references in apa style")
        noisy_assignment_request = document_generator.detect_document_request(
            "write 10 pages professional format assignment on sociology give download link in pdf"
        )

        self.assertIsNotNone(notes_request)
        self.assertEqual(notes_request.document_type, "notes")
        self.assertEqual(notes_request.topic, "transformers")
        self.assertEqual(notes_request.export_format, "pdf")

        self.assertIsNotNone(assignment_request)
        self.assertEqual(assignment_request.document_type, "assignment")
        self.assertEqual(assignment_request.topic, "machine learning")
        self.assertEqual(assignment_request.export_format, "docx")
        self.assertEqual(assignment_request.page_target, 5)

        self.assertIsNotNone(prefix_notes_request)
        self.assertEqual(prefix_notes_request.document_type, "notes")
        self.assertEqual(prefix_notes_request.topic, "ai")
        self.assertEqual(prefix_notes_request.export_format, "docx")

        self.assertIsNotNone(inline_format_notes_request)
        self.assertEqual(inline_format_notes_request.document_type, "notes")
        self.assertEqual(inline_format_notes_request.topic, "transformers")
        self.assertEqual(inline_format_notes_request.export_format, "pdf")

        self.assertIsNotNone(inferred_assignment_request)
        self.assertEqual(inferred_assignment_request.document_type, "assignment")
        self.assertEqual(inferred_assignment_request.topic, "transformers")
        self.assertEqual(inferred_assignment_request.export_format, "pdf")
        self.assertEqual(inferred_assignment_request.page_target, 10)

        self.assertIsNotNone(inline_assignment_request)
        self.assertEqual(inline_assignment_request.document_type, "assignment")
        self.assertEqual(inline_assignment_request.topic, "artificial intelligence")
        self.assertEqual(inline_assignment_request.export_format, "pdf")

        self.assertIsNotNone(multi_output_request)
        self.assertEqual(multi_output_request.topic, "artificial intelligence")
        self.assertEqual(multi_output_request.requested_formats, ("txt", "pptx"))
        self.assertEqual(multi_output_request.style, "professional")
        self.assertTrue(multi_output_request.include_references)
        self.assertEqual(multi_output_request.citation_style, "apa")

        self.assertIsNotNone(noisy_assignment_request)
        self.assertEqual(noisy_assignment_request.document_type, "assignment")
        self.assertEqual(noisy_assignment_request.topic, "sociology")
        self.assertEqual(noisy_assignment_request.export_format, "pdf")
        self.assertEqual(noisy_assignment_request.page_target, 10)

    def test_generate_document_writes_requested_export_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value={
                "success": True,
                "content": "Introduction\nThis is a generated assignment.",
                "provider": "local",
                "model": "template",
                "source": "local_template",
                "degraded": True,
                "providers_tried": [],
            },
        ):
            txt_result = document_generator.generate_document("notes", "artificial intelligence", "txt")
            pdf_result = document_generator.generate_document("assignment", "machine learning", "pdf", formats=("pdf", "pptx"), include_references=True, citation_style="apa")
            docx_result = document_generator.generate_document("assignment", "deep learning", "docx", page_target=6)

            self.assertTrue(Path(txt_result["file_path"]).exists())
            self.assertTrue(Path(pdf_result["file_path"]).exists())
            self.assertTrue(Path(docx_result["file_path"]).exists())
            self.assertTrue(Path(pdf_result["artifacts"]["pptx"]["file_path"]).exists())
            self.assertTrue(txt_result["download_url"].startswith("/downloads/"))
            self.assertEqual(Path(pdf_result["file_path"]).suffix.lower(), ".pdf")
            self.assertEqual(Path(docx_result["file_path"]).suffix.lower(), ".docx")
            self.assertEqual(docx_result["page_target"], 6)
            self.assertEqual(txt_result["message"], "Done. Your notes are ready.")
            self.assertEqual(pdf_result["message"], "Done. Your document set is ready.")
            self.assertEqual(sorted(txt_result["available_formats"]), ["docx", "pdf", "pptx", "txt"])
            self.assertIn("pdf", txt_result["alternate_format_links"])
            self.assertIn("docx", txt_result["alternate_format_links"])
            self.assertIn("document_delivery", txt_result)
            self.assertEqual(txt_result["document_delivery"]["download_url"], txt_result["download_url"])
            self.assertEqual(txt_result["document_delivery"]["format"], "txt")
            self.assertEqual(pdf_result["requested_formats"], ["pdf", "pptx"])
            self.assertEqual([item["format"] for item in pdf_result["files"]], ["pdf", "pptx"])
            self.assertEqual(txt_result["file_name"], "AI-Notes.txt")
            self.assertEqual(pdf_result["file_name"], "ML-Assignment.pdf")
            self.assertEqual(docx_result["file_name"], "DL-Assignment.docx")
            self.assertEqual(pdf_result["artifacts"]["pptx"]["file_name"], "ML-Assignment-Slides.pptx")
            self.assertTrue(txt_result["preview_text"].startswith("Introduction") or txt_result["preview_text"].startswith("Overview"))
            self.assertEqual(txt_result["document_delivery"]["preview_text"], txt_result["preview_text"])
            txt_content = Path(txt_result["file_path"]).read_text(encoding="utf-8")
            self.assertIn("ARTIFICIAL INTELLIGENCE", txt_content)
            self.assertIn("DOCUMENT DETAILS", txt_content)
            assignment_txt = Path(pdf_result["artifacts"]["txt"]["file_path"]).read_text(encoding="utf-8")
            self.assertIn("Topic: Machine Learning", assignment_txt)
            self.assertIn("1. Introduction", assignment_txt)
            self.assertIn("References", assignment_txt)
            with zipfile.ZipFile(pdf_result["artifacts"]["pptx"]["file_path"]) as presentation_archive:
                archived_names = set(presentation_archive.namelist())
            self.assertIn("ppt/presentation.xml", archived_names)
            self.assertIn("ppt/slides/slide1.xml", archived_names)

    def test_assignment_generation_enforces_structure_length_and_topic_quality(self):
        weak_payload = {
            "success": True,
            "content": "Introduction\nThis section explains what should be discussed.",
            "provider": "local",
            "model": "template",
            "source": "local_template",
            "degraded": True,
            "providers_tried": [],
        }
        required_headings = [
            "Introduction",
            "Background / History",
            "Core Concepts",
            "Applications",
            "Advantages",
            "Limitations",
            "Conclusion",
        ]
        topic_keywords = {
            "sociology": "social institutions",
            "AI": "machine learning",
            "climate change": "greenhouse gas emissions",
        }

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=weak_payload,
        ):
            for topic, keyword in topic_keywords.items():
                result = document_generator.generate_document(
                    "assignment",
                    f"write 3 pages professional format assignment on {topic} give download link",
                    "txt",
                    page_target=3,
                )
                content = result["content"]
                content_lines = set(content.splitlines())

                self.assertEqual(result["topic"], topic)
                for heading in required_headings:
                    self.assertIn(heading, content_lines)
                self.assertGreaterEqual(len(content.split()), 3 * 180)
                self.assertLessEqual(len(content.split()), 3 * 230)
                self.assertIn(keyword, content.lower())
                self.assertNotIn("this section explains", content.lower())
                self.assertNotIn("you should discuss", content.lower())

    def test_assignment_generation_respects_page_bands_and_exact_structure(self):
        weak_payload = {
            "success": True,
            "content": (
                "Introduction\n"
                "This section explains what should be discussed.\n\n"
                "Conclusion\n"
                "A strong conclusion should summarize the topic."
            ),
            "provider": "local",
            "model": "template",
            "source": "local_template",
            "degraded": True,
            "providers_tried": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=weak_payload,
        ):
            for pages in (3, 7, 10):
                result = document_generator.generate_document(
                    "assignment",
                    "climate change",
                    "txt",
                    page_target=pages,
                )

                self._assert_assignment_quality(
                    result["content"],
                    pages=pages,
                    topic_keyword="greenhouse gas emissions",
                )

    def test_assignment_exports_preserve_clean_academic_structure(self):
        weak_payload = {
            "success": True,
            "content": "Introduction\nThis section explains what should be discussed.",
            "provider": "local",
            "model": "template",
            "source": "local_template",
            "degraded": True,
            "providers_tried": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=weak_payload,
        ):
            result = document_generator.generate_document(
                "assignment",
                "artificial intelligence",
                "docx",
                formats=("docx", "pdf", "txt", "pptx"),
                page_target=3,
            )

            txt_content = Path(result["artifacts"]["txt"]["file_path"]).read_text(encoding="utf-8")
            self.assertIn("1. Introduction", txt_content)
            self.assertIn("7. Conclusion", txt_content)

            pdf_bytes = Path(result["artifacts"]["pdf"]["file_path"]).read_bytes()
            self.assertIn(b"1. Introduction", pdf_bytes)
            self.assertIn(b"7. Conclusion", pdf_bytes)

            with zipfile.ZipFile(result["artifacts"]["docx"]["file_path"]) as docx_archive:
                document_xml = docx_archive.read("word/document.xml").decode("utf-8")
            self.assertIn("1. Introduction", document_xml)
            self.assertIn("7. Conclusion", document_xml)

            with zipfile.ZipFile(result["artifacts"]["pptx"]["file_path"]) as pptx_archive:
                slide_xml = "\n".join(
                    pptx_archive.read(name).decode("utf-8")
                    for name in pptx_archive.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                )
            self.assertIn("Introduction", slide_xml)
            self.assertIn("Conclusion", slide_xml)

    def test_resolve_document_request_supports_format_followup(self):
        first_request = document_generator.resolve_document_request(
            "write assignment on artificial intelligence",
            session_id="session-doc",
        )
        followup_request = document_generator.resolve_document_request(
            "as pdf and ppt",
            session_id="session-doc",
        )

        self.assertIsNotNone(first_request)
        self.assertIsNotNone(followup_request)
        self.assertEqual(followup_request.document_type, "assignment")
        self.assertEqual(followup_request.topic, "artificial intelligence")
        self.assertEqual(followup_request.export_format, "pdf")
        self.assertEqual(followup_request.requested_formats, ("pdf", "pptx"))

    def test_detect_document_retrieval_followup_matches_link_requests(self):
        matches = [
            "give me the download link",
            "send me the file",
            "pdf link",
            "the docx",
            "send file",
            "share the link",
            "where is the file",
            "show preview",
            "resend it",
            "can you send the pdf",
            "give me docx",
        ]
        for phrase in matches:
            intent = document_generator.detect_document_retrieval_followup(phrase)
            self.assertIsNotNone(intent, msg=f"Expected retrieval intent for {phrase!r}")

    def test_detect_document_retrieval_followup_ignores_new_generation(self):
        self.assertIsNone(
            document_generator.detect_document_retrieval_followup(
                "make notes on transformers in pdf"
            )
        )
        self.assertIsNone(
            document_generator.detect_document_retrieval_followup("")
        )
        self.assertIsNone(
            document_generator.detect_document_retrieval_followup("what is python")
        )

    def test_detect_document_retrieval_followup_captures_requested_format(self):
        intent = document_generator.detect_document_retrieval_followup("give me the pdf link")
        self.assertEqual(intent["requested_format"], "pdf")
        self.assertFalse(intent["wants_preview"])

        preview_intent = document_generator.detect_document_retrieval_followup("show me the preview")
        self.assertTrue(preview_intent["wants_preview"])

    def test_resolve_document_retrieval_followup_returns_cached_primary(self):
        session_id = "session-retrieval"
        document_generator.LAST_GENERATED_DOCUMENT.pop(session_id, None)
        cached = {
            "success": True,
            "document_type": "notes",
            "topic": "transformers",
            "format": "txt",
            "primary_format": "txt",
            "requested_formats": ["txt"],
            "file_name": "Transformers-Notes.txt",
            "file_path": "/tmp/Transformers-Notes.txt",
            "download_url": "/downloads/Transformers-Notes.txt",
            "title": "Transformers",
            "subtitle": "Study Notes",
            "preview_text": "Overview: Transformers.",
            "style": "simple",
            "include_references": False,
            "citation_style": None,
            "artifacts": {
                "txt": {"file_name": "Transformers-Notes.txt", "file_path": "/tmp/Transformers-Notes.txt", "download_url": "/downloads/Transformers-Notes.txt"},
                "pdf": {"file_name": "Transformers-Notes.pdf", "file_path": "/tmp/Transformers-Notes.pdf", "download_url": "/downloads/Transformers-Notes.pdf"},
                "docx": {"file_name": "Transformers-Notes.docx", "file_path": "/tmp/Transformers-Notes.docx", "download_url": "/downloads/Transformers-Notes.docx"},
                "pptx": {"file_name": "Transformers-Notes-Slides.pptx", "file_path": "/tmp/Transformers-Notes-Slides.pptx", "download_url": "/downloads/Transformers-Notes-Slides.pptx"},
            },
            "format_links": {
                "txt": "/downloads/Transformers-Notes.txt",
                "pdf": "/downloads/Transformers-Notes.pdf",
                "docx": "/downloads/Transformers-Notes.docx",
                "pptx": "/downloads/Transformers-Notes-Slides.pptx",
            },
            "message": "Done. Your notes are ready.",
        }
        document_generator.remember_generated_document(session_id, cached)

        plain = document_generator.resolve_document_retrieval_followup(
            "give me the download link", session_id=session_id
        )
        self.assertIsNotNone(plain)
        self.assertEqual(plain["format"], "txt")
        self.assertEqual(plain["download_url"], "/downloads/Transformers-Notes.txt")
        self.assertTrue(plain["retrieval_followup"])
        self.assertIn("pdf", plain["alternate_format_links"])

        pdf = document_generator.resolve_document_retrieval_followup(
            "give me the pdf link", session_id=session_id
        )
        self.assertIsNotNone(pdf)
        self.assertEqual(pdf["format"], "pdf")
        self.assertEqual(pdf["file_name"], "Transformers-Notes.pdf")
        self.assertEqual(pdf["download_url"], "/downloads/Transformers-Notes.pdf")
        self.assertNotIn("pdf", pdf["alternate_format_links"])
        self.assertIn("txt", pdf["alternate_format_links"])

    def test_resolve_document_retrieval_followup_returns_none_without_cache(self):
        self.assertIsNone(
            document_generator.resolve_document_retrieval_followup(
                "give me the pdf link", session_id="no-session-here"
            )
        )


class RuntimeDocumentRoutingTests(unittest.TestCase):
    def test_document_generation_permission_is_safe(self):
        permission = build_permission_response("document_generation")

        self.assertTrue(permission["success"])
        self.assertEqual(permission["permission"]["trust_level"], "safe")

    def test_runtime_routes_document_request_directly(self):
        with patch.object(
            runtime_core,
            "handle_document_generation",
            return_value={
                "success": True,
                "message": "Done. Your notes are ready.",
                "download_url": "/downloads/notes-transformers.txt",
                "file_name": "notes-transformers.txt",
                "file_path": "D:/HeyGoku/generated/notes-transformers.txt",
                "document_type": "notes",
                "format": "txt",
                "page_target": 4,
                "topic": "transformers",
                "source": "local_template",
                "provider": "local",
                "model": "template",
                "providers_tried": [],
                "available_formats": ["txt", "pdf", "docx"],
                "requested_formats": ["txt", "pdf"],
                "files": [
                    {
                        "format": "txt",
                        "file_name": "notes-transformers.txt",
                        "download_url": "/downloads/notes-transformers.txt",
                        "primary": True,
                    },
                    {
                        "format": "pdf",
                        "file_name": "notes-transformers.pdf",
                        "download_url": "/downloads/notes-transformers.pdf",
                        "primary": False,
                    },
                ],
                "format_links": {
                    "txt": "/downloads/notes-transformers.txt",
                    "pdf": "/downloads/notes-transformers.pdf",
                    "docx": "/downloads/notes-transformers.docx",
                },
                "alternate_format_links": {
                    "pdf": "/downloads/notes-transformers.pdf",
                    "docx": "/downloads/notes-transformers.docx",
                },
                "document_delivery": {
                    "kind": "document_delivery",
                    "delivery_message": "Done. Your notes are ready.",
                    "document_type": "notes",
                    "format": "txt",
                    "file_name": "notes-transformers.txt",
                    "download_url": "/downloads/notes-transformers.txt",
                    "preview_text": "Overview: Key ideas about transformers.",
                    "requested_formats": ["txt", "pdf"],
                    "files": [
                        {
                            "format": "txt",
                            "file_name": "notes-transformers.txt",
                            "download_url": "/downloads/notes-transformers.txt",
                            "primary": True,
                        },
                        {
                            "format": "pdf",
                            "file_name": "notes-transformers.pdf",
                            "download_url": "/downloads/notes-transformers.pdf",
                            "primary": False,
                        },
                    ],
                },
                "preview_text": "Overview: Key ideas about transformers.",
            },
        ), patch.object(runtime_core, "respond_in_language", side_effect=lambda response, language: response), patch.object(
            runtime_core,
            "store_and_learn",
        ):
            result = runtime_core.process_single_command_detailed("make notes on transformers", session_id="session-doc")

        self.assertEqual(result["execution_mode"], "document_generation")
        self.assertEqual(result["download_url"], "/downloads/notes-transformers.txt")
        self.assertEqual(result["document_type"], "notes")
        self.assertEqual(result["provider"], "local")
        self.assertEqual(result["permission_action"], "document_generation")
        self.assertTrue(result["permission"]["success"])
        self.assertEqual(result["page_target"], 4)
        self.assertEqual(result["response"], "Done. Your notes are ready.")
        self.assertEqual(result["document_delivery"]["download_url"], "/downloads/notes-transformers.txt")
        self.assertIn("pdf", result["alternate_format_links"])
        self.assertEqual(result["document_preview"], "Overview: Key ideas about transformers.")
        self.assertEqual(result["requested_formats"], ["txt", "pdf"])
        self.assertEqual(len(result["document_files"]), 2)


class ApiDocumentEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api_server.app)

    def test_prepare_chat_context_marks_document_request_safe(self):
        with patch.object(api_server, "load_user_profile", return_value={}), patch.object(
            api_server,
            "detect_intent_with_confidence",
            return_value=("content", 0.91),
        ):
            context = api_server._prepare_chat_context(
                "write assignment on artificial intelligence",
                "hybrid",
                user=None,
            )

        self.assertEqual(context["detected_intent"], "document")
        self.assertTrue(context["permission"]["success"])
        self.assertEqual(context["permission"]["permission"]["trust_level"], "safe")

    def test_prepare_chat_context_preserves_document_followup_format(self):
        with patch.object(api_server, "load_user_profile", return_value={}), patch.object(
            api_server,
            "detect_intent_with_confidence",
            return_value=("content", 0.91),
        ):
            first_context = api_server._prepare_chat_context(
                "write assignment on artificial intelligence",
                "hybrid",
                session_id="session-doc",
                user=None,
            )
            followup_context = api_server._prepare_chat_context(
                "as pdf",
                "hybrid",
                session_id="session-doc",
                user=None,
            )

        self.assertEqual(first_context["detected_intent"], "document")
        self.assertEqual(followup_context["detected_intent"], "document")
        self.assertEqual(followup_context["document_request"].export_format, "pdf")

    def test_generate_document_endpoint_returns_download_url(self):
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "generate_document",
            return_value={
                "success": True,
                "download_url": "/downloads/notes-ai.txt",
                "file_name": "notes-ai.txt",
                "document_type": "notes",
                "format": "txt",
                "page_target": 3,
                "topic": "artificial intelligence",
                "provider": "local",
                "source": "local_template",
                "title": "Artificial Intelligence",
                "subtitle": "Study Notes",
                "preview_text": "Overview: Artificial intelligence in simple terms.",
                "available_formats": ["txt", "pdf", "docx"],
                "requested_formats": ["txt", "pptx"],
                "files": [
                    {
                        "format": "txt",
                        "file_name": "notes-ai.txt",
                        "download_url": "/downloads/notes-ai.txt",
                        "primary": True,
                    },
                    {
                        "format": "pptx",
                        "file_name": "notes-ai-slides.pptx",
                        "download_url": "/downloads/notes-ai-slides.pptx",
                        "primary": False,
                    },
                ],
                "style": "detailed",
                "include_references": True,
                "citation_style": "apa",
                "format_links": {
                    "txt": "/downloads/notes-ai.txt",
                    "pdf": "/downloads/notes-ai.pdf",
                    "docx": "/downloads/notes-ai.docx",
                    "pptx": "/downloads/notes-ai-slides.pptx",
                },
                "alternate_format_links": {
                    "pdf": "/downloads/notes-ai.pdf",
                    "docx": "/downloads/notes-ai.docx",
                    "pptx": "/downloads/notes-ai-slides.pptx",
                },
                "document_delivery": {
                    "kind": "document_delivery",
                    "delivery_message": "Done. Your document set is ready.",
                    "document_type": "notes",
                    "format": "txt",
                    "file_name": "notes-ai.txt",
                    "download_url": "/downloads/notes-ai.txt",
                    "preview_text": "Overview: Artificial intelligence in simple terms.",
                    "requested_formats": ["txt", "pptx"],
                    "files": [
                        {
                            "format": "txt",
                            "file_name": "notes-ai.txt",
                            "download_url": "/downloads/notes-ai.txt",
                            "primary": True,
                        },
                        {
                            "format": "pptx",
                            "file_name": "notes-ai-slides.pptx",
                            "download_url": "/downloads/notes-ai-slides.pptx",
                            "primary": False,
                        },
                    ],
                },
                "message": "Done. Your document set is ready.",
            },
        ) as generate_mock:
            response = self.client.post(
                "/api/generate/document",
                json={
                    "type": "notes",
                    "topic": "artificial intelligence",
                    "format": "txt",
                    "formats": ["txt", "pptx"],
                    "page_target": 3,
                    "style": "detailed",
                    "include_references": True,
                    "citation_style": "apa",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["download_url"], "/downloads/notes-ai.txt")
        self.assertEqual(payload["page_target"], 3)
        self.assertEqual(payload["kind"], "document_delivery")
        self.assertEqual(payload["reply"], "Done. Your document set is ready.")
        self.assertIn("pptx", payload["alternate_format_links"])
        self.assertEqual(payload["document_delivery"]["download_url"], "/downloads/notes-ai.txt")
        self.assertEqual(payload["preview_text"], "Overview: Artificial intelligence in simple terms.")
        self.assertEqual(payload["requested_formats"], ["txt", "pptx"])
        self.assertEqual(len(payload["files"]), 2)
        self.assertEqual(generate_mock.call_args.kwargs["page_target"], 3)
        self.assertEqual(generate_mock.call_args.kwargs["formats"], ("txt", "pptx"))

    def test_api_chat_document_request_bypasses_permission_block(self):
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "load_user_profile",
            return_value={},
        ), patch.object(
            api_server,
            "detect_intent_with_confidence",
            return_value=("content", 0.91),
        ), patch.object(
            api_server,
            "process_command_detailed",
            return_value={
                "intent": "document",
                "detected_intent": "document",
                "confidence": 1.0,
                "response": "Done. Your assignment is ready.",
                "used_agents": ["document_generator"],
                "agent_capabilities": [],
                "execution_mode": "document_generation",
                "decision": {"intent": "document"},
                "orchestration": {"primary_agent": "document_generator"},
                "permission_action": "document_generation",
                "permission": build_permission_response("document_generation"),
                "provider": "local",
                "model": "template",
                "providers_tried": [],
                "download_url": "/downloads/assignment-ai.txt",
                "file_name": "assignment-ai.txt",
                "document_type": "assignment",
                "document_format": "txt",
                "page_target": 5,
                "document_topic": "artificial intelligence",
                "document_source": "local_template",
                "document_preview": "Introduction: Artificial intelligence connects intelligent behaviour with practical applications.",
                "alternate_format_links": {
                    "pdf": "/downloads/assignment-ai.pdf",
                    "docx": "/downloads/assignment-ai.docx",
                    "pptx": "/downloads/assignment-ai-slides.pptx",
                },
                "format_links": {
                    "txt": "/downloads/assignment-ai.txt",
                    "pdf": "/downloads/assignment-ai.pdf",
                    "docx": "/downloads/assignment-ai.docx",
                    "pptx": "/downloads/assignment-ai-slides.pptx",
                },
                "available_formats": ["txt", "pdf", "docx", "pptx"],
                "requested_formats": ["txt", "pptx"],
                "document_files": [
                    {
                        "format": "txt",
                        "file_name": "assignment-ai.txt",
                        "download_url": "/downloads/assignment-ai.txt",
                        "primary": True,
                    },
                    {
                        "format": "pptx",
                        "file_name": "assignment-ai-slides.pptx",
                        "download_url": "/downloads/assignment-ai-slides.pptx",
                        "primary": False,
                    },
                ],
                "document_delivery": {
                    "kind": "document_delivery",
                    "delivery_message": "Done. Your document set is ready.",
                    "document_type": "assignment",
                    "format": "txt",
                    "file_name": "assignment-ai.txt",
                    "download_url": "/downloads/assignment-ai.txt",
                    "preview_text": "Introduction: Artificial intelligence connects intelligent behaviour with practical applications.",
                    "requested_formats": ["txt", "pptx"],
                    "files": [
                        {
                            "format": "txt",
                            "file_name": "assignment-ai.txt",
                            "download_url": "/downloads/assignment-ai.txt",
                            "primary": True,
                        },
                        {
                            "format": "pptx",
                            "file_name": "assignment-ai-slides.pptx",
                            "download_url": "/downloads/assignment-ai-slides.pptx",
                            "primary": False,
                        },
                    ],
                },
                "degraded": False,
            },
        ), patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": True},
        ):
            response = self.client.post(
                "/api/chat",
                json={"message": "write assignment on artificial intelligence", "mode": "hybrid"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["execution_mode"], "document_generation")
        self.assertEqual(payload["download_url"], "/downloads/assignment-ai.txt")
        self.assertEqual(payload["page_target"], 5)
        self.assertEqual(payload["kind"], "document_delivery")
        self.assertEqual(payload["reply"], "Done. Your document set is ready.")
        self.assertIn("pdf", payload["alternate_format_links"])
        self.assertEqual(payload["document_delivery"]["download_url"], "/downloads/assignment-ai.txt")
        self.assertEqual(payload["document_preview"], "Introduction: Artificial intelligence connects intelligent behaviour with practical applications.")
        self.assertEqual(payload["requested_formats"], ["txt", "pptx"])
        self.assertNotIn("Approval is required", payload["reply"])
        self.assertEqual(payload["action_trace"]["response_mode"], "document")
        self.assertEqual(payload["action_trace"]["permission_state"]["action_name"], "document_generation")
        self.assertEqual(payload["action_trace"]["final_status"], "ok")


class CoreAiDocumentDeliveryTests(unittest.TestCase):
    def test_core_ai_keeps_document_delivery_reply_clean(self):
        with patch.object(core_ai, "_sync_context_into_response_engine"), patch.object(
            core_ai.runtime_core_module,
            "process_command_detailed",
            return_value={
                "intent": "document",
                "detected_intent": "document",
                "confidence": 1.0,
                "response": "Done. Your assignment is ready.",
                "provider": "local",
                "model": "template",
                "providers_tried": [],
                "used_agents": ["document_generator"],
                "execution_mode": "document_generation",
                "decision": {"intent": "document"},
                "orchestration": {"primary_agent": "document_generator"},
                "permission_action": "document_generation",
                "permission": build_permission_response("document_generation"),
                "document_delivery": {
                    "kind": "document_delivery",
                    "delivery_message": "Done. Your assignment is ready.",
                    "download_url": "/downloads/assignment-ai.pdf",
                },
            },
        ), patch.object(core_ai, "_record_exchange"), patch.object(
            core_ai.agent_bus,
            "publish",
        ):
            result = core_ai.process_command_detailed(
                "write assignment on artificial intelligence",
                session_id="session-doc",
                user_profile={"proactive_suggestions": True},
            )

        self.assertEqual(result["response"], "Done. Your assignment is ready.")
        self.assertEqual(result["document_delivery"]["download_url"], "/downloads/assignment-ai.pdf")

    def test_core_ai_replaces_placeholder_like_response_with_meaningful_degraded_reply(self):
        with patch.object(core_ai, "_sync_context_into_response_engine"), patch.object(
            core_ai.runtime_core_module,
            "process_command_detailed",
            return_value={
                "intent": "write",
                "detected_intent": "write",
                "confidence": 0.92,
                "response": "I ran into a problem while generating a response. Please try again.",
                "provider": None,
                "model": None,
                "providers_tried": [{"provider": "groq", "status": "rate_limited"}],
                "used_agents": ["writing_runtime"],
                "execution_mode": "single_agent",
                "decision": {"intent": "write"},
                "orchestration": {"primary_agent": "writing_runtime"},
                "permission_action": "general",
                "permission": build_permission_response("general"),
            },
        ), patch.object(
            core_ai,
            "_call_live_brain_direct",
            return_value={
                "success": False,
                "degraded_reply": "",
                "providers_tried": [{"provider": "groq", "status": "rate_limited"}],
                "error": "Groq rate limited",
            },
        ), patch.object(core_ai, "_record_exchange"), patch.object(
            core_ai.agent_bus,
            "publish",
        ):
            result = core_ai.process_command_detailed(
                "write a short post about AI",
                session_id="session-doc",
                user_profile={"proactive_suggestions": True},
            )

        self.assertEqual(result["execution_mode"], "degraded_assistant")
        self.assertTrue(result["degraded"])
        self.assertNotEqual(result["response"].strip(), "")
        self.assertNotEqual(result["response"], core_ai.FALLBACK_USER_MESSAGE)


class ContentExtractorTests(unittest.TestCase):
    def test_extract_text_passthrough(self):
        from tools.content_extractor import extract_content

        result = extract_content("Machine learning is a subset of AI.")
        self.assertTrue(result.success)
        self.assertEqual(result.source_type, "text")
        self.assertEqual(result.source_label, "pasted text")
        self.assertIn("Machine learning", result.text)

    def test_extract_txt_bytes(self):
        from tools.content_extractor import extract_content

        content = b"Transformers are a type of neural network architecture."
        result = extract_content(content, filename="notes.txt")
        self.assertTrue(result.success)
        self.assertEqual(result.source_type, "txt")
        self.assertIn("Transformers", result.text)

    def test_extract_empty_text_fails(self):
        from tools.content_extractor import extract_content

        result = extract_content("   ")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_extract_docx_bytes(self):
        from tools.content_extractor import extract_content
        import zipfile
        import io

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Deep learning uses multiple layers.</w:t></w:r></w:p>"
            "</w:body>"
            "</w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("word/document.xml", body_xml)
        docx_bytes = buf.getvalue()

        result = extract_content(docx_bytes, filename="notes.docx")
        self.assertTrue(result.success)
        self.assertEqual(result.source_type, "docx")
        self.assertIn("Deep learning", result.text)

    def test_is_youtube_url_detection(self):
        from tools.content_extractor import is_youtube_url

        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=abc123"))
        self.assertTrue(is_youtube_url("https://youtu.be/abc123"))
        self.assertTrue(is_youtube_url("https://www.youtube.com/shorts/abc123"))
        self.assertFalse(is_youtube_url("https://vimeo.com/12345"))
        self.assertFalse(is_youtube_url("make notes on transformers"))

    def test_extract_unsupported_type_fails(self):
        from tools.content_extractor import extract_content

        result = extract_content("data", source_type="video")
        self.assertFalse(result.success)
        self.assertIn("Unsupported", result.error)

    def test_image_type_detection_from_filename(self):
        from tools.content_extractor import _detect_type

        self.assertEqual(_detect_type(b"", "photo.jpg"), "image_bytes")
        self.assertEqual(_detect_type(b"", "scan.png"), "image_bytes")
        self.assertEqual(_detect_type(b"", "figure.tiff"), "image_bytes")
        self.assertEqual(_detect_type(b"", "notes.docx"), "docx_bytes")
        self.assertEqual(_detect_type(b"", "notes.pdf"), "pdf_bytes")

    def test_extract_content_sets_extraction_mode(self):
        from tools.content_extractor import extract_content

        result = extract_content("Some text content about AI.")
        self.assertEqual(result.extraction_mode, "text")

        txt_result = extract_content(b"Plain text content.", filename="file.txt")
        self.assertEqual(txt_result.extraction_mode, "text")

    def test_docx_structured_extraction_with_python_docx(self):
        from tools.content_extractor import extract_content
        import io
        from unittest.mock import patch, MagicMock

        # Simulate python-docx returning structured content
        mock_para1 = MagicMock()
        mock_para1.text = "Introduction to Deep Learning"
        mock_para1.style.name = "Heading 1"

        mock_para2 = MagicMock()
        mock_para2.text = "Deep learning uses multiple layers of neural networks."
        mock_para2.style.name = "Normal"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]

        # Create minimal valid zip so the fallback doesn't break import
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("word/document.xml", "<w:document><w:body></w:body></w:document>")
        docx_bytes = buf.getvalue()

        with patch("docx.Document", return_value=mock_doc):
            result = extract_content(docx_bytes, filename="notes.docx")

        self.assertTrue(result.success)
        self.assertEqual(result.source_type, "docx")
        self.assertEqual(result.extraction_mode, "structured")
        self.assertIn("Introduction to Deep Learning", result.text)
        self.assertIn("Deep learning", result.text)

    def test_docx_fallback_to_zip_regex(self):
        from tools.content_extractor import extract_content
        import io

        body_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Deep learning uses multiple layers.</w:t></w:r></w:p>"
            "</w:body>"
            "</w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("word/document.xml", body_xml)
        docx_bytes = buf.getvalue()

        result = extract_content(docx_bytes, filename="notes.docx")
        self.assertTrue(result.success)
        self.assertEqual(result.source_type, "docx")
        self.assertIn("Deep learning", result.text)

    def test_pdf_ocr_fallback_called_when_no_text(self):
        from tools.content_extractor import _extract_pdf
        from unittest.mock import patch, MagicMock

        # PyPDF2 returns empty, OCR should be tried
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_image = MagicMock()
        mock_ocr_text = "Scanned page text about machine learning."

        with patch("PyPDF2.PdfReader", return_value=mock_reader), \
             patch("pdf2image.convert_from_bytes", return_value=[mock_image]), \
             patch("pytesseract.image_to_string", return_value=mock_ocr_text):
            text, mode = _extract_pdf(b"fake_pdf_bytes")

        self.assertEqual(mode, "ocr")
        self.assertIn("Scanned page text", text)

    def test_youtube_extraction_mode_transcript(self):
        from tools.content_extractor import _extract_youtube
        from unittest.mock import patch, MagicMock

        def _make_snippet(t):
            s = MagicMock()
            s.text = t
            return s

        snippets = [
            _make_snippet("Hello and welcome to this video about deep learning. "),
            _make_snippet("Today we will cover neural networks and backpropagation. "),
            _make_snippet("This is an important topic in modern AI research. " * 3),
        ]
        mock_fetched = MagicMock()
        mock_fetched.__iter__ = MagicMock(return_value=iter(snippets))

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as MockAPI:
            MockAPI.return_value.fetch.return_value = mock_fetched
            text, mode = _extract_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertEqual(mode, "transcript")
        self.assertIn("deep learning", text)
        self.assertNotIn("[Note:", text)

    def test_youtube_extraction_falls_back_to_metadata(self):
        from tools.content_extractor import _extract_youtube
        from unittest.mock import patch, MagicMock

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as MockAPI:
            MockAPI.return_value.fetch.side_effect = Exception("disabled")
            with patch("agents.integration.youtube_agent.summarize_youtube", return_value={
                "success": True,
                "message": "TITLE: Deep Learning Explained\nCHANNEL: AI Academy\nSUMMARY: An overview of deep learning.",
            }):
                text, mode = _extract_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertEqual(mode, "metadata")
        self.assertIn("[Note:", text)
        self.assertIn("Deep Learning Explained", text)


class TransformationRoutingTests(unittest.TestCase):
    def test_handle_transformation_returns_none_without_source(self):
        from brain.runtime_core import handle_transformation

        result = handle_transformation("make notes on machine learning")
        self.assertIsNone(result)

    def test_handle_transformation_returns_none_without_trigger(self):
        from brain.runtime_core import handle_transformation

        result = handle_transformation("what is machine learning?", source_content="ML is about algorithms.")
        self.assertIsNone(result)

    def test_handle_transformation_with_inline_content(self):
        from brain.runtime_core import handle_transformation
        from unittest.mock import patch
        import tools.document_generator as document_generator

        with patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value={
                "success": True,
                "content": "Overview\n- Key machine learning concepts.",
                "provider": "local",
                "model": "template",
                "source": "transformation",
                "degraded": False,
                "providers_tried": [],
            },
        ), tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator, "GENERATED_DIR", Path(tmp_dir)
        ):
            result = handle_transformation(
                "convert this into notes:",
                source_content="Machine learning is a method of data analysis.",
            )

        self.assertIsNotNone(result)
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("document_type"), "notes")
        self.assertIn("download_url", result)

    def test_inline_source_splitting(self):
        from brain.runtime_core import _extract_inline_source_content

        long_content = (
            "Neural networks learn from data. They have multiple layers that process "
            "information hierarchically, allowing them to detect patterns in complex datasets."
        )
        cmd, content = _extract_inline_source_content(f"make notes from this:  {long_content}")
        self.assertIn("make notes", cmd)
        self.assertIn("Neural networks", content)

    def test_no_inline_split_for_short_content(self):
        from brain.runtime_core import _extract_inline_source_content

        cmd, content = _extract_inline_source_content("make notes from this: short")
        self.assertEqual(content, "")

    def test_youtube_url_detection_in_command(self):
        from brain.runtime_core import _find_youtube_url_in_text

        url = _find_youtube_url_in_text(
            "make notes from https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        self.assertIsNotNone(url)
        self.assertIn("youtube.com", url)

    def test_detect_transformation_doc_type(self):
        from brain.runtime_core import _detect_transformation_doc_type

        self.assertEqual(_detect_transformation_doc_type("convert this into notes"), "notes")
        self.assertEqual(_detect_transformation_doc_type("turn this into an assignment"), "assignment")
        self.assertEqual(_detect_transformation_doc_type("summarize this text"), "notes")

    def test_transformation_topic_extraction(self):
        from brain.runtime_core import _extract_transformation_topic

        topic = _extract_transformation_topic("make notes on deep learning from this", "uploaded_file.pdf")
        self.assertEqual(topic, "deep learning")

        topic = _extract_transformation_topic("convert this into notes", "lecture.pdf")
        self.assertEqual(topic, "lecture")

        topic = _extract_transformation_topic("summarize this", "pasted text")
        self.assertEqual(topic, "Source Material")


class DocumentAccessAndRateLimitTests(unittest.TestCase):
    def setUp(self):
        api_server.DOCUMENT_RATE_LIMIT_STATE.clear()
        self.client = TestClient(api_server.app)

    def _content_payload(self):
        return {
            "success": True,
            "content": (
                "Introduction\n"
                "Artificial intelligence includes systems that learn from data and perform useful tasks.\n\n"
                "Core Concepts\n"
                "Machine learning, pattern recognition, and automation give the topic real structure."
            ),
            "provider": "local",
            "model": "template",
            "source": "local_template",
            "degraded": False,
            "providers_tried": [],
        }

    def test_generated_download_requires_same_browser_session(self):
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=self._content_payload(),
        ), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ):
            response = self.client.post(
                "/api/generate/document",
                json={"type": "notes", "topic": "artificial intelligence", "format": "txt"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["access_scope"], "browser_session")
            self.assertIn("access=", payload["download_url"])
            self.assertIn("voris_local_session", self.client.cookies)

            allowed = self.client.get(payload["download_url"])
            self.assertEqual(allowed.status_code, 200)

            other_client = TestClient(api_server.app)
            blocked = other_client.get(payload["download_url"])
            self.assertEqual(blocked.status_code, 403)
            self.assertIn("same browser session", blocked.json()["error"])

    def test_generated_download_requires_same_authenticated_user(self):
        owner = {"id": "owner-1", "username": "owner"}
        stranger = {"id": "owner-2", "username": "other"}

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=self._content_payload(),
        ):
            with patch.object(api_server, "_current_user", return_value=owner):
                response = self.client.post(
                    "/api/generate/document",
                    json={"type": "assignment", "topic": "artificial intelligence", "format": "pdf"},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()

            self.assertEqual(payload["access_scope"], "authenticated_user")
            self.assertIn("access=", payload["download_url"])

            with patch.object(api_server, "_current_user", return_value=owner):
                allowed = self.client.get(payload["download_url"])
            self.assertEqual(allowed.status_code, 200)

            with patch.object(api_server, "_current_user", return_value=stranger):
                blocked = self.client.get(payload["download_url"])
            self.assertEqual(blocked.status_code, 403)
            self.assertIn("Sign in with the account", blocked.json()["error"])

    def test_document_endpoint_is_rate_limited(self):
        with patch.object(api_server, "DOCUMENT_RATE_LIMIT_MAX_REQUESTS", 1), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "generate_document",
            return_value={
                "success": True,
                "message": "Done. Your notes are ready.",
                "download_url": "/downloads/AI-Notes.txt?access=test-token",
                "file_name": "AI-Notes.txt",
                "document_type": "notes",
                "format": "txt",
                "topic": "artificial intelligence",
                "title": "Artificial Intelligence",
                "subtitle": "Study Notes",
                "preview_text": "Introduction: Artificial intelligence overview.",
                "style": "professional",
                "include_references": False,
                "citation_style": None,
                "access_scope": "browser_session",
                "requested_formats": ["txt"],
                "available_formats": ["txt"],
                "files": [{"format": "txt", "file_name": "AI-Notes.txt", "download_url": "/downloads/AI-Notes.txt?access=test-token", "primary": True}],
                "format_links": {"txt": "/downloads/AI-Notes.txt?access=test-token"},
                "alternate_format_links": {},
                "document_delivery": {"kind": "document_delivery", "download_url": "/downloads/AI-Notes.txt?access=test-token"},
            },
        ), patch.object(
            api_server,
            "secure_generated_document_access",
            side_effect=lambda generated, **_: generated,
        ):
            first = self.client.post(
                "/api/generate/document",
                json={"type": "notes", "topic": "artificial intelligence", "format": "txt"},
            )
            second = self.client.post(
                "/api/generate/document",
                json={"type": "notes", "topic": "artificial intelligence", "format": "txt"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["status"], "rate_limited")

    def test_chat_routed_document_generation_is_rate_limited(self):
        context = {
            "raw_message": "make notes on ai",
            "requested_mode": "hybrid",
            "session_id": "chat-doc-session",
            "cleaned_message": "make notes on ai",
            "detected_intent": "document",
            "confidence": 1.0,
            "decision": {"agent": "document_generator"},
            "permission": {"success": True, "status": "approved", "permission": {"trust_level": "safe"}},
            "user": None,
            "user_profile": {},
            "confirmation_required": False,
            "confirmation_ok": False,
            "document_request": {"document_type": "notes"},
            "document_retrieval_followup": None,
        }
        response_payload = {
            "success": True,
            "reply": "Done. Your notes are ready.",
            "content": "Done. Your notes are ready.",
            "intent": "document",
            "execution_mode": "document_generation",
            "agent_used": "document_generator",
            "provider": "local",
            "mode": "document_generation",
        }

        with patch.object(api_server, "DOCUMENT_RATE_LIMIT_MAX_REQUESTS", 1), patch.object(
            api_server,
            "requires_first_run_setup",
            return_value=False,
        ), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "_prepare_chat_context",
            return_value=context,
        ), patch.object(
            api_server,
            "_execute_chat_pipeline",
            return_value=response_payload,
        ) as execute_mock, patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": True},
        ):
            first = self.client.post("/api/chat", json={"message": "make notes on ai", "mode": "hybrid"})
            second = self.client.post("/api/chat", json={"message": "make notes on ai", "mode": "hybrid"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["status"], "rate_limited")
        self.assertEqual(execute_mock.call_count, 1)

    def test_secured_download_url_contains_access_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            document_generator,
            "GENERATED_DIR",
            Path(tmp_dir),
        ), patch.object(
            document_generator,
            "generate_document_content_payload",
            return_value=self._content_payload(),
        ):
            generated = document_generator.generate_document("notes", "artificial intelligence", "txt")
            secured = document_generator.secure_generated_document_access(
                generated,
                owner_session_id="browser-session-1",
            )

        parsed = urlparse(secured["download_url"])
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, f"/downloads/{secured['file_name']}")
        self.assertTrue(query.get("access"))
        self.assertEqual(secured["access_scope"], "browser_session")


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.api_server as api_server
import tools.media_generation as media_generation
from tools import tool_registry
from tests.support import SetupGateBypassMixin


class MediaPreflightTests(unittest.TestCase):
    """Preflight must report missing weights up front, not mid-generation."""

    def test_preflight_reports_every_missing_model_with_install_command(self):
        with TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir)
            with patch.object(media_generation, "MODELS_DIR", empty), patch.object(
                media_generation, "SD_BINARY", empty / "bin" / "sd.exe"
            ), patch.object(media_generation.shutil, "which", return_value=None):
                report = media_generation.preflight()

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "not_installed")
        for model in media_generation.REQUIRED_MODELS:
            self.assertIn(model["filename"], report["missing"])
        self.assertIn("huggingface-cli download", report["install_hint"])

    def test_install_hint_names_schnell_and_warns_against_dev(self):
        hint = media_generation.install_hint()
        self.assertIn("black-forest-labs/FLUX.1-schnell", hint)
        self.assertNotIn("FLUX.1-dev ae", hint)
        # The dev checkpoint is non-commercial; the hint must say so.
        self.assertIn("non-commercial", hint.lower())

    def test_generate_image_refuses_before_starting_a_job_when_not_installed(self):
        with TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir)
            with patch.object(media_generation, "MODELS_DIR", empty), patch.object(
                media_generation, "SD_BINARY", empty / "bin" / "sd.exe"
            ), patch.object(media_generation.shutil, "which", return_value=None):
                result = media_generation.generate_image("a quiet observatory at night")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not_installed")
        self.assertNotIn("job_id", result)

    def test_generate_image_rejects_an_empty_prompt(self):
        result = media_generation.generate_image("   ")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "invalid_prompt")


class MediaVideoTests(unittest.TestCase):
    """Video is unsupported on this hardware and must say so, not pretend."""

    def test_generate_video_reports_unsupported_hardware_honestly(self):
        result = media_generation.generate_video("a drone shot over a city")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unsupported_hardware")
        self.assertIn("CUDA", result["required"])
        self.assertTrue(result["detected"])

    def test_video_is_not_registered_as_an_agent_tool(self):
        # A tool row would surface in the UI as a capability. There is no
        # working video capability, so there must be no row.
        handlers = {record.handler for record in tool_registry.TOOL_REGISTRY.values()}
        self.assertNotIn(media_generation.generate_video, handlers)


class MediaToolRegistrationTests(unittest.TestCase):
    def test_image_tool_is_registered_as_hybrid_not_real(self):
        record = tool_registry.get_tool("media.image")
        self.assertIsNotNone(record)
        self.assertIs(record.handler, media_generation.generate_image)
        self.assertEqual(record.required_inputs, ("prompt",))
        # No generation has run on this host, so claiming "real" would be false.
        self.assertEqual(record.capability_mode, "hybrid")


class MediaSizeTests(unittest.TestCase):
    def test_size_is_clamped_to_a_multiple_of_64_within_bounds(self):
        self.assertEqual(media_generation._clamp_size(None), media_generation.DEFAULT_SIZE)
        self.assertEqual(media_generation._clamp_size(100), 256)
        self.assertEqual(media_generation._clamp_size(9999), media_generation.MAX_SIZE)
        self.assertEqual(media_generation._clamp_size(700) % 64, 0)

    def test_progress_is_parsed_from_backend_step_output(self):
        self.assertAlmostEqual(media_generation._parse_progress("|===>  | 2/4 - 3.10s/it"), 0.5)
        self.assertIsNone(media_generation._parse_progress("loading model"))


class MediaApiTests(SetupGateBypassMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(api_server.app)

    def test_media_status_endpoint_is_public_and_truthful_about_video(self):
        response = self.client.get("/api/media/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()["media_generation"]
        self.assertFalse(body["video"]["available"])
        self.assertEqual(body["video"]["status"], "unsupported_hardware")
        self.assertIn("stable-diffusion.cpp", body["image"]["backend"])

    def test_unknown_media_job_returns_404(self):
        response = self.client.get("/api/media/job", params={"job_id": "img-doesnotexist"})
        self.assertEqual(response.status_code, 404)

    def test_media_routes_are_public_paths(self):
        # PUBLIC_PATHS is matched by equality, so a path parameter would never
        # match; these must be exact strings.
        self.assertIn("/api/media/status", api_server.PUBLIC_PATHS)
        self.assertIn("/api/media/job", api_server.PUBLIC_PATHS)


if __name__ == "__main__":
    unittest.main()

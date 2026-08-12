from agents.agent_fabric import build_agent_exports

globals().update(build_agent_exports(__file__))
import unittest
from unittest.mock import patch

import agents.integration.youtube_agent as youtube_agent


class YouTubeAgentTests(unittest.TestCase):
    def test_summarize_youtube_uses_metadata_and_llm_summary(self):
        metadata = youtube_agent.VideoMetadata(
            video_id="abc123xyz89",
            title="AURA Demo",
            channel="HeyGoku",
            url="https://www.youtube.com/watch?v=abc123xyz89",
        )
        with patch.object(youtube_agent.youtube_agent.metadata, "fetch", return_value=metadata), patch.object(
            youtube_agent.youtube_agent.llm,
            "summarize_from_metadata",
            return_value="This video explains the AURA operating system demo.",
        ):
            result = youtube_agent.summarize_youtube(metadata.url)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["video_id"], "abc123xyz89")
        self.assertIn("AURA operating system", result["message"])


if __name__ == "__main__":
    unittest.main()

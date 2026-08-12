import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import memory.vector_memory as vector_memory


class VectorMemoryTests(unittest.TestCase):
    def test_fallback_store_search_delete_and_clear_work_when_vector_backend_is_unavailable(self):
        root = Path(mkdtemp())
        fallback_file = root / "vector_fallback.json"

        with patch.object(vector_memory, "FALLBACK_FILE", fallback_file), patch.object(
            vector_memory,
            "chromadb",
            None,
        ), patch.object(
            vector_memory,
            "client",
            None,
        ), patch.object(
            vector_memory,
            "collection",
            None,
        ), patch.object(
            vector_memory,
            "backend",
            "uninitialized",
        ), patch.object(
            vector_memory,
            "last_error",
            None,
        ):
            stored = vector_memory.store_memory("Remember this project", {"type": "note"})
            self.assertTrue(stored)

            results = vector_memory.search_memory("project", n_results=2)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["text"], "Remember this project")
            self.assertEqual(results[0]["metadata"]["type"], "note")

            memory_id = results[0]["id"]
            self.assertTrue(vector_memory.delete_memory(memory_id))
            self.assertEqual(vector_memory.search_memory("project", n_results=2), [])

            self.assertTrue(vector_memory.store_memory("One more memory"))
            self.assertTrue(vector_memory.clear_all_memories())
            self.assertEqual(vector_memory.get_all_memories(), [])

    def test_status_reports_fallback_backend_without_vector_connection(self):
        with patch.object(vector_memory, "collection", None), patch.object(
            vector_memory,
            "backend",
            "fallback",
        ), patch.object(
            vector_memory,
            "last_error",
            "disk I/O error",
        ):
            status = vector_memory.get_status()

        self.assertEqual(status["backend"], "fallback")
        self.assertFalse(status["vector_store_ready"])
        self.assertEqual(status["last_error"], "disk I/O error")


if __name__ == "__main__":
    unittest.main()

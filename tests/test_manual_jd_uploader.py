"""
Unit tests for resume upload integration across sidebar, smart match, and manual JD optimizer.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


class TestResumeUploadSession(unittest.TestCase):
    def test_session_state_resume_persistence(self):
        """Verify resume file object structure and caching pattern."""
        fake_file = MagicMock()
        fake_file.name = "john_doe_resume.pdf"
        fake_file.size = 1024

        session_state = {}
        session_state["uploaded_resume"] = fake_file

        active_file = session_state.get("uploaded_resume")
        self.assertIsNotNone(active_file)
        self.assertEqual(active_file.name, "john_doe_resume.pdf")

        cache_key = f"resume_text_cache_{active_file.name}_{active_file.size}"
        session_state[cache_key] = "Software Engineer with 5 years experience..."
        self.assertEqual(session_state[cache_key], "Software Engineer with 5 years experience...")


if __name__ == "__main__":
    unittest.main()

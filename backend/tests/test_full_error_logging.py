# backend\tests\test_full_error_logging.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full Error Simulation + Traceback Logging Tests.
Simulates timeout/OOM/SyntaxError + verifies ErrorInterpreter JSONL logs.
"""

import asyncio
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.error_interpreter import get_error_interpreter


class FullErrorLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interpreter = get_error_interpreter()
        cls.initial_logs = len(cls.interpreter.get_recent_logs())

    def _simulate_and_check(self, error_name, exc_class, exc_msg):
        """Simulate error + check log."""
        try:
            if error_name == "timeout":
                raise asyncio.TimeoutError(exc_msg)
            elif error_name == "oom":
                raise MemoryError(exc_msg)
            elif error_name == "syntax":
                raise SyntaxError(exc_msg)
            else:
                raise Exception(exc_msg)
        except Exception:
            tb = traceback.format_exc()
            human, fix = self.interpreter.handle(
                exc_class(exc_msg), context={"test": error_name, "tb": tb}, agent="test", model="debug"
            )

        logs = self.interpreter.get_recent_logs()
        self.assertGreater(len(logs), self.initial_logs)
        latest = logs[-1]
        self.assertEqual(latest["agent"], "test")
        self.assertIn(error_name, latest["error_code"] or latest["error_message"].lower())
        print(f"✅ {error_name}: Logged '{latest['error_code']}' - {latest['recommendation'][:100]}")

    def test_timeout_logging(self):
        self._simulate_and_check("timeout", asyncio.TimeoutError, "LLM timeout")

    def test_oom_logging(self):
        self._simulate_and_check("oom", MemoryError, "VRAM OOM")

    def test_syntax_error_logging(self):
        self._simulate_and_check("syntax", SyntaxError, "Model parse fail")

    def test_generic_model_fail(self):
        self._simulate_and_check("model_fail", Exception, "Provider crash")

    @patch("app.services.error_interpreter.LOG_FILE")
    def test_jsonl_tail_analysis(self, mock_file):
        """Verify recent errors count."""
        logs = self.interpreter.get_recent_logs(10)
        errors = self.interpreter.analyze_recent_errors()
        self.assertIsInstance(errors, dict)
        print(f"Recent errors: {errors}")


if __name__ == "__main__":
    unittest.main()

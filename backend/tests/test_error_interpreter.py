from pathlib import Path
import sys
import asyncio
import json

# ============================
# Корректные пути для импорта
# ============================
ROOT_DIR = Path(__file__).resolve().parents[2]  # Enigma
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import unittest
from unittest.mock import MagicMock, patch
from app.services.error_interpreter import get_error_interpreter
from app.services.orchestrator import ERROR_CODES


class TestErrorInterpreter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.error_interpreter = get_error_interpreter()

    def test_timeout_error(self):
        e = asyncio.TimeoutError("LLM timeout")
        human_msg, fix = self.error_interpreter.handle(e, {"agent": "dm", "model": "qwen_7b"}, "dm", "qwen_7b")
        self.assertIn("timed out", human_msg.lower())
        self.assertIn("llama-server", fix.lower())

    def test_oom_error(self):
        e = MemoryError("OOM")
        human_msg, fix = self.error_interpreter.handle(e, {"agent": "npc", "model": "npc_major"}, "npc", "npc_major")
        self.assertIn("oom", human_msg.lower())
        self.assertIn("vram", fix.lower())

    def test_context_overflow(self):
        e = ValueError("Context too long")
        human_msg, fix = self.error_interpreter.handle(e, {"agent": "rules", "model": "saiga"}, "rules", "saiga")
        self.assertIn("лимит контекста", human_msg)
        self.assertIn("context_size", fix.lower())

    def test_json_parse(self):
        e = json.JSONDecodeError("Parse fail", "", 0)
        human_msg, fix = self.error_interpreter.handle(e, {"agent": "memory", "model": "saiga"}, "memory", "saiga")
        self.assertIn("провалился", human_msg)
        self.assertIn("/api/health", fix)

    def test_model_fail(self):
        e = Exception("Model crash")
        human_msg, fix = self.error_interpreter.handle(e, {"agent": "world", "model": "qwen_9b"}, "world", "qwen_9b")
        self.assertIn("провалился", human_msg)
        self.assertIn("/api/health", fix)

    def test_jsonl_logging(self):
        interpreter = get_error_interpreter()
        e = Exception("Test error")
        interpreter.handle(e, {"agent": "test"}, "test", "test")
        logs = interpreter.get_recent_logs()
        self.assertGreater(len(logs), 0)
        log_entry = logs[-1]
        self.assertEqual(log_entry["agent"], "test")
        self.assertEqual(log_entry["model"], "test")
        self.assertIn("Test error", log_entry["error_message"])
        self.assertIn("model_fail", log_entry["error_code"])


if __name__ == "__main__":
    unittest.main()
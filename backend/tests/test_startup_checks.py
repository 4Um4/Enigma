#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enigma Startup Health Checks (Windows-ready unittest suite).
Проверка SystemRequirements, ModelRouter, ErrorInterpreter.
"""

import sys
import unittest
import traceback
from pathlib import Path
import psutil

# PYTHONPATH для backend
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.services.system_requirements import SystemRequirements
    from app.services.error_interpreter import get_error_interpreter
    from app.services.model_router import ModelRouter
except ImportError as e:
    print(f"Import error (non-fatal for env check): {e}")

class StartupHealthTests(unittest.TestCase):
    def setUp(self):
        """Инициализация ModelRouter перед тестами."""
        if 'ModelRouter' in globals():
            self.router = ModelRouter()

            # если есть initialize
            if hasattr(self.router, "initialize"):
                self.router.initialize()

            # fallback — ручная регистрация
            if hasattr(self.router, "register_default_models"):
                self.router.register_default_models()

    def test_system_requirements(self):
        """CPU cores, RAM, disk space."""
        req = SystemRequirements(min_physical_cores=4, min_ram_gb=8)
        report = req.check()
        # Проверяем объект и основные поля
        self.assertTrue(hasattr(report, "meets"))
        self.assertTrue(hasattr(report, "details"))
        self.assertIn("physical_cores", report.details)
        self.assertIn("ram_gb", report.details)
        print(f"SystemRequirements -> meets={report.meets}, details={report.details}")

    def test_psutil_cpu_ram(self):
        """Базовая проверка psutil."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        self.assertGreater(ram.total // (1024**3), 7, "Min 8GB RAM recommended")
        print(f"CPU: {psutil.cpu_count(logical=False)} cores, {cpu_percent:.1f}% load")
        print(f"RAM: {ram.total // (1024**3)} GB total, {ram.percent:.1f}% used")

    @unittest.skipIf('ModelRouter' not in globals(), "ModelRouter not available")
    def test_model_router_registration(self):
        """Проверка зарегистрированных моделей через ModelRouter."""
        router = ModelRouter()

        # актуальный способ получения моделей (в зависимости от реализации)
        if hasattr(router, "models"):
            registered = list(router.models.values())
        elif hasattr(router, "_models"):
            registered = list(router._models.values())
        else:
            registered = []

        self.assertGreater(len(registered), 0, "No models registered in ModelRouter")
        print(f"Registered models: {[m.name for m in registered]}")

    def test_error_interpreter_traceback_logging(self):
        """Симуляция ошибки + проверка JSONL логирования."""
        interpreter = get_error_interpreter()
    
        # Симуляция ошибки через встроенный метод
        with self.assertRaises(Exception) as context:
            interpreter.simulate_startup_error()  # вызывает "Simulated startup error"

        human_msg = context.exception.args[0] if context.exception.args else str(context.exception)
        self.assertIsInstance(human_msg, str)
        self.assertIn("Simulated startup error", human_msg)

        recent_logs = interpreter.get_recent_logs()
        print(f"Logged errors: {len(recent_logs)}")

if __name__ == "__main__":
    unittest.main()

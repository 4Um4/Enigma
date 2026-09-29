# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_ghost_reaper.py
Назначение: юнит-тесты KILLER_SPIRIT (Ш-1 гейт): детерминированные моки
    таблицы процессов (psutil мокается патчем process_iter/_live_owner_
    outside) — вердикты kill/spare не зависят от живой машины.
    Четыре канонических случая + autonomy (IPT_NO_REAPER).
Зависимости: unittest, unittest.mock, scripts.ghost_reaper (psutil mocked).
Основные сущности: TestGhostReaper.
"""

import os
import unittest
from unittest import mock

import scripts.ghost_reaper as gr


def _info(pid, name, cmdline, orphan=True):
    """Фальш-снимок процесса: orphan=True — родитель мёртв (сирота)."""
    return {"pid": pid, "name": name, "cmdline": cmdline, "cwd": gr._REPO_ROOT, "_orphan": orphan}


class TestGhostReaper(unittest.TestCase):
    def setUp(self):
        # _REPO_ROOT обязательно присутствует в мок-cmdline (_is_ours)
        self.repo = gr._REPO_ROOT

    def test_spare_live_owner(self):
        """Живой ланчер над связкой = живой владелец = пощадить ВСЁ."""
        bundle = [
            _info(100, "python.exe", f"{self.repo}\\.venv\\python.exe -m uvicorn app.main:app --port 8000"),
            _info(101, "llama-server.exe", f"{self.repo}\\Models LLM\\llama\\llama-server.exe --port 8181"),
        ]
        with mock.patch.object(gr, "psutil", create=True) as _ps, \
             mock.patch.object(gr, "_safe_info", side_effect=lambda p: next(b for b in bundle if b["pid"] == p.pid)), \
             mock.patch.object(gr, "_live_owner_outside", return_value="живой владелец pid=999"), \
             mock.patch.object(gr.psutil, "process_iter", return_value=[mock.Mock(pid=b["pid"]) for b in bundle], create=True):
            rep = gr.reap(dry_run=True, verbose=False)
        self.assertEqual(len(rep["spared"]), 2)
        self.assertEqual(rep["killed"], [])

    def test_kill_orphan_bundle(self):
        """Сирота + сигнатура = убить всю связку (dry-run вердикты)."""
        bundle = [
            _info(200, "python.exe", f"{self.repo}\\.venv\\python.exe -m uvicorn app.main:app --port 8000"),
            _info(201, "llama-server.exe", f"{self.repo}\\Models LLM\\llama\\llama-server.exe --port 8181"),
        ]
        with mock.patch.object(gr, "_safe_info", side_effect=lambda p: next(b for b in bundle if b["pid"] == p.pid)), \
             mock.patch.object(gr, "_live_owner_outside", return_value=None), \
             mock.patch.object(gr, "psutil", create=True) as _ps:
            _ps.process_iter = mock.Mock(return_value=[mock.Mock(pid=b["pid"]) for b in bundle])
            rep = gr.reap(dry_run=True, verbose=False)
        self.assertEqual(len(rep["killed"]), 2)
        self.assertEqual(rep["spared"], [])

    def test_spare_foreign_python(self):
        """Чужой pytest/DriftLab: не-сигнатура = неприкосновенен."""
        foreign = [_info(300, "python.exe", f"{self.repo}\\.venv\\python.exe -m pytest tests/ -q")]
        with mock.patch.object(gr, "_safe_info", side_effect=lambda p: foreign[0]), \
             mock.patch.object(gr, "psutil", create=True) as _ps:
            _ps.process_iter = mock.Mock(return_value=[mock.Mock(pid=300)])
            rep = gr.reap(dry_run=True, verbose=False)
        self.assertEqual(rep["killed"], [])
        self.assertEqual(rep["spared"], [])  # не в связке вообще — не отражается

    def test_fault_psutil_missing(self):
        """psutil недоступен = FAULT, не исключение."""
        with mock.patch.object(gr, "psutil", None):
            rep = gr.reap(dry_run=True, verbose=False)
        self.assertEqual(len(rep["fault"]), 1)
        self.assertIn("psutil", str(rep["fault"][0]))


if __name__ == "__main__":
    unittest.main()
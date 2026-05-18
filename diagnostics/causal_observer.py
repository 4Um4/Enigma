"""
path: diagnostics/causal_observer.py
Назначение: Читает backend-лог в фоновом потоке (tail -f аналог).
            Парсит строки через COMPILED-паттерны и вызывает методы health-checker-ов.
            Crash в этом модуле НЕ должен ронять игру — весь код в try/except.
Зависимости: diagnostics.pattern_registry,
             diagnostics.health_checkers.tick_health,
             diagnostics.health_checkers.movement_health
Основные сущности: CausalObserver
"""

import ast
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from diagnostics.pattern_registry import COMPILED
from diagnostics.health_checkers.tick_health import TickHealthChecker, TickHealthReport
from diagnostics.health_checkers.movement_health import MovementHealthChecker, MovementHealthReport


class CausalObserver:
    """
    Фоновый наблюдатель за backend-логом.
    Запускается через start(), останавливается через stop().
    После stop() можно вызвать export() для записи LAST_SESSION.md.
    """

    def __init__(self, log_dir: Optional[str] = None) -> None:
        # Определяем директорию логов относительно расположения этого файла
        if log_dir is None:
            _root = Path(__file__).parent.parent  # корень Enigma/
            log_dir = str(_root / "backend" / "logs")
        self._log_dir = Path(log_dir)
        self._log_file: Optional[Path] = None   # актуальный лог текущей сессии

        self._tick_checker = TickHealthChecker()
        self._movement_checker = MovementHealthChecker()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started_at = datetime.now()

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Запускает фоновый поток чтения лога."""
        try:
            self._log_file = self._find_latest_log()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="CausalObserver",
            )
            self._thread.start()
        except Exception as exc:
            print(f"[CDS] Observer start failed (игра продолжится): {exc}")

    def stop(self) -> None:
        """Сигнализирует потоку остановиться и ждёт завершения (max 3 сек)."""
        try:
            self._stop_event.set()
            if self._thread is not None:
                self._thread.join(timeout=3.0)
        except Exception:
            pass

    def export(self, output_path: str) -> None:
        """
        Строит отчёт и записывает LAST_SESSION.md.
        Вызывается после stop() из game_launcher.py.
        """
        try:
            from diagnostics.report_renderer import ReportRenderer
            tick_report = self._tick_checker.build()
            movement_report = self._movement_checker.build()
            renderer = ReportRenderer(
                tick_report=tick_report,
                movement_report=movement_report,
                started_at=self._started_at,
            )
            renderer.write(output_path)
        except Exception as exc:
            print(f"[CDS] Export failed (игра уже завершилась): {exc}")

    # ------------------------------------------------------------------
    # Внутренний поток
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Главный цикл фонового потока — читает лог построчно."""
        if self._log_file is None:
            return
        try:
            with open(self._log_file, "r", encoding="utf-8", errors="replace") as fh:
                # Если файл уже существовал — переходим в конец
                fh.seek(0, 2)
                while not self._stop_event.is_set():
                    line = fh.readline()
                    if not line:
                        # Проверяем не появился ли новый лог-файл (backend перезапустился)
                        new_log = self._find_latest_log()
                        if new_log != self._log_file:
                            self._log_file = new_log
                            fh.close()
                            fh = open(self._log_file, "r", encoding="utf-8", errors="replace")
                            fh.seek(0, 2)
                        time.sleep(0.05)
                        continue
                    self._dispatch(line.rstrip("\n"))
        except Exception as exc:
            print(f"[CDS] Reader thread error: {exc}")

    def _find_latest_log(self) -> Optional[Path]:
        """Возвращает самый свежий backend_*.log файл."""
        try:
            logs = sorted(
                self._log_dir.glob("backend_*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return logs[0] if logs else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Диспетчер строк лога → health-checkers
    # ------------------------------------------------------------------

    def _dispatch(self, line: str) -> None:
        """Пробует все паттерны для строки и вызывает нужный handler."""
        try:
            # --- Startup ---
            if COMPILED["startup_complete"].search(line):
                self._tick_checker.on_startup_complete()
                return

            m = COMPILED["llm_server_ok"].search(line)
            if m:
                self._tick_checker.on_llm_server_ok(m.group(1))
                return

            m = COMPILED["player_select"].search(line)
            if m:
                self._tick_checker.on_player_select(m.group(1), m.group(2))
                return

            m = COMPILED["session_loaded"].search(line)
            if m:
                self._tick_checker.on_player_select(m.group(1), m.group(2))
                return

            # --- Tick / Decision health ---
            m = COMPILED["decisions_count"].search(line)
            if m:
                self._tick_checker.on_decisions_count(int(m.group(1)))
                return

            m = COMPILED["tick_decisions_end"].search(line)
            if m:
                self._tick_checker.on_decisions_count(int(m.group(1)))
                return

            m = COMPILED["decision_hub"].search(line)
            if m:
                npc, intent, score, event = m.group(1), m.group(2), float(m.group(3)), m.group(4)
                self._movement_checker.on_decision_hub(npc, intent, score, event)
                return

            m = COMPILED["state_applied"].search(line)
            if m:
                self._movement_checker.on_state_applied(m.group(1), float(m.group(2)), m.group(3))
                return

            # --- LLM health ---
            if COMPILED["llm_call"].search(line):
                self._tick_checker.on_llm_call()
                return

            m = COMPILED["llm_response"].search(line)
            if m:
                self._tick_checker.on_llm_response(int(m.group(1)))
                return

            if COMPILED["llm_nothing"].search(line):
                self._tick_checker.on_llm_nothing()
                return

            if COMPILED["llm_cjk"].search(line):
                self._tick_checker.on_llm_cjk()
                return

            # --- Movement / Traversal ---
            m = COMPILED["traversal_start"].search(line)
            if m:
                self._movement_checker.on_traversal_start(m.group(1), m.group(2))
                return

            m = COMPILED["node_not_found"].search(line)
            if m:
                self._movement_checker.on_node_not_found(m.group(1), m.group(2), m.group(3))
                return

            if COMPILED["spatial_fallback"].search(line):
                self._movement_checker.on_spatial_fallback()
                return

            m = COMPILED["graph_fallback"].search(line)
            if m:
                self._movement_checker.on_graph_fallback(m.group(1))
                return

            # --- Координаты NPC из TRACE SNAPSHOT ---
            m = COMPILED["trace_snapshot"].search(line)
            if m:
                self._movement_checker.on_trace_snapshot(m.group(1), float(m.group(2)), float(m.group(3)))
                return

            m = COMPILED["engine_received"].search(line)
            if m:
                self._movement_checker.on_engine_received(m.group(1), m.group(2))
                return

            # --- Perception ---
            m = COMPILED["perception_filter"].search(line)
            if m:
                # Парсим список NPC: "['thief_shadow', 'guard_borko']"
                try:
                    npc_list = ast.literal_eval(m.group(3))
                    self._movement_checker.on_perception_filter(npc_list)
                except Exception:
                    pass
                return

        except Exception:
            # Любой сбой диспетчера — тихо глотаем, лог не должен ронять игру
            pass

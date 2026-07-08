"""
path: diagnostics/causal_observer.py
Назначение: Пост-мортем анализатор каузальных логов.
            Читает лог-файл сессии после завершения игры, парсит строки
            через COMPILED-паттерны и вызывает методы health-checker-ов.
            Crash в этом модуле НЕ должен ронять игру — весь код в try/except.
Зависимости: diagnostics.pattern_registry,
             diagnostics.health_checkers.tick_health,
             diagnostics.health_checkers.movement_health
Основные сущности: CausalObserver
"""

import ast
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from diagnostics.pattern_registry import COMPILED
from diagnostics.health_checkers.tick_health import TickHealthChecker, TickHealthReport
from diagnostics.health_checkers.movement_health import MovementHealthChecker, MovementHealthReport
from diagnostics.health_checkers.invariant_health import InvariantHealthChecker
from diagnostics.dna_metrics import DNAComputer

logger = logging.getLogger(__name__)


class CausalObserver:
    """
    Пост-мортем наблюдатель: читает лог-файл после завершения игры.
    Не перехватывает stdout, не ломает SSE.
    """

    def __init__(self, log_path: Optional[str] = None) -> None:
        self._log_path = Path(log_path) if log_path else None
        self._tick_checker = TickHealthChecker()
        self._movement_checker = MovementHealthChecker()
        self._invariant_checker = InvariantHealthChecker()
        self._started_at = datetime.now()
        self._dna_computer: Optional[DNAComputer] = None

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Заглушка — данные читаются post-mortem из лога."""
        pass

    def stop(self) -> None:
        """Заглушка."""
        pass

    def export(self, output_path: str) -> None:
        """
        Читает лог-файл пост-мортем, строит отчёт и записывает LAST_SESSION.md.
        Вызывается после stop() из game_launcher.py.
        """
        try:
            self._parse_log_file()
            
            from diagnostics.report_renderer import ReportRenderer
            tick_report = self._tick_checker.build()
            movement_report = self._movement_checker.build()
            invariant_violations = self._invariant_checker.build()

            self._dna_computer = DNAComputer(
                tick_report=tick_report,
                movement_report=movement_report,
                started_at=self._started_at,
                invariant_violations=invariant_violations,
            )
            
            renderer = ReportRenderer(
                tick_report=tick_report,
                movement_report=movement_report,
                dna_computer=self._dna_computer,
                invariant_violations=invariant_violations,
                started_at=self._started_at,
            )
            renderer.write(output_path)
            print(f"[CDS] Отчёт LAST_SESSION.md сохранён: {output_path}")
        except Exception as exc:
            print(f"[CDS] Export failed: {exc}")
            logger.error(f"[CDS] Export failed: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # Парсинг лога
    # ------------------------------------------------------------------

    def _parse_log_file(self) -> None:
        """Построчно читает лог-файл и диспетчеризует строки."""
        if not self._log_path or not self._log_path.exists():
            logger.warning(f"[CDS] Log file not found: {self._log_path}")
            return

        logger.info(f"[CDS] Parsing log: {self._log_path}")
        with open(self._log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                self._dispatch(line.rstrip("\n"))

    # ------------------------------------------------------------------
    # Диспетчер строк → health-checkers (ЕДИНСТВЕННЫЙ МЕТОД)
    # ------------------------------------------------------------------

    def _dispatch(self, line: str) -> None:
        """Пробует все паттерны для строки и вызывает нужный handler."""
        try:
            # --- Startup ---
            if COMPILED["startup_complete"].search(line):
                self._tick_checker.on_startup_complete()
                return

            if COMPILED["llm_server_ok"].search(line):
                self._tick_checker.on_llm_server_ok()
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
                # Не вызываем on_decisions_count() — [R3_DIRECT] уже учитывает тик.
                # [TICK_DECISIONS] end дублирует подсчёт, завышая total_ticks и занижая SHI.
                return

            m = COMPILED["decision_hub"].search(line)
            if m:
                npc, intent, score, event = m.group(1), m.group(2), float(m.group(3)), m.group(4)
                self._movement_checker.on_decision_hub(npc, intent, score, event)
                self._tick_checker.on_individual_decision()
                return

            m = COMPILED["decision_score"].search(line)
            if m:
                # Резервный канал: [TRACE][DECISION_SCORE] ловит решения
                # даже если [DECISION_HUB] не совпал (другой формат лога)
                self._tick_checker.on_individual_decision()
                return

            m = COMPILED["state_applied"].search(line)
            if m:
                self._movement_checker.on_state_applied(m.group(1), float(m.group(2)), m.group(3))
                return

            # --- Pipeline pre-bus failures (Инвариант 3: Наблюдаемость отказа) ---
            if COMPILED["pipeline_critical"].search(line):
                self._tick_checker.on_pipeline_critical()
                return

            if COMPILED["causality_crash"].search(line):
                self._tick_checker.on_causality_crash()
                return

            if COMPILED["phase8_crash"].search(line):
                self._tick_checker.on_phase8_crash()
                return

            if COMPILED["tick_orch_error"].search(line):
                self._tick_checker.on_tick_orch_error()
                return

            if COMPILED["affect_decay_fail"].search(line):
                self._tick_checker.on_affect_decay_fail()
                return

            # --- LLM health ---
            if COMPILED["llm_call"].search(line):
                self._tick_checker.on_llm_call()
                return

            m = COMPILED["llm_response"].search(line)
            if m:
                self._tick_checker.on_llm_response(int(m.group(1)))
                return

            if COMPILED["llm_worker_call"].search(line):
                self._tick_checker.on_llm_call()
                return

            m = COMPILED["llm_worker_response"].search(line)
            if m:
                self._tick_checker.on_llm_response(int(m.group(1)))
                return

            # Streaming path observability (ADR-147)
            if COMPILED["llm_stream_call"].search(line):
                self._tick_checker.on_llm_call()
                return

            m = COMPILED["llm_stream_response"].search(line)
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

            m = COMPILED["editor_json_found"].search(line)
            if m:
                self._movement_checker.on_editor_json_found(m.group(1))
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

            # --- Directive pipeline (для OBI) ---
            m = COMPILED["obedience_pressure"].search(line)
            if m:
                try:
                    pressure = float(m.group(3))
                    if self._dna_computer is not None:
                        self._dna_computer.on_directive(pressure)
                except Exception:
                    pass
                return

            # --- Perception ---
            m = COMPILED["perception_filter"].search(line)
            if m:
                try:
                    npc_list = ast.literal_eval(m.group(3))
                    self._movement_checker.on_perception_filter(npc_list)
                except Exception:
                    pass
                return

            # --- Invariant Defense System ---
            m_sim = COMPILED["sim_integrity"].search(line)
            if m_sim:
                self._invariant_checker.on_sim_integrity(
                    invariant_id=m_sim.group(1),
                    file=m_sim.group(3),
                    line=int(m_sim.group(4)),
                )
                return
            
            m_tick = COMPILED["tick_complete"].search(line)
            if m_tick:
                self._invariant_checker.on_tick_complete(
                    tick=int(m_tick.group(1)),
                    game_time_seconds=float(m_tick.group(2)),
                    decisions_count=int(m_tick.group(3)),
                    verbal_intents_count=int(m_tick.group(4)),
                    npc_moved_count=int(m_tick.group(5)),
                )
                return
            
            m_scene = COMPILED["scene_events_verbal"].search(line)
            if m_scene:
                self._invariant_checker.on_dialogue_emitted(int(m_scene.group(1)))
                return

        except Exception:
            pass
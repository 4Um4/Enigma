"""
path: diagnostics/health_checkers/tick_health.py
Назначение: Агрегирует метрики здоровья тик-пайплайна из разобранных событий лога.
            Считает decisions, events, LLM-вызовы, CJK-галлюцинации.
Зависимости: diagnostics.pattern_registry
Основные сущности: TickHealthChecker, TickHealthReport
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class TickHealthReport:
    """Итоговый срез здоровья тик-пайплайна за сессию."""
    total_ticks: int = 0            # сколько раз сработал R3_DIRECT
    decisions_zero_ticks: int = 0  # тики с 0 decisions (симуляция заморожена)
    decisions_nonzero_ticks: int = 0
    total_decisions: int = 0
    llm_calls: int = 0
    llm_responses: int = 0
    llm_nothing_count: int = 0     # "Ничего не произошло." — LLM молчит
    llm_cjk_lines: int = 0         # строки с китайскими галлюцинациями
    startup_ok: bool = True   # uvicorn в subprocess — не перехватывается, считаем True если игра запустилась
    llm_server_ok: bool = False
    player_campaign: str = ""
    player_name: str = ""
    # Инвариант 3: Наблюдаемость пред-шинных отказов
    pipeline_critical_count: int = 0     # [PIPELINE][CRITICAL] — каузальный разрыв
    causality_crash_count: int = 0       # [CAUSALITY_CRASH] — краш подписчика
    phase8_crash_count: int = 0          # [PHASE8_CRASH] — краш обработчика Phase 8
    tick_orch_error_count: int = 0       # [TICK_ORCH] — фатальный краш тика
    affect_decay_fail_count: int = 0     # [AFFECT_DECAY] — потеря аффективных следов
    warnings: List[str] = field(default_factory=list)

    def is_simulation_dead(self) -> bool:
        """
        Симуляция мертва только если:
        - были тики с действием игрока (llm_calls > 0) И все decisions = 0.
        - Idle-тики с 0 decisions — норма (нет игрока рядом).
        """
        if self.total_ticks == 0:
            return False  # сессия слишком короткая для вывода
        if self.llm_calls == 0:
            return False  # игрок ничего не делал — idle норма
        # ВАЖНО: Проверяем total_decisions, так как [R3_DIRECT] 0 может затереть
        # decisions_nonzero_ticks, хотя [DECISION_HUB] фиксирует решения NPC.
        return self.decisions_nonzero_ticks == 0 and self.total_decisions == 0

    def on_individual_decision(self) -> None:
        """Вызывается при парсинге [DECISION_HUB], чтобы учесть реальные решения NPC."""
        self.total_decisions += 1
        # Гарантируем, что тик не считается мертвым, если было хоть одно решение
        if self.decisions_nonzero_ticks == 0:
            self.decisions_nonzero_ticks = 1

    def summary_line(self) -> str:
        status = "❌ МЕРТВА" if self.is_simulation_dead() else "✅ живёт"
        return (
            f"Тиков: {self.total_ticks} | "
            f"Decisions > 0: {self.decisions_nonzero_ticks}/{self.total_ticks} | "
            f"LLM: {self.llm_calls} вызовов / {self.llm_responses} ответов | "
            f"Симуляция: {status}"
        )


class TickHealthChecker:
    """
    Накапливает события из CausalObserver и строит TickHealthReport.
    Вызывается через методы on_*() по мере парсинга лога.
    """

    def __init__(self) -> None:
        self._report = TickHealthReport()
        # Временный счётчик decisions текущего тика
        self._current_tick_decisions: int = 0

    # --- Точки входа (вызываются из causal_observer) ---

    def on_decisions_count(self, count: int) -> None:
        """Сработал [R3_DIRECT] с N decisions."""
        self._report.total_ticks += 1
        self._current_tick_decisions = count
        self._report.total_decisions += count
        if count == 0:
            self._report.decisions_zero_ticks += 1
        else:
            self._report.decisions_nonzero_ticks += 1

    def on_llm_call(self) -> None:
        self._report.llm_calls += 1

    def on_llm_response(self, chars: int) -> None:
        self._report.llm_responses += 1

    def on_llm_nothing(self) -> None:
        self._report.llm_nothing_count += 1

    def on_llm_cjk(self) -> None:
        self._report.llm_cjk_lines += 1

    def on_startup_complete(self) -> None:
        self._report.startup_ok = True

    def on_llm_server_ok(self) -> None:
        self._report.llm_server_ok = True

    def on_player_select(self, campaign: str, player: str) -> None:
        self._report.player_campaign = campaign
        self._report.player_name = player

    # Инвариант 3: Наблюдаемость пред-шинных отказов
    def on_pipeline_critical(self) -> None:
        self._report.pipeline_critical_count += 1

    def on_causality_crash(self) -> None:
        self._report.causality_crash_count += 1

    def on_phase8_crash(self) -> None:
        self._report.phase8_crash_count += 1

    def on_tick_orch_error(self) -> None:
        self._report.tick_orch_error_count += 1

    def on_affect_decay_fail(self) -> None:
        self._report.affect_decay_fail_count += 1

    # --- Финальный отчёт ---

    def build(self) -> TickHealthReport:
        # Предупреждения — формируем при сборке, не накопительно
        self._report.warnings.clear()
        if self._report.is_simulation_dead():
            self._report.warnings.append("КРИТИЧНО: все тики вернули 0 decisions — симуляция заморожена")
        if self._report.llm_cjk_lines > 0:
            self._report.warnings.append(
                f"LLM галлюцинирует на китайском: {self._report.llm_cjk_lines} строк"
            )
        if self._report.llm_nothing_count > 2:
            self._report.warnings.append(
                f"LLM возвращает 'Ничего не произошло' {self._report.llm_nothing_count} раз подряд"
            )
        if self._report.llm_calls > 0 and self._report.llm_responses == 0:
            self._report.warnings.append("LLM вызывалась но ни разу не ответила — проверь llm_server")
        # Инвариант 3: Пред-шинные отказы — система должна быть шумной при смерти
        _prebus_total = (self._report.pipeline_critical_count + self._report.causality_crash_count +
                         self._report.phase8_crash_count + self._report.tick_orch_error_count)
        if _prebus_total > 0:
            self._report.warnings.append(
                f"КРИТИЧНО: {_prebus_total} пред-шинных отказов "
                f"(pipeline={self._report.pipeline_critical_count}, "
                f"causality={self._report.causality_crash_count}, "
                f"phase8={self._report.phase8_crash_count}, "
                f"tick_orch={self._report.tick_orch_error_count}) — "
                f"CDS слеп к этим багам без Инварианта 3"
            )
        if self._report.affect_decay_fail_count > 2:
            self._report.warnings.append(
                f"Аффективные отпечатки теряются: {self._report.affect_decay_fail_count} сбоев decay"
            )
        return self._report

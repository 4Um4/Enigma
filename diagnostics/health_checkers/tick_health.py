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
    startup_ok: bool = False
    llm_server_ok: bool = False
    player_campaign: str = ""
    player_name: str = ""
    warnings: List[str] = field(default_factory=list)

    def is_simulation_dead(self) -> bool:
        """Симуляция мертва если 100% тиков — нулевые decisions."""
        if self.total_ticks == 0:
            return True
        return self.decisions_zero_ticks == self.total_ticks

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

    def on_llm_server_ok(self, url: str) -> None:
        self._report.llm_server_ok = True

    def on_player_select(self, campaign: str, player: str) -> None:
        self._report.player_campaign = campaign
        self._report.player_name = player

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
        return self._report

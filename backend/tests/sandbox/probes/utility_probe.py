"""
Пробник полезности. Фиксирует сдвиг скоринга до и после давления.

Файл: backend/tests/sandbox/probes/utility_probe.py
Назначение: Наблюдает за изменением скоринга решений NPC под давлением.
Зависимости: caual_trace

TODO:
- В будущем можно расширить функционал, добавив разные типы полезности (социальная, физическая, экзистенциальная) и их взаимодействия.
"""
from tests.sandbox.runtime.causal_trace import CausalTrace

class UtilityProbe:
    def __init__(self, trace: CausalTrace):
        self.trace = trace

    def observe_utility_shift(self, tick: int, entity_id: str, action: str, old_score: float, new_score: float, parent_id: str):
        self.trace.observe(
            tick=tick,
            phase="UTILITY",
            entity_id=entity_id,
            event=f"{action}_SCORE_SHIFT",
            data={"old": old_score, "new": new_score, "delta": new_score - old_score},
            parent_id=parent_id
        )
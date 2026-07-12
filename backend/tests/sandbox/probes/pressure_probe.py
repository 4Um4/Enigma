"""
Пробник давления. Фиксирует искривление социального пространства.

Файл: backend/tests/sandbox/probes/pressure_probe.py
Назначение: Наблюдает за рождением психологического давления.
Зависимости: caual_trace

TODO:
- В будущем можно расширить функционал, добавив разные типы давления (социальное, физическое, экзистенциальное) и их взаимодействия.
"""

from tests.sandbox.runtime.causal_trace import CausalTrace


class PressureProbe:
    def __init__(self, trace: CausalTrace):
        self.trace = trace

    def observe_pressure(self, tick: int, entity_id: str, pressure_type: str, magnitude: float, parent_id: str):
        self.trace.observe(
            tick=tick,
            phase="PRESSURE",
            entity_id=entity_id,
            event=pressure_type,
            data={"magnitude": magnitude},
            parent_id=parent_id,
        )

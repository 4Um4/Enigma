"""
Каузальный Осциллограф ENIGMA.
Не тест. Инструмент наблюдения за фазовыми переходами симуляции.
Проверяет не координаты, а ЗАКОННОСТЬ рождения движения.

Файл: backend/tests/sandbox/causal_oscilloscope.py
Назначение: Инструмент наблюдения за током причинности. Пробники (Probes) внедряются в шину и оркестратор, фиксируя фазовые переходы без изменения мира.
Зависимости: typing, json, dataclasses
Основные сущности: CausalProbe, PressureProbe, UtilityProbe, TraversalProbe, CausalOscilloscope

запуск:
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

@dataclass
class CausalFrame:
    """Единица наблюдения. Снимок одного фазового перехода."""
    tick: int
    domain: str          # SEMANTIC, PRESSURE, UTILITY, DECISION, TRAVERSAL
    entity_id: str
    event: str
    data: Dict[str, Any]

class CausalProbe:
    """Базовый наблюдатель. Не меняет мир, только фиксирует."""
    def __init__(self, name: str, domain: str):
        self.name = name
        self.domain = domain
        self.trace: List[CausalFrame] = []

    def observe(self, tick: int, entity_id: str, event: str, data: Dict[str, Any]):
        self.trace.append(CausalFrame(
            tick=tick,
            domain=self.domain,
            entity_id=entity_id,
            event=event,
            data=data
        ))

class PressureProbe(CausalProbe):
    """Наблюдает за возникновением психологического давления (Физика Власти)."""
    def __init__(self):
        super().__init__("PressureProbe", "PRESSURE")

class UtilityProbe(CausalProbe):
    """Наблюдает за искажением пространства решений NPC."""
    def __init__(self):
        super().__init__("UtilityProbe", "UTILITY")

class TraversalProbe(CausalProbe):
    """Наблюдает за материализацией решения в физическое движение."""
    def __init__(self):
        super().__init__("TraversalProbe", "TRAVERSAL")

class CausalOscilloscope:
    """
    Главный модуль Песочницы.
    Собирает данные с пробников и визуализирует каузальную цепь.
    """
    def __init__(self):
        self.pressure = PressureProbe()
        self.utility = UtilityProbe()
        self.traversal = TraversalProbe()
        self._current_tick: int = 0

    def set_tick(self, tick: int):
        self._current_tick = tick

    def trace_flow(self) -> str:
        """Выводит каузальную цепь в виде читаемого лога."""
        output = ["\n=== CAUSAL TRACE ==="]
        all_frames = self.pressure.trace + self.utility.trace + self.traversal.trace
        all_frames.sort(key=lambda f: (f.tick, f.domain))

        for frame in all_frames:
            output.append(
                f"T:{frame.tick} | {frame.domain:10} | {frame.entity_id:15} | "
                f"{frame.event:25} | {json.dumps(frame.data)}"
            )
        output.append("===================\n")
        return "\n".join(output)

    def assert_causal_legitimacy(self, npc_id: str, expected_decision: str):
        """
        Проверяет не результат, а ДОПУСТИМОСТЬ процесса.
        Движение возможно только если есть давление -> решение -> транзит.
        """
        # 1. Было ли давление?
        pressure_events = [f for f in self.pressure.trace if f.entity_id == npc_id]
        if not pressure_events:
            raise AssertionError(f"CAUSAL VIOLATION: NPC {npc_id} решил двигаться БЕЗ давления.")

        # 2. Было ли решение?
        decision_events = [f for f in self.utility.trace if f.entity_id == npc_id and f.event == "DECISION_MADE"]
        if not decision_events:
            raise AssertionError(f"CAUSAL VIOLATION: NPC {npc_id} двигается БЕЗ акта воли (DecisionHub).")

        # 3. Был ли транзит (а не телепортация)?
        traversal_events = [f for f in self.traversal.trace if f.entity_id == npc_id and f.event == "TRAVERSAL_STARTED"]
        if not traversal_events:
            raise AssertionError(f"CAUSAL VIOLATION: NPC {npc_id} сменил позицию БЕЗ TraversalState (Телепортация!).")

        # 4. Проверяем соответствие решения давлению
        final_decision = decision_events[-1].data.get("action")
        if final_decision != expected_decision:
            raise AssertionError(
                f"CAUSAL DRIFT: Ожидалось решение {expected_decision}, NPC {npc_id} выбрал {final_decision}"
            )

        return True
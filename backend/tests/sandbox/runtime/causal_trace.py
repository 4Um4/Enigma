"""
Каузальный след. Доказательство легитимности состояния.

Файл: backend/tests/sandbox/runtime/causal_trace.py
Назначение: Структура данных для хранения фазовых переходов причинности. Позволяет отследить, ПОЧЕМУ система пришла к состоянию.
Зависимости: dataclasses, uuid, typing
Основные сущности: CausalFrame, CausalTrace

TODO:
- В будущем можно расширить функционал, добавив возможность "заморозки" времени, ускорения/замедления, или даже обратного отсчета.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class CausalFrame:
    """Единица наблюдения. Снимок одного фазового перехода."""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tick: int = 0
    phase: str = "" # SEMANTIC, PRESSURE, UTILITY, DECISION
    entity_id: str = ""
    event: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    causal_parent_id: Optional[str] = None # ID кадра, который породил этот

class CausalTrace:
    """Регистратор причинности. Наблюдает, не мутирует."""
    def __init__(self):
        self.frames: List[CausalFrame] = []

    def observe(self, tick: int, phase: str, entity_id: str, event: str, data: Dict[str, Any], parent_id: Optional[str] = None) -> str:
        frame = CausalFrame(
            tick=tick, phase=phase, entity_id=entity_id, event=event, data=data, causal_parent_id=parent_id
        )
        self.frames.append(frame)
        return frame.frame_id

    def find_frame(self, phase: str, event: str, entity_id: Optional[str] = None) -> Optional[CausalFrame]:
        """Ищет последний кадр, соответствующий критериям."""
        for f in reversed(self.frames):
            if f.phase == phase and f.event == event:
                if entity_id is None or f.entity_id == entity_id:
                    return f
        return None

    def print_lineage(self, frame_id: str) -> str:
        """Восстанавливает генеалогию решения от первопричины."""
        lineage = []
        current = next((f for f in self.frames if f.frame_id == frame_id), None)
        while current:
            lineage.append(f"[T:{current.tick} {current.phase}] {current.entity_id} | {current.event} | {current.data}")
            current = next((f for f in self.frames if f.frame_id == current.causal_parent_id), None)
        return "\n <- ".join(reversed(lineage))
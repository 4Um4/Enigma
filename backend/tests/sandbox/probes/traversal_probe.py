"""Пробник транзита. Фиксирует рождение непрерывного перемещения."""
from tests.sandbox.runtime.causal_trace import CausalTrace

class TraversalProbe:
    def __init__(self, trace: CausalTrace):
        self.trace = trace

    def observe_traversal_started(self, tick: int, entity_id: str, from_node: str, to_node: str, duration: float, parent_id: str):
        self.trace.observe(
            tick=tick, phase="TRAVERSAL", entity_id=entity_id, event="TRAVERSAL_STARTED",
            data={"from": from_node, "to": to_node, "duration": duration},
            parent_id=parent_id
        )

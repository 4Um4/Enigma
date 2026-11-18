from __future__ import annotations

# backend/app/services/world_model/world_graph.py
"""
Назначение: Ленивый граф состояний мира (ТЗ Отчёт №6 §3, ADR-O-445; Спринт 2A).
            Узлы — снапшоты, рёбра — Process через ProcessSource. find_paths —
            детерминированный BFS «симуляция достижимости» (решение Мастера по 2A):
            каждый путь несёт собственную гипотетическую копию снапшота; эффекты
            процесса применяются ТОЛЬКО к копии, реальный мир не читается и не
            пишется ни на одном шаге (Causal Integrity: план != действие).
            Ребро доступно, если requires_world_state процесса И requires_provider_state
            источника удовлетворены гипотетическому снапшоту — две ОТДЕЛЬНЫЕ проверки.
            Fail-closed: отсутствующее/несравнимое значение = условие не выполнено;
            числовая дельта без числовой базы в гипотезе не применяется;
            условный переход 'x->y' применяется только при совпадении текущего
            значения с x; безусловный '->y' — установка значения (с числовой
            коэрцией правой стороны).
            Плоскость 2A: снапшот без таргет-размерности (WorldSnapshotData);
            target_ref/{placeholders} резолвит ProcessExecutor (Спринт 2B).
            Эпистемический фильтр NPCKnowledge из сигнатуры ТЗ (§3) — Спринт 3.
Зависимости: stdlib (collections, typing); app.models.world.plan; app.models.world.process;
            app.services.world_model.process_registry; app.services.world_model.source_registry.
Основные сущности: WorldGraph
"""

from collections import deque
from typing import Deque, Dict, Iterable, List, Mapping, Set, Tuple

from app.models.world.plan import Plan, PlanStep, WorldSnapshotData
from app.models.world.process import WorldStateDelta
from app.models.world.world_predicate import WorldPredicate
from app.services.world_model.process_registry import ProcessRegistry
from app.services.world_model.source_registry import SourceRegistry

MAX_DEPTH = 5
MAX_PLANS = 10


def _coerce_scalar(raw: str) -> object:
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


class WorldGraph:
    """Ленивый BFS-граф достижимости поверх реестров Process/ProcessSource."""

    def __init__(self, processes: ProcessRegistry, sources: SourceRegistry) -> None:
        self._processes = processes
        self._sources = sources

    def find_paths(
        self,
        from_snapshot: WorldSnapshotData,
        target_predicates: Iterable[WorldPredicate],
        max_depth: int = MAX_DEPTH,
        max_plans: int = MAX_PLANS,
    ) -> List[Plan]:
        """Гипотетические пути от from_snapshot к состоянию, удовлетворяющему
        всем target_predicates. Детерминирован: процессы и источники обходятся
        в отсортированном порядке идентификаторов; результат — не более
        max_plans планов; каждый план — гипотеза о достижимости, не обещание NPC.
        """
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
            raise ValueError(f"max_depth должен быть целым >= 1, получен {max_depth!r}")
        if isinstance(max_plans, bool) or not isinstance(max_plans, int) or max_plans < 1:
            raise ValueError(f"max_plans должен быть целым >= 1, получен {max_plans!r}")

        targets = tuple(target_predicates)
        base: Dict[Tuple[str, str], object] = dict(from_snapshot)
        if self._satisfies_all(base, targets):
            return [Plan()]

        plans: List[Plan] = []
        visited: Set[Tuple[Tuple[str, str, str], ...]] = set()
        queue: Deque[Tuple[Dict[Tuple[str, str], object], Tuple[PlanStep, ...]]] = deque()
        queue.append((base, ()))

        while queue and len(plans) < max_plans:
            current, path = queue.popleft()
            key = self._snapshot_key(current)
            if key in visited:
                continue
            visited.add(key)
            if len(path) >= max_depth:
                continue
            for process in sorted(self._processes.all(), key=lambda p: p.process_id):
                if not self._satisfies_all(current, process.requires_world_state):
                    continue
                for source in sorted(
                    self._sources.for_process(process.process_id),
                    key=lambda s: s.source_id,
                ):
                    if not self._satisfies_all(current, source.requires_provider_state):
                        continue
                    new_snapshot = dict(current)
                    self._apply_deltas(new_snapshot, process.applies_deltas)
                    new_path = path + (
                        PlanStep(process=process, source=source, snapshot=new_snapshot),
                    )
                    if self._satisfies_all(new_snapshot, targets):
                        plans.append(Plan(steps=new_path))
                        if len(plans) >= max_plans:
                            break
                    else:
                        queue.append((new_snapshot, new_path))
        return plans

    @staticmethod
    def _satisfies_all(
        snapshot: Mapping[Tuple[str, str], object],
        predicates: Tuple[WorldPredicate, ...],
    ) -> bool:
        for pred in predicates:
            if not pred.is_satisfied_by(snapshot.get((pred.domain, pred.attribute))):
                return False
        return True

    @staticmethod
    def _snapshot_key(snapshot: Mapping[Tuple[str, str], object]) -> Tuple[Tuple[str, str, str], ...]:
        return tuple(
            (domain, attribute, repr(value))
            for (domain, attribute), value in sorted(snapshot.items())
        )

    @staticmethod
    def _apply_deltas(
        snapshot: Dict[Tuple[str, str], object],
        deltas: Tuple[WorldStateDelta, ...],
    ) -> None:
        for delta in deltas:
            key = (delta.domain, delta.attribute)
            current = snapshot.get(key)
            d = delta.delta
            if isinstance(d, bool):
                snapshot[key] = d
            elif isinstance(d, (int, float)):
                if isinstance(current, (int, float)) and not isinstance(current, bool):
                    snapshot[key] = current + d
                # иначе fail-closed: нет числовой базы — дельта не применяется
            elif isinstance(d, str):
                if d.startswith("->"):
                    snapshot[key] = _coerce_scalar(d[2:])
                elif "->" in d:
                    src, _, dst = d.partition("->")
                    if current == src:
                        snapshot[key] = _coerce_scalar(dst)
                else:
                    snapshot[key] = d
            else:
                snapshot[key] = d

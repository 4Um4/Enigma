from __future__ import annotations

# backend/app/services/world_model/process_registry.py
"""
Назначение: Читатель каталога Process'ов config/world/ontology/processes.yaml
            (ТЗ Отчёт №6 §2/§7, ADR-O-445). YAML — единственный источник истины;
            код только валидирует схему (fail-fast) и держит индекс
            process_id -> frozen Process.
Зависимости: stdlib (pathlib, typing); yaml; app.models.world.process; app.models.world.world_predicate.
Основные сущности: ProcessRegistry
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from app.models.world.process import Process, WorldStateDelta
from app.models.world.world_predicate import WorldPredicate

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROCESSES_PATH = _REPO_ROOT / "config" / "world" / "ontology" / "processes.yaml"

_DELTA_KEYS = {"domain", "attribute", "delta", "target_ref"}
_PREDICATE_KEYS = {"domain", "attribute", "value"}


class ProcessRegistry:
    """Индекс process_id -> Process (неизменяем после загрузки)."""

    def __init__(self, processes: Dict[str, Process]):
        self._processes: Dict[str, Process] = dict(processes)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ProcessRegistry":
        load_path = Path(path) if path is not None else DEFAULT_PROCESSES_PATH
        raw = yaml.safe_load(load_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("processes"), dict):
            raise ValueError(f"processes.yaml: ожидается корень 'processes: ...' ({load_path})")
        processes: Dict[str, Process] = {}
        for process_id, spec in raw["processes"].items():
            processes[process_id] = cls._build(process_id, spec)
        if not processes:
            raise ValueError("processes.yaml: каталог процессов пуст")
        return cls(processes)

    @staticmethod
    def _build(process_id: str, spec: dict) -> Process:
        if not isinstance(spec, dict):
            raise ValueError(f"process '{process_id}': ожидается отображение")

        deltas_raw = spec.get("applies_deltas")
        if not deltas_raw or not isinstance(deltas_raw, list):
            raise ValueError(f"process '{process_id}': applies_deltas обязателен и непустой")
        for d in deltas_raw:
            if not isinstance(d, dict) or not _DELTA_KEYS <= set(d):
                raise ValueError(f"process '{process_id}': каждая дельта требует domain/attribute/delta/target_ref")
        deltas = tuple(
            WorldStateDelta(
                domain=str(d["domain"]),
                attribute=str(d["attribute"]),
                delta=d["delta"],
                target_ref=str(d["target_ref"]),
            )
            for d in deltas_raw
        )

        requires_raw = spec.get("requires_world_state", [])
        for r in requires_raw:
            if not isinstance(r, dict) or not _PREDICATE_KEYS <= set(r):
                raise ValueError(f"process '{process_id}': каждый requires требует domain/attribute/value")
        requires = tuple(
            WorldPredicate(domain=str(r["domain"]), attribute=str(r["attribute"]), value=r["value"])
            for r in requires_raw
        )

        duration = spec.get("duration_ticks", 1)
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
            raise ValueError(f"process '{process_id}': duration_ticks должен быть int >= 1")

        return Process(
            process_id=process_id,
            applies_deltas=deltas,
            requires_world_state=requires,
            duration_ticks=duration,
            side_effects=tuple(str(e) for e in spec.get("side_effects", ())),
        )

    def all(self) -> Tuple[Process, ...]:
        return tuple(self._processes.values())

    def get(self, process_id: str) -> Optional[Process]:
        return self._processes.get(process_id)

    def __contains__(self, process_id: str) -> bool:
        return process_id in self._processes

    def __len__(self) -> int:
        return len(self._processes)

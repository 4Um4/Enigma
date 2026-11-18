from __future__ import annotations

# backend/app/services/world_model/source_registry.py
"""
Назначение: Читатель каталога ProcessSource config/world/sources/*.yaml
            (ТЗ Отчёт №6 §2.1/§7, ADR-O-445, Спринт 2A). Один YAML-файл —
            один источник; YAML — единственный источник истины, код только
            валидирует схему (fail-fast) и держит индекс source_id -> frozen
            ProcessSource. source_id обязан совпадать с именем файла.
            ТребованияProviderState и доступность процессов (available_processes)
            хранятся как объявлены; интерпретация — забота WorldGraph (2A-3).
Зависимости: stdlib (pathlib); yaml; app.models.world.process; app.models.world.world_predicate.
Основные сущности: SourceRegistry
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from app.models.world.process import ProcessSource
from app.models.world.world_predicate import WorldPredicate

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCES_DIR = _REPO_ROOT / "config" / "world" / "sources"

_SOURCE_KINDS = frozenset({"npc", "location", "item", "environment", "time"})
_REQUIRED_KEYS = ("source_id", "source_kind", "available_processes", "requires_provider_state")
_PROVIDER_KEYS = frozenset({"domain", "attribute", "value"})


class SourceRegistry:
    """Read-only каталог источников процессов. Загрузка fail-fast по схеме."""

    def __init__(self, sources: Dict[str, ProcessSource]):
        self._sources: Dict[str, ProcessSource] = dict(sources)

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "SourceRegistry":
        load_dir = Path(directory) if directory is not None else DEFAULT_SOURCES_DIR
        if not load_dir.is_dir():
            raise ValueError(f"sources: каталог не найден ({load_dir})")
        paths = sorted(load_dir.glob("*.yaml"))
        if not paths:
            raise ValueError(f"sources: каталог пуст ({load_dir})")
        sources: Dict[str, ProcessSource] = {}
        for path in paths:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"{path.name}: корень должен быть отображением")
            for key in _REQUIRED_KEYS:
                if key not in raw:
                    raise ValueError(f"{path.name}: нет обязательного ключа '{key}'")
            source_id = raw["source_id"]
            if not isinstance(source_id, str) or not source_id:
                raise ValueError(f"{path.name}: пустой/нестроковый source_id")
            if source_id != path.stem:
                raise ValueError(f"{path.name}: source_id '{source_id}' != имени файла")
            source_kind = raw["source_kind"]
            if source_kind not in _SOURCE_KINDS:
                raise ValueError(f"{path.name}: неизвестный source_kind '{source_kind}'")
            available = raw["available_processes"]
            if not isinstance(available, list) or not all(
                isinstance(p, str) and p for p in available
            ):
                raise ValueError(f"{path.name}: available_processes — список непустых строк")
            provider_preds = tuple(
                cls._parse_provider(entry, path.name) for entry in raw["requires_provider_state"]
            )
            sources[source_id] = ProcessSource(
                source_id=source_id,
                source_kind=source_kind,
                available_processes=tuple(available),
                requires_provider_state=provider_preds,
            )
        return cls(sources)

    @staticmethod
    def _parse_provider(entry: object, filename: str) -> WorldPredicate:
        if not isinstance(entry, dict) or set(entry.keys()) != _PROVIDER_KEYS:
            raise ValueError(f"{filename}: предикат provider-state должен иметь ровно {sorted(_PROVIDER_KEYS)}")
        if not all(isinstance(entry[k], str) and entry[k] for k in ("domain", "attribute")):
            raise ValueError(f"{filename}: domain/attribute provider-state — непустые строки")
        return WorldPredicate(
            domain=entry["domain"],
            attribute=entry["attribute"],
            value=entry["value"],
        )

    def all(self) -> Tuple[ProcessSource, ...]:
        return tuple(self._sources.values())

    def get(self, source_id: str) -> Optional[ProcessSource]:
        return self._sources.get(source_id)

    def for_process(self, process_id: str) -> Tuple[ProcessSource, ...]:
        """Источники, объявившие process_id в available_processes."""
        return tuple(
            s for s in self._sources.values() if process_id in s.available_processes
        )

    def __contains__(self, source_id: object) -> bool:
        return source_id in self._sources

    def __len__(self) -> int:
        return len(self._sources)

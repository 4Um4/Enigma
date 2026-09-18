"""
path: backend/app/domain/epoch.py
Назначение: Temporal Epoch (ADR-TEMPORAL-EPOCH) — иммутабельный факт мира
            + read-only проекция для вычисления тика.
Зависимости: domain (не знает ни о ком — Закон 1.2).
Основные сущности: WorldEpoch, WorldView
"""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class WorldEpoch:
    """Иммутабельный факт мира: Epoch N никогда не мутирует во время Tick N."""

    epoch_id: int


class WorldView:
    """Read-only проекция Epoch N для фаз тика.

    READ → снапшот эпохи. Любая попытка записи = ArchitecturalViolationError
    (по образцу PK Write Guard ADR-O-379): мутация committed-мира невозможна
    ПО ПОСТРОЕНИЮ, а не по гейту..Writer-сторона (Delta/Overlay) — PR-6.
    """

    __slots__ = ("_epoch", "_data")

    _MUTATION_MSG = (
        "[EPOCH-VIOLATION] Запись в WorldView запрещена: Epoch N не мутирует "
        "во время Tick N. Изменения — только через Delta/Overlay (PR-6)."
    )

    def __init__(self, epoch: WorldEpoch, data: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_epoch", epoch)
        object.__setattr__(self, "_data", data)

    @property
    def epoch_id(self) -> int:
        return self._epoch.epoch_id

    # --- Read API (Mapping-совместимый, §IV мандата: сначала совместимость) ---
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    # --- Write Guard: мутация = громкая смерть (L4, ADR-INV-DEF) ---
    def __setitem__(self, key: Any, value: Any) -> None:
        raise ArchitecturalViolationError(self._MUTATION_MSG)

    def __delitem__(self, key: Any) -> None:
        raise ArchitecturalViolationError(self._MUTATION_MSG)

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise ArchitecturalViolationError(self._MUTATION_MSG)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        raise ArchitecturalViolationError(self._MUTATION_MSG)

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise ArchitecturalViolationError(self._MUTATION_MSG)

    def clear(self) -> None:
        raise ArchitecturalViolationError(self._MUTATION_MSG)
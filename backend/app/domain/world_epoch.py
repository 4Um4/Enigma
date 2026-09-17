"""
path: /project/backend/app/domain/world_epoch.py
Назначение: TEMPORAL EPOCH ARCHITECTURE (S266, приказ Мастера).
    Мир как последовательность immutable эпох; тик = вычисление поверх
    read-only view с записью в overlay/delta; commit = атомарная
    сборка следующей эпохи. Замещает deepcopy-изоляцию (S-143),
    сохранённую после ADR-O-346 как броню от призрака: INV-хеш
    доказывает — редьюсер не мутирует вход.
Зависимости: typing (чистый домен)
Основные сущности: WorldEpoch, WorldView, TickOverlay
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class WorldEpoch:
    """Immutable факт мира. READ-ONLY for eternity.

    Это НЕ SSOT — это ЗАКРЕПЛЁННЫЙ момент SSOT (SceneStateManager
    остаётся владельцем). Epoch = снимок, который никто не может
    мутировать, потому что он не предоставляет write-API.
    """

    __slots__ = ("epoch_id", "_state", "_npcs")

    def __init__(self, epoch_id: int, state: Dict[str, Any],
                 npcs: Optional[List[Dict[str, Any]]] = None):
        # ВЛАДЕНИЕ ПЕРЕДАНО вызывающим (move-semantics): после создания
        # Epoch вызывающий обязан прекратить мутировать переданные dict.
        # Это контракт, enforcing — через WorldView (нет write-пути).
        object.__setattr__(self, "epoch_id", int(epoch_id))
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_npcs", npcs or [])

    @property
    def state(self) -> Dict[str, Any]:
        """Read-only доступ. Нарушение = нарушение контракта."""
        return self._state

    @property
    def npcs(self) -> List[Dict[str, Any]]:
        return self._npcs

    def view(self) -> "WorldView":
        """Единственная легальная точка чтения для фаз."""
        return WorldView(self)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            f"WorldEpoch is immutable (epoch={self.epoch_id}); "
            "mutation requires TickOverlay → atomic commit → new epoch"
        )


class WorldView:
    """READ-путь к эпохе. Фазы получают ТОЛЬКО это.

    Совместимость: duck-typed к dict-подобному чтению ([], .get, in,
    keys, values, items) — существующие call-sites не меняются.
    ЗАПИСЬ: запрещена (AttributeError) — единственный write-путь
    это TickOverlay.
    """

    __slots__ = ("_epoch",)

    def __init__(self, epoch: WorldEpoch):
        object.__setattr__(self, "_epoch", epoch)

    # ── dict-compat READ (бесплатно, ноль копий) ──

    def __getitem__(self, key: str) -> Any:
        return self._epoch.state[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._epoch.state.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._epoch.state

    def keys(self):
        return self._epoch.state.keys()

    def values(self):
        return self._epoch.state.values()

    def items(self):
        return self._epoch.state.items()

    def __len__(self) -> int:
        return len(self._epoch.state)

    def __iter__(self):
        return iter(self._epoch.state)

    # ── Свойства эпохи ──

    @property
    def epoch_id(self) -> int:
        return self._epoch.epoch_id

    @property
    def npcs(self) -> List[Dict[str, Any]]:
        """NPC-список эпохи — read-only."""
        return self._epoch.npcs

    # ── ЗАПРЕТ МУТАЦИИ (главный инвариант) ──

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("WorldView is read-only; use TickOverlay")

    def __setitem__(self, key: str, value: Any) -> None:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )
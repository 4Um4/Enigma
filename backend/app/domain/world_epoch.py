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

from typing import Any, Dict, ItemsView, Iterator, KeysView, List, Optional, ValuesView


class WorldEpoch:
    """Immutable факт мира. READ-ONLY for eternity.

    Это НЕ SSOT — это ЗАКРЕПЛЁННЫЙ момент SSOT (SceneStateManager
    остаётся владельцем). Epoch = снимок, который никто не может
    мутировать, потому что он не предоставляет write-API.
    """

    __slots__ = ("epoch_id", "_state", "_npcs")

    # PEP 526-аннотации (без присваивания — совместимы с __slots__):
    # дают mypy типы атрибутов, устанавливаемых через object.__setattr__.
    epoch_id: int
    _state: Dict[str, Any]
    _npcs: List[Dict[str, Any]]

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

    _epoch: "WorldEpoch"

    def __init__(self, epoch: WorldEpoch) -> None:
        object.__setattr__(self, "_epoch", epoch)

    # ── dict-compat READ (бесплатно, ноль копий) ──

    def __getitem__(self, key: str) -> Any:
        return self._epoch.state[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._epoch.state.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._epoch.state

    def keys(self) -> KeysView[str]:
        return self._epoch.state.keys()

    def values(self) -> ValuesView[Any]:
        return self._epoch.state.values()

    def items(self) -> ItemsView[str, Any]:
        return self._epoch.state.items()

    def __len__(self) -> int:
        return len(self._epoch.state)

    def __iter__(self) -> Iterator[str]:
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
    # S268/PR-6: полный набор write-гвардов (по образцу PK Write Guard
    # ADR-O-379). Отсутствие метода — не защита: явный гвард даёт
    # диагностику и не зависит от __getattr__-прокси в будущем.

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("WorldView is read-only; use TickOverlay")

    def __setitem__(self, key: str, value: Any) -> None:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )

    def __delitem__(self, key: str) -> None:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )

    def setdefault(self, key: str, default: Any = None) -> Any:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )

    def clear(self) -> None:
        raise AttributeError(
            "WorldView is read-only; use TickOverlay for writes"
        )


class TickOverlay:
    """WRITE-путь тика (PR-6, S268). Tick-local буфер мутаций поверх Epoch N.

    Duck-typed к dict-записи ([key]=, setdefault, .append-цели, .get, in),
    чтобы легаси-писатели Фаз 5-10 работали без изменения вызовов (мандат IV),
    но каждая мутация попадает в mutation_log (наблюдаемость, мандат VIII).
    Живёт ровно один тик. Commit = единственная сборка следующего состояния
    (вызов из Фазы 10, терминальный).

    Это НЕ второй SSOT: committed world принадлежит SSM; overlay —
    proposed transition (мандат II).
    """

    __slots__ = ("_epoch", "_data", "_log")

    _epoch: WorldEpoch
    _data: Dict[str, Any]
    _log: List[Dict[str, Any]]

    def __init__(self, epoch: WorldEpoch) -> None:
        object.__setattr__(self, "_epoch", epoch)
        object.__setattr__(self, "_data", {})
        object.__setattr__(self, "_log", [])

    @property
    def epoch_id(self) -> int:
        return self._epoch.epoch_id

    @property
    def mutation_log(self) -> List[Dict[str, Any]]:
        """Журнал мутаций тика: (key, action, source) — только наблюдение."""
        return self._log

    # ── READ: epoch-состояние, затем overlay поверх (shadow-read) ──

    def __getitem__(self, key: str) -> Any:
        if key in self._data:
            return self._data[key]
        return self._epoch.state[key]

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            return self._data[key]
        return self._epoch.state.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._data or key in self._epoch.state

    def keys(self):
        return self._data.keys() if self._data else self._epoch.state.keys()

    def __len__(self) -> int:
        return len(self._data) if self._data else len(self._epoch.state)

    def __iter__(self):
        return iter(self._data) if self._data else iter(self._epoch.state)

    # ── WRITE: только в overlay, каждая мутация в журнал ──

    def _touch(self, key: str, action: str) -> None:
        self._log.append({"key": key, "action": action, "epoch_id": self._epoch.epoch_id})

    def __setitem__(self, key: str, value: Any) -> None:
        self._touch(key, "set")
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        self._touch(key, "del")
        self._data.pop(key, None)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self._data and key not in self._epoch.state:
            self._touch(key, "setdefault")
            self._data[key] = default
        return self[key]

    def update(self, other: Any = None, **kwargs: Any) -> None:
        for k, v in dict(other or {}).items():
            self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def commit(self) -> Dict[str, Any]:
        """Терминальная сборка: overlay поверх среза эпохи. Один вызов за тик.

        Возвращает dict следующего состояния (потребитель — существующий
        atomic_commit). Мутация epoch.state невозможна по построению.
        """
        merged = dict(self._epoch.state)
        merged.update(self._data)
        return merged
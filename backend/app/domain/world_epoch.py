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

from typing import Any, Dict, ItemsView, Iterator, KeysView, List, Optional, Tuple, ValuesView


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
        # S268: без интерполяции атрибутов — на свежесконструированном
        # объекте (deepcopy._reconstruct) их ещё нет, сообщение само падало
        raise AttributeError(
            "WorldEpoch is immutable; "
            "mutation requires TickOverlay → atomic commit → new epoch"
        )

    def __deepcopy__(self, memo: Any) -> "WorldEpoch":
        # S268: immutable → шаринг безопасен по построению (deepcopy-совместимость:
        # default _reconstruct идёт через setattr и бился об __setattr__-гвард)
        return self


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

    def __deepcopy__(self, memo: Any) -> "WorldView":
        # S268: проекция иммутабельной эпохи → шаринг безопасен
        return self

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


class TickOverlay(dict):
    """WRITE-путь тика (PR-6, S268). Tick-local буфер мутаций поверх Epoch N.

    S268-фикс: наследует dict — isinstance-гварды сцены (10 точек:
    SSM, persistence, activity_lifecycle, game_loop) возвращали
    пустой dict на duck-typed overlay и ТЕРЯЛИ мир. Type-совместимость —
    часть контракта scene_state, не прихоть. Underlying dict держит
    только overlay-записи; чтения — shadow (epoch → overlay).

    Duck-typed к dict-записи ([key]=, setdefault, .append-цели, .get, in),
    чтобы легаси-писатели Фаз 5-10 работали без изменения вызовов (мандат IV),
    но каждая мутация попадает в mutation_log (наблюдаемость, мандат VIII).
    Живёт ровно один тик. Commit = единственная сборка следующего состояния
    (вызов из Фазы 10, терминальный).

    Это НЕ второй SSOT: committed world принадлежит SSM; overlay —
    proposed transition (мандат II).
    """

    # PEP 526-аннотации: атрибуты устанавливаются через object.__setattr__
    # (тот же паттерн, что и в WorldEpoch) — дают mypy типы.
    _epoch: WorldEpoch
    _log: List[Dict[str, Any]]

    def __init__(self, epoch: WorldEpoch) -> None:
        super().__init__()  # underlying dict = только overlay-записи
        object.__setattr__(self, "_epoch", epoch)
        object.__setattr__(self, "_log", [])

    @property
    def epoch_id(self) -> int:
        return self._epoch.epoch_id

    @property
    def mutation_log(self) -> List[Dict[str, Any]]:
        """Журнал мутаций тика: (key, action, source) — только наблюдение."""
        return self._log

    # ── READ: epoch-состояние, затем overlay поверх (shadow-read) ──

    def _overlay_keys(self) -> Any:
        return super().keys()

    def __getitem__(self, key: str) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self._epoch.state[key]

    def get(self, key: str, default: Any = None) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self._epoch.state.get(key, default)

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or key in self._epoch.state

    # Обход видит ОБЪЕДИНЕНИЕ epoch и overlay (патч S268/PR-6b-pre).
    # S268-урок: dict(self)/update(self) на dict-подклассе с переопределённым
    # __iter__ ЗАЦИКЛИВАЕТСЯ (PyDict_Merge теряет быстрый путь → generic-путь
    # → iter(self) → keys() → dict(self) → ∞). Обход — только через
    # super().keys() = raw-хранилище без виртуальных вызовов.
    def keys(self) -> KeysView[str]:  # type: ignore[override]
        seen = dict.fromkeys(self._epoch.state)
        for _k in super().keys():
            seen[_k] = None
        return seen.keys()

    def values(self) -> List[Any]:  # type: ignore[override]
        return [self[k] for k in self.keys()]

    def items(self) -> List[Tuple[str, Any]]:  # type: ignore[override]
        return [(k, self[k]) for k in self.keys()]

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    # ── WRITE: в underlying dict (через dict-API, мимо shadow-чтений) ──

    def _touch(self, key: str, action: str) -> None:
        self._log.append({"key": key, "action": action, "epoch_id": self._epoch.epoch_id})

    def __setitem__(self, key: str, value: Any) -> None:
        self._touch(key, "set")
        dict.__setitem__(self, key, value)

    def __delitem__(self, key: str) -> None:
        self._touch(key, "del")
        dict.__delitem__(self, key)

    def setdefault(self, key: str, default: Any = None) -> Any:
        if not dict.__contains__(self, key) and key not in self._epoch.state:
            self._touch(key, "setdefault")
            dict.__setitem__(self, key, default)
        return self[key]

    def update(self, other: Any = None, **kwargs: Any) -> None:  # type: ignore[override]
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
        for _k in super().keys():
            merged[_k] = dict.__getitem__(self, _k)
        return merged

    def __deepcopy__(self, memo: Any) -> Dict[str, Any]:
        # S268: deepcopy overlay = снимок ПОЛНОГО состояния (commit),
        # а не пустого tick-local буфера. WorldSnapshot (deepcopy сцены
        # в начале тика) получает плоский dictmerged — семантика
        # «снимок мира» сохранена. Возврат dict — не overlay!
        import copy as _copy
        return _copy.deepcopy(self.commit(), memo)
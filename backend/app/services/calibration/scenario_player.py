"""
path: backend/app/services/calibration/scenario_player.py
Назначение: Воспроизведение scripted-сценариев Лаборатории калибровки
    (M1/Задача 2, S221). Единственная ответственность: YAML-таймлайн →
    запланированные InterventionEvent со структурированной семантикой
    (ADR-O-367: ядро текст не парсит). Плеер — НЕ второй оркестратор
    (правило M1, мастер-решение S220): он не мутирует состояние мира и
    не вызывает решающие сервисы ядра — всю каузальную работу выполняет
    production pipeline. Нарушение границы ловит тест-гейт
    test_scenario_player_is_not_second_orchestrator.
    seed сценария — метаданные протокола: ядро детерминировано
    KernelRNG(tick, npc_id, salt) и от seed не зависит (ADR-O-301).
Зависимости: yaml, app.contracts.interventions (единственный контракт ядра).
Основные сущности: ScenarioError, ScenarioEvent, Scenario, load_scenario,
    ScenarioPlayer.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from yaml import safe_load

from app.contracts.interventions import InterventionEvent

# Действия, зарегистрированные в production-обработчике ядра
# (_process_player_action): consequence-ветвь компилятора
# (HELP/BLACKMAIL/ACCUSE — ADR-O-367), боевая труба (ATTACK — S122),
# директивная ветвь (MOVE/THREATEN/PERSUADE/GIVE — S115) и DIALOGUE
# (раскрытие секрета, M-07/M-08). Расширение списка = мини-ADR
# (прецедент ADR-O-362/O-367).
SUPPORTED_ACTIONS: frozenset = frozenset(
    {
        "HELP",
        "BLACKMAIL",
        "ACCUSE",
        "ATTACK",
        "MOVE",
        "THREATEN",
        "PERSUADE",
        "GIVE",
        "DIALOGUE",
    }
)

_ROOT_KEYS: frozenset = frozenset({"scenario_id", "description", "seed", "events"})
_EVENT_KEYS: frozenset = frozenset({"tick", "action", "target", "secret_id"})


class ScenarioError(RuntimeError):
    """Громкий отказ загрузки сценария: перечисляет ВСЕ найденные проблемы
    (house-style preset_io; тихий no-op в сценарии = ложь эксперимента, L4)."""


@dataclass(frozen=True)
class ScenarioEvent:
    """Одно запланированное вмешательство. tick — 1-based: событие
    исполняется на тике N (poll(N) его возвращает)."""

    tick: int
    action: str  # канонический UPPERCASE из SUPPORTED_ACTIONS
    target: str
    secret_id: Optional[str] = None


@dataclass(frozen=True)
class Scenario:
    """Валидированный сценарий: идентичность протокола + таймлайн."""

    scenario_id: str
    description: str = ""
    seed: Optional[int] = None
    events: Tuple[ScenarioEvent, ...] = ()


def load_scenario(path: "str | Path") -> Scenario:
    """Загружает и валидирует сценарий. Любая проблема = ScenarioError
    со списком ВСЕХ нарушений (не только первой попавшейся)."""
    scenario_path = Path(path)
    if not scenario_path.is_file():
        raise ScenarioError(f"Сценарий не найден: {scenario_path}")
    try:
        raw = safe_load(scenario_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ScenarioError(f"YAML не разобран ({scenario_path}): {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ScenarioError(f"Сценарий должен быть YAML-отображением: {scenario_path}")

    errors: List[str] = []
    unknown_root = [k for k in raw if k not in _ROOT_KEYS]
    if unknown_root:
        errors.append(
            f"неизвестные ключи корня {unknown_root} (разрешены {sorted(_ROOT_KEYS)})"
        )
    scenario_id = raw.get("scenario_id", "")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        errors.append("scenario_id: непустая строка обязательна")
        scenario_id = ""
    description = raw.get("description", "")
    if not isinstance(description, str):
        errors.append("description: ожидается строка")
        description = ""
    seed = raw.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        errors.append(f"seed: ожидается целое число, получено {seed!r}")
        seed = None
    events_raw = raw.get("events")
    if not isinstance(events_raw, list) or not events_raw:
        errors.append("events: непустой список обязателен")
        events_raw = []

    events: List[ScenarioEvent] = []
    for idx, entry in enumerate(events_raw):
        if not isinstance(entry, Mapping):
            errors.append(f"events[{idx}]: ожидается отображение")
            continue
        unknown = [k for k in entry if k not in _EVENT_KEYS]
        if unknown:
            errors.append(
                f"events[{idx}]: неизвестные ключи {unknown} "
                f"(разрешены {sorted(_EVENT_KEYS)})"
            )
            continue
        tick = entry.get("tick")
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 1:
            errors.append(
                f"events[{idx}].tick: ожидается целое >= 1, получено {tick!r}"
            )
            continue
        action_raw = entry.get("action", "")
        if not isinstance(action_raw, str):
            errors.append(
                f"events[{idx}].action: ожидается строка, получено {action_raw!r}"
            )
            continue
        action = action_raw.strip().upper()
        if action not in SUPPORTED_ACTIONS:
            errors.append(
                f"events[{idx}].action: '{action_raw}' не поддержан "
                f"(разрешены {sorted(SUPPORTED_ACTIONS)}; расширение = мини-ADR)"
            )
            continue
        target = entry.get("target", "")
        if not isinstance(target, str) or not target.strip():
            errors.append(f"events[{idx}].target: непустой npc_id обязателен")
            continue
        secret_id = entry.get("secret_id")
        if secret_id is not None and not isinstance(secret_id, str):
            errors.append(f"events[{idx}].secret_id: ожидается строка или отсутствие")
            continue
        if action == "BLACKMAIL" and not secret_id:
            errors.append(
                f"events[{idx}]: BLACKMAIL без secret_id не имеет каузального "
                f"эффекта (компилятор требует секрет) — укажите secret_id"
            )
            continue
        events.append(
            ScenarioEvent(
                tick=tick,
                action=action,
                target=target.strip(),
                secret_id=secret_id,
            )
        )

    if errors:
        raise ScenarioError(
            f"Сценарий невалиден ({scenario_path}):\n  - " + "\n  - ".join(errors)
        )
    return Scenario(
        scenario_id=scenario_id,
        description=description,
        seed=seed,
        events=tuple(sorted(events, key=lambda e: e.tick)),
    )


class ScenarioPlayer:
    """Таймлайн-эмиттер: сценарий → InterventionEvent на назначенном тике.

    Единственная точка контакта с ядром — фабрика InterventionEvent
    (ADR-TZ08-1). Журнал эмуляций (journal) — replay-идентичность
    протокола (мастер-требование S220): вот вход, вот что эмулировано.
    """

    def __init__(self, scenario: Scenario) -> None:
        self._scenario = scenario
        # events уже отсортированы load_scenario; рабочая копия
        self._pending: List[ScenarioEvent] = list(scenario.events)
        self.journal: List[Dict[str, Any]] = []

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def pending(self) -> List[ScenarioEvent]:
        """Неисполненные события (сценарий длиннее сессии)."""
        return list(self._pending)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def poll(self, next_tick: int) -> List[InterventionEvent]:
        """Возвращает события, назначенные ровно на тик next_tick (1-based),
        и переводит их в журнал. Повторный poll того же тика — пуст."""
        due: List[ScenarioEvent] = []
        remaining: List[ScenarioEvent] = []
        for event in self._pending:
            (due if event.tick == next_tick else remaining).append(event)
        self._pending = remaining

        emitted: List[InterventionEvent] = []
        for event in due:
            extra: Dict[str, Any] = {}
            if event.secret_id:
                extra["secret_id"] = event.secret_id
            emitted.append(
                InterventionEvent.from_player_action(
                    action_text=f"{event.action} -> {event.target}",
                    player_name="player",
                    tick=next_tick,
                    target_id=event.target,
                    semantic_action=event.action,
                    target_reference=event.target,
                    **extra,
                )
            )
            self.journal.append(
                {
                    "tick": next_tick,
                    "action": event.action,
                    "target": event.target,
                    "secret_id": event.secret_id,
                    "emitted": True,
                }
            )
        return emitted
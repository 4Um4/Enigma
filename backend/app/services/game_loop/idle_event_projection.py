"""
path: /project/backend/app/services/game_loop/idle_event_projection.py
Назначение: Наблюдаемая проекция idle-событий (ADR-O-421, LC-IMPL-1).
    Источник — EventDTO-поток тика (вердикт Мастера В1): наблюдательное
    окно-подписчик вокруг TickOrchestrator.execute в game_loop.idle_tick.
    v1-словарь УЗКИЙ (вердикт В2): {ACTIVITY_OUTCOME, THEFT} — значимое
    наблюдаемое, не представленное анимацией/другими каналами; NPC_MOVED
    и прочее — EXCLUDED с причиной на каждый член enum (не debug-log мира).
    Гейт восприятия — наблюдательная мембрана ADR-O-360 (LOS + дистанция,
    симметрия игрок↔NPC-свидетель; DEBT-R1: event.radius контрактом
    наблюдения НЕ является) + whisper-адресат по контракту EventDTO.
    Строго read-only (§15.4-8): проекция ничего не пишет в мир.
Зависимости: app.domain.events, app.domain.idle_projection,
    app.services.events.event_types, app.services.events.event_bus,
    app.services.events.observation_subscriber (константа мембраны),
    app.services.spatial.spatial_query_service
Основные сущности: idle_events_projection_enabled, PROJECTION_EVENT_TYPES,
    EXCLUDED_EVENT_TYPES, IdleEventTap, project_idle_events
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Tuple

from app.domain.events import EventDTO
from app.domain.idle_projection import IdleEventProjection, ProjectionValue
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.spatial.spatial_query_service import SpatialQueryService

logger = logging.getLogger(__name__)

# Радиус прямой видимости наблюдателя — SSOT ADR-O-360 (один факт — одно
# место: тот же, что у NPC-свидетелей ObservationSubscriber; симметрия
# игрок↔NPC, Устав §12.2).
from app.services.events.observation_subscriber import (
    _OBSERVATION_SIGHT_RADIUS as OBSERVATION_SIGHT_RADIUS,
)

# Идентификатор аватара игрока (SSOT позиций: npc_positions["player"]).
_PLAYER_ID = "player"

# Lifecycle-флаг (вердикт Мастера В4): ON default с коммита D — после
# зелёного LC-GC-01-ядра (SUPERBOX 3/3, read-only/детерминизм доказаны);
# флип исполнен этим коммитом; OFF — только явным env (=0). Вечный мёртвый
# (вечный мёртвый выключатель не оставляется). Чтение call-time, не кэш
# на импорте (прецедент micro/conftest D8P-иммунитета).
_DEFAULT_ENABLED = "1"


def idle_events_projection_enabled() -> bool:
    """Env-флаг IDLE_EVENTS_PROJECTION_ENABLED (ON default — вердикт В4, коммит D; OFF только явным env)."""
    return os.environ.get(
        "IDLE_EVENTS_PROJECTION_ENABLED", _DEFAULT_ENABLED
    ).strip().lower() in ("1", "true", "yes")


# ── v1-словарь: экстракторы наблюдаемой сути payload ───────────────────
# Формат value — компактная наблюдаемая строка/скаляр. Расширение словаря
# = вердикт Мастера + мини-ADR (прецедент _INTENT_EVENT_MAP, ADR-O-349).


def _value_activity_outcome(payload: Dict[str, Any]) -> ProjectionValue:
    """activity_outcome: «eat:ok» / «eat:fail» — исход деятельности."""
    _activity = str(payload.get("activity_type", ""))
    if not _activity:
        raise ValueError("activity_outcome: payload.activity_type отсутствует")
    _success = payload.get("success")
    if _success is True:
        return f"{_activity}:ok"
    if _success is False:
        return f"{_activity}:fail"
    raise ValueError("activity_outcome: payload.success не булев (контракт продюсера)")


def _value_theft(payload: Dict[str, Any]) -> ProjectionValue:
    """theft: наблюдаемый объект посягательства (target_id, S209 Producer)."""
    _target = payload.get("target_id")
    if not isinstance(_target, str) or not _target:
        raise ValueError("theft: payload.target_id отсутствует (Producer-контракт)")
    return _target


PROJECTION_EVENT_TYPES: Dict[EventType, Callable[[Dict[str, Any]], ProjectionValue]] = {
    EventType.ACTIVITY_OUTCOME: _value_activity_outcome,
    EventType.THEFT: _value_theft,
}

# ── EXCLUDED-реестр: причина на каждый член enum вне словаря ────────────
# Замок полноты (микро-тест): set(EventType) == словарь ∪ EXCLUDED — новых
# EventType без вердикта не бывает, молчаливых дыр нет.
EXCLUDED_EVENT_TYPES: Dict[EventType, str] = {
    # Канал 1 (физически видно анимацией/позициями — дублирование запрещено):
    EventType.NPC_MOVED: "визуально наблюдаемо перемещением",
    EventType.PLAYER_MOVED: "авторство игрока + анимация",
    EventType.MOVEMENT: "визуально наблюдаемо",
    EventType.OBJECT_MOVED: "визуально наблюдаемо",
    EventType.PROXIMITY_CLOSE: "производная позиций",
    EventType.PROXIMITY_LEAVE: "производная позиций",
    EventType.NPC_PROXIMITY_CLOSE: "NPC-NPC производная позиций",
    EventType.NPC_PROXIMITY_LEAVE: "NPC-NPC производная позиций",
    # Канал 3 (речь/обращение — существующие контуры + будущий режим разговора):
    EventType.NPC_SPOKE: "речь — perceived_narratives/журнал; обращение к игроку = будущий режим разговора (В3)",
    EventType.PLAYER_SPOKE: "авторство игрока",
    EventType.PLAYER_TALKS: "авторство игрока",
    EventType.DIALOGUE: "диалоговый контур",
    EventType.COMMUNICATION_CLAIM: "внутренняя эпистемика (Закон XI)",
    # Внутренняя эпистемика/телеметрия причинности (observation-only, Закон XI):
    EventType.EXPERIENCE_DELTA_COMMITTED: "внутренняя телеметрия причинности",
    EventType.CONCLUSION_FORMED: "внутренняя эпистемика",
    EventType.NPC_STATE_CHANGED: "внутреннее состояние",
    EventType.WILL_CONFLICT: "внутренний контур воли",
    EventType.DREAM: "внутреннее (сон); вердикт — LC-IMPL-5",
    EventType.NIGHTMARE: "внутреннее (сон); вердикт — LC-IMPL-5",
    EventType.DM_NARRATED: "нарративный канал DM",
    # Внутренняя физиология/жизнь NPC:
    EventType.SLEEPWALK: "физиология сна",
    # Авторство игрока:
    EventType.PLAYER_ATTACKED: "авторство игрока",
    EventType.PLAYER_ATTACK: "авторство игрока",
    EventType.PLAYER_ATTACKS: "авторство игрока",
    EventType.PLAYER_INSULTS: "авторство игрока",
    EventType.PLAYER_THREATENS: "авторство игрока",
    EventType.PLAYER_HELPERS: "авторство игрока",
    EventType.PLAYER_INTERACTS: "авторство игрока",
    EventType.PLAYER_USED_ITEM: "авторство игрока",
    EventType.PLAYER_CAST_SPELL: "авторство игрока",
    EventType.PLAYER_ASKS_WHY: "авторство игрока (NL-D5)",
    # Боевой контур — до контрактов перехода LC-07/08:
    EventType.COMBAT: "боевой контур — LC-GC-07",
    EventType.ACTOR_ATTACKS: "боевой контур — LC-GC-07",
    EventType.INTIMIDATION: "социальное давление боя",
    EventType.HELP: "социальный интент — речевой класс",
    # Речевые/коммуникативные интенты (future режим разговора, канал 3):
    EventType.OFFER_JOB: "речевой интент",
    EventType.REQUEST_SERVICE: "речевой интент",
    EventType.SPREAD_RUMOR: "речевой интент",
    EventType.CALL_FOR_HELP: "речевой интент",
    EventType.CHANGE_ROLE: "речевой интент",
    EventType.WARN: "речевой интент",
    EventType.TRADE: "речевой интент (материализация — TRADE β)",
    EventType.REPORT: "речевой интент",
    EventType.SOCIAL_ACTION: "социальный интент-канал",
    EventType.NPC_INTERACTS_NPC: "NPC-NPC социальная инициатива — вне v1-словаря (кандидат v1.x по вердикту Мастера)",
    EventType.BETRAYAL: "социальная семантика — речевой класс",
    EventType.SAVED_LIFE: "социальная семантика",
    # RE M2/D dormant (консьюмер Фр4 — отдельная фаза, Anti-Race):
    EventType.FLIRT_ACCEPTED: "RE dormant за флагом",
    EventType.FLIRT_REJECTED: "RE dormant за флагом",
    EventType.INTIMATE_ENCOUNTER: "RE dormant за флагом",
    EventType.INTIMATE_REJECTION: "RE dormant за флагом",
    # Инфраструктура/служебное:
    EventType.TIME_PASSED: "служебное время",
    EventType.TICK_COMPLETED: "служебный маркер тика",
    EventType.WORLD_TICK: "служебный проактивный тик",
    EventType.FACTION_EVENT: "вне сцены наблюдения v1",
    EventType.FATE_EVENT: "телеметрия судьбы",
    EventType.WEATHER_CHANGED: "ambient-канал — v1.x кандидат по вердикту",
    EventType.LIGHT_CHANGED: "ambient-канал — v1.x кандидат по вердикту",
    EventType.SOUND_EMITTED: "ambient-канал — v1.x кандидат по вердикту",
    EventType.SMELL_EMITTED: "ambient-канал — v1.x кандидат по вердикту",
    EventType.OBJECT_DESTROYED: "W-TRACK объектный контур",
    EventType.OBJECT_CHANGED: "W-TRACK объектный контур",
    EventType.PROPHECY_VISION: "нарративный контур",
    EventType.IDLE: "служебный маркер",
    EventType.UNKNOWN: "не-событие (fallback запрещён ADR-O-349)",
}


class IdleEventTap:
    """Наблюдательное окно проекции (§11: наблюдение не создаёт причинность).

    Подписывается ТОЛЬКО на v1-словарь; handler только захватывает EventDTO
    (возврат None — легален по контракту EventHandler). Публикаций нет.
    Отписка обязательна (синглтон шины не течёт) — game_loop закрывает окно
    в finally.
    """

    def __init__(self) -> None:
        self.captured: List[EventDTO] = []
        self._wired: List[Tuple[EventBus, EventType, Callable[[EventDTO], None]]] = []

    def subscribe(self, bus: EventBus) -> None:
        for _event_type in PROJECTION_EVENT_TYPES:
            _handler = self._make_handler()
            bus.subscribe(_event_type, _handler)
            self._wired.append((bus, _event_type, _handler))

    def unsubscribe(self) -> None:
        while self._wired:
            _bus, _event_type, _handler = self._wired.pop()
            _bus.unsubscribe(_event_type, _handler)

    def _make_handler(self) -> Callable[[EventDTO], None]:
        def _capture(event: EventDTO) -> None:
            self.captured.append(event)

        return _capture


def _player_perceives(event: EventDTO, sq: SpatialQueryService) -> bool:
    """Гейт восприятия аватара игрока (вердикт Мастера В2: МИР → CRFT → игрок).

    (0) private: наблюдатель ≠ источник — не видит никогда (§17.3);
    (1) whisper-адресат: событие, адресованное игроку, видит адресат по
        контракту EventDTO (THEFT у игрока из кармана);
    (2) наблюдательная мембрана ADR-O-360: LOS-видимость + дистанция до
        источника (симметрия NPC-свидетелей; event.radius НЕ контракт
        наблюдения — DEBT-R1).
    """
    if event.visibility == "private":
        # §17.3 (изоляция потребителей): private видит только источник;
        # игрок — не источник мировых событий; гейт ДО мембраны.
        return False
    if event.visibility == "whisper":
        _target = event.payload.get("target_id")
        if isinstance(_target, str) and _target == _PLAYER_ID:
            return True
    try:
        _dist = sq.distance(_PLAYER_ID, event.source)
    except Exception as exc:  # деградация наблюдателя, не тика (§11.2)
        logger.error(f"[IDLE_PROJECTION] distance({event.source}) failed: {exc}")
        return False
    if _dist > OBSERVATION_SIGHT_RADIUS:
        return False
    try:
        return bool(sq.visibility(_PLAYER_ID, event.source))
    except Exception as exc:
        logger.error(f"[IDLE_PROJECTION] visibility({event.source}) failed: {exc}")
        return False


def project_idle_events(
    captured: List[EventDTO], scene_state: Dict[str, Any]
) -> List[IdleEventProjection]:
    """Pure-проекция захваченных событий в наблюдаемые {cause, target, value}.

    Read-only: входы не мутируются (EventDTO frozen; scene_state только
    читается). Позиции — пост-тиковые (авторитетная сцена): эпистемическая
    аппроксимация тика — «что игрок, находясь здесь сейчас, мог воспринять».
    Отказ экстрактора/мембраны = logger.error + пропуск события
    (деградация канала наблюдаемости, не тика; guard-ошибки не глотаются
    здесь — они уже переброшены продюсером).
    """
    if not captured:
        return []
    try:
        _sq = SpatialQueryService(
            npc_positions=scene_state.get("npc_positions", {}),
            scene_state=scene_state,
        )
    except Exception as exc:
        logger.error(f"[IDLE_PROJECTION] SpatialQueryService build failed: {exc}")
        return []
    _projections: List[IdleEventProjection] = []
    for _event in captured:
        try:
            _event_key = EventType(_event.type)
        except ValueError:
            # Окно подписано только на словарь; чужой тип = контрактный
            # разрыв — деградация наблюдателя (лог + пропуск), не крах тика.
            logger.error(
                f"[IDLE_PROJECTION] неизвестный тип в окне: {_event.type!r}"
            )
            continue
        _extractor = PROJECTION_EVENT_TYPES.get(_event_key)
        if _extractor is None:
            continue  # вне v1-словаря (окно подписано только на словарь)
        try:
            _value = _extractor(_event.payload)
        except ValueError as exc:
            logger.error(f"[IDLE_PROJECTION] extractor {_event.type}: {exc}")
            continue
        if not _player_perceives(_event, _sq):
            continue
        _projections.append(
            IdleEventProjection(cause=_event.type, target=_event.source, value=_value)
        )
    return _projections

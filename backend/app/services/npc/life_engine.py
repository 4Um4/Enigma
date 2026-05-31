# -*- coding: utf-8 -*-
"""
LifeEngine — движок симуляции жизни NPC.
backend/app/services/npc/life_engine.py

Фаза 3B.1 (ROADMAP v5.1)

ПРИНЦИПЫ:
  - LifeEngine — чистый Python, НИКАКИХ LLM-вызовов
  - Python считает → SceneChange → SceneStateManager применяет
  - Мир живёт без участия игрока: каждый тик обновляет NPC по расписанию
  - Все изменения логируются через SceneStateManager (JSONL)

ТИРЫ СИМУЛЯЦИИ:
  Major → полная симуляция каждый тик (позиция + случайные события + стресс)
  Minor → расписание + случайные события раз в 3 тика
  Mass  → только флаги присутствия (instantaneous, не грузит CPU)

ВХОДНЫЕ ДАННЫЕ:
  major_npcs.json  — список Major NPC с расписанием (routine.schedule)
  scene_state      — текущее состояние сцены (откуда берём time_of_day)

ВЫХОДНЫЕ ДАННЫЕ:
  list[SceneChange] — изменения для применения через SceneStateManager.apply_changes()
  + обновляет NPC в памяти (caller сохраняет через _save_npcs)

ИНТЕГРАЦИЯ:
  orchestrator._run_python_engines() → LifeEngine.tick() → apply_changes()
  WorldScheduler.maybe_tick() вызывается отдельно (LLM-события — не наша зона)

TICK ARCHITECTURE (Блок 1):
  - sim_tick: persisted counter (JSON), сколько тиков РЕАЛЬНО обработано
  - НЕ привязан к wall-clock времени — tick ≠ время
  - macro_simulate(): state(t+Δ) = f(state(t), Δ) для долгого отсутствия
  - HOT (RAM): npc_cache, tick_cache — быстрые копии
  - COLD (JSON): world_tick.json, major_npcs.json — персистентное
  - LRU: HOT очищается по TTL (1ч) и лимиту (100 кампаний)
  - Hybrid persistence: JSON пишется раз в N тиков, не каждый
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.services.scene_change import (
    SceneChange,
    ChangeType,
)
from app.domain.movement import MovementIntent, PRIORITY_RANDOM
from app.services.spatial.movement_engine import MovementEngine

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Константы и маппинги
# ──────────────────────────────────────────────────────────────────────────────

from app.core.constants import (
    CAMPAIGN_TTL_SECONDS,
    MACRO_SIM_THRESHOLD_SECONDS,
    MAX_CACHED_CAMPAIGNS,
    MINOR_TICK_INTERVAL,
    RANDOM_EVENT_CHANCE,
    STRESS_RECOVERY_SAFE,
    STRESS_RECOVERY_SLEEPING,
)

# ── Need-driven movement: простой прокси потребностей ──────────────────
# Не зависит от NeedEngine/EconomicProfile — живёт в словаре NPC
# Позже можно заменить на интеграцию с NeedEngine через DTO

# Маппинг: имя потребности → активность в activity_map
_NEED_TO_ACTIVITY: Dict[str, str] = {
    "hunger": "eating",
    "shelter_urge": "resting",
    "social_urge": "socializing",
}

# Порог: если value >= threshold → NPC идёт удовлетворять потребность
_NEED_THRESHOLD: float = 0.7

# Прирост за тик, если активность не удовлетворяет потребность
_NEED_DECAY_PER_TICK: float = 0.05

# Восстановление стресса за тик (см. psyche_engine)
# ── Tick Architecture (Блок 1) ──────────────────────────────────────────────

# Hybrid persistence: сохранять tick в JSON раз в N тиков

# LRU защита для HOT кэша

# Порог для макро-симуляции (в секундах реального времени)

# Fallback для неизвестных NPC
# ADR-0011: Расписание удалено. Движение теперь — следствие социальных потребностей (Social Motility).
# NPC не телепортируются по расписанию. Макро-перемещение (LOD1) только для редких нужд (кухня, выход).
_DEFAULT_ACTIVITY_MAP: dict[str, tuple[str, str, str]] = {}

# ──────────────────────────────────────────────────────────────────────────────
# Случайные события
# Формат: (event_id, описание_для_лога, генератор SceneChange)
# Генератор получает npc dict и возвращает list[SceneChange]
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции времени
# ──────────────────────────────────────────────────────────────────────────────

def _time_to_minutes(time_str: str) -> int:
    """
    Конвертирует строку времени "HH:MM" в минуты от полуночи.
    Возвращает 0 при ошибке парсинга.
    """
    try:
        h, m = map(int, time_str.strip().split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0


def _in_time_range(time_range: str, current_minutes: int) -> bool:
    """
    Проверяет попадает ли current_minutes в диапазон "HH:MM-HH:MM".
    Поддерживает ночные диапазоны пересекающие полночь (22:00-06:00).
    """
    try:
        start_str, end_str = time_range.split("-")
        start = _time_to_minutes(start_str)
        end   = _time_to_minutes(end_str)
        # Ночной диапазон: start > end означает переход через полночь
        if start > end:
            return current_minutes >= start or current_minutes < end
        return start <= current_minutes < end
    except (ValueError, AttributeError):
        return False


def _parse_game_time(scene_state: Optional[dict]) -> str:
    """
    Извлекает текущее игровое время из SceneState.
    Возвращает строку "HH:MM". Fallback: "12:00".
    """
    if not scene_state:
        return "12:00"
    env = scene_state.get("environment", {})
    tod = env.get("time_of_day", "12:00")
    # Нормализуем: "вечер" → "20:00", "ночь" → "02:00" и т.д.
    _verbal_map = {
        "утро":      "08:00",
        "день":      "14:00",
        "вечер":     "20:00",
        "ночь":      "02:00",
        "рассвет":   "06:00",
        "полдень":   "12:00",
        "полночь":   "00:00",
        "рано утром": "07:00",
    }
    if tod in _verbal_map:
        return _verbal_map[tod]
    # Если уже "HH:MM" формат — возвращаем как есть
    return str(tod) if ":" in str(tod) else "12:00"


# ──────────────────────────────────────────────────────────────────────────────
# LifeEngine
# ──────────────────────────────────────────────────────────────────────────────

class LifeEngine:
    """
    Движок жизни NPC — симулирует расписание и случайные события без LLM.

    Использование:
        engine = LifeEngine(data_dir=settings.data_dir)
        
        # При входе игрока — решить как симулировать
        changes = engine.macro_simulate(campaign_id, scene_state)
        # (внутри решает: обычный tick или макро-аппроксимация)
        
        # Или явный одиночный тик
        changes = engine.tick(campaign_id, scene_state)
        
        scene_manager.apply_changes(campaign_id, changes, scene_state)
        engine.save_npcs(campaign_id)

    Tick Architecture:
        - sim_tick: persisted counter, сколько тиков РЕАЛЬНО обработано
        - tick ≠ время: инкрементируется только при реальной обработке
        - macro_simulate(): для долгого отсутствия — state(t+Δ) = f(state(t), Δ)
        - hybrid persistence: JSON пишется раз в TICK_SAVE_INTERVAL тиков
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir  = Path(data_dir or settings.data_dir)
        self.npcs_dir  = self.data_dir / "npcs"
        self.sessions_dir = self.data_dir / "sessions"
        
        # ── HOT кэш (RAM) ──────────────────────────────────────────────────
        # Кэш NPC для быстрого доступа между тиками
        # ключ: campaign_id → list[dict]
        self._npc_cache: dict[str, list] = {}
                
        # LRU tracking для HOT кэша
        # ключ: campaign_id → timestamp последнего доступа
        self._last_access: OrderedDict[str, float] = OrderedDict()
        
        # Фаза 2.2 — in-memory давление NPC (не персистентно, сбрасывается при рестарте)
        # ключ: (campaign_id, npc_id) → float
        self._idle_pressure: dict[tuple[str, str], float] = {}
        
        # TemporalEngine — единая точка времени/decay (перенесено из LifeEngine)
        from app.services.temporal.temporal_engine import TemporalEngine
        self._temporal = TemporalEngine(sessions_dir=self.sessions_dir)
        
        # Слой 2: MovementEngine — конвертирует MovementIntent → SceneChange с {x, y}
        self._movement_engine = MovementEngine()
        
        # Слой 3: SpatialService v1.2 — семантическая навигация (инжекция извне)
        self._spatial_service: Optional[Any] = None

    def set_spatial_service(self, svc: Any) -> None:
        """Инжекция SpatialService для резолва NodeRole вместо хардкода."""
        self._spatial_service = svc
        # Пробрасываем в MovementEngine для A* с учётом оверлея
        if hasattr(self, '_movement_engine') and self._movement_engine:
            self._movement_engine.set_spatial_service(svc)

    # ADR-0010: set_transit_tracker удалён. TransitTracker ампутирован из макро-пайплайна.

    def macro_simulate(
        self,
        campaign_id: str,
        scene_state: Optional[dict] = None,
        runtime_path: Optional[Path] = None,
    ) -> tuple[list[SceneChange], "MovementIntent | None"]:
        """
        Аппроксимация долгого отсутствия игрока.
        
        Вместо: for _ in range(500): tick()
        Делает: state(t+Δ) = f(state(t), Δ)
        
        Что аппроксимирует:
        - Расписание: прыгает к текущему слоту
        - Стресс: нормализуется к baseline
        - События: агрегированная вероятность
        """
        idle_seconds = self.get_idle_seconds(campaign_id)

        if idle_seconds < MACRO_SIM_THRESHOLD_SECONDS:
            # Короткое отсутствие — обычный тик (или несколько)
            return self.tick(campaign_id, scene_state, runtime_path=runtime_path)

        logger.info(
            f"[LIFE_ENGINE] macro_simulate для '{campaign_id}': "
            f"idle={idle_seconds:.0f}s"
        )

        from app.services.npc.npc_loader import load_npcs_merged
        npcs = load_npcs_merged(runtime_path=runtime_path)
        all_changes: list[SceneChange] = []
        current_time = _parse_game_time(scene_state)

        for npc in npcs:
            tier = npc.get("tier", "major")
            npc_id = npc.get("id", "?")

            if tier == "mass":
                continue

            try:
                # 1. Расписание — прыгаем к текущему слоту
                routine_changes, routine_intent = self.update_routine(npc, current_time)
                all_changes.extend(routine_changes)
                # 2. Стресс — нормализация к baseline
                psyche = npc.setdefault("psyche", {})
                current_stress = psyche.get("stress", 0)
                if current_stress > 20:
                    # Долгое отсутствие → стресс снижается к baseline
                    # Формула: stress = baseline + (current - baseline) * decay
                    baseline = 10  # нормальный фоновый стресс
                    decay = 0.3    # за долгое отсутствие сбросить на 70%
                    psyche["stress"] = round(baseline + (current_stress - baseline) * decay)

                # 3. Агрегированные события — вероятность * время
                # 5% за тик, но мы не считаем тики — используем эвристику
                if tier == "major" and random.random() < 0.4:  # 40% шанс за долгий idle
                    event_changes = self.check_random_events(npc, self.get_current_tick(campaign_id))
                    all_changes.extend(event_changes)

            except Exception as e:
                logger.error(f"[LIFE_ENGINE] macro_simulate error for '{npc_id}': {e}")

        # Обновляем кэш и tick
        self._npc_cache[campaign_id] = npcs
        self._increment_tick(campaign_id)  # Один тик за всю макро-симуляцию

        logger.info(
            f"[LIFE_ENGINE] macro_simulate завершена: "
            f"{len(all_changes)} changes"
        )
        return all_changes, [] # ADR-049: macro_simulate не генерирует intents (только tick)

    # ─────────────────────────────────────────────────────────────────────────
    # LRU защита для HOT кэша
    # ─────────────────────────────────────────────────────────────────────────

    def _touch(self, campaign_id: str) -> None:
        """Обновляет время последнего доступа (LRU)."""
        self._last_access[campaign_id] = time.time()
        self._last_access.move_to_end(campaign_id)

    def _evict_stale(self) -> list[str]:
        """
        Вызывает очистку неактивных кампаний.
        Удаляет: (1) просроченные по TTL, (2) лишние по LRU.
        Возвращает список evicted campaign_id.
        """
        now = time.time()
        evicted = []
        
        # Слой 1: TTL eviction
        stale = [
            cid for cid, ts in self._last_access.items()
            if now - ts > CAMPAIGN_TTL_SECONDS
        ]
        for cid in stale:
            self.cleanup_campaign(cid)
            evicted.append(f"{cid}(TTL)")
        
        # Слой 2: LRU eviction (если всё ещё слишком много)
        while len(self._last_access) > MAX_CACHED_CAMPAIGNS:
            oldest_cid, _ = self._last_access.popitem(last=False)
            self.cleanup_campaign(oldest_cid)
            evicted.append(f"{oldest_cid}(LRU)")
        
        if evicted:
            logger.debug(f"[LIFE_ENGINE] evicted: {evicted}")
        return evicted

    def cleanup_campaign(self, campaign_id: str) -> None:
        """
        Очистка HOT кэша + flush tick перед удалением.
        COLD storage (JSON) сохраняется, но не удаляется.
        """
        self.flush_ticks(campaign_id)
        self._npc_cache.pop(campaign_id, None)
        self._temporal.cleanup_campaign(campaign_id)
        self._last_access.pop(campaign_id, None)

    def cleanup_all_campaigns(self) -> int:
        """
        Очистка всего HOT + flush всех ticks.
        COLD storage (JSON) сохраняется, но не удаляется.
        """
        self.flush_ticks()  # Сначала сохраняем
        count = len(self._npc_cache)
        self._npc_cache.clear()
        self._temporal.cleanup_all()
        self._last_access.clear()
        logger.info(f"[LIFE_ENGINE] cleared all HOT cache: {count} campaigns")
        return count

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────────

    def reconcile_state(self, campaign_id: str, elapsed_seconds: float) -> None:
        """
        ADR-047: Аналитическое согласование состояния при загрузке сцены.
        Без ретро-симуляции (TICK_CATCHUP убит). Применяет экспоненциальный декэй 
        стресса и рост базовых потребностей пропорционально elapsed_seconds.
        """
        if elapsed_seconds <= 0:
            return
            
        npcs = self._npc_cache.get(campaign_id, [])
        # Предполагаем 1 тик = 10 секунд (GAME_TICK_INTERVAL_SECONDS)
        ticks_equivalent = elapsed_seconds / 10.0
        
        for npc in npcs:
            psyche = npc.get("psyche", {})
            body_state = npc.get("body_state", {})
            
            # 1. Стресс: экспоненциальный декэй к базовой линии
            current_stress = psyche.get("stress", 0)
            if current_stress > 0:
                baseline = 0.0
                decay_rate = 0.05  # Примерно 5% восстановления за тик
                # Формула: S_t = baseline + (S_0 - baseline) * (1 - decay_rate)^T
                decayed_stress = baseline + (current_stress - baseline) * ((1 - decay_rate) ** ticks_equivalent)
                psyche["stress"] = max(0.0, round(decayed_stress, 2))
                
            # 2. Голод и Усталость: линейный рост (если были в пути)
            hunger_rate = 0.1  # условных единиц за тик
            fatigue_rate = 0.1
            
            if "hunger" in body_state:
                body_state["hunger"] = min(100.0, body_state.get("hunger", 0.0) + hunger_rate * ticks_equivalent)
            if "fatigue" in body_state:
                body_state["fatigue"] = min(100.0, body_state.get("fatigue", 0.0) + fatigue_rate * ticks_equivalent)

        logger.info(f"[LIFE_ENGINE] Аналитическое согласование для '{campaign_id}': {elapsed_seconds:.1f}s ({ticks_equivalent:.1f} тиков)")

    def tick(
        self,
        campaign_id: str,
        scene_state: Optional[dict] = None,
        runtime_path: Optional[Path] = None,
    ) -> tuple[list[SceneChange], "MovementIntent | None"]:
        """
        Главная точка входа — один тик движка жизни.

        Обрабатывает всех NPC:
          - обновляет позицию по расписанию
          - need-driven movement при критических потребностях
          - восстанавливает стресс
          - с 5% шансом генерирует случайное событие

        Возвращает list[SceneChange] для применения через apply_changes().
        """
        from app.services.npc.npc_loader import load_npcs_merged

        # LRU: автоочистка перед доступом
        self._evict_stale()
        self._touch(campaign_id)

        # Tick: инкремент с персистенцией
        current_tick = self._increment_tick(campaign_id)
        current_time = _parse_game_time(scene_state)

        logger.info(
            f"[LIFE_ENGINE] Тик #{current_tick} для '{campaign_id}' "
            f"(время: {current_time})"
        )

        # Используем кэшированных NPC если есть, иначе загружаем с диска
        npcs = self._npc_cache.get(campaign_id) or load_npcs_merged(runtime_path=runtime_path)
        all_changes: list[SceneChange] = []
        all_intents: list[MovementIntent] = [] # ADR-049: Сборка намерений
        npcs_updated = False

        for npc in npcs:
            tier   = npc.get("tier", "major")
            npc_id = npc.get("id", "?")

            try:
                # ── MAJOR: полная симуляция каждый тик ──────────────────────
                if tier == "major":
                    changes, intents = self._simulate_major(npc, current_time, current_tick)
                    all_changes.extend(changes)
                    all_intents.extend(intents)
                    npcs_updated = True

                elif tier == "minor":
                    last_minor = npc.get("routine", {}).get("_last_life_tick", 0)
                    if (current_tick - last_minor) >= MINOR_TICK_INTERVAL:
                        changes, intents = self._simulate_minor(npc, current_time, current_tick)
                        all_changes.extend(changes)
                        all_intents.extend(intents)
                        npc.setdefault("routine", {})["_last_life_tick"] = current_tick
                        npcs_updated = True

            except Exception as e:
                logger.error(f"[LIFE_ENGINE] Ошибка при обработке NPC '{npc_id}': {e}")

        # Кэш уже обновлён in-place (NPC — словари, изменения применились)
        if npcs_updated:
            self._npc_cache[campaign_id] = npcs

        logger.info(
            f"[LIFE_ENGINE] Тик #{current_tick} завершён: "
            f"{len(all_changes)} SceneChange, {len(all_intents)} MovementIntent"
        )
        return all_changes, all_intents # ADR-049: Возвращаем намерения в оркестратор

    def tick_decisions(
        self,   
        campaign_id: str,
        scene_state: dict,
        topics: Optional[dict[str, str]] = None,
        identities: Optional[dict[str, dict[str, float]]] = None,
    ) -> tuple[list[dict], list, list]:
        """
        Фаза 5 — DecisionHub для NPC в idle tick.
        Чистая математика, без LLM.
        
        Читает NPC из кэша (после Phase 0), НЕ с диска (Устав §3.1).
        
        Returns:
            (decision_dicts, communication_intents):
            - decision_dicts: список dicts для триггера телеграфа на клиенте.
              Формат совместим с significant_events в routes.py.
            - communication_intents: CommunicationIntent для EventBus (Фаза 6).
        """
        from app.core.constants import (
            IDLE_DECISION_SCORE_THRESHOLD,
            IDLE_PRESSURE_ACCUM_RATE,
            IDLE_PRESSURE_DECAY_RATE,
        )
        from app.services.npc.decision_hub import DecisionHub, EventContext
        from app.services.npc.npc_loader import (
            load_profile_from_legacy_json,
            load_l2_state_from_runtime_dict,
        )
        from app.services.events.event_types import EventType
        from app.models.npc_state import NPCIdentityL1, WillState, compute_drive_modifiers
        from app.domain.decision_context import DecisionContext
        from app.services.cfrm.pressure_translator import translate_kernel_to_context
        from app.services.npc.interpretation_engine import InterpretationEngine
        from app.domain.communication import CommunicationIntent

        # Читаем из кэша — после Phase 0 там уже мутации (Устав §3.1)
        npcs = self._npc_cache.get(campaign_id)
        if not npcs:
            logger.error(
                f"[LIFE_ENGINE] tick_decisions: кэш пуст для '{campaign_id}'. "
                "Phase 0 (tick) не была вызвана перед Phase 5?"
            )
            return [], [], [] # ADR-049: Всегда возвращаем кортеж (decisions, comms, movements)        # Читаем из кэша — после Phase 0 там уже мутации (Устав §3.1)
        npcs = self._npc_cache.get(campaign_id)
        if not npcs:
            logger.error(
                f"[LIFE_ENGINE] tick_decisions: кэш пуст для '{campaign_id}'. "
                "Phase 0 (tick) не была вызвана перед Phase 5?"
            )
            return [], [], [] # ADR-049: Всегда возвращаем кортеж (decisions, comms, movements)
        logger.warning(f"[TICK_DECISIONS] cache_hit: {len(npcs)} NPCs for '{campaign_id}'")
        hub = DecisionHub()
        decisions: list[dict] = []
        communication_intents: list[CommunicationIntent] = []
        movement_intents: list[MovementIntent] = []
        logger.info(f"[TICK_DECISIONS] start: {len(npcs)} NPCs")

        for npc in npcs:
            npc_id = npc.get("id", "?")

            try:
                state_l2 = load_l2_state_from_runtime_dict(npc)
                profile_l0 = load_profile_from_legacy_json(npc)

                # Пропускаем мёртвых/сломанных
                if state_l2.hp <= 0:
                    continue
                if state_l2.will_state == WillState.BROKEN:
                    continue

                # ДОЛГ 2 FIX: idle tick = мир тикает проактивно (WORLD_TICK).
                # EventType.IDLE убивал все proactive-интенты, давление
                # никогда не накапливалось, 0 решений за 14 тиков.
                event = EventContext(
                    event_type=EventType.WORLD_TICK,
                    actor_id=npc_id,
                    success=True,
                    intensity=0.2,
                    distance=0.0,
                    witness_count=0,
                    location=scene_state.get("location_id", ""),
                    scene_flags=set(scene_state.get("active_flags", [])),
                    scene_facts=[],
                )

                # Когнитивные искажения — idle NPC подвержены накопленным bias (Устав §3.1)
                interpretation = InterpretationEngine().compute(
                    state=state_l2, event=event, drives_base=profile_l0.drives_base
                )

                # Drive modifiers из temporary_drives
                _drive_mods = None
                if state_l2.temporary_drives:
                    _drive_mods = compute_drive_modifiers(state_l2.temporary_drives)

                # Identity L1 — кристаллизованные черты личности
                _identity = None
                if identities and npc_id in identities:
                    _identity = NPCIdentityL1(
                        npc_id=npc_id,
                        active_traits=identities[npc_id],
                    )

                # Каузальное замыкание: консолидированное восприятие T-1 деформирует пространство решений.
                # Логика проекции вынесена в pressure_translator (устранение дублирования Устав §10).
                # GAP3 FIX: Передаем body_state для соматического вето
                _body = getattr(state_l2, 'body_state', None)
                _kernel = getattr(state_l2, 'perceptual_kernel', None)
                _decision_ctx = translate_kernel_to_context(_kernel, body_state=_body) if _kernel else None

                result = hub.compute(
                    state=state_l2,
                    personality=profile_l0,
                    event=event,
                    scene_state=scene_state,
                    identity=_identity,
                    eco_modifiers=interpretation.score_modifiers or None,
                    social_modifiers=None,
                    reputation_modifiers=None,
                    drive_modifiers=_drive_mods,
                    reflex_constraints=None,
                    topic=topics.get(npc_id) if topics else None,
                    decision_ctx=_decision_ctx,
                )

                # Фаза 2.2 — накопление давления (in-memory)
                _key = (campaign_id, npc_id)
                _current_pressure = self._idle_pressure.get(_key, 0.0)
                
                _pressure_delta = 0.0
                _intent_val = result.intent.value if result.intent else "none"
                if result.intent and _intent_val != "idle":
                    # Накапливаем score как давление (медленно)
                    _pressure_delta = result.score * IDLE_PRESSURE_ACCUM_RATE
                else:
                    # Decay — давление спадает если нет стимула
                    _pressure_delta = -_current_pressure * IDLE_PRESSURE_DECAY_RATE
                
                _new_pressure = max(0.0, min(1.0, _current_pressure + _pressure_delta))
                self._idle_pressure[_key] = _new_pressure
                
                # Извлекаем CommunicationIntent для Фазы 6 (Устав §3.3)
                if result.communication is not None:
                    communication_intents.append(result.communication)

                # Каузальный мост: невербальные пространственные решения → MovementIntent
                if result.intent and result.intent.value in ("APPROACH", "FLEE"):
                    # В idle-пути (WORLD_TICK) intent_target == npc_id — нет смысла подходить к себе.
                    # Fallback: approach/flee к игроку как основному социальному объекту.
                    _move_target = result.intent_target if result.intent_target and result.intent_target != npc_id else "player"
                    _target_pos = scene_state.get("npc_positions", {}).get(_move_target, {})
                    _target_node = _target_pos.get("position", "")
                    if result.intent.value == "APPROACH" and _target_node:
                        movement_intents.append(MovementIntent(
                            npc_id=npc_id,
                            target_node_id=_target_node,
                            reason=f"decision:approach_target={_move_target}",
                            priority=0.7,
                        ))
                        logger.warning(f"[CAUSAL_BRIDGE] APPROACH: npc={npc_id} → target={_move_target} node={_target_node}")
                    elif result.intent.value == "FLEE":
                        # FLEE: ищем позицию NPC и узел, ближайший к нему, но не к угрозе
                        _npc_pos = scene_state.get("npc_positions", {}).get(npc_id, {})
                        _npc_node = _npc_pos.get("position", "")
                        if _npc_node:
                            movement_intents.append(MovementIntent(
                                npc_id=npc_id,
                                target_node_id=_npc_node,
                                reason=f"decision:flee_stay={_move_target}",
                                priority=1.0,
                            ))
                            logger.warning(f"[CAUSAL_BRIDGE] FLEE: npc={npc_id} stays at {_npc_node} (flee from {_move_target})")
                        else:
                            logger.warning(f"[CAUSAL_BRIDGE] FLEE BLOCKED: npc={npc_id} has no position node")
                    elif result.intent.value == "APPROACH" and not _target_node:
                        logger.warning(f"[CAUSAL_BRIDGE] APPROACH BLOCKED: npc={npc_id} target={_move_target} has no position (entry={list(_target_pos.keys()) if _target_pos else 'EMPTY'})")

                # Триггер когда давление накопилось
                if _new_pressure >= IDLE_DECISION_SCORE_THRESHOLD:
                    decisions.append({
                        "npc_id": npc_id,
                        "cause": "idle_pressure",
                        "type": "proactive",
                        "target": npc_id,
                        "field": "intent",
                        "value": f"{result.intent.value if result.intent else 'observe'}",
                        "intent_target": result.intent_target,
                        "topic": topics.get(npc_id, "наблюдение") if topics else "наблюдение",
                    })
                    # Сброс давления после триггера
                    self._idle_pressure[_key] = 0.0

            except Exception as e:
                import traceback
                logger.warning(f"[LIFE_ENGINE] Idle decision error for {npc_id}: {e}\n{traceback.format_exc()}")
                logger.error(f"[TICK_DECISIONS] error: {npc_id} → {e}")
                print(traceback.format_exc())
                continue

        logger.info(f"[TICK_DECISIONS] end: {len(decisions)} decisions, {len(communication_intents)} comms, {len(movement_intents)} movements")
        return decisions, communication_intents, movement_intents

    def save_npcs(self, campaign_id: str) -> None:
        """
        Сохраняет обновлённые NPC обратно в major_npcs.json.
        Вызывается после apply_changes() в orchestrator.
        """
        npcs = self._npc_cache.get(campaign_id)
        if not npcs:
            return
        path = self._npcs_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(
                json.dumps(npcs, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.debug(f"[LIFE_ENGINE] NPC сохранены: {path}")
        except OSError as e:
            logger.error(f"[LIFE_ENGINE] Ошибка сохранения NPC: {e}")

    def get_activity_description(self, npc: dict) -> str:
        """
        Возвращает читаемое описание текущей активности NPC.
        Используется DM для описания сцены и LifeEngine для логов.

        Пример: "Торнин стоит за стойкой, протирает кружки"
        """
        name = npc.get("name", npc.get("id", "NPC"))
        activity = npc.get("routine", {}).get("current", "")
        location = npc.get("location", "")

        _activity_phrases = {
            "sleeping":         "спит",
            "cleaning_tables":  "протирает столы",
            "serving_tables":   "разносит еду и напитки",
            "guarding_gate":    "несёт стражу у ворот",
            "haggling":         "торгуется с покупателями",
            "observing":        "наблюдает за посетителями",
            "resting":          "отдыхает",
            "eating":           "ест",
            "drinking":         "пьёт",
            "working":          "работает",
            "on_duty":          "на дежурстве",
            "off_duty":         "отдыхает после смены",
            "talking_at_bar":   "разговаривает у стойки",
            "hiding":           "прячется в тени",
        }
        phrase = _activity_phrases.get(activity, activity or "находится здесь")
        return f"{name} {phrase}"

    # ─────────────────────────────────────────────────────────────────────────
    # Tick management (persistent)
    # ─────────────────────────────────────────────────────────────────────────

    def _increment_tick(self, campaign_id: str) -> int:
        """
        Делегирует инкремент тика в TemporalEngine.
        Возвращает новый tick.
        """
        ctx = self._temporal.advance_tick(campaign_id)
        return ctx.current_tick

    def flush_ticks(self, campaign_id: Optional[str] = None) -> None:
        """Делегирует принудительную запись tick(s) в TemporalEngine."""
        self._temporal.flush_ticks(campaign_id)

    def get_current_tick(self, campaign_id: str) -> int:
        """Делегирует чтение текущего тика в TemporalEngine."""
        return self._temporal.get_current_tick(campaign_id)

    def get_temporal_context(self, campaign_id: str):
        """Возвращает TemporalContext для подсистем, которым нужно больше чем просто тик."""
        return self._temporal.get_temporal_context(campaign_id)

    def get_idle_seconds(self, campaign_id: str) -> float:
        """Делегирует в TemporalEngine."""
        return self._temporal.get_idle_seconds(campaign_id)

    def get_world_ticks_elapsed(self, campaign_id: str) -> int:
        """Делегирует в TemporalEngine."""
        return self._temporal.get_world_ticks_elapsed(campaign_id)

    def mark_decay_executed(self, campaign_id: str) -> None:
        """Фиксирует, что memory decay был запущен на текущем тике."""
        self._temporal.mark_decay_executed(campaign_id)

    def invalidate_cache(self, campaign_id: str) -> None:
        """
        Сбрасывает HOT кэш NPC для campaign_id.
        Вызвать если major_npcs.json был изменён извне (например, SandboxHandler).
        """
        self._npc_cache.pop(campaign_id, None)
        self._temporal.invalidate_cache(campaign_id)

    # ─────────────────────────────────────────────────────────────────────────
    # Внутренние методы загрузки NPC
    # ─────────────────────────────────────────────────────────────────────────

    def _npcs_file(self) -> Path:
        """Путь к файлу NPC (для совместимости с legacy кодом)."""
        return self.npcs_dir / "major_npcs.json"

    def _load_npcs(self, campaign_id: str) -> list:
        """
        Загружает NPC из кэша или файла.
        Для campaign-specific файлов путь: sessions/{campaign_id}/major_npcs.json
        """
        # HOT cache hit
        if campaign_id in self._npc_cache:
            return self._npc_cache[campaign_id]

        # COLD storage: campaign-specific файл
        campaign_file = self.sessions_dir / campaign_id / "major_npcs.json"
        if campaign_file.exists():
            try:
                return self._extracted_from__load_npcs_14(campaign_file, campaign_id)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[LIFE_ENGINE] Ошибка чтения campaign NPC: {e}")

        # Fallback: глобальный файл
        global_file = self._npcs_file()
        if global_file.exists():
            try:
                return self._extracted_from__load_npcs_14(global_file, campaign_id)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[LIFE_ENGINE] Ошибка чтения global NPC: {e}")

        return []

    # TODO Rename this here and in `_load_npcs`
    def _extracted_from__load_npcs_14(self, arg0, campaign_id):
        npcs = json.loads(arg0.read_text(encoding="utf-8"))
        self._npc_cache[campaign_id] = npcs
        return npcs

    def get_npc_states(self, campaign_id: str) -> list[dict]:
        """Возвращает кэшированные NPC states после мутации в tick().
        
        Вызывать ТОЛЬКО после tick() в рамках одного тика.
        Если кэш пуст — значит tick() не была вызвана, возвращаем [].
        """
        if cached := self._npc_cache.get(campaign_id):
            return list(cached)
        logger.warning(
            f"[LIFE_ENGINE] get_npc_states: кэш пуст для '{campaign_id}'. "
            "tick() не была вызвана перед этим?"
        )
        return []  # БАГ G FIX: get_npc_states возвращает list[dict], не tuple  

    # ─────────────────────────────────────────────────────────────────────────
    # Симуляция по тирам
    # ─────────────────────────────────────────────────────────────────────────

    def _make_random_events(self, npc: dict, tick: int) -> list:
        """Таблица случайных событий для Major NPC.
        
        5% шанс одного события за тик.
        Возвращает список (event_id, changes, intent_or_none).
        """
        npc_id   = npc.get("id", "unknown")
        location = npc.get("location", "tavern_silver_wolf")

        # Резолвим BAR узел через SpatialService v1.2, fallback на хардкод
        bar_target = "bar_area"  # @deprecated: fallback
        if self._spatial_service:
            from app.models.spatial_contracts import NodeRole
            if bar_ref := self._spatial_service.resolve_node(
                role=NodeRole.BAR,
                origin_zone=location,
            ):
                # MovementEngine ожидает legacy-ID, денормализуем
                bar_target = self._spatial_service.denormalize_id(bar_ref.node_id)

        events = [
            # NPC переходит к стойке поговорить с кем-то
            ("wanders_to_bar", [
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="activity",
                    value="talking_at_bar",
                    cause="life_engine_random",
                    tick=tick,
                ),
            ], MovementIntent(
                npc_id=npc_id,
                target_node_id=bar_target,
                from_node_id=npc.get("position", ""),
                location_id=location,
                reason="random:wanders_to_bar",
                priority=PRIORITY_RANDOM,
            )),
            # NPC становится более бдительным (заметил что-то)
            ("notices_something", [
                SceneChange(
                    type=ChangeType.NPC_STATE,
                    target=npc_id,
                    field="psyche_state",
                    value="alert",
                    cause="life_engine_random",
                    tick=tick,
                ),
            ], None),
            # Небольшой стресс — ссора с кем-то
            ("minor_argument", [
                SceneChange(
                    type=ChangeType.NPC_STATE,
                    target=npc_id,
                    field="stress_delta",
                    value=10,
                    cause="life_engine_argument",
                    tick=tick,
                ),
            ], None),
            # NPC на мгновение выходит (в туалет, за товаром, на улицу)
            ("brief_exit", [
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="visible",
                    value=False,
                    cause="life_engine_random",
                    tick=tick,
                ),
            ], None),
        ]
        # Событие wanders_to_bar только в таверне — иначе MovementEngine не найдёт узел
        if location != "tavern_silver_wolf":
            events = [e for e in events if e[0] != "wanders_to_bar"]
        return events

    def _simulate_major(
          self,
          npc: dict,
          current_time: str,
          tick: int,
      ) -> tuple[list[SceneChange], list["MovementIntent"]]:
        """
          Полная симуляция Major NPC за один тик.
          Порядок: need-driven → расписание → стресс → случайные события.
          Need-driven имеет приоритет: если потребность критична — schedule пропускается.
          ADR-049: Возвращает list[MovementIntent] вместо прямого исполнения.
          """
        # ADR-052: Cognitive Override Guard. Паралич воли блокирует любую активность.
        _kernel = npc.get("perceptual_kernel")
        _init_sup = _kernel.get("initiative_suppression", 0.0) if isinstance(_kernel, dict) else getattr(_kernel, "initiative_suppression", 0.0) if _kernel else 0.0
        _recent_dir = _kernel.get("recent_directive") if isinstance(_kernel, dict) else getattr(_kernel, "recent_directive", None) if _kernel else None
        if _init_sup > 0.7:
            npc_id = npc.get("id", "unknown")
            logger.debug(f"[LIFE_ENGINE] {npc_id}: Major cycle bypassed due to initiative_suppression={_init_sup:.2f}")
            return [], []

        changes: list[SceneChange] = []
        intents: list[MovementIntent] = []

        # ── D6: сбор всех intent-ов с приоритетами ──
        candidates: list[MovementIntent] = []

        # 1. Need-driven: растём потребности, проверяем порог
        self._tick_needs(npc)
        if need_intent := self._check_need_driven_movement(npc):
            candidates.append(need_intent)

        # 2. Расписание (всегда генерирует, но может быть None)
        routine_changes, routine_intent = self.update_routine(npc, current_time, tick)
        changes.extend(routine_changes)
        if routine_intent:
            candidates.append(routine_intent)

        # 3. Случайные события (5% шанс) — могут породить intent
        event_changes, event_intent = self.check_random_events(npc, tick)
        changes.extend(event_changes)
        if event_intent:
            candidates.append(event_intent)

        # 4. Восстанавливаем стресс (без SceneChange — только данные NPC)
        self.recover_stress_tick(npc)

        # ── D6: выбираем лучший intent по priority ──
        if candidates:
            candidates.sort(key=lambda i: i.priority, reverse=True)
            winner = candidates[0]
            # ADR-049: LifeEngine больше не диктатор. Он не исполняет намерения сам.
            # Намерение передается в TickOrchestrator для прохождения каузального конвейера.
            logger.info(f"[PIPELINE][MOVEMENT][INTENT_SCHEDULE] npc={winner.npc_id} target={winner.target_node_id} reason={winner.reason}")
            intents.append(winner)
            # Обновляем activity в scene_state
            if winner.reason.startswith("need_driven:"):
                if target_activity := _NEED_TO_ACTIVITY.get(
                    winner.reason.split(":")[1].split("=")[0], ""
                ):
                    activity_entry = npc.get("activity_map", {}).get(target_activity, {})
                    changes.append(SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=winner.npc_id,
                        field="activity",
                        value=activity_entry.get("display", target_activity),
                        cause=f"life_engine_need_driven:{winner.reason}",
                        tick=tick,
                    ))
            logger.debug(
                f"[LIFE_ENGINE] {npc.get('id', '?')}: "
                f"{len(candidates)} intents, winner={winner.reason} (p={winner.priority})"
            )

        return changes, intents

    # ─────────────────────────────────────────────────────────────────────
    # Need-driven movement — перемещение по потребностям
    # ─────────────────────────────────────────────────────────────────────

    def _ensure_needs_state(self, npc: dict) -> dict:
        """Инициализирует словарь потребностей в NPC dict.
        Дополняет недостающие ключи если dict уже существует.
        """
        if "needs" not in npc:
            npc["needs"] = {}
        needs = npc["needs"]
        # Гарантируем что все потребности из маппинга присутствуют
        for need_name in _NEED_TO_ACTIVITY:
            if need_name not in needs:
                needs[need_name] = 0.0
        return needs

    def _tick_needs(self, npc: dict) -> None:
        """
        Увеличивает потребности за тик.
        Если текущая активность удовлетворяет потребность — сбрасываем.
        """
        needs = self._ensure_needs_state(npc)
        current_activity = npc.get("routine", {}).get("current", "")

        for need_name, activity_name in _NEED_TO_ACTIVITY.items():
            if activity_name in current_activity:
                # NPC удовлетворяет потребность — сбрасываем
                needs[need_name] = 0.0
            else:
                # Потребность растёт
                needs[need_name] = min(1.0, needs[need_name] + _NEED_DECAY_PER_TICK)

    def _check_need_driven_movement(
        self,
        npc: dict,
    ) -> Optional[MovementIntent]:
        """
        Если потребность выше порога — возвращает MovementIntent.
        Приоритет: самая критичная потребность.
        Конвертация в SceneChange — ответственность MovementEngine (Слой 2).
        """
        needs = npc.get("needs", {})
        if not needs:
            return None

        activity_map = npc.get("activity_map", {})
        npc_id = npc.get("id", "unknown")
        current_position = npc.get("position", "")

        # Находим самую критичную потребность
        urgent_needs = [
            (name, val) for name, val in needs.items()
            if val >= _NEED_THRESHOLD
        ]

        if not urgent_needs:
            return None

        # Самая срочная первой
        urgent_needs.sort(key=lambda x: x[1], reverse=True)
        need_name, need_value = urgent_needs[0]

        target_activity = _NEED_TO_ACTIVITY.get(need_name)
        if not target_activity:
            return None

        target_entry = activity_map.get(target_activity)
        if not target_entry:
            return None

        target_node = target_entry.get("position", "")
        target_location = target_entry.get("location", "")

        # Не двигаемся если уже на целевом узле
        if current_position == target_node:
            return None

        logger.info(
            f"[LIFE_ENGINE] Need-driven: {npc_id} → {target_activity} "
            f"(need={need_name}={need_value:.2f})"
        )

        # ADR-049: Запрещена прямая мутация позиции. LifeEngine — генератор намерений, не диктатор.
        # Движение реализуется через MovementIntent → MovementEngine → TraversalState.
        # npc["position"] = target_node
        # if target_location:
        #     npc["location"] = target_location
        npc.get("routine", {})["current"] = target_activity

        from app.domain.movement import PRIORITY_NEEDS
        # ADR-0010: movement_mode удалён. Макро-перемещение — Semantic Relocation.
        return MovementIntent(
            npc_id=npc_id,
            target_node_id=target_node,
            from_node_id=npc.get("position", ""),
            location_id=target_location,
            reason=f"need_driven:{need_name}={need_value:.2f}",
            priority=PRIORITY_NEEDS,
        )

    def _simulate_minor(
          self,
          npc: dict,
          current_time: str,
          tick: int,
      ) -> tuple[list[SceneChange], list["MovementIntent"]]:
          """
          Симуляция Minor NPC раз в MINOR_TICK_INTERVAL тиков.
          Только расписание + случайные события (без полного стресс-расчёта).
          ADR-049: Возвращает list[MovementIntent] вместо прямого исполнения.
          """
          changes: list[SceneChange] = []
          intents: list[MovementIntent] = []
          
          routine_changes, routine_intent = self.update_routine(npc, current_time, tick)
          changes.extend(routine_changes)
          if routine_intent:
              intents.append(routine_intent)
              
          event_changes, event_intent = self.check_random_events(npc, tick)
          changes.extend(event_changes)
          if event_intent:
              intents.append(event_intent)
              
          return changes, intents

    # ─────────────────────────────────────────────────────────────────────────
    # update_routine — обновление по расписанию
    # ─────────────────────────────────────────────────────────────────────────

    def update_routine(
        self,
        npc: dict,
        current_time: str,
        tick: int = 0,
    ) -> tuple[list[SceneChange], "MovementIntent | None"]:
        """
        Обновляет позицию NPC согласно расписанию и текущему времени.

        Алгоритм:
          1. Определяет текущую активность из routine.schedule
          2. Сравнивает с предыдущей (routine.current)
          3. Если изменилась → обновляет npc dict и генерирует SceneChange

        SceneChange:
          - NPC_POSITION.location  — если NPC перешёл в другую локацию
          - NPC_POSITION.position  — позиция внутри сцены
          - NPC_POSITION.activity  — текущая деятельность

        Возвращает пустой список если активность не изменилась.
        """
        npc_id   = npc.get("id", "unknown")
        schedule = npc.get("routine", {}).get("schedule", {})

        if not schedule:
            return [], None

        # ADR-052: Cognitive Override Guard. Расписание игнорируется при параличе воли.
        # NPC не идет спать или на работу, если инициатива подавлена давлением (initiative_suppression > 0.7).
        _kernel = npc.get("perceptual_kernel")
        _recent_dir = _kernel.get("recent_directive") if isinstance(_kernel, dict) else getattr(_kernel, "recent_directive", None) if _kernel else None
        if _recent_dir and _recent_dir.get("interrupts_routine"):
            logger.debug(f"[LIFE_ENGINE] {npc_id}: Schedule bypassed due to Attention Capture from {_recent_dir.get('source')}")
            # GAP9 FIX: Не сжигаем директиву мгновенно! Иначе на следующем тике LifeEngine снова уложит NPC спать,
            # перезаписав реактивный транзит (reactive:approach). Сон прерывается до снижения угрозы.
            return [], None

        # ADR-081: Physical Urgency Wake. Угроза пробуждает NPC из сна.
        # Скалярная оценка: если угроза рядом и велика — расписание ломается.
        _threat = _kernel.get("threat_gradient", 0.0) if isinstance(_kernel, dict) else getattr(_kernel, "threat_gradient", 0.0) if _kernel else 0.0
        if _threat > 0.7:
            logger.debug(f"[LIFE_ENGINE] {npc_id}: Schedule bypassed due to proximate physical threat ({_threat:.2f})")
            return [], None

        new_activity = self._get_current_activity(schedule, current_time)
        if not new_activity:
            return [], None

        prev_activity = npc.get("routine", {}).get("current", "")

        if new_activity == prev_activity:
            return [], None

        # GAP9 FIX: Реалистичное Пробуждение. Если NPC напуган или в стрессе, он не может уснуть.
        # Угроза (threat_gradient) и стресс — непрерывные скаляры, в отличие от сгорающей директивы.
        if "sleeping" in new_activity or "resting" in new_activity:
            _threat = _kernel.get("threat_gradient", 0.0) if isinstance(_kernel, dict) else getattr(_kernel, 'threat_gradient', 0.0) if _kernel else 0.0
            _stress = npc.get("stress", 0.0)
            if _threat > 0.3 or _stress > 50:
                logger.debug(f"[LIFE_ENGINE] {npc_id}: Sleep bypassed — threat={_threat:.2f}, stress={_stress}")
                return [], None

        new_location, new_position, activity_display = self._resolve_position(
            npc, new_activity
        )

        prev_location = npc.get("location", new_location)
        changes: list[SceneChange] = [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="activity",
                value=activity_display,
                cause="life_engine_schedule",
                tick=tick,
            )
        ]

        going_to_sleep = "sleeping" in new_activity or "resting" in new_activity
        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="visible",
            value=not going_to_sleep,
            cause="life_engine_schedule",
            tick=tick,
        ))

        # ADR-049: Запрещена генерация SceneChange для смены location.
        # Смена локации — физический процесс, реализуемый через MovementIntent → TraversalState.
        # if new_location != prev_location:
        #     changes.append(SceneChange(
        #         type=ChangeType.NPC_POSITION,
        #         target=npc_id,
        #         field="location",
        #         value=new_location,
        #         cause="life_engine_schedule",
        #         tick=tick,
        #     ))
        #     logger.info(
        #         f"[LIFE_ENGINE] {npc_id}: {prev_location} → {new_location} "
        #         f"(активность: {prev_activity} → {new_activity})"
        #     )

        # ── MovementIntent для MovementEngine (Слой 2) ────────────────────
        from app.domain.movement import PRIORITY_SCHEDULE
        # ADR-0010: movement_mode удалён. Макро-перемещение — Semantic Relocation.
        intent = MovementIntent(
            npc_id=npc_id,
            target_node_id=new_position,
            from_node_id=npc.get("position", ""),
            location_id=new_location,
            reason=f"schedule:{new_activity}",
            priority=PRIORITY_SCHEDULE,
        )

        # ── Обновляем NPC dict в памяти ────────────────────────────────────
        routine = npc.setdefault("routine", {})
        routine["current"]   = new_activity
        routine["mood"]      = self._mood_for_activity(new_activity)
        if "interrupted" not in routine:
            routine["interrupted"] = False
        # ADR-049: Запрещена прямая мутация пространства из расписания.
        # NPC принял решение сменить активность (когнитивный слой), 
        # но физическое перемещение к новой локации — задача MovementEngine.
        # npc["location"] = new_location
        # npc["position"] = new_position

        logger.debug(
            f"[LIFE_ENGINE] {npc_id}: активность {prev_activity!r} → {new_activity!r} "
            f"в {current_time}"
        )
        return changes, intent

    def _get_current_activity(self, schedule: dict, current_time: str) -> str:
        """
        Определяет текущую активность NPC по расписанию и времени.
        Возвращает строку активности или '' если ничего не совпало.

        schedule: {"06:00-22:00": "working", "22:00-06:00": "sleeping"}
        """
        current_minutes = _time_to_minutes(current_time)
        return next(
            (
                activity
                for time_range, activity in schedule.items()
                if _in_time_range(time_range, current_minutes)
            ),
            "",
        )

    def _resolve_position(
        self,
        npc: dict,
        activity: str,
    ) -> tuple[str, str, str]:
        """
        Возвращает (location_id, position_in_scene, activity_display).
        Читает activity_map из профиля NPC (data-driven).
        Fallback: _DEFAULT_ACTIVITY_MAP для неизвестных активностей.
        """
        npc_map: dict = npc.get("activity_map", {})

        if activity in npc_map:
            entry = npc_map[activity]
            return (entry["location"], entry["position"], entry["display"])

        return next(
            (
                (entry["location"], entry["position"], entry["display"])
                for key, entry in npc_map.items()
                if activity.startswith(key) or key.startswith(activity)
            ),
            (
                _DEFAULT_ACTIVITY_MAP[activity]
                if activity in _DEFAULT_ACTIVITY_MAP
                else (npc.get("location", "unknown"), "common_area", activity)
            ),
        )

    @staticmethod
    def _mood_for_activity(activity: str) -> str:
        """Определяет настроение NPC по активности."""
        _mood_map = {
            "sleeping": "neutral",
            "resting":  "neutral",
            "working":  "focused",
            "on_duty":  "alert",
            "eating":   "content",
            "drinking": "relaxed",
            "haggling": "focused",
            "hiding":   "tense",
        }
        return _mood_map.get(activity, "neutral")

    # ─────────────────────────────────────────────────────────────────────────
    # check_random_events — случайные события
    # ─────────────────────────────────────────────────────────────────────────

    def check_random_events(
        self,
        npc: dict,
        tick: int = 0,
    ) -> tuple[list[SceneChange], "MovementIntent | None"]:
        """
        С вероятностью RANDOM_EVENT_CHANCE (5%) генерирует случайное событие.
        Возвращает список SceneChange или пустой список.

        Спящие NPC не получают случайных событий.
        """
        npc_id   = npc.get("id", "unknown")
        activity = npc.get("routine", {}).get("current", "")

        if "sleeping" in activity:
            return [], None

        # ADR-052: Парализованный страхом NPC не инициирует случайные события
        _kernel = npc.get("perceptual_kernel")
        _init_sup = _kernel.get("initiative_suppression", 0.0) if isinstance(_kernel, dict) else getattr(_kernel, "initiative_suppression", 0.0) if _kernel else 0.0
        _recent_dir = _kernel.get("recent_directive") if isinstance(_kernel, dict) else getattr(_kernel, "recent_directive", None) if _kernel else None
        if _init_sup > 0.7:
            return [], None

        if random.random() > RANDOM_EVENT_CHANCE:
            return [], None

        events = self._make_random_events(npc, tick)
        event_id, changes, movement_intent = random.choice(events)

        if event_id == "minor_argument":
            psyche = npc.setdefault("psyche", {})
            psyche["stress"] = min(100, psyche.get("stress", 0) + 10)

        logger.info(f"[LIFE_ENGINE] {npc_id}: случайное событие '{event_id}'")

        # ADR-049: LifeEngine не исполняет движение напрямую. Возвращаем Intent.
        # Если событие требует перемещения — намерение передается в оркестратор.

        return changes, movement_intent

    # ─────────────────────────────────────────────────────────────────────────
    # Stress recovery (без SceneChange — только данные NPC)
    # ─────────────────────────────────────────────────────────────────────────

    def recover_stress_tick(self, npc: dict) -> None:
        """
        Восстанавливает стресс NPC за один тик.
        Спящие восстанавливаются быстрее.
        """
        activity = npc.get("routine", {}).get("current", "")
        is_sleeping = "sleeping" in activity

        psyche = npc.setdefault("psyche", {})
        current_stress = psyche.get("stress", 0)

        if current_stress <= 0:
            return

        recovery = STRESS_RECOVERY_SLEEPING if is_sleeping else STRESS_RECOVERY_SAFE
        psyche["stress"] = max(0, current_stress - recovery)


# ──────────────────────────────────────────────────────────────────────────────
# Глобальный синглтон
# ──────────────────────────────────────────────────────────────────────────────

_life_engine_instance: LifeEngine | None = None


def get_life_engine() -> LifeEngine:
    """
    Возвращает глобальный синглтон LifeEngine.
    Используется в orchestrator и world_scheduler.
    """
    global _life_engine_instance
    if _life_engine_instance is None:
        _life_engine_instance = LifeEngine()
    return _life_engine_instance


def shutdown_life_engine() -> None:
    """
    Graceful shutdown: flush all ticks, clear HOT cache.
    Вызывать в app shutdown hook.
    """
    global _life_engine_instance
    if _life_engine_instance is not None:
        _life_engine_instance.cleanup_all_campaigns()
    _life_engine_instance = None


def reset_life_engine() -> None:
    """
    Сбрасывает синглтон. Для тестов.
    """
    shutdown_life_engine()
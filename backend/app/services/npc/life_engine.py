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
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass

from app.core.config import settings
from app.domain.movement import PRIORITY_RANDOM, IntentDomain, MacroMovementGoal
from app.services.drf_bus import DRFBus
from app.services.npc.kernel_rng import KernelRNG
from app.services.scene_change import (
    ChangeType,
    SceneChange,
)
from app.services.spatial.movement_engine import MovementEngine

logger = logging.getLogger(__name__)

# ── Motion Routing: порог микро/макро перемещения ──
# NPC и цель в одном узле графа → DriveVector (ETKE-IK, непрерывная кинематика).
# NPC и цель в разных узлах → MovementIntent (Traversal FSM, дискретный граф).
# Порог не влияет на маршрутизацию (решение = same_node vs different_node),
# но используется для логирования и будущей адаптивной интенсивности.
MOTION_ROUTING_THRESHOLD = 5.0  # единиц координат (для logging / future use)

# ──────────────────────────────────────────────────────────────────────────────
# Константы и маппинги
# ──────────────────────────────────────────────────────────────────────────────

from app.core.constants import (
    DEFAULT_LOCATION_ID,
    MACRO_SIM_THRESHOLD_SECONDS,
    MAX_CACHED_CAMPAIGNS,
    MINOR_TICK_INTERVAL,
    RANDOM_EVENT_CHANCE,
    STRESS_RECOVERY_SAFE,
    STRESS_RECOVERY_SLEEPING,
)
from app.services.npc.sleep_states import is_sleeping

# ── Need-driven movement: простой прокси потребностей ──────────────────
# Не зависит от NeedEngine/EconomicProfile — живёт в словаре NPC
# Позже можно заменить на интеграцию с NeedEngine через DTO

# Маппинг: имя потребности → активность в activity_map
_NEED_TO_ACTIVITY = {
    "hunger": "eating",
    "shelter_urge": "sleeping",  # Фикс C: shelter_urge должен вести в кровать, а не к камину
    "social_urge": "socializing",
    "fatigue": "sleeping",
}

# Порог: если value >= threshold → NPC идёт удовлетворять потребность
_NEED_THRESHOLD: float = 0.5

# Прирост за тик, если активность не удовлетворяет потребность
_NEED_DECAY_PER_TICK: float = 0.08

# Восстановление стресса за тик
# ── Tick Architecture (Блок 1) ──────────────────────────────────────────────

# Hybrid persistence: сохранять tick в JSON раз в N тиков

# LRU защита для HOT кэша

# Порог для макро-симуляции (в секундах реального времени)

# Fallback для неизвестных NPC
# ADR-0011: Расписание удалено. Движение теперь — следствие социальных потребностей (Social Motility).
# NPC не телепортируются по расписанию. Макро-перемещение (LOD1) только для редких нужд (кухня, выход).
# DEBT-S85.1.1: _DEFAULT_ACTIVITY_MAP удалён (мёртвый код). ADR-S85.2 запрещает хардкод позиций в архетипах.

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
    except (ValueError, AttributeError) as e:
        logger.debug(f"Time parse error in _parse_time_to_minutes: {e}")
        return 0


def _in_time_range(time_range: str, current_minutes: int) -> bool:
    """
    Проверяет попадает ли current_minutes в диапазон "HH:MM-HH:MM".
    Поддерживает ночные диапазоны пересекающие полночь (22:00-06:00).
    """
    try:
        start_str, end_str = time_range.split("-")
        start = _time_to_minutes(start_str)
        end = _time_to_minutes(end_str)
        # Ночной диапазон: start > end означает переход через полночь
        if start > end:
            return current_minutes >= start or current_minutes < end
        return start <= current_minutes < end
    except (ValueError, AttributeError) as e:
        logger.debug(f"Time range parse error: {e}")
        return False


def _parse_game_time(scene_state: Optional[Dict[str, Any]]) -> str:
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
        "утро": "08:00",
        "день": "14:00",
        "вечер": "20:00",
        "ночь": "02:00",
        "рассвет": "06:00",
        "полдень": "12:00",
        "полночь": "00:00",
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
        self.data_dir = Path(data_dir or settings.data_dir)
        self.npcs_dir = self.data_dir / "npcs"
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

        # BUG-CORE-004 FIX: Атрибуты инъекции перенесены в __init__.
        # Ранее они находились внутри update_idle_pressure, что приводило
        # к обнулению сервисов каждый тик (S-3: NPC теряли маршрут).
        # Слой 3: SpatialService v1.2 — семантическая навигация (инжекция извне)
        self._spatial_service: Optional[Any] = None

        # ADR-128: PersistencePort для read-back при cache miss.
        # Без этого body_state (injuries, blood_loss, shock_impulse) теряется
        # после TTL/LRU eviction — SQLite пишется, но никогда не читается.
        self._persistence: Optional[Any] = None

        self._claim_bus: Optional["DRFBus"] = None  # DRF Causal Bus

    def get_idle_pressure_map(self) -> dict:
        """V8-SOC-5 FIX: Возвращает текущее давление разговоров для TickState."""
        return self._idle_pressure.copy()

    def update_idle_pressure(self, updates: dict) -> None:
        """V8-SOC-5 FIX: Обновляет давление разговоров из TickMutation."""
        self._idle_pressure.update(updates)

    def set_claim_bus(self, bus: "DRFBus") -> None:
        """DRF: Инъекция единой причинной шины из TickOrchestrator."""
        self._claim_bus = bus

    def set_spatial_service(self, svc: Any) -> None:
        """Инжекция SpatialService для резолва NodeRole вместо хардкода."""
        self._spatial_service = svc
        # Пробрасываем в MovementEngine для A* с учётом оверлея
        if hasattr(self, "_movement_engine") and self._movement_engine:
            self._movement_engine.set_spatial_service(svc)

    def set_persistence(self, persistence: Any) -> None:
        """ADR-128: Инъекция PersistencePort для read-back при cache miss.

        Без этого SQLite runtime пишется (atomic_commit), но никогда не
        читается обратно. После TTL/LRU eviction injuries, blood_loss,
        affective_load и прочие runtime-поля теряются навсегда.
        """
        self._persistence = persistence
        logger.info(
            "[LIFE_ENGINE] PersistencePort инжектирован — SQLite read-back активен"
        )

    def macro_simulate(
        self,
        campaign_id: str,
        scene_state: Optional[Dict[str, Any]] = None,
        runtime_path: Optional[Path] = None,
    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:
        """
        Аппроксимация долгого отсутствия игрока.

        Вместо: for _ in range(500): tick()
        Делает: state(t+Δ) = f(state(t), Δ)

        Что аппроксимирует:
        - Расписание: прыгает к текущему слоту
        - Стресс: нормализуется к baseline
        - События: агрегированная вероятность
        """
        # ADR-O-302: get_idle_seconds удалён. Ретросимуляция запрещена.
        # macro_simulate вырождена в tick() до полной ликвидации мёртвого кода.
        idle_seconds = 0.0

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
                    decay = 0.3  # за долгое отсутствие сбросить на 70%
                    psyche["stress"] = round(
                        baseline + (current_stress - baseline) * decay
                    )

                # 3. Агрегированные события — вероятность * время
                # 5% за тик, но мы не считаем тики — используем эвристику
                # KERNEL-ISOLATION: deterministic RNG вместо global random.
                _tick = self.get_current_tick(campaign_id)
                _rng = KernelRNG(tick=_tick, npc_id=npc_id, salt="life_engine_random_events")
                if tier == "major" and _rng.random() < 0.4:  # 40% шанс, deterministic
                    event_changes, _ = self.check_random_events(npc, _tick, rng=_rng)
                    all_changes.extend(event_changes)

            except Exception as e:
                logger.error(f"[LIFE_ENGINE] macro_simulate error for '{npc_id}': {e}")

        # Обновляем кэш и tick
        self._npc_cache[campaign_id] = npcs
        self._increment_tick(campaign_id)  # Один тик за всю макро-симуляцию

        logger.info(
            f"[LIFE_ENGINE] macro_simulate завершена: {len(all_changes)} changes"
        )
        return (
            all_changes,
            [],
        )  # ADR-049: macro_simulate не генерирует intents (только tick)

    # ─────────────────────────────────────────────────────────────────────────
    # LRU защита для HOT кэша
    # ─────────────────────────────────────────────────────────────────────────

    def _touch(self, campaign_id: str) -> None:
        """Обновляет время последнего доступа (LRU)."""
        if not hasattr(self, "_touch_counter"):
            self._touch_counter = 0
        self._touch_counter += 1
        self._last_access[campaign_id] = float(self._touch_counter)
        self._last_access.move_to_end(campaign_id)

    def _evict_stale(self) -> list[str]:
        """
        Вызывает очистку неактивных кампаний.
        Удаляет: (1) просроченные по TTL, (2) лишние по LRU.
        Возвращает список evicted campaign_id.
        """
        if not hasattr(self, "_touch_counter"):
            self._touch_counter = 0
        current_counter = self._touch_counter
        evicted = []

        # Слой 1: TTL eviction (по количеству операций, а не wall-clock)
        stale = [
            cid
            for cid, ts in self._last_access.items()
            if current_counter - ts > 1000
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
        ADR-047 / ADR-O-302: REAL_TIME_BRIDGE.
        Аналитическое согласование состояния при загрузке сцены (после простоя).
        Без ретро-симуляции (TICK_CATCHUP убит). Переводит REAL_TIME (секунды) в TICK_TIME.
        """
        if elapsed_seconds <= 0:
            return

        npcs = self._npc_cache.get(campaign_id, [])
        # ADR-O-302: Явный мост REAL_TIME -> TICK_TIME. 1 тик = 60 секунд (GAME_TICK_INTERVAL_SECONDS).
        # Магическое число 10.0 убито. Согласование идёт строго по константе ядра.
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS

        ticks_equivalent = elapsed_seconds / float(GAME_TICK_INTERVAL_SECONDS)

        for npc in npcs:
            psyche = npc.get("psyche", {})
            body_state = npc.get("body_state", {})

            # 1. Стресс: экспоненциальный декэй к базовой линии
            current_stress = psyche.get("stress", 0)
            if current_stress > 0:
                baseline = 0.0
                decay_rate = 0.05  # Примерно 5% восстановления за тик
                # Формула: S_t = baseline + (S_0 - baseline) * (1 - decay_rate)^T
                decayed_stress = baseline + (current_stress - baseline) * (
                    (1 - decay_rate) ** ticks_equivalent
                )
                psyche["stress"] = max(0.0, round(decayed_stress, 2))

            # 2. Голод и Усталость: линейный рост (если были в пути)
            # ADR-S96.3: Унификация скорости роста потребностей. _NEED_DECAY_PER_TICK = 0.08 (шкала 0.0-1.0).
            # Для body_state (шкала 0-100) умножаем на 100.
            hunger_rate = _NEED_DECAY_PER_TICK * 100.0  # 8.0 за тик
            # ADR-O-373: fatigue-reconcile DORMANT — skip-семантика усталости
            # уходит в BodyEngine-контур; catch-up физиологии = S2B.6/S2B.8.

            if "hunger" in body_state:
                body_state["hunger"] = min(
                    100.0,
                    body_state.get("hunger", 0.0) + hunger_rate * ticks_equivalent,
                )
            # ADR-O-373: блок fatigue-reconcile удалён (см. комментарий выше);
            # hunger-строка жива до S2B.10 (LEGACY-HUNGER, не трогать).

        logger.info(
            f"[LIFE_ENGINE] Аналитическое согласование для '{campaign_id}': {elapsed_seconds:.1f}s ({ticks_equivalent:.1f} тиков)"
        )

    def tick(
        self,
        campaign_id: str,
        scene_state: Optional[Dict[str, Any]] = None,
        runtime_path: Optional[Path] = None,
    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:
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

        # ADR-123/127: Мёртвые NPC не генерируют интенты и не двигаются.
        _alive_npcs = []
        for _npc in (self._npc_cache.get(campaign_id) or load_npcs_merged(runtime_path=runtime_path)):
            _life_status = _npc.get("body_state", {}).get("life_status", "ALIVE")
            if _life_status == "ALIVE":
                _alive_npcs.append(_npc)
        npcs = _alive_npcs
        logger.debug(
            f"[LIFE_SET] tick={current_tick} npcs={sorted([n.get('id', '?') for n in npcs]) if npcs else []}"
        )
        all_changes: list[SceneChange] = []
        all_intents: list["MacroMovementGoal"] = []  # ADR-049: Сборка намерений
        npcs_updated = False

        # S-145 FIX: Синхронизация location_id и position из scene_state в _npc_cache.
        # Это исправляет DOUBLE TRUTH, когда position уже "city_gate:...", а location_id="tavern".
        _ss_positions = scene_state.get("npc_positions", {}) if scene_state else {}
        for npc in npcs:
            npc_id = npc.get("id", "?")
            _ss_data = _ss_positions.get(npc_id)
            if isinstance(_ss_data, dict):
                _ss_pos = _ss_data.get("position")
                _ss_loc = _ss_data.get("location_id")
                # V8-SP-19 FIX: Синхронизируем position и location_id из scene_state (SSOT).
                # Если position содержит префикс (loc:node), извлекаем локацию из него.
                # Иначе доверяем location_id из scene_state.
                _resolved_loc = _ss_loc
                if _ss_pos and ":" in _ss_pos:
                    _pos_loc = _ss_pos.split(":")[0]
                    # V8-SP-19 FIX: boundary nodes (exit_*) не определяют location_id
                    if "exit_" not in _ss_pos and _ss_loc != _pos_loc:
                        _resolved_loc = _pos_loc
                    elif _ss_loc:
                        _resolved_loc = _ss_loc

                if _resolved_loc:
                    if npc.get("location_id") != _resolved_loc:
                        npc["location_id"] = _resolved_loc
                        npc["location"] = _resolved_loc
                if _ss_pos and npc.get("position") != _ss_pos:
                    npc.update({"position": _ss_pos})

        for npc in npcs:
            tier = npc.get("tier", "major")
            npc_id = npc.get("id", "?")

            # ADR-OFFSCREEN-SKIP: NPC не в текущей локации не симулируются.
            # S112 FIX: Восстановление location_id из legacy location или scene_state, если он потерян.
            if not npc.get("location_id") and npc.get("location"):
                npc["location_id"] = npc["location"]

            assert scene_state is not None, "scene_state is required for tick"
            _current_loc = scene_state.get("location_id", "")
            _npc_loc = npc.get("location_id") or npc.get("location", "")

            # S112 FIX: Если NPC нет в scene_state (npc_positions), значит он оффскрин.
            # LifeEngine не должен симулировать его, так как у него нет актуальной позиции.
            _in_scene = npc_id in scene_state.get("npc_positions", {})
            if not _in_scene and _current_loc:
                logger.debug(
                    f"[LIFE_ENGINE][OFFSCREEN] npc={npc_id} not in scene_state (loc={_npc_loc}) — skipped"
                )
                continue

            # S144 FIX: Нормализация локации. "tavern" в конфиге NPC и "tavern_silver_wolf" в scene_state
            # должны считаться одной локацией, иначе NPC будут пропущены как оффскрин.
            _loc_match = (
                _npc_loc == _current_loc
                or _npc_loc in _current_loc
                or _current_loc in _npc_loc
            )
            if _current_loc and _npc_loc and not _loc_match:
                logger.debug(
                    f"[LIFE_ENGINE][OFFSCREEN] npc={npc_id} loc={_npc_loc} != scene_loc={_current_loc} — skipped"
                )
                continue

            # KERNEL-ISOLATION: Единый deterministic RNG для LifeEngine на этом тике.
            # Изолирован от MovementEngine и DecisionHub через salt="life_events".
            _rng = KernelRNG(tick=current_tick, npc_id=npc_id, salt="life_events")

            # Motion Router: очистка устаревшего DriveVector от предыдущего тика.
            # DriveVector эфемерен — если DecisionHub не сгенерировал новый,
            # NPC должен остановиться (нет давления = нет движения, ADR-O-208 L3-P1).
            npc.pop("drive_vector", None)

            try:
                # ── MAJOR: полная симуляция каждый тик ──────────────────────
                if tier == "major":
                    changes, intents = self._simulate_major(
                        npc, current_time, current_tick, scene_state, rng=_rng
                    )
                    all_changes.extend(changes)
                    all_intents.extend(intents)
                    npcs_updated = True

                elif tier == "minor":
                    last_minor = npc.get("routine", {}).get("_last_life_tick", 0)
                    if (current_tick - last_minor) >= MINOR_TICK_INTERVAL:
                        changes, intents = self._simulate_minor(
                            npc, current_time, current_tick, scene_state, rng=_rng
                        )
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
        return all_changes, all_intents  # ADR-049: Возвращаем намерения в оркестратор

    # BUG-CORE-016/017 FIX: Метод tick_decisions удалён как мёртвый код.
    # Логика принятия решений перенесена в NpcTickPipeline (pure reducer, ADR-TZ09-1).

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
                json.dumps(npcs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.debug(f"[LIFE_ENGINE] NPC сохранены: {path}")
        except OSError as e:
            logger.error(f"[LIFE_ENGINE] Ошибка сохранения NPC: {e}")

    def get_activity_description(self, npc: Dict[str, Any]) -> str:
        """
        Возвращает читаемое описание текущей активности NPC.
        Используется DM для описания сцены и LifeEngine для логов.

        Пример: "Торнин стоит за стойкой, протирает кружки"
        """
        name = npc.get("name", npc.get("id", "NPC"))
        activity = npc.get("routine", {}).get("current", "")
        location = npc.get("location", "")

        _activity_phrases = {
            "sleeping": "спит",
            "cleaning_tables": "протирает столы",
            "serving_tables": "разносит еду и напитки",
            "guarding_gate": "несёт стражу у ворот",
            "haggling": "торгуется с покупателями",
            "observing": "наблюдает за посетителями",
            "resting": "отдыхает",
            "eating": "ест",
            "drinking": "пьёт",
            "working": "работает",
            "on_duty": "на дежурстве",
            "off_duty": "отдыхает после смены",
            "talking_at_bar": "разговаривает у стойки",
            "hiding": "прячется в тени",
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

    def get_temporal_context(self, campaign_id: str) -> Any:
        """Возвращает TemporalContext для подсистем, которым нужно больше чем просто тик."""
        return self._temporal.get_temporal_context(campaign_id)

    # ADR-O-302 / DEBT-TIME-3: get_idle_seconds и get_world_ticks_elapsed УДАЛЕНЫ.
    # Они нарушали §14 (Law of Singular Time) и §15.1 (Law of Wall-Clock Isolation).
    # TICK_CATCHUP мёртв с ADR-047.

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

    def reset_campaign(self, campaign_id: str) -> list[dict]:
        """Сброс NPC кампании к чистому static config с healthy body_state.
        Вызывается из new_game() ПОСЛЕ очистки persistence.
        1. Очищает кэш
        2. Загружает NPC из static config (fallback в _load_npcs)
        3. Инжектит BODY_STATE_HEALTHY для NPC без body_state
        4. Сохраняет в persistence для следующих загрузок
        5. Обновляет кэш"""
        from app.models.npc_state import BODY_STATE_HEALTHY

        # Очистка кэша
        self._npc_cache.pop(campaign_id, None)
        self._last_access.pop(campaign_id, None)
        # Загрузка из static (persistence уже очищен, будет fallback)
        npcs = self._load_npcs(campaign_id)
        # ADR-O-146: Принудительный сброс ВСЕГО runtime состояния.
        # Новая игра = чистый лист. Старый body_state с pain=95 — не "disabled",
        # но должен быть перезаписан. Аналогично affective_load, emotion, PK.
        for npc in npcs:
            npc["body_state"] = dict(BODY_STATE_HEALTHY)
            npc["affective_load"] = 0.0
            npc["emotion"] = "neutral"
            npc["emotion_delta"] = 0.0
            npc["perceptual_kernel"] = {}
            npc["narrative_cache"] = []
            npc.pop("wounds", None)
            npc.pop("conditions", None)
        # BUG-AUDIT-13 (Atomic Commit): Не сохраняем здесь!
        # Сохранение будет атомарным в GameLoop.new_game() через atomic_commit.
        # Обновление кэша
        self._npc_cache[campaign_id] = npcs
        logger.info(
            f"[LIFE_ENGINE] Campaign '{campaign_id}' reset: "
            f"{len(npcs)} NPCs with healthy body_state"
        )
        return npcs

    def update_cache(self, campaign_id: str, npc_dicts: list[dict]) -> None:
        """Обновляет HOT кэш NPC мутированными данными после apply_batch.

        Без этого affective_load, emotion, body_state и другие runtime-поля
        теряются между тиками — каждый player turn загружает свежий статический конфиг.
        """
        if npc_dicts:
            self._npc_cache[campaign_id] = list(npc_dicts)

    # ─────────────────────────────────────────────────────────────────────────
    # Внутренние методы загрузки NPC
    # ─────────────────────────────────────────────────────────────────────────

    def _npcs_file(self) -> Path:
        """Путь к файлу NPC (для совместимости с legacy кодом)."""
        return self.npcs_dir / "major_npcs.json"

    def _load_npcs(self, campaign_id: str) -> List[Any]:
        """
        Загружает NPC из кэша или файла.
        Для campaign-specific файлов путь: sessions/{campaign_id}/major_npcs.json
        """
        # HOT cache hit
        if campaign_id in self._npc_cache:
            return self._npc_cache[campaign_id]

        # ADR-128: COLD-1 — SQLite runtime (authoritative runtime truth).
        # atomic_commit пишет полный npc_dict с body_state в SQLite.
        # Без этого read-back'а injuries, blood_loss, affective_load
        # теряются после TTL/LRU eviction.
        if self._persistence is not None:
            try:
                runtime_npcs = self._persistence.load_npc_runtime(campaign_id)
                if runtime_npcs is not None:
                    runtime_npcs = self._normalize_runtime_npcs(runtime_npcs)
                    self._npc_cache[campaign_id] = runtime_npcs
                    # BUG-DRIFT-009 FIX: Используем единый монотонный счётчик _touch_counter,
                    # как в _touch(). Раньше тут был float(len(self._last_access)) + 1.0,
                    # что сбрасывало таймер при пустом кэше и вызывало мгновенный re-eviction.
                    if not hasattr(self, "_touch_counter"):
                        self._touch_counter = 0
                    self._touch_counter += 1
                    self._last_access[campaign_id] = float(self._touch_counter)
                    self._last_access.move_to_end(campaign_id)
                    logger.info(
                        f"[LIFE_ENGINE] Восстановлен из SQLite: {campaign_id} "
                        f"({len(runtime_npcs)} NPC)"
                    )
                    return runtime_npcs
            except Exception as e:
                logger.warning(
                    f"[LIFE_ENGINE] Ошибка чтения SQLite runtime для "
                    f"'{campaign_id}': {e}"
                )

        # COLD-2: campaign-specific JSON файл (bootstrap для новых игр)
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

    @staticmethod
    def _normalize_runtime_npcs(npcs: List[Any]) -> List[Any]:
        """Migration Boundary: приводит загруженные NPC dicts к runtime-контракту.

        Все источники (SQLite, JSON, cache) проходят эту нормализацию
        при холодной загрузке. Горячий путь (cache hit) пропускается —
        данные уже нормализованы при первом заходе.

        Инвариант: после этого метода каждый NPC dict гарантированно имеет
        npc_id, body_state, location_id.
        """
        from app.core.constants import DEFAULT_LOCATION_ID
        from app.models.npc_state import BODY_STATE_HEALTHY

        for npc in npcs:
            if "npc_id" not in npc and "id" in npc:
                npc["npc_id"] = npc["id"]
            if not npc.get("body_state"):
                npc["body_state"] = dict(BODY_STATE_HEALTHY)
            if "location_id" not in npc:
                npc["location_id"] = npc.get("location", DEFAULT_LOCATION_ID)
        return npcs

    def _extracted_from__load_npcs_14(self, arg0, campaign_id):
        npcs = json.loads(arg0.read_text(encoding="utf-8-sig"))
        npcs = self._normalize_runtime_npcs(npcs)
        self._npc_cache[campaign_id] = npcs
        return npcs

    def get_npc_observed_state(self, campaign_id: str, npc_id: str) -> Dict[str, Any]:
        """Возвращает безопасный наблюдаемый слепок NPC для LLM (Эпистемический Барьер ADR-TZ08-6).
        L-03 FIX: Возвращает voice_profile, backstory, author_notes для уникального голоса NPC.
        """
        cached = self._npc_cache.get(campaign_id, [])
        for n in cached:
            if n.get("npc_id") == npc_id or n.get("id") == npc_id:
                return {
                    "name": n.get("name", npc_id),
                    "description": n.get("description", ""),
                    "voice_profile": n.get("voice_profile", ""),
                    "backstory": n.get("backstory", ""),
                    "author_notes": n.get("author_notes", ""),
                }
        return {"name": npc_id, "description": ""}

    def get_npc_light_states(self, campaign_id: str) -> list[dict]:
        """Возвращает лёгкий срез NPC states для детекторов Time Skip.
        Извлекает только npc_id, life_status, identity_integrity и drives без deepcopy.
        """
        cached = self._npc_cache.get(campaign_id, [])
        light_snap = []
        for n in cached:
            light_snap.append(
                {
                    "npc_id": n.get("npc_id"),
                    "body_state": {
                        "life_status": n.get("body_state", {}).get(
                            "life_status", "ALIVE"
                        )
                    },
                    "psyche": {
                        "identity_integrity": n.get("psyche", {}).get(
                            "identity_integrity", 1.0
                        )
                    },
                    "drives": n.get("drives", {}).copy(),
                }
            )
        return light_snap

    def get_npc_states(self, campaign_id: str) -> list[dict]:
        """Возвращает кэшированные NPC states после мутации в tick().

        ADR-128: При cache miss пытается восстановить из SQLite (COLD-1),
        затем из static config (COLD-2). Без этого body_state (injuries,
        blood_loss, shock_impulse) теряется после TTL/LRU eviction.
        """
        if cached := self._npc_cache.get(campaign_id):
            return cached

        # COLD RECOVERY: Возвращаем пустой список, если кэш пуст.
        # Загрузка из БД будет выполнена при следующем вызове _load_npcs.
        return []


    # ─────────────────────────────────────────────────────────────────────────
    # Симуляция по тирам
    # ─────────────────────────────────────────────────────────────────────────

    def _make_random_events(self, npc: Dict[str, Any], tick: int) -> List[Any]:
        """Таблица случайных событий для Major NPC.

        5% шанс одного события за тик.
        Возвращает список (event_id, changes, intent_or_none).
        """
        npc_id = npc.get("id", "unknown")
        location = npc.get("location_id", DEFAULT_LOCATION_ID)

        from app.domain.spatial_target import SpatialTargetIntent, SpatialTargetType

        # ADR-O-330: LifeEngine формирует только семантическое намерение (SA-1).
        # Поиск физического узла делегирован SpatialTargetResolver.
        bar_intent = SpatialTargetIntent(
            target_type=SpatialTargetType.ANCHOR,
            target_id="bar",
            reason="random:wanders_to_bar",
            confidence=0.8
        )

        events = [
            # NPC переходит к стойке поговорить с кем-то
            (
                "wanders_to_bar",
                [
                    SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=npc_id,
                        field="activity",
                        value="talking_at_bar",
                        cause="life_engine_random",
                        tick=tick,
                    ),
                ],
                MacroMovementGoal(
                    actor_id=npc_id,
                    target_intent=bar_intent,
                    from_node_id=npc.get("position", ""),
                    location_id=location,
                    reason="random:wanders_to_bar",
                    domain=IntentDomain.EXPLORATION,
                    priority=PRIORITY_RANDOM,
                ),
            ),
            # NPC становится более бдительным (заметил что-то)
            (
                "notices_something",
                [
                    SceneChange(
                        type=ChangeType.NPC_STATE,
                        target=npc_id,
                        field="psyche_state",
                        value="alert",
                        cause="life_engine_random",
                        tick=tick,
                    ),
                ],
                None,
            ),
            # Небольшой стресс — ссора с кем-то
            (
                "minor_argument",
                [
                    SceneChange(
                        type=ChangeType.NPC_STATE,
                        target=npc_id,
                        field="stress_delta",
                        value=10,
                        cause="life_engine_argument",
                        tick=tick,
                    ),
                ],
                None,
            ),
            # NPC на мгновение выходит (в туалет, за товаром, на улицу)
            (
                "brief_exit",
                [
                    SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=npc_id,
                        field="visible",
                        value=False,
                        cause="life_engine_random",
                        tick=tick,
                    ),
                ],
                None,
            ),
        ]
        # Событие wanders_to_bar только в таверне — иначе MovementEngine не найдёт узел
        if location != DEFAULT_LOCATION_ID:
            events = [e for e in events if e[0] != "wanders_to_bar"]
        return events

    def _simulate_major(
        self,
        npc: Dict[str, Any],
        current_time: str,
        tick: int,
        scene_state: Optional[Dict[str, Any]] = None,
        rng: Optional[KernelRNG] = None,
    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:
        """
        Полная симуляция Major NPC за один тик.
        Порядок: need-driven → расписание → стресс → случайные события.
        Need-driven имеет приоритет: если потребность критична — schedule пропускается.
        ADR-049: Возвращает list["MacroMovementGoal"] вместо прямого исполнения.
        ДОЛГ 4.3: Viability Pre-Generation Gate — ROUTINE не генерируется при SURVIVAL давлении.
        """
        npc_id = npc.get("id", "unknown")

        # S112 FIX: Синхронизация пространственных данных из scene_state (SSOT) в npc_dict (cache).
        # LifeEngine ожидает position и location_id в npc_dict, но авторитетный источник — scene_state.
        # Без этого NPC теряет позицию между тиками и генерирует NO_POSITION / DUPLICATE_POSITION_CHANGE.
        if scene_state:
            _pos_data = scene_state.get("npc_positions", {}).get(npc_id, {})
            if _pos_data:
                if "position" in _pos_data:
                    npc.update({"position": _pos_data["position"]})
                if "location_id" not in npc or not npc["location_id"]:
                    npc["location_id"] = _pos_data.get(
                        "location_id", scene_state.get("location_id", "")
                    )
                if "local_position" in _pos_data:
                    npc.update({"local_position": _pos_data["local_position"]})
            else:
                # S112 DIAG: Если NPC нет в scene_state, значит он offscreen.
                # LifeEngine не должен генерировать для него интенты, так как он не в этой локации.
                if npc_id == "guard_borko":
                    logger.debug(
                        f"[DIAG_BORKO] npc_id={npc_id} NOT in scene_state! npc_loc={npc.get('location_id')} scene_loc={scene_state.get('location_id')} npc_pos={npc.get('position')}"
                    )

        # BUG-SLEEP-007 FIX: Логика пробуждения перенесена в SleepLifecycleService (Phase 0.6)
        # LifeEngine теперь отвечает только за генерацию интентов (пойти спать), а не за lifecycle.

        # ── ДОЛГ 4.3: Viability Pre-Generation Gate ──
        # Вычисляем допустимые домены ДО генерации кандидатов.
        # Viability — не предпочтение (priority), а физика возможностей.
        # SURVIVAL давление (threat > 0.3) исключает ROUTINE из пространства генерации.
        # NPC не может «выбрать» работу при угрозе — это не вопрос priority, а вопрос существования.
        # Источник: PerceptualKernel (персистентен между тиками, доступен в Phase 0).
        _viable = self._compute_viability_mask(npc)

        # ADR-052: Cognitive Override Guard. Паралич воли блокирует любую активность.
        _kernel = npc.get("perceptual_kernel")
        _init_sup = (
            _kernel.get("initiative_suppression", 0.0)
            if isinstance(_kernel, dict)
            else getattr(_kernel, "initiative_suppression", 0.0)
            if _kernel
            else 0.0
        )
        _recent_dir = (
            _kernel.get("recent_directive")
            if isinstance(_kernel, dict)
            else getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA001, ENIGMA002
            if _kernel
            else None
        )
        if _init_sup > 0.7:
            logger.debug(
                f"[LIFE_ENGINE] {npc_id}: Major cycle bypassed due to initiative_suppression={_init_sup:.2f}"
            )
            return [], []

        # ADR-130: Movement Lock. Если NPC уже в активном транзите —
        # LifeEngine не генерирует новые интенты (ни schedule, ни need-driven).
        # Это предотвращает "бесконечный бег" и топологические дрейфы.
        if scene_state:
            _active_travs = scene_state.get("active_traversals", {})
            _my_trav = _active_travs.get(npc_id)
            if _my_trav and _my_trav.get("status") == "MOVING":
                logger.debug(
                    f"[LIFE_ENGINE] {npc_id}: Major cycle bypassed — active traversal (target={_my_trav.get('target_node', '?')})"
                )
                return [], []

        changes: list[SceneChange] = []
        intents: list["MacroMovementGoal"] = []

        # ── D6: сбор всех intent-ов с приоритетами ──
        candidates: list["MacroMovementGoal"] = []

        # 1. Need-driven: только если ROUTINE жизнеспособен
        # Фикс A: Sleep schedule non-interruptible. Если по расписанию NPC должен спать,
        # потребности (shelter_urge, social_urge) его не прерывают.
        _routine_dict = npc.get("routine", {})
        _scheduled_activity = self._get_current_activity(_routine_dict.get("schedule", {}), current_time)
        if IntentDomain.ROUTINE in _viable and _scheduled_activity != "sleeping":
            self._tick_needs(npc)
            if need_intent := self._check_need_driven_movement(npc):
                need_intent.domain = IntentDomain.ROUTINE
                # S89: Need-driven OVERRIDE — критическая потребность перезаписывает schedule
                # Модель: schedule = constitution, needs = emergency signals
                # Когда потребность > threshold → schedule пропускается (не конкурирует)
                need_intent.priority = 0.8  # PRIORITY_REACTIVE level — выше schedule
                candidates.append(need_intent)

        # 2. Расписание: только если ROUTINE жизнеспособен И нет критической потребности
        # S89: Need override — если need_intent уже в кандидатах, schedule не генерируется
        # Модель: голодный кузнец не идёт на работу, он идёт есть
        _has_critical_need = any(
            c.reason.startswith("need_driven:") for c in candidates
        )
        if IntentDomain.ROUTINE in _viable and not _has_critical_need:
            routine_changes, routine_intent = self.update_routine(
                npc, current_time, tick, scene_state=scene_state
            )
            changes.extend(routine_changes)
            if routine_intent:
                routine_intent.domain = IntentDomain.ROUTINE
                candidates.append(routine_intent)

        # 3. Случайные события: только если EXPLORATION жизнеспособен
        if IntentDomain.EXPLORATION in _viable:
            event_changes, event_intent = self.check_random_events(npc, tick, rng=rng)
            changes.extend(event_changes)
            if event_intent:
                event_intent.domain = IntentDomain.EXPLORATION
                candidates.append(event_intent)

        # S188 ARCH-SLEEP: recover_stress_tick перенесён в SleepLifecycleService (Phase 0.6).
        # Оставление вызова здесь нарушает ADR-O-353 (двойное применение восстановления).

        # ── Viability логирование ──
        if IntentDomain.ROUTINE not in _viable:
            logger.info(
                f"[VIABILITY] npc={npc_id}: ROUTINE pruned (threat) — viable={[d.value for d in _viable]}"
            )

        # ── D6: выбираем лучший intent по priority ──
        if candidates:
            candidates.sort(key=lambda i: i.priority, reverse=True)
            winner = candidates[0]
            # ADR-049: LifeEngine больше не диктатор. Он не исполняет намерения сам.
            # Намерение передается в TickOrchestrator для прохождения каузального конвейера.
            logger.info(
                f"[PIPELINE][MOVEMENT][INTENT_SCHEDULE] npc={winner.npc_id} target={winner.target_node_id} reason={winner.reason}"
            )

            # DRF Side-Channel Bus: Пишем давление напрямую в шину, минуя Intent DTO
            # ДОЛГ 4.3: pressure_type из домена победителя, не хардкод
            _winner_domain = getattr(winner, "domain", IntentDomain.ROUTINE)
            _claim = {
                "source": "life_engine_intent",
                "target_npc": winner.npc_id,
                "pressure_type": _winner_domain.value,
                "vector": winner.reason,
                "energy": 0.5,
                "target_node": winner.target_node_id,
                "half_life": 5.0,
            }
            if self._claim_bus is not None:
                self._claim_bus.emit(_claim)
                logger.debug(
                    f"[DRF_EMIT] source=life_engine npc={winner.npc_id} vector={winner.reason} bus_id={id(self._claim_bus)} stream_size={len(self._claim_bus.stream)}"
                )

            intents.append(winner)
            # Обновляем activity в scene_state
            if winner.reason.startswith("need_driven:"):
                if target_activity := _NEED_TO_ACTIVITY.get(
                    winner.reason.split(":")[1].split("=")[0], ""
                ):
                    activity_entry = npc.get("activity_map", {}).get(
                        target_activity, {}
                    )
                    changes.append(
                        SceneChange(
                            type=ChangeType.NPC_POSITION,
                            target=winner.npc_id,
                            field="activity",
                            value=activity_entry.get("display", target_activity),
                            cause=f"life_engine_need_driven:{winner.reason}",
                            tick=tick,
                        )
                    )
                    # BUG SC FIX: Обновление routine.current при победе need-driven
                    # Без этого routine.current остаётся на schedule activity, пока NPC
                    # физически на need-driven позиции → DOUBLE TRUTH → Schedule Freeze
                    # Голодный NPC решил есть → routine.current = "eating" →
                    # _tick_needs сбросит hunger → schedule вернёт NPC на работу
                    _routine = npc.setdefault("routine", {})
                    _routine["current"] = target_activity
                    _routine["mood"] = self._mood_for_activity(target_activity)
            logger.debug(
                f"[LIFE_ENGINE] {npc.get('id', '?')}: "
                f"{len(candidates)} intents, winner={winner.reason} (p={winner.priority})"
            )

        return changes, intents

    # ─────────────────────────────────────────────────────────────────────
    # Need-driven movement — перемещение по потребностям
    # ─────────────────────────────────────────────────────────────────────

    def _ensure_needs_state(self, npc: Dict[str, Any]) -> Dict[str, Any]:
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

    def _tick_needs(self, npc: Dict[str, Any]) -> None:
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
        npc: Dict[str, Any],
    ) -> Optional["MacroMovementGoal"]:
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
            (name, val) for name, val in needs.items() if val >= _NEED_THRESHOLD
        ]

        if not urgent_needs:
            return None

        # Самая срочной первой
        urgent_needs.sort(key=lambda x: x[1], reverse=True)
        need_name, need_value = urgent_needs[0]

        target_activity = _NEED_TO_ACTIVITY.get(need_name)
        if not target_activity:
            return None

        # S89: Диагностика need-driven
        _has_am = target_activity in activity_map
        logger.debug(
            f"[NEED_TRACE] npc={npc_id} need={need_name}:{need_value:.2f} activity={target_activity} has_am={_has_am}"
        )

        target_entry = activity_map.get(target_activity)

        # S89: Semantic spatial binding fallback для need-driven
        # Если activity_map не имеет нужной активности (напр. "socializing"),
        # резолвим через SpatialService по роли — как в _resolve_position
        if not target_entry and self._spatial_service:
            from app.models.spatial_contracts import NodeRole

            _NEED_ROLE_MAP = {
                "eating": NodeRole.TABLE,
                "sleeping": NodeRole.BED,
                "resting": NodeRole.BED,
                "working": NodeRole.WORKBENCH,
                "socializing": NodeRole.BAR,
                "drinking": NodeRole.BAR,
                "haggling": NodeRole.MARKET,
                "guarding_gate": NodeRole.ENTRANCE,
            }
            _role = _NEED_ROLE_MAP.get(target_activity)
            if _role:
                # ADR-O-330: Affordance Compatibility Adapter для сна
                _npc_xy = npc.get("local_position", {})
                _origin_xy = (_npc_xy.get("x", 0.0), _npc_xy.get("y", 0.0))
                if _role == NodeRole.BED and hasattr(self._spatial_service, 'resolve_affordance'):
                    _ref = self._spatial_service.resolve_affordance(
                        affordance_type="sleep",
                        origin_xy=_origin_xy,
                        origin_zone=npc.get("location_id"),
                        owner=npc.get("id") # пока передаём ID, чтобы在未来 фильтровать палатки
                    )
                    # S-146 FIX: Фоллбэк на роль BED, если в карте нет affordance_objects
                    if not _ref:
                        # BUG-SPATIAL-033 FIX: Не ограничиваем поиск кровати текущей зоной NPC.
                        # NPC может спать в любой зоне локации (например, kitchen_bed в зоне kitchen).
                        _ref = self._spatial_service.resolve_node(
                            role=NodeRole.BED, origin_xy=(npc.get("local_position", {}).get("x"), npc.get("local_position", {}).get("y"))
                        )
                else:
                    _ref = self._spatial_service.resolve_node(
                        role=_role, origin_zone=npc.get("location_id")
                    )
                if _ref:
                    target_entry = {
                        "location": _ref.zone_id,
                        "position": _ref.node_id,
                        "display": target_activity,
                    }
                elif target_activity in ("resting", "sleeping"):
                    # Fallback: BED не найден → отдых на любом доступном узле (скамейка, земля)
                    # sleeping требует BED строго, resting — нет
                    if target_activity == "resting":
                        _ref = self._spatial_service.resolve_node(
                            role=NodeRole.DEFAULT, origin_zone=npc.get("location_id")
                        )
                        if _ref:
                            target_entry = {
                                "location": _ref.zone_id,
                                "position": _ref.node_id,
                                "display": target_activity,
                            }
                            logger.debug(
                                f"[NEED_TRACE] npc={npc_id} BED not found, resting fallback to DEFAULT node {_ref.node_id}"
                            )

        if not target_entry:
            return None

        target_node = target_entry.get("position", "")
        target_location = target_entry.get("location", "")

        # SHI-FIX: No-op guard. Нормализуем ID узла, чтобы избежать mismatch.
        _loc = target_location or npc.get("location_id", "")
        _norm_target = target_node if ":" in target_node else f"{_loc}:{target_node}"
        _norm_current = (
            current_position
            if ":" in current_position
            else f"{_loc}:{current_position}"
        )
        if _norm_target == _norm_current:
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
        return MacroMovementGoal(
            actor_id=npc_id,
            target_node_id=target_node,
            from_node_id=npc.get("position", ""),
            location_id=target_location,
            reason=f"need_driven:{need_name}={need_value:.2f}",
            domain=IntentDomain.ROUTINE,
            priority=PRIORITY_NEEDS,
        )

    def _arousal_gate(self, npc: Dict[str, Any], tick: int) -> list[SceneChange]:
        """ADR-O-142A: Behavior transition gate — missing wake edge.

        Arousal Gate определяет, должен ли спящий NPC пробудиться.
        Это behavior transition gate, НЕ consciousness transition.
        Не трогает body_state["consciousness"].

        Формула (скорректирована по результатам сценарного анализа):
          wake_pressure  = threat*0.35 + (pain/100)*0.25 + directive_salience*0.3 + acoustic*0.1
          sleep_resistance = (fatigue/100)*0.4 + 0.05 + depth*0.1

        Ключевые сценарии:
          fatigue=0.1, threat=0.5      → pressure=0.175 > resist=0.09  → WAKE ✓
          fatigue=0.5, directive=0.8   → pressure=0.24  > resist=0.25  → спит (устал)
          fatigue=0.5, dir=0.8+thr=0.5 → pressure=0.415 > resist=0.25  → WAKE ✓
          fatigue=0.8, no stimuli      → pressure=0     < resist=0.37  → спит ✓
          fatigue=0.8, thr=0.8+pain=0.5→ pressure=0.405 > resist=0.37  → WAKE ✓

        Переход: sleeping/resting → idle (через SceneChange pipeline)
        Побочный эффект: routine["current"] = "" (нет активности)

        Returns:
            Список SceneChange если NPC пробуждён, [] если нет.
        """
        _routine = npc.get("routine", {})
        _current = _routine.get("current", "")

        # Gate применяется только к спящим NPC
        if "sleeping" not in _current and "resting" not in _current:
            return []

        # Когнитивный паралич (initiative_suppression > 0.7) замораживает ВСЁ,
        # включая пробуждение. NPC не может действовать — не может и проснуться.
        _kernel = npc.get("perceptual_kernel")
        _init_sup = (
            _kernel.get("initiative_suppression", 0.0)
            if isinstance(_kernel, dict)
            else getattr(_kernel, "initiative_suppression", 0.0)
            if _kernel
            else 0.0
        )
        if _init_sup > 0.7:
            return []

        # Attention Capture (recent_directive.interrupts_routine=True) замораживает
        # поведенческие переходы. Arousal Gate не должен перекрывать когнитивный захват.
        _rd = (
            _kernel.get("recent_directive")
            if isinstance(_kernel, dict)
            else getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA001, ENIGMA002
            if _kernel
            else None
        )
        if _rd and isinstance(_rd, dict) and _rd.get("interrupts_routine"):
            return []

        # ── Wake pressure ──────────────────────────────────────────────
        _threat = 0.0
        _directive_salience = 0.0
        if isinstance(_kernel, dict):
            _threat = _kernel.get("threat_gradient", 0.0)
            # Приказ от игрока — сильный сигнал пробуждения (но НЕ если interrupts_routine=True —
            # это уже обработано guard'ом выше)
            _directive_salience = 0.8 if _rd else 0.0
        elif _kernel:
            _threat = getattr(_kernel, "threat_gradient", 0.0)
            _directive_salience = 0.8 if _rd else 0.0

        _body = npc.get("body_state", {})
        if isinstance(_body, dict):
            # MSOC: pain/fatigue хранятся в 0-100, нормализуем к 0-1 (ADR-094)
            _pain = float(_body.get("pain", 0.0)) / 100.0
            _fatigue = float(_body.get("fatigue", 0.0)) / 100.0
        else:
            _pain = 0.0
            _fatigue = 0.0

        # BUG-SLEEP-008 FIX: Читаем acoustic_stimulus из npc (если инжектирован оркестратором).
        # По умолчанию 0.0, если событий громкого звука (крик, взрыв) поблизости нет.
        _acoustic = npc.get("acoustic_stimulus", 0.0)

        wake_pressure = (
            _threat * 0.35 + _pain * 0.25 + _directive_salience * 0.3 + _acoustic * 0.1
        )

        # ── Sleep resistance ───────────────────────────────────────────
        # SLEEP_FIX #6b: depth вычисляется из _sleep_start_tick, который
        # теперь записывается в update_routine (см. SLEEP_FIX #6a).
        # 20 тиков до полного depth (1.0). До этого NPC спит «поверхностно»
        # и легко пробуждается.
        _sleep_start = _routine.get("_sleep_start_tick", tick)
        _depth = min(1.0, max(0.0, (tick - _sleep_start) / 20.0))
        sleep_resistance = _fatigue * 0.4 + 0.05 + _depth * 0.1

        if wake_pressure > sleep_resistance:
            npc_id = npc.get("id", "unknown")
            logger.info(
                f"[AROUSAL_GATE] {npc_id}: WAKE — "
                f"pressure={wake_pressure:.3f} > resistance={sleep_resistance:.3f} "
                f"(threat={_threat:.2f}, pain={_pain:.2f}, directive={_directive_salience:.2f})"
            )

            # Transition: sleeping/resting → нет активности
            # НЕ вводим "awake" как состояние мира (ADR-O-142A constraint)
            _routine["current"] = ""
            # BUG-SLEEP-004 FIX: Сбрасываем _sleep_start_tick при пробуждении,
            # чтобы при следующем засыпании depth считался с нуля.
            _routine.pop("_sleep_start_tick", None)

            changes = [
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="activity",
                    value="",
                    cause="arousal_gate",
                    tick=tick,
                ),
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="visible",
                    value=True,
                    cause="arousal_gate",
                    tick=tick,
                ),
            ]

            return changes

        return []

    @staticmethod
    def _compute_viability_mask(npc: Dict[str, Any]) -> set[IntentDomain]:
        """ДОЛГ 4.3: Viability Projection — какие домены действий допустимы для NPC.

        Viability — не предпочтение, а физика возможностей.
        SURVIVAL давление (threat_gradient > 0.3) исключает ROUTINE из пространства генерации.
        NPC не может «выбрать» работу при угрозе — это не вопрос priority, а вопрос существования.

        Источник: PerceptualKernel (персистентен между тиками, доступен в Phase 0).
        НЕ использует DRF claims — viability локальна, claims для кросс-NPC давления.

        Returns:
            Множество ДОПУСТИМЫХ доменов. Отсутствие домена = действие невозможно.
        """
        _kernel = npc.get("perceptual_kernel")
        _threat = 0.0
        _init_sup = 0.0
        if isinstance(_kernel, dict):
            _threat = _kernel.get("threat_gradient", 0.0)
            _init_sup = _kernel.get("initiative_suppression", 0.0)
        elif _kernel:
            _threat = getattr(_kernel, "threat_gradient", 0.0)
            _init_sup = getattr(_kernel, "initiative_suppression", 0.0)

        _viable: set[IntentDomain] = {
            IntentDomain.SURVIVAL,
            IntentDomain.SOCIAL,
            IntentDomain.ROUTINE,
            IntentDomain.EXPLORATION,
        }

        # ADR-O-209: Trait-driven viability modulation.
        # Traumatized NPC входит в SURVIVAL режим при более низкой угрозе.
        _identity = npc.get("identity") or {}
        _active_traits = (
            _identity.active_traits
            if hasattr(_identity, "active_traits")
            else _identity.get("active_traits", {})
        )
        _trauma_mod = (
            _active_traits.get("traumatized", 0.0) * 0.25
        )  # Макс эффект: снижение порога с 0.3 до 0.05
        _survival_threshold = 0.3 - _trauma_mod

        # SURVIVAL ⟂ ROUTINE: угроза сжимает пространство — рутина невозможна
        if _threat > _survival_threshold:
            _viable.discard(IntentDomain.ROUTINE)

        # Паралич воли: подавление инициативы сжимает всё до SURVIVAL
        if _init_sup > 0.7:
            _viable.discard(IntentDomain.ROUTINE)
            _viable.discard(IntentDomain.EXPLORATION)
            _viable.discard(IntentDomain.SOCIAL)

        return _viable

    def _simulate_minor(
        self,
        npc: Dict[str, Any],
        current_time: str,
        tick: int,
        scene_state: Optional[Dict[str, Any]] = None,
        rng: Optional[KernelRNG] = None,
    ) -> tuple[list[SceneChange], list["MacroMovementGoal"]]:
        """
        Симуляция Minor NPC раз в MINOR_TICK_INTERVAL тиков.
        Только расписание + случайные события (без полного стресс-расчёта).
        ADR-049: Возвращает list["MacroMovementGoal"] вместо прямого исполнения.
        ДОЛГ 4.3: Viability Pre-Generation Gate — ROUTINE не генерируется при SURVIVAL давлении.
        """
        # S188 ARCH-SLEEP: Arousal Gate перенесён в SleepLifecycleService (Phase 0.6).
        # Оставление вызова здесь нарушает ADR-O-353 (двойное срабатывание пробуждения).

        _viable = self._compute_viability_mask(npc)
        changes: list[SceneChange] = []
        intents: list["MacroMovementGoal"] = []

        if IntentDomain.ROUTINE in _viable:
            routine_changes, routine_intent = self.update_routine(
                npc, current_time, tick, scene_state=scene_state
            )
            changes.extend(routine_changes)
            if routine_intent:
                routine_intent.domain = IntentDomain.ROUTINE
                intents.append(routine_intent)

        if IntentDomain.EXPLORATION in _viable:
            event_changes, event_intent = self.check_random_events(npc, tick, rng=rng)
            changes.extend(event_changes)
            if event_intent:
                event_intent.domain = IntentDomain.EXPLORATION
                intents.append(event_intent)

        return changes, intents

    # ─────────────────────────────────────────────────────────────────────────
    # update_routine — обновление по расписанию
    # ─────────────────────────────────────────────────────────────────────────

    def update_routine(
        self,
        npc: Dict[str, Any],
        current_time: str,
        tick: int = 0,
        scene_state: Optional[Dict[str, Any]] = None,
    ) -> tuple[list[SceneChange], Optional["MacroMovementGoal"]]:
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
        npc_id = npc.get("id", "unknown")
        _routine = npc.get("routine") or {}
        logger.debug(f"[DIAG_ROUTINE] npc={npc_id} routine={_routine}")
        schedule = _routine.get("schedule", {})

        # ADR-123: Мёртвые NPC не обновляют расписание. Зомби-NPC запрещены.
        if npc.get("body_state", {}).get("life_status") == "DEAD":
            return [], None

        if not schedule:
            return [], None

        # ADR-052: Cognitive Override Guard. Расписание игнорируется при параличе воли.
        # NPC не идет спать или на работу, если инициатива подавлена давлением (initiative_suppression > 0.7).
        _kernel = npc.get("perceptual_kernel")
        _recent_dir = (
            _kernel.get("recent_directive")
            if isinstance(_kernel, dict)
            else getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA001, ENIGMA002
            if _kernel
            else None
        )
        if _recent_dir and _recent_dir.get("interrupts_routine"):
            logger.debug(
                f"[LIFE_ENGINE] {npc_id}: Schedule bypassed due to Attention Capture from {_recent_dir.get('source')}"
            )
            # GAP9 FIX: Не сжигаем директиву мгновенно! Иначе на следующем тике LifeEngine снова уложит NPC спать,
            # перезаписав реактивный транзит (reactive:approach). Сон прерывается до снижения угрозы.
            return [], None

        # ADR-081: Physical Urgency Wake. Угроза пробуждает NPC из сна.
        # Скалярная оценка: если угроза рядом и велика — расписание ломается.
        _threat = (
            _kernel.get("threat_gradient", 0.0)
            if isinstance(_kernel, dict)
            else getattr(_kernel, "threat_gradient", 0.0)
            if _kernel
            else 0.0
        )
        if _threat > 0.7:
            logger.debug(
                f"[LIFE_ENGINE] {npc_id}: Schedule bypassed due to proximate physical threat ({_threat:.2f})"
            )
            return [], None

        # S139: Interruptibility Contract. Если NPC в активном транзите,
        # расписание может его прервать, ТОЛЬКО если это не боевой/критический транзит.
        if scene_state:
            _active_travs = scene_state.get("active_traversals", {})
            _my_trav = _active_travs.get(npc_id)
            if _my_trav and _my_trav.get("status") == "MOVING":
                _trav_reason = _my_trav.get("reason", "")
                # Non-interruptible: flee, combat, reactive threats.
                if "flee" in _trav_reason or "combat" in _trav_reason:
                    logger.debug(
                        f"[LIFE_ENGINE] {npc_id}: Schedule bypassed — non-interruptible traversal ({_trav_reason})"
                    )
                    return [], None
                # Social traversals (approach, seek_ally) are interruptible by schedule.
                # BUG-SPATIAL-037 FIX: Транзиты расписания не должны прерывать сами себя!
                if "schedule:" in _trav_reason:
                    return [], None

        new_activity = self._get_current_activity(schedule, current_time)
        if not new_activity:
            return [], None

        # Bridge 6: LifeProject → schedule mutation
        # ADR-O-317: В состоянии LOST или SEARCHING NPC игнорирует расписание (кризис идентичности).
        _psyche = npc.get("psyche", {})
        _life_project_state = _psyche.get("life_project_state", "ACTIVE")
        if _life_project_state in ("LOST", "SEARCHING"):
            logger.debug(
                f"[LIFE_ENGINE] {npc_id}: Schedule bypassed due to LifeProject crisis ({_life_project_state})"
            )
            return [], None

        # Bridge 6: Если жизненный проект сменился на кризисный (isolation, hermit, revenge),
        # NPC не ходит на работу, даже если FSM вернулся в ACTIVE. Fallback to resting.
        _life_project = _psyche.get("life_project", npc.get("core_orientation", "survival"))
        if _life_project in ("isolation", "hermit", "revenge", "survival") and new_activity == "working":
            new_activity = "resting"

        prev_activity = npc.get("routine", {}).get("current", "")

        # S89: Диагностика Schedule Freeze — отслеживание переходов активности
        if new_activity != prev_activity:
            logger.info(
                f"[SCHED_TRACE] npc={npc_id} prev={prev_activity!r} new={new_activity!r} CHANGE"
            )

        if new_activity == prev_activity:
            logger.debug(f"[DIAG_S140] {npc_id}: new={new_activity} == prev={prev_activity}")
            # S140: Spatial Verification. Если активность не сменилась, но NPC не на месте —
            # продолжаем генерировать MacroMovementGoal, пока он не дойдёт.
            _resolved = self._resolve_position(npc, new_activity)
            if not _resolved:
                logger.debug(f"[DIAG_S140] {npc_id}: _resolve_position returned None (1)")
                return [], None

            _exp_loc, _exp_pos, _ = _resolved
            _cur_loc = npc.get("location_id", npc.get("location", ""))
            _cur_pos = npc.get("position", "")

            # Нормализуем для сравнения
            _norm_exp_pos = _exp_pos if ":" in _exp_pos else f"{_exp_loc}:{_exp_pos}"
            _norm_cur_pos = _cur_pos if ":" in _cur_pos else f"{_cur_loc}:{_cur_pos}"
            logger.debug(f"[DIAG_S140] {npc_id}: exp_pos={_norm_exp_pos} cur_pos={_norm_cur_pos}")

            if _norm_exp_pos == _norm_cur_pos:
                logger.debug(f"[LIFE_ENGINE] {npc_id}: already at {_exp_pos} for {new_activity}.")
                return [], None

        # GAP9 FIX: Реалистичное Пробуждение. Если NPC напуган или в стрессе, он не может уснуть.
        # Угроза (threat_gradient) и стресс — непрерывные скаляры, в отличие от сгорающей директивы.
        if is_sleeping(new_activity):
            _threat = (
                _kernel.get("threat_gradient", 0.0)
                if isinstance(_kernel, dict)
                else getattr(_kernel, "threat_gradient", 0.0)
                if _kernel
                else 0.0
            )
            _stress = npc.get("psyche", {}).get("stress", 0.0) # V8-PSY-10 FIX
            logger.debug(f"[DIAG_GAP9] {npc_id}: threat={_threat:.2f} stress={_stress:.2f}")
            if _threat > 0.3 or _stress > 50:
                logger.debug(f"[DIAG_GAP9] {npc_id}: SLEEP BYPASSED!")
                logger.debug(
                    f"[LIFE_ENGINE] {npc_id}: Sleep bypassed — threat={_threat:.2f}, stress={_stress}"
                )
                # V8-PSY-FIX: Обновляем рутину на sleeping, чтобы DecisionHub подавил социализацию.
                # Это позволяет apply_tick_recovery (Phase 2) давать x3 восстановление стресса,
                # пока NPC не может дойти до кровати из-за высокого стресса. Когда стресс
                # упадёт ниже 50, GAP9 пропустит сон и NPC дойдёт до кровати.
                npc["routine"]["current"] = "sleeping"
                return [], None

        resolved = self._resolve_position(npc, new_activity)
        if resolved is None:
            # ADR-S85.1: не удалось резолвить позицию — пропускаем movement intent,
            # NPC остаётся на месте. Лог уже записан в _resolve_position.
            return [], None
        new_location, new_position, activity_display = resolved

        # BUG-DRIFT-010 FIX: Нормализуем target_node_id, добавляя префикс локации.
        # Без этого movement_engine в исходной локации не может однозначно определить target_loc
        # и гоняет NPC по boundary-узлам бесконечно ("батут" S186_TRANSFER).
        if new_position and ":" not in new_position and new_location:
            new_position = f"{new_location}:{new_position}"

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

        going_to_sleep = is_sleeping(new_activity)
        changes.append(
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="visible",
                value=not going_to_sleep,
                cause="life_engine_schedule",
                tick=tick,
            )
        )

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

        # SHI-FIX: No-op guard. Если NPC уже на целевом узле — не генерируем MovementIntent.
        # Нормализуем ID узла, чтобы избежать mismatch (bar_area vs tavern_silver_wolf:bar_area).
        _loc = new_location or prev_location
        _norm_new_pos = (
            new_position if ":" in new_position else f"{_loc}:{new_position}"
        )
        _norm_curr_pos = (
            npc.get("position", "")
            if ":" in npc.get("position", "")
            else f"{_loc}:{npc.get('position', '')}"
        )
        if _norm_new_pos == _norm_curr_pos:
            logger.debug(
                f"[LIFE_ENGINE] {npc_id}: no-op movement (уже на {new_position})."
            )
            return changes, None

        # ── MovementIntent для MovementEngine (Слой 2) ────────────────────
        from app.domain.movement import PRIORITY_SCHEDULE

        # ADR-0010: movement_mode удалён. Макро-перемещение — Semantic Relocation.
        intent = MacroMovementGoal(
            actor_id=npc_id,
            target_node_id=new_position,
            from_node_id=npc.get("position", ""),
            location_id=new_location,
            reason=f"schedule:{new_activity}",
            domain=IntentDomain.ROUTINE,  # ДОЛГ 4.3: Расписание = рутина
            priority=PRIORITY_SCHEDULE,
        )

        # ── Обновляем NPC dict в памяти ────────────────────────────────────
        routine = npc.setdefault("routine", {})
        routine["current"] = new_activity
        routine["mood"] = self._mood_for_activity(new_activity)
        if "interrupted" not in routine:
            routine["interrupted"] = False
        # SLEEP_FIX #6a: записываем _sleep_start_tick для расчёта depth сна
        # в _arousal_gate. Без этого depth всегда 0.0 (TODO автора кода).
        if new_activity == "sleeping":
            routine["_sleep_start_tick"] = tick
        else:
            routine.pop("_sleep_start_tick", None)
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

    def _get_current_activity(self, schedule: Dict[str, Any], current_time: str) -> str:
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
        npc: Dict[str, Any],
        activity: str,
    ) -> Optional[tuple[str, str, str]]:
        """Возвращает (location_id, position_in_scene, activity_display) или None.

        ADR-S85.1: позиция NPC резолвится ТОЛЬКО через:
          1. npc.activity_map[activity] (data-driven, приоритет)
          2. SpatialService.resolve_node(role, origin_zone) (семантический биндинг)
          3. SpatialService.resolve_node(NodeRole.DEFAULT, origin_zone) (последний шанс)
          4. Текущая позиция NPC (no-op fallback — остаться на месте)

        Хардкод "common_area" удалён (BUG-3: NODE_NOT_FOUND, нарушение §13).
        Если ни один источник не дал позицию — возвращается None,
        вызывающий код обрабатывает как no-op movement (без intent).
        """
        npc_map: Dict[str, Any] = npc.get("activity_map", {})

        # 1. Точное совпадение в activity_map (data-driven)
        if activity in npc_map:
            entry = npc_map[activity]
            return (entry["location"], entry["position"], entry["display"])

        # 2. S85: Semantic Spatial Binding — резолв через SpatialService по роли
        if self._spatial_service:
            from app.models.spatial_contracts import NodeRole

            _ACTIVITY_TO_ROLE_MAP = {
                # Питьё/еда — социальные точки
                "drinking": NodeRole.BAR,
                "eating": NodeRole.TABLE,

                # Рабочие точки (конкретные)
                "serving_tables": NodeRole.SERVING_STATION,
                "cleaning_tables": NodeRole.TABLE,
                "guarding_gate": NodeRole.GUARD_POST,
                "observing": NodeRole.DARK_CORNER,
                "innkeeping": NodeRole.INN_DESK,

                # Базовые
                "sleeping": NodeRole.BED,
                "resting": NodeRole.BED,
                "working": NodeRole.WORKBENCH,
                "idle": NodeRole.DEFAULT,
                "active": NodeRole.TABLE,
                "planning": NodeRole.TABLE,
                "socializing": NodeRole.BAR,
                "haggling": NodeRole.MARKET,
            }
            role = _ACTIVITY_TO_ROLE_MAP.get(activity)
            if role:
                # ADR-O-326: Ищем персональное рабочее место NPC по тегу
                _npc_id = npc.get("id", "")
                _workplace_tag = f"workplace:{_npc_id}"

                # ADR-O-330: Affordance Compatibility Adapter для сна
                _npc_xy = npc.get("local_position", {})
                _origin_xy = (_npc_xy.get("x", 0.0), _npc_xy.get("y", 0.0))
                if role == NodeRole.BED and hasattr(self._spatial_service, 'resolve_affordance'):
                    ref = self._spatial_service.resolve_affordance(
                        affordance_type="sleep",
                        origin_xy=_origin_xy,
                        origin_zone=npc.get("location_id"),
                        owner=npc.get("id")
                    )
                else:
                    ref = self._spatial_service.resolve_node(
                        role=role, origin_zone=npc.get("location_id"),
                        filters=[_workplace_tag] if _workplace_tag else None  # noqa: ENIGMA001
                    )
                # Fallback: Если персонального места нет, ищем любое по роли
                if not ref:
                    ref = self._spatial_service.resolve_node(
                        role=role, origin_zone=npc.get("location_id")
                    )
                if ref:
                    return (ref.zone_id, ref.node_id, activity)

            # 3. Fallback: NodeRole.DEFAULT в текущей локации NPC
            #    Паттерн уже используется в life_engine (см. _NEED_ROLE_MAP).
            origin_zone = npc.get("location_id")
            if origin_zone:
                default_ref = self._spatial_service.resolve_node(
                    role=NodeRole.DEFAULT,
                    origin_zone=origin_zone,
                )
                if default_ref:
                    logger.debug(
                        f"[LIFE_ENGINE][DEFAULT_NODE] npc={npc.get('id')} "
                        f"activity={activity!r} -> default node {default_ref.node_id} "
                        f"in zone={origin_zone}"
                    )
                    return (default_ref.zone_id, default_ref.node_id, activity)

        # 4. Last-resort: NPC остаётся на текущей позиции (no-op movement)
        #    НЕ выдумываем node_id — это и есть фикс ADR-S85.1 + §13.
        current_location = npc.get("location_id")
        current_position = npc.get("position")

        # ADR-GUARD: position recovery must be deterministic
        # SpatialService is allowed ONLY if mapping table exists or confidence == 1.0
        if not current_position or not isinstance(current_position, str):
            _lp = npc.get("local_position", {})
            if (
                isinstance(_lp, dict)
                and isinstance(_lp.get("x"), (int, float))
                and self._spatial_service
            ):
                origin_zone = current_location
                if origin_zone:
                    _ref = self._spatial_service.get_nearest(
                        zone_id=origin_zone, origin_xy=(_lp["x"], _lp["y"])
                    )
                    if _ref:
                        current_position = getattr(_ref, "node_id", str(_ref))
                        assert isinstance(current_position, str)
                        if current_position.startswith(f"{origin_zone}:"):
                            current_position = current_position.split(":")[-1]
                        if getattr(_ref, "confidence", 1.0) < 1.0:
                            logger.warning(
                                f"[POSITION_RECOVERY][LOW_CONFIDENCE] npc={npc.get('id')} "
                                f"node={current_position} confidence={getattr(_ref, 'confidence', None)}"  # noqa: ENIGMA002
                            )
                        else:
                            logger.info(
                                f"[LIFE_ENGINE][POSITION_RECOVERY] npc={npc.get('id')} recovered position={current_position} from local_position={_lp}"
                            )

        if current_location and current_position and isinstance(current_position, str):
            logger.warning(
                f"[LIFE_ENGINE][NO_RESOLVE] npc={npc.get('id')} activity={activity!r} "
                f"unresolved by activity_map/SpatialService; staying at "
                f"location={current_location} position={current_position}"
            )
            return (current_location, current_position, activity)

        # 5. Нет ни location, ни position — критическая аномалия данных
        logger.error(
            f"[LIFE_ENGINE][NO_POSITION] npc={npc.get('id')} has no location AND no position. "
            f"Activity={activity!r}. Data integrity bug — investigate npc_state. "
            f"Returning None; caller must skip movement intent."
        )
        return None

    @staticmethod
    def _mood_for_activity(activity: str) -> str:
        """Определяет настроение NPC по активности."""
        _mood_map = {
            "sleeping": "neutral",
            "resting": "neutral",
            "working": "focused",
            "on_duty": "alert",
            "eating": "content",
            "drinking": "relaxed",
            "haggling": "focused",
            "hiding": "tense",
        }
        return _mood_map.get(activity, "neutral")

    # ─────────────────────────────────────────────────────────────────────────
    # check_random_events — случайные события
    # ─────────────────────────────────────────────────────────────────────────

    def check_random_events(
        self,
        npc: Dict[str, Any],
        tick: int = 0,
        rng: Optional[KernelRNG] = None,
    ) -> tuple[list[SceneChange], Optional["MacroMovementGoal"]]:
        """
        С вероятностью RANDOM_EVENT_CHANCE (5%) генерирует случайное событие.
        Возвращает список SceneChange или пустой список.

        Спящие NPC не получают случайных событий.

        KERNEL-ISOLATION: rng must be provided for replay determinism.
        """
        npc_id = npc.get("id", "unknown")
        if rng is None:
            # KERNEL-ISOLATION: Фоллбэк с salt="life_events" для изоляции потока.
            rng = KernelRNG(tick=tick, npc_id=npc_id, salt="life_events")
        activity = npc.get("routine", {}).get("current", "")

        if is_sleeping(activity):
            return [], None

        # ADR-052: Парализованный страхом NPC не инициирует случайные события
        _kernel = npc.get("perceptual_kernel")
        _init_sup = (
            _kernel.get("initiative_suppression", 0.0)
            if isinstance(_kernel, dict)
            else getattr(_kernel, "initiative_suppression", 0.0)
            if _kernel
            else 0.0
        )
        _recent_dir = (
            _kernel.get("recent_directive")
            if isinstance(_kernel, dict)
            else getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA001, ENIGMA002
            if _kernel
            else None
        )
        if _init_sup > 0.7:
            return [], None

        # KERNEL-ISOLATION: deterministic RNG.
        if rng.random() > RANDOM_EVENT_CHANCE:
            return [], None

        events = self._make_random_events(npc, tick)
        event_id, changes, movement_intent = rng.choice(events)

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

    def recover_stress_tick(self, npc: Dict[str, Any]) -> None:
        """
        Восстанавливает стресс NPC за один тик.
        Спящие восстанавливаются быстрее.
        """
        activity = npc.get("routine", {}).get("current", "")
        _is_sleeping = is_sleeping(activity)

        psyche = npc.setdefault("psyche", {})
        current_stress = psyche.get("stress", 0)

        if current_stress <= 0:
            return

        recovery = STRESS_RECOVERY_SLEEPING if _is_sleeping else STRESS_RECOVERY_SAFE
        psyche["stress"] = max(0, current_stress - recovery)

        # BUG-SLEEP-002 FIX: Sleep restores fatigue 7x faster than waking rest.
        # Без этого сон бесполезен функционально — усталость убывает одинаково быстро и днём, и ночью.
        _fatigue_rate = 0.20 if _is_sleeping else 0.03
        _drives = npc.setdefault("drives_runtime", {})
        _curr_fatigue = _drives.get("fatigue", 0.0)
        if _curr_fatigue > 0:
            _drives["fatigue"] = max(0.0, _curr_fatigue - _fatigue_rate)


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

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
from datetime import datetime
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
    TICK_SAVE_INTERVAL,
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
_DEFAULT_ACTIVITY_MAP: dict[str, tuple[str, str, str]] = {          
    "working":   ("tavern_silver_wolf", "behind_bar",     "working"),
    "sleeping": ("tavern_silver_wolf", "corner_table",  "sleeping"),
    "on_duty":   ("tavern_silver_wolf", "entrance",     "on_duty"),
    "off Duty":  ("tavern_silver_wolf", "corner_table",  "resting"),
    "resting":   ("tavern_silver_wolf", "corner_table",  "resting"),
    "eating":    ("tavern_silver_wolf", "corner_table",  "eating"),
    "drinking":  ("tavern_silver_wolf", "bar_area",     "drinking"),
}

# ──────────────────────────────────────────────────────────────────────────────
# Случайные события
# Формат: (event_id, описание_для_лога, генератор SceneChange)
# Генератор получает npc dict и возвращает list[SceneChange]
# ──────────────────────────────────────────────────────────────────────────────

def _make_random_events(npc: dict, tick: int) -> list:
    """
    Таблица случайных событий для Major NPC.
    5% шанс одного события за тик.
    Возвращает список (event_id, changes, intent_or_none) из которых выбирается одно.
    changes — SceneChange без position (activity, state и т.д.)
    intent — MovementIntent если событие требует перемещения, иначе None
    """
    npc_id   = npc.get("id", "unknown")
    location = npc.get("location", "tavern_silver_wolf")

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
            target_node_id="near_bar",
            from_node_id=npc.get("position", ""),
            location_id=location,
            reason="random:wanders_to_bar",
            movement_mode="path",
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
    if ":" in str(tod):
        return str(tod)
    return "12:00"


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
        
        # Кэш sim_tick для быстрого доступа (копия JSON)
        # ключ: campaign_id → int
        self._tick_cache: dict[str, int] = {}
                
        # LRU tracking для HOT кэша
        # ключ: campaign_id → timestamp последнего доступа
        self._last_access: OrderedDict[str, float] = OrderedDict()
        
        # Фаза 2.2 — in-memory давление NPC (не персистентно, сбрасывается при рестарте)
        # ключ: (campaign_id, npc_id) → float
        self._idle_pressure: dict[tuple[str, str], float] = {}
        
        # Счётчик для batched persistence
        # ключ: campaign_id → int (сколько тиков с последнего save)
        self._ticks_since_save: dict[str, int] = {}
        
        # Слой 2: MovementEngine — конвертирует MovementIntent → SceneChange с {x, y}
        self._movement_engine = MovementEngine()

    def set_transit_tracker(self, tracker) -> None:
        """Пробрасывает TransitTracker в MovementEngine для pathing."""
        self._movement_engine.set_transit_tracker(tracker)

    # ─────────────────────────────────────────────────────────────────────────
    # Tick Architecture (Блок 1)
    # ─────────────────────────────────────────────────────────────────────────

    def _tick_file_path(self, campaign_id: str) -> Path:
        """Путь к файлу persistent tick."""
        return self.sessions_dir / campaign_id / "world_tick.json"

    def _load_tick(self, campaign_id: str) -> int:
        """
        Загружает sim_tick из JSON (COLD storage).
        Возвращает 0 если файл не существует или повреждён.
        """
        path = self._tick_file_path(campaign_id)
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data.get("sim_tick", 0)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[LIFE_ENGINE] Ошибка чтения tick: {e}")
            return 0

    def _save_tick(self, campaign_id: str, tick: int) -> None:
        """
        Сохраняет sim_tick в JSON (COLD storage).
        Вызывается автоматически (batched) или вручную (flush_ticks).
        """
        path = self._tick_file_path(campaign_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Читаем существующий файл чтобы сохранить created_at
        _existing = {}
        if path.exists():
            try:
                _existing = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                pass

        data = {
            "sim_tick": tick,
            "updated_at": datetime.now().isoformat(),
            # created_at пишется один раз при создании — не перезаписывается
            "created_at": _existing.get("created_at") or datetime.now().isoformat(),
        }
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"[LIFE_ENGINE] Ошибка сохранения tick: {e}")


    def get_idle_seconds(self, campaign_id: str) -> float:
        """
        Сколько секунд прошло с последнего тика.
        Возвращает inf если тик никогда не был.
        """
        path = self._tick_file_path(campaign_id)
        if not path.exists():
            return float('inf')
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            last_ts = data.get("updated_at")
            if not last_ts:
                return float('inf')
            last_dt = datetime.fromisoformat(last_ts)
            return (datetime.now() - last_dt).total_seconds()
        except (json.JSONDecodeError, OSError, ValueError):
            return float('inf')

    def get_world_ticks_elapsed(self, campaign_id: str) -> int:
        """
        Вычисляет сколько тиков ДОЛЖНО было пройти с момента создания кампании.
        Основан на реальном времени (world_time), не на sim_tick.
        Персистентен — не зависит от рестартов сервера.
        """
        from app.core.constants import TICK_REAL_SECONDS
        path = self._tick_file_path(campaign_id)
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            created_at = data.get("created_at")
            if not created_at:
                return self.get_current_tick(campaign_id)
            elapsed = (datetime.now() - datetime.fromisoformat(created_at)).total_seconds()
            return int(elapsed // TICK_REAL_SECONDS)
        except (json.JSONDecodeError, OSError, ValueError):
            return self.get_current_tick(campaign_id)

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
                if routine_intent:
                    movement_changes = self._movement_engine.process_intents(
                        [routine_intent], tick=0,
                    )
                    all_changes.extend(movement_changes)
                
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
        return all_changes

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
        self._tick_cache.pop(campaign_id, None)
        self._last_access.pop(campaign_id, None)
        self._ticks_since_save.pop(campaign_id, None)

    def cleanup_all_campaigns(self) -> int:
        """
        Очистка всего HOT + flush всех ticks.
        COLD storage (JSON) сохраняется, но не удаляется.
        """
        self.flush_ticks()  # Сначала сохраняем
        count = len(self._npc_cache)
        self._npc_cache.clear()
        self._tick_cache.clear()
        self._last_access.clear()
        self._ticks_since_save.clear()
        logger.info(f"[LIFE_ENGINE] cleared all HOT cache: {count} campaigns")
        return count

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────────

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
        npcs = self._npc_cache.get(campaign_id)
        if not npcs:
            npcs = load_npcs_merged(runtime_path=runtime_path)
        all_changes: list[SceneChange] = []
        npcs_updated = False

        for npc in npcs:
            tier   = npc.get("tier", "major")
            npc_id = npc.get("id", "?")

            try:
                # ── MAJOR: полная симуляция каждый тик ──────────────────────
                if tier == "major":
                    changes = self._simulate_major(npc, current_time, current_tick)
                    all_changes.extend(changes)
                    npcs_updated = True

                # ── MINOR: расписание + случайные события раз в N тиков ─────
                elif tier == "minor":
                    last_minor = npc.get("routine", {}).get("_last_life_tick", 0)
                    if (current_tick - last_minor) >= MINOR_TICK_INTERVAL:
                        changes = self._simulate_minor(npc, current_time, current_tick)
                        all_changes.extend(changes)
                        npc.setdefault("routine", {})["_last_life_tick"] = current_tick
                        npcs_updated = True

                # ── MASS: только проверяем присутствие (0ms) ─────────────────
                elif tier == "mass":
                    pass

            except Exception as e:
                logger.error(f"[LIFE_ENGINE] Ошибка при обработке NPC '{npc_id}': {e}")

        # Кэш уже обновлён in-place (NPC — словари, изменения применились)
        if npcs_updated:
            self._npc_cache[campaign_id] = npcs

        logger.info(
            f"[LIFE_ENGINE] Тик #{current_tick} завершён: "
            f"{len(all_changes)} SceneChange сгенерировано"
        )
        return all_changes

    def tick_decisions(
        self,
        campaign_id: str,
        scene_state: dict,
        runtime_path: Optional[Path] = None,
    ) -> list[dict]:
        """
        Фаза 2.1 — DecisionHub для NPC в idle tick.
        Чистая математика, без LLM.
        
        Возвращает список dicts для триггера телеграфа на клиенте.
        Формат совместим с significant_events в routes.py.
        """
        from app.core.constants import (
            IDLE_DECISION_SCORE_THRESHOLD,
            IDLE_PRESSURE_ACCUM_RATE,
            IDLE_PRESSURE_DECAY_RATE,
        )
        from app.services.npc.decision_hub import DecisionHub, EventContext
        from app.services.npc.npc_loader import (
            load_npcs_merged,
            load_profile_from_legacy_json,
            load_l2_state_from_runtime_dict,
        )
        from app.services.events.event_types import EventType
        from app.models.npc_state import WillState

        # Используем правильный загрузчик (config + runtime), а не major_npcs.json
        npcs = load_npcs_merged(runtime_path=runtime_path)
        hub = DecisionHub()
        decisions: list[dict] = []
        print(f"[TICK_DECISIONS] start: {len(npcs)} NPCs")

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

                # Контекст для idle tick — низкая интенсивность, нет стимула
                event = EventContext(
                    event_type=EventType.IDLE,
                    actor_id=npc_id,
                    success=True,
                    intensity=0.2,
                    distance=0.0,
                    witness_count=0,
                    location=scene_state.get("location_id", ""),
                    scene_flags=set(scene_state.get("active_flags", [])),
                    scene_facts=[],
                )

                result = hub.compute(
                    state=state_l2,
                    personality=profile_l0,
                    event=event,
                    scene_state=scene_state,
                    social_modifiers=None,
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
                
                # Триггер когда давление накопилось
                if _new_pressure >= IDLE_DECISION_SCORE_THRESHOLD:
                    decisions.append({
                        "npc_id": npc_id,
                        "cause": "idle_pressure",
                        "type": "proactive",
                        "target": npc_id,
                        "field": "intent",
                        "value": f"{result.intent.value if result.intent else 'observe'}",
                    })
                    # Сброс давления после триггера
                    self._idle_pressure[_key] = 0.0

            except Exception as e:
                import traceback
                logger.warning(f"[LIFE_ENGINE] Idle decision error for {npc_id}: {e}\n{traceback.format_exc()}")
                print(f"[TICK_DECISIONS] error: {npc_id} → {e}")
                print(traceback.format_exc())
                continue

        print(f"[TICK_DECISIONS] end: {len(decisions)} decisions")
        return decisions

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
        Инкрементирует sim_tick с hybrid persistence.
        
        Порядок:
          1. Прочитать текущий (из RAM кэша или JSON)
          2. +1
          3. Записать в RAM кэш (всегда)
          4. Записать в JSON (раз в TICK_SAVE_INTERVAL тиков)
        
        Возвращает новый tick.
        """
        current = self._tick_cache.get(campaign_id)
        if current is None:
            # Прочитать из JSON
            current = self._load_tick(campaign_id)
        
        new_tick = current + 1
        
        # Обновить HOT (RAM) — всегда
        self._tick_cache[campaign_id] = new_tick
        
        # Hybrid persistence: COLD (JSON) раз в N тиков
        unsaved = self._ticks_since_save.get(campaign_id, 0) + 1
        if unsaved >= TICK_SAVE_INTERVAL:
            self._save_tick(campaign_id, new_tick)
            self._ticks_since_save[campaign_id] = 0
        else:
            self._ticks_since_save[campaign_id] = unsaved
        
        return new_tick

    def flush_ticks(self, campaign_id: Optional[str] = None) -> None:
        """
        Принудительная запись tick(s) в JSON.
        Вызывать при: shutdown, critical event, manual save.
        """
        if campaign_id:
            tick = self._tick_cache.get(campaign_id)
            if tick is not None:
                self._save_tick(campaign_id, tick)
                self._ticks_since_save[campaign_id] = 0
        else:
            # Flush all
            for cid, tick in self._tick_cache.items():
                self._save_tick(cid, tick)
            self._ticks_since_save.clear()

    def get_current_tick(self, campaign_id: str) -> int:
        """
        Возвращает текущий sim_tick (без инкремента).
        Читает из RAM кэша, fallback — из JSON.
        """
        cached = self._tick_cache.get(campaign_id)
        if cached is not None:
            return cached
        return self._load_tick(campaign_id)

    def invalidate_cache(self, campaign_id: str) -> None:
        """
        Сбрасывает HOT кэш NPC для campaign_id.
        Вызвать если major_npcs.json был изменён извне (например, SandboxHandler).
        """
        self._npc_cache.pop(campaign_id, None)

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
                npcs = json.loads(campaign_file.read_text(encoding="utf-8"))
                self._npc_cache[campaign_id] = npcs
                return npcs
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[LIFE_ENGINE] Ошибка чтения campaign NPC: {e}")
        
        # Fallback: глобальный файл
        global_file = self._npcs_file()
        if global_file.exists():
            try:
                npcs = json.loads(global_file.read_text(encoding="utf-8"))
                self._npc_cache[campaign_id] = npcs
                return npcs
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[LIFE_ENGINE] Ошибка чтения global NPC: {e}")
        
        return []

    # ─────────────────────────────────────────────────────────────────────────
    # Симуляция по тирам
    # ─────────────────────────────────────────────────────────────────────────

    def _simulate_major(
        self,
        npc: dict,
        current_time: str,
        tick: int,
    ) -> tuple[list[SceneChange], "MovementIntent | None"]:
        """
        Полная симуляция Major NPC за один тик.
        Порядок: need-driven → расписание → стресс → случайные события.
        Need-driven имеет приоритет: если потребность критична — schedule пропускается.
        """
        changes: list[SceneChange] = []

        # ── D6: сбор всех intent-ов с приоритетами ──
        candidates: list[MovementIntent] = []

        # 1. Need-driven: растим потребности, проверяем порог
        self._tick_needs(npc)
        need_intent = self._check_need_driven_movement(npc)
        if need_intent:
            candidates.append(need_intent)

        # 2. Расписание (всегда генерирует, но может быть None)
        routine_changes, routine_intent = self.update_routine(npc, current_time, tick)
        changes.extend(routine_changes)
        if routine_intent:
            candidates.append(routine_intent)

        # 3. Случайные события (5% шанс) — могут породить intent
        event_changes = self.check_random_events(npc, tick)
        changes.extend(event_changes)

        # 4. Восстанавливаем стресс (без SceneChange — только данные NPC)
        self.recover_stress_tick(npc)

        # ── D6: выбираем лучший intent по priority ──
        if candidates:
            candidates.sort(key=lambda i: i.priority, reverse=True)
            winner = candidates[0]
            intent_changes = self._movement_engine.process_intents(
                [winner], tick=tick,
            )
            changes.extend(intent_changes)
            # Обновляем activity в scene_state
            if winner.reason.startswith("need_driven:"):
                target_activity = _NEED_TO_ACTIVITY.get(
                    winner.reason.split(":")[1].split("=")[0], ""
                )
                if target_activity:
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

        return changes

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

        # Обновляем NPC dict in-place (для следующего тика)
        npc["position"] = target_node
        if target_location:
            npc["location"] = target_location
        npc.get("routine", {})["current"] = target_activity

        from app.domain.movement import PRIORITY_NEEDS
        return MovementIntent(
            npc_id=npc_id,
            target_node_id=target_node,
            from_node_id=npc.get("position", ""),
            location_id=target_location,
            reason=f"need_driven:{need_name}={need_value:.2f}",
            priority=PRIORITY_NEEDS,
            movement_mode="path",
        )

    def _simulate_minor(
        self,
        npc: dict,
        current_time: str,
        tick: int,
    ) -> list[SceneChange]:
        """
        Симуляция Minor NPC раз в MINOR_TICK_INTERVAL тиков.
        Только расписание + случайные события (без полного стресс-расчёта).
        """
        changes: list[SceneChange] = []
        routine_changes, routine_intent = self.update_routine(npc, current_time, tick)
        changes.extend(routine_changes)
        if routine_intent:
            movement_changes = self._movement_engine.process_intents(
                [routine_intent], tick=tick,
            )
            changes.extend(movement_changes)
        event_changes = self.check_random_events(npc, tick)
        changes.extend(event_changes)
        return changes

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

        new_activity = self._get_current_activity(schedule, current_time)
        if not new_activity:
            return [], None

        prev_activity = npc.get("routine", {}).get("current", "")

        if new_activity == prev_activity:
            return [], None

        new_location, new_position, activity_display = self._resolve_position(
            npc, new_activity
        )

        prev_location = npc.get("location", new_location)
        changes: list[SceneChange] = []

        # ── Генерируем SceneChange (БЕЗ position — через MovementEngine) ──

        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="activity",
            value=activity_display,
            cause="life_engine_schedule",
            tick=tick,
        ))

        going_to_sleep = "sleeping" in new_activity or "resting" in new_activity
        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="visible",
            value=not going_to_sleep,
            cause="life_engine_schedule",
            tick=tick,
        ))

        if new_location != prev_location:
            changes.append(SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="location",
                value=new_location,
                cause="life_engine_schedule",
                tick=tick,
            ))
            logger.info(
                f"[LIFE_ENGINE] {npc_id}: {prev_location} → {new_location} "
                f"(активность: {prev_activity} → {new_activity})"
            )

        # ── MovementIntent для MovementEngine (Слой 2) ────────────────────
        from app.domain.movement import PRIORITY_SCHEDULE
        intent = MovementIntent(
            npc_id=npc_id,
            target_node_id=new_position,
            from_node_id=npc.get("position", ""),
            location_id=new_location,
            reason=f"schedule:{new_activity}",
            priority=PRIORITY_SCHEDULE,
            movement_mode="path",
        )

        # ── Обновляем NPC dict в памяти ────────────────────────────────────
        routine = npc.setdefault("routine", {})
        routine["current"]   = new_activity
        routine["mood"]      = self._mood_for_activity(new_activity)
        if "interrupted" not in routine:
            routine["interrupted"] = False
        npc["location"] = new_location
        npc["position"] = new_position

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
        for time_range, activity in schedule.items():
            if _in_time_range(time_range, current_minutes):
                return activity
        return ""

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

        for key, entry in npc_map.items():
            if activity.startswith(key) or key.startswith(activity):
                return (entry["location"], entry["position"], entry["display"])

        if activity in _DEFAULT_ACTIVITY_MAP:
            return _DEFAULT_ACTIVITY_MAP[activity]

        return ("tavern_silver_wolf", "common_area", activity)

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
            return []

        if random.random() > RANDOM_EVENT_CHANCE:
            return []

        events = _make_random_events(npc, tick)
        event_id, changes, movement_intent = random.choice(events)

        if event_id == "minor_argument":
            psyche = npc.setdefault("psyche", {})
            psyche["stress"] = min(100, psyche.get("stress", 0) + 10)

        logger.info(f"[LIFE_ENGINE] {npc_id}: случайное событие '{event_id}'")

        # Если событие требует перемещения — через MovementEngine
        if movement_intent:
            movement_changes = self._movement_engine.process_intents(
                [movement_intent], tick=tick,
            )
            changes.extend(movement_changes)

        return changes

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
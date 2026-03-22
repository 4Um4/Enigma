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
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.scene_change import (
    SceneChange,
    ChangeType,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Константы и маппинги
# ──────────────────────────────────────────────────────────────────────────────

# Для Minor NPC: тик симуляции раз в N тиков
_MINOR_TICK_INTERVAL = 3

# Вероятность случайного события за один тик (5%)
_RANDOM_EVENT_CHANCE = 0.05

# Восстановление стресса за тик (см. psyche_engine)
_STRESS_RECOVERY_SAFE    = 5    # безопасное место, бодрствует
_STRESS_RECOVERY_SLEEPING = 15  # спит

# ──────────────────────────────────────────────────────────────────────────────
# Маппинг: npc_id → activity → (location_id, position_in_scene, activity_display)
#
# Используется в update_routine() для генерации NPC_POSITION SceneChange.
# При sleeping NPC покидает основную сцену и уходит в inn_rooms/home.
# ──────────────────────────────────────────────────────────────────────────────
_NPC_ACTIVITY_MAP: dict[str, dict[str, tuple[str, str, str]]] = {
    "tavern_keeper_tornin": {
        "working":        ("tavern_silver_wolf", "behind_bar",       "cleaning_tables"),
        "sleeping":       ("inn_rooms",          "bed",              "sleeping"),
        "eating":         ("tavern_silver_wolf", "corner_table",     "eating"),
        "resting":        ("inn_rooms",          "bed",              "resting"),
    },
    "maid_lusya": {
        "working":        ("tavern_silver_wolf", "serving_table_3",  "serving_tables"),
        "sleeping":       ("inn_rooms",          "bed",              "sleeping"),
        "eating":         ("tavern_silver_wolf", "corner_table",     "eating"),
        "resting":        ("inn_rooms",          "bed",              "resting"),
    },
    "guard_borko": {
        "on_duty":        ("city_gate",          "gate_post",        "guarding_gate"),
        "off_duty":       ("tavern_silver_wolf", "corner_table",     "resting"),
        "sleeping":       ("inn_rooms",          "bed",              "sleeping"),
        "working":        ("city_gate",          "gate_post",        "guarding_gate"),
    },
    "merchant_goran": {
        "working":        ("market_square",      "stall_3",          "haggling"),
        "sleeping":       ("inn_rooms",          "bed",              "sleeping"),
        "on_duty":        ("market_square",      "stall_3",          "haggling"),
        "off_duty":       ("tavern_silver_wolf", "corner_table",     "drinking"),
    },
    "thief_shadow": {
        "working":        ("tavern_silver_wolf", "corner_table",     "observing"),
        "sleeping":       ("inn_rooms",          "bed",              "sleeping"),
        "scouting":       ("city_gate",          "shadows_near_gate","hiding"),
        "off_duty":       ("tavern_silver_wolf", "corner_table",     "observing"),
    },
}

# Fallback для неизвестных NPC
_DEFAULT_ACTIVITY_MAP: dict[str, tuple[str, str, str]] = {
    "working":   ("tavern_silver_wolf", "common_area",  "working"),
    "sleeping":  ("inn_rooms",          "bed",          "sleeping"),
    "on_duty":   ("city_gate",          "gate_post",    "on_duty"),
    "off_duty":  ("tavern_silver_wolf", "corner_table", "resting"),
    "resting":   ("inn_rooms",          "bed",          "resting"),
    "eating":    ("tavern_silver_wolf", "corner_table", "eating"),
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
    Возвращает список (event_id, changes) из которых выбирается одно.
    """
    npc_id   = npc.get("id", "unknown")
    location = npc.get("location", "tavern_silver_wolf")

    return [
        # NPC переходит к стойке поговорить с кем-то
        ("wanders_to_bar", [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="position",
                value="near_bar",
                cause="life_engine_random",
                tick=tick,
            ),
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="activity",
                value="talking_at_bar",
                cause="life_engine_random",
                tick=tick,
            ),
        ]),
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
        ]),
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
        ]),
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
        ]),
    ]


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
        changes = engine.tick(campaign_id, scene_state)
        scene_manager.apply_changes(campaign_id, changes, scene_state)
        engine.save_npcs(campaign_id)  # после apply_changes
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir  = Path(data_dir or settings.data_dir)
        self.npcs_dir  = self.data_dir / "npcs"
        # Счётчик тиков жизни — хранится в памяти, сбрасывается при рестарте
        # ключ: campaign_id → int
        self._tick_counters: dict[str, int] = {}
        # Кэш NPC в RAM для быстрого доступа между тиками
        # ключ: campaign_id → list[dict]
        self._npc_cache: dict[str, list] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────────────────

    def tick(
        self,
        campaign_id: str,
        scene_state: Optional[dict] = None,
    ) -> list[SceneChange]:
        """
        Главная точка входа — один тик движка жизни.

        Обрабатывает всех Major NPC:
          - обновляет позицию по расписанию
          - восстанавливает стресс
          - с 5% шансом генерирует случайное событие

        Minor NPC обрабатываются раз в _MINOR_TICK_INTERVAL тиков.
        Mass NPC — только флаги присутствия (без SceneChange, 0ms).

        Возвращает list[SceneChange] для применения через apply_changes().
        """
        current_tick = self._increment_tick(campaign_id)
        current_time = _parse_game_time(scene_state)

        logger.info(
            f"[LIFE_ENGINE] Тик #{current_tick} для '{campaign_id}' "
            f"(время: {current_time})"
        )

        npcs = self._load_npcs(campaign_id)
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
                    if (current_tick - last_minor) >= _MINOR_TICK_INTERVAL:
                        changes = self._simulate_minor(npc, current_time, current_tick)
                        all_changes.extend(changes)
                        npc.setdefault("routine", {})["_last_life_tick"] = current_tick
                        npcs_updated = True

                # ── MASS: только проверяем присутствие (0ms) ─────────────────
                elif tier == "mass":
                    # Mass NPC не генерируют SceneChange — их статус управляется
                    # NPCAutoGenerator (фаза 3B.4), который создаёт их при контакте.
                    # Здесь только логируем если нужно.
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
    # Симуляция по тирам
    # ─────────────────────────────────────────────────────────────────────────

    def _simulate_major(
        self,
        npc: dict,
        current_time: str,
        tick: int,
    ) -> list[SceneChange]:
        """
        Полная симуляция Major NPC за один тик.
        Порядок: расписание → стресс → случайные события.
        """
        changes: list[SceneChange] = []

        # 1. Обновляем позицию/активность по расписанию
        routine_changes = self.update_routine(npc, current_time, tick)
        changes.extend(routine_changes)

        # 2. Восстанавливаем стресс (без SceneChange — только данные NPC)
        self.recover_stress_tick(npc)

        # 3. Случайные события (5% шанс)
        event_changes = self.check_random_events(npc, tick)
        changes.extend(event_changes)

        return changes

    def _simulate_minor(
        self,
        npc: dict,
        current_time: str,
        tick: int,
    ) -> list[SceneChange]:
        """
        Симуляция Minor NPC раз в _MINOR_TICK_INTERVAL тиков.
        Только расписание + случайные события (без полного стресс-расчёта).
        """
        changes: list[SceneChange] = []
        routine_changes = self.update_routine(npc, current_time, tick)
        changes.extend(routine_changes)
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
    ) -> list[SceneChange]:
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
            # NPC без расписания — не трогаем
            return []

        # Определяем текущую активность по времени
        new_activity = self._get_current_activity(schedule, current_time)
        if not new_activity:
            return []

        prev_activity = npc.get("routine", {}).get("current", "")

        # Если активность не изменилась — ничего не генерируем
        if new_activity == prev_activity:
            return []

        # Определяем новую позицию и локацию
        new_location, new_position, activity_display = self._resolve_position(
            npc_id, new_activity
        )

        prev_location = npc.get("location", new_location)
        changes: list[SceneChange] = []

        # ── Генерируем SceneChange ────────────────────────────────────────────

        # Активность (всегда)
        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="activity",
            value=activity_display,
            cause="life_engine_schedule",
            tick=tick,
        ))

        # Позиция (всегда)
        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="position",
            value=new_position,
            cause="life_engine_schedule",
            tick=tick,
        ))

        # Видимость: если ушёл спать → скрыт из основной сцены
        going_to_sleep = "sleeping" in new_activity or "resting" in new_activity
        changes.append(SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="visible",
            value=not going_to_sleep,
            cause="life_engine_schedule",
            tick=tick,
        ))

        # Если NPC сменил локацию → фиксируем
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

        # ── Обновляем NPC dict в памяти ────────────────────────────────────
        routine = npc.setdefault("routine", {})
        routine["current"]   = new_activity
        routine["mood"]      = self._mood_for_activity(new_activity)
        if "interrupted" not in routine:
            routine["interrupted"] = False
        npc["location"] = new_location

        logger.debug(
            f"[LIFE_ENGINE] {npc_id}: активность {prev_activity!r} → {new_activity!r} "
            f"в {current_time}"
        )
        return changes

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
        npc_id: str,
        activity: str,
    ) -> tuple[str, str, str]:
        """
        Возвращает (location_id, position_in_scene, activity_display)
        для данного NPC и активности.
        Использует _NPC_ACTIVITY_MAP, с fallback на _DEFAULT_ACTIVITY_MAP.
        """
        npc_map = _NPC_ACTIVITY_MAP.get(npc_id, {})
        if activity in npc_map:
            return npc_map[activity]

        # Попытка частичного совпадения: "working_bar" → "working"
        for key, val in npc_map.items():
            if activity.startswith(key) or key.startswith(activity):
                return val

        # Fallback на общую таблицу
        if activity in _DEFAULT_ACTIVITY_MAP:
            return _DEFAULT_ACTIVITY_MAP[activity]

        # Последний fallback: остаётся на месте
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
    ) -> list[SceneChange]:
        """
        С вероятностью _RANDOM_EVENT_CHANCE (5%) генерирует случайное событие.
        Возвращает список SceneChange или пустой список.

        Случайные события:
          - wanders_to_bar: NPC подходит к стойке
          - notices_something: NPC стал бдительным
          - minor_argument: NPC поспорил → +10 стресса
          - brief_exit: NPC вышел → visible=False

        Спящие NPC не получают случайных событий.
        """
        npc_id   = npc.get("id", "unknown")
        activity = npc.get("routine", {}).get("current", "")

        # Спящих NPC не тревожим
        if "sleeping" in activity:
            return []

        # Бросаем кубик
        if random.random() > _RANDOM_EVENT_CHANCE:
            return []

        # Выбираем случайное событие из таблицы
        events = _make_random_events(npc, tick)
        event_id, changes = random.choice(events)

        # Применяем стресс если событие — ссора (только к данным NPC, без SceneChange)
        if event_id == "minor_argument":
            psyche = npc.setdefault("psyche", {})
            psyche["stress"] = min(100, psyche.get("stress", 0) + 10)
            # SceneChange для стресса не генерируем — это внутренние данные NPC
            changes = []  # убираем stress_delta SceneChange (он не поддерживается)

        logger.info(
            f"[LIFE_ENGINE] Случайное событие: {npc_id} → {event_id} (тик {tick})"
        )
        return changes

    # ─────────────────────────────────────────────────────────────────────────
    # recover_stress_tick — восстановление стресса
    # ─────────────────────────────────────────────────────────────────────────

    def recover_stress_tick(self, npc: dict) -> None:
        """
        Снижает стресс NPC за один тик.

        Правила:
          - Спит → -_STRESS_RECOVERY_SLEEPING (15) за тик
          - Бодрствует в безопасности → -_STRESS_RECOVERY_SAFE (5) за тик
          - Если stress уже 0 — ничего не делаем

        Модифицирует npc dict в памяти (без SceneChange — это внутренние данные).
        Caller (save_npcs) сохранит изменения на диск.
        """
        psyche = npc.setdefault("psyche", {
            "willpower": 50, "stress": 0, "breakpoint": 80,
            "loyalty_true": 50, "loyalty_fake": 50,
            "state": "free", "trauma_flags": [],
        })

        current_stress = psyche.get("stress", 0)
        if current_stress <= 0:
            return

        activity = npc.get("routine", {}).get("current", "")
        recovery = (
            _STRESS_RECOVERY_SLEEPING
            if "sleeping" in activity
            else _STRESS_RECOVERY_SAFE
        )

        psyche["stress"] = max(0, current_stress - recovery)

        logger.debug(
            f"[LIFE_ENGINE] {npc.get('id', '?')}: стресс "
            f"{current_stress} → {psyche['stress']} (восстановление: -{recovery})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Загрузка / счётчик тиков
    # ─────────────────────────────────────────────────────────────────────────

    def _load_npcs(self, campaign_id: str) -> list:
        """
        Загружает NPC из major_npcs.json.
        Использует кэш в RAM если уже загружено (экономия IO).
        """
        if campaign_id in self._npc_cache:
            return self._npc_cache[campaign_id]

        path = self._npcs_file()
        if not path.exists():
            logger.warning(f"[LIFE_ENGINE] {path} не найден — NPC пусто")
            self._npc_cache[campaign_id] = []
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._npc_cache[campaign_id] = data if isinstance(data, list) else []
            logger.debug(
                f"[LIFE_ENGINE] Загружено {len(self._npc_cache[campaign_id])} NPC"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[LIFE_ENGINE] Ошибка загрузки NPC: {e}")
            self._npc_cache[campaign_id] = []

        return self._npc_cache[campaign_id]

    def _npcs_file(self) -> Path:
        """Путь к major_npcs.json."""
        return self.npcs_dir / "major_npcs.json"

    def _increment_tick(self, campaign_id: str) -> int:
        """
        Увеличивает внутренний счётчик тиков для campaign_id.
        Сбрасывается при рестарте сервера (хранится в RAM).
        """
        self._tick_counters[campaign_id] = (
            self._tick_counters.get(campaign_id, 0) + 1
        )
        return self._tick_counters[campaign_id]

    def get_current_tick(self, campaign_id: str) -> int:
        """Возвращает текущий тик для campaign_id (без инкремента)."""
        return self._tick_counters.get(campaign_id, 0)

    def invalidate_cache(self, campaign_id: str) -> None:
        """
        Сбрасывает кэш NPC для campaign_id.
        Вызвать если major_npcs.json был изменён извне (например, SandboxHandler).
        """
        self._npc_cache.pop(campaign_id, None)


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

# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene_state_manager.py
# -*- coding: utf-8 -*-
"""
SceneStateManager — Python как единственный источник истины о состоянии мира.
backend/app/services/scene_state_manager.py

ФАЗА S (ROADMAP v5.0):
  Принцип: любой объект которого нет в SceneState — не существует.
  LLM только описывает SceneState словами, никогда не меняет его.
  Изменения поступают через SceneChange → validate_change → apply_change.

ФАЗА S.0 (ROADMAP v5.2):
  Добавлены поля player_target_npc, player_target_object, player_position,
  player_distances — для пространственного контекста в промптах DM и NPC.
  Добавлены методы:
    update_player_target()    — обновляет цель игрока в SceneState
    build_npc_context_block() — пространственный блок для промпта конкретного NPC

SceneState хранится в:
  backend/data/campaigns/{campaign_id}/campaign_state.json
  ключ "scene_state" — по одному на активную локацию

Шаблоны локаций:
  backend/data/locations/location_templates.json

Лог изменений:
  backend/data/logs/scene_changes_YYYYMMDD.jsonl
"""

from __future__ import annotations

import json
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from app.core.config import settings
from app.services.scene_change import SceneChange, ChangeType

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR  = Path(settings.data_dir)
_LOG_DIR   = _DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _scene_log_file() -> Path:
    return _LOG_DIR / f"scene_changes_{datetime.now().strftime('%Y%m%d')}.jsonl"


def _log_change(change: SceneChange, campaign_id: str, applied: bool) -> None:
    """Логирует SceneChange в scene_changes_YYYYMMDD.jsonl."""
    entry = {
        "ts":          datetime.now().isoformat(timespec="seconds"),
        "campaign_id": campaign_id,
        "applied":     applied,
        **change.to_dict(),
    }
    with open(_scene_log_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# ChangeValidator — проверка допустимости изменения
# ──────────────────────────────────────────────────────────────────────────────

class ChangeValidator:
    """
    Проверяет допустимость SceneChange перед применением.
    Возвращает (valid: bool, reason: str).
    """

    @staticmethod
    def validate(scene_state: dict, change: SceneChange) -> tuple[bool, str]:
        ct = change.type

        if ct == ChangeType.OBJECT_STATE:
            if change.target not in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' не существует в SceneState"
            return True, ""

        if ct == ChangeType.OBJECT_REMOVE:
            if change.target not in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' не существует — нечего удалять"
            return True, ""

        if ct == ChangeType.OBJECT_ADD:
            if change.target in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' уже существует в SceneState"
            return True, ""

        if ct == ChangeType.OBJECT_MOVE:
            if change.target not in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' не существует — нечего перемещать"
            return True, ""

        if ct in (ChangeType.NPC_POSITION, ChangeType.NPC_STATE):
            return True, ""

        if ct == ChangeType.ENVIRONMENT:
            return True, ""

        if ct == ChangeType.INVENTORY:
            return True, ""

        if ct in (ChangeType.EFFECT_ADD, ChangeType.EFFECT_REMOVE):
            return True, ""

        return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# SceneStateManager
# ──────────────────────────────────────────────────────────────────────────────

class SceneStateManager:
    """
    Управляет SceneState — состоянием сцены в текущей локации.

    SceneState хранится как ключ "scene_state" внутри campaign_state.json.

    Принципы:
      1. get_scene_state → загрузить или None
      2. initialize_scene → создать из шаблона (первый визит)
      3. apply_change → изменить через SceneChange (валидация + лог)
      4. apply_changes → пакетное применение
      5. update_player_target → обновить цель/позицию игрока (S.0)
      6. build_npc_context_block → пространственный блок для NPC (S.0)
      7. get_scene_description → текст для DM промпта
      8. save_scene_state → сохранить в campaign_state.json
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir      = Path(data_dir) if data_dir else _DATA_DIR
        self.campaigns_dir = self.data_dir / "campaigns"
        self.templates_dir = self.data_dir / "locations"
        self.validator     = ChangeValidator()
        self._templates_cache: dict | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # Пути
    # ─────────────────────────────────────────────────────────────────────────

    def _state_file(self, campaign_id: str) -> Path:
        path = self.campaigns_dir / campaign_id / "campaign_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _templates_file(self) -> Path:
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        return self.templates_dir / "location_templates.json"

    # ─────────────────────────────────────────────────────────────────────────
    # Чтение / запись campaign_state.json
    # ─────────────────────────────────────────────────────────────────────────

    def _read_campaign_json(self, campaign_id: str) -> dict:
        path = self._state_file(campaign_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[SCENE] Ошибка чтения {path}: {e}")
            return {}

    def _write_campaign_json(self, campaign_id: str, data: dict) -> None:
        path = self._state_file(campaign_id)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # get_scene_state
    # ─────────────────────────────────────────────────────────────────────────

    def get_scene_state(self, campaign_id: str, location_id: str) -> dict | None:
        data = self._read_campaign_json(campaign_id)
        scene = data.get("scene_state")
        if scene and scene.get("location_id") == location_id:
            return scene
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # save_scene_state
    # ─────────────────────────────────────────────────────────────────────────

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет SceneState обратно в campaign_state.json."""
        data = self._read_campaign_json(campaign_id)
        data["scene_state"] = scene_state
        self._write_campaign_json(campaign_id, data)
        logger.debug(f"[SCENE] Сохранён SceneState: {scene_state.get('location_id')}")

    # ─────────────────────────────────────────────────────────────────────────
    # S.0 — update_player_target
    # ─────────────────────────────────────────────────────────────────────────

    def update_player_target(
        self,
        campaign_id: str,
        scene_state: dict,
        target_npc_id: str | None,
        target_npc_name: str | None,
        target_object_id: str | None,
        player_position: str | None = None,
        player_distances: dict | None = None,
        player_spatial: dict | None = None,
    ) -> None:
        """
        Обновляет поля пространственного контекста игрока в SceneState.

        Вызывается из orchestrator._run_python_engines() после
        _extract_player_target(). Сохраняет на диск.

        Аргументы:
            target_npc_id    — id NPC к которому обращается игрок (или None)
            target_npc_name  — читаемое имя NPC (для промпта)
            target_object_id — id объекта с которым взаимодействует (или None)
            player_position  — текущая позиция игрока ("стоит", "на коленях" и т.д.)
            player_distances — {npc_id: float} расстояния до NPC в метрах
            player_spatial   — spatial-контекст игрока:
                               {location_id, position, local_position{x,y}}
        """
        scene_state["player_target_npc"]      = target_npc_id
        scene_state["player_target_npc_name"] = target_npc_name
        scene_state["player_target_object"]   = target_object_id

        if player_position is not None:
            scene_state["player_position"] = player_position

        if player_distances is not None:
            scene_state["player_distances"] = player_distances

        if player_spatial is not None:
            scene_state["player_spatial"] = player_spatial

        self.save_scene_state(campaign_id, scene_state)
        logger.info(
            f"[SCENE S.0] player_target → npc={target_npc_name!r} "
            f"obj={target_object_id!r} pos={player_position!r}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # S.0 — build_npc_context_block (пространственный блок для NPC промпта)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def build_npc_context_block(
        scene_state: dict,
        npc_id: str,
        npc_name: str,
    ) -> str:
        """
        Строит пространственный блок для промпта конкретного NPC.

        NPC должен знать:
          - Где сейчас стоит игрок и на каком расстоянии
          - К нему ли обращается игрок или к кому-то другому
          - Если не к нему — NPC молчит

        Принцип: без этого блока модель галлюцинирует положение персонажей.
        Работает для любого NPC — имена и id из аргументов, не хардкод.

        Пример вывода:
          ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ:
          - Ты: за стойкой, протираешь стаканы
          - Игрок: на коленях, расстояние до тебя: ~0.5 м
          - ИГРОК ОБРАЩАЕТСЯ ИМЕННО К ТЕБЕ — отвечай.
          ВАЖНО: Игрок физически рядом (< 1 м) — ты не можешь одновременно
          быть в другом месте сцены.
        """
        if not scene_state:
            return ""

        lines = ["ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ:"]

        # ── Собственная позиция NPC ───────────────────────────────────────────
        npc_positions = scene_state.get("npc_positions", {})
        own_pos = npc_positions.get(npc_id, {})
        pos_text = own_pos.get("position", "")
        act_text = own_pos.get("activity", "")

        _position_map = {
            "behind_bar":      "за стойкой",
            "serving_table_3": "у третьего стола",
            "corner_table":    "в тёмном углу",
            "gate_post":       "у ворот",
            "stall_3":         "у третьего прилавка",
        }
        _activity_map = {
            "cleaning_tables": "протираешь стаканы",
            "serving_tables":  "несёшь поднос",
            "observing":       "наблюдаешь",
            "guarding_gate":   "несёшь стражу",
            "sleeping":        "спишь",
            "haggling":        "торгуешься",
        }
        pos_label = _position_map.get(pos_text, pos_text)
        act_label = _activity_map.get(act_text, act_text)
        own_desc = ", ".join(p for p in [pos_label, act_label] if p)
        lines.append(f"- Ты: {own_desc or 'в локации'}")

        # ── Позиция и расстояние игрока ───────────────────────────────────────
        player_pos  = scene_state.get("player_position") or "рядом"
        distances   = scene_state.get("player_distances", {})
        distance_m  = distances.get(npc_id, None)

        if distance_m is not None:
            dist_str = f"~{distance_m:.1f} м"
        else:
            dist_str = "неизвестно"

        lines.append(f"- Игрок: {player_pos}, расстояние до тебя: {dist_str}")

        # ── Кому обращается игрок ─────────────────────────────────────────────
        target_id   = scene_state.get("player_target_npc")
        target_name = scene_state.get("player_target_npc_name")
        target_obj  = scene_state.get("player_target_object")

        is_addressed = (target_id == npc_id)

        if is_addressed:
            lines.append(f"- ИГРОК ОБРАЩАЕТСЯ ИМЕННО К ТЕБЕ ({npc_name}) — отвечай.")
            if target_obj:
                lines.append(f"- Игрок взаимодействует с объектом: {target_obj}")
        elif target_id:
            # Игрок обращается к другому конкретному NPC
            lines.append(
                f"- Игрок обращается к {target_name or target_id}, НЕ к тебе. "
                f"Ты МОЛЧИШЬ — не говори ничего вслух."
            )
        else:
            # Нет явного адресата
            lines.append("- Игрок не обращается ни к кому конкретно.")

        # ── Предупреждение о физическом присутствии ───────────────────────────
        if distance_m is not None and distance_m < 1.5:
            lines.append(
                "ВАЖНО: Игрок физически рядом с тобой (< 1.5 м). "
                "Ты НЕ МОЖЕШЬ одновременно находиться в другом месте сцены."
            )

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Загрузка шаблонов
    # ─────────────────────────────────────────────────────────────────────────

    def _load_templates(self) -> dict:
        if self._templates_cache is not None:
            return self._templates_cache
        path = self._templates_file()
        if path.exists():
            try:
                self._templates_cache = json.loads(path.read_text(encoding="utf-8"))
                return self._templates_cache
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[SCENE] Ошибка чтения шаблонов: {e}")
        logger.warning(
            "[SCENE] location_templates.json недоступен — используется builtin fallback. "
            "JSON должен быть основным source of truth."
        )
        self._templates_cache = self._builtin_templates()
        return self._templates_cache

    @staticmethod
    def _builtin_templates() -> dict:
        """Встроенные шаблоны на случай отсутствия файла."""
        return {
            "tavern_silver_wolf": {
                "name": "Таверна «Серебряный Волк»",
                "type": "tavern",
                "default_objects": {
                    "bar_counter": {
                        "name": "барная стойка", "state": "intact",
                        "material": "oak", "hp": 30, "max_hp": 30,
                        "interactable": True
                    },
                    "fireplace": {
                        "name": "очаг", "state": "burning",
                        "light": 40, "interactable": False
                    },
                    "tables": {
                        "name": "столы", "count": 6, "state": "intact",
                        "interactable": True
                    },
                },
                "time_variants": {
                    "06:00-10:00": {
                        "light_level": "dim", "noise_level": "silent",
                        "candles": {"state": "unlit"},
                        "weather_inside": "cool_fresh",
                    },
                    "10:00-22:00": {
                        "light_level": "bright", "noise_level": "moderate",
                        "candles": {"state": "lit", "count": 12},
                        "weather_inside": "warm_busy",
                    },
                    "22:00-02:00": {
                        "light_level": "dim", "noise_level": "low",
                        "candles": {"state": "lit", "count": 6},
                        "weather_inside": "warm_smoky",
                    },
                    "02:00-06:00": {
                        "light_level": "dark", "noise_level": "silent",
                        "candles": {"state": "unlit"},
                        "weather_inside": "cold_quiet",
                    },
                },
                "npc_defaults": {
                    "tavern_keeper_tornin": {
                        "position": "behind_bar", "activity": "cleaning_tables", "visible": True
                    },
                    "maid_lusya": {
                        "position": "serving_table_3", "activity": "serving_tables", "visible": True
                    },
                    "thief_shadow": {
                        "position": "corner_table", "activity": "observing", "visible": False
                    },
                },
                "connected_locations": ["city_gate", "market_square", "inn_rooms"],
            },
            "city_gate": {
                "name": "Городские ворота",
                "type": "gate",
                "default_objects": {
                    "gate_doors": {
                        "name": "створки ворот", "state": "open",
                        "hp": 60, "max_hp": 60, "interactable": True
                    },
                    "guard_post": {
                        "name": "пост охраны", "state": "manned", "interactable": False
                    },
                },
                "time_variants": {
                    "06:00-22:00": {
                        "light_level": "natural", "noise_level": "moderate",
                        "weather_inside": "outdoor"
                    },
                    "22:00-06:00": {
                        "light_level": "torchlit", "noise_level": "low",
                        "weather_inside": "outdoor"
                    },
                },
                "npc_defaults": {
                    "guard_borko": {
                        "position": "gate_post", "activity": "guarding_gate", "visible": True
                    },
                },
                "connected_locations": ["tavern_silver_wolf", "market_square"],
            },
            "market_square": {
                "name": "Рыночная площадь",
                "type": "market",
                "default_objects": {
                    "market_stalls": {
                        "name": "торговые прилавки", "count": 8, "state": "open",
                        "interactable": True
                    },
                    "fountain": {
                        "name": "фонтан", "state": "flowing", "interactable": True
                    },
                },
                "time_variants": {
                    "06:00-18:00": {
                        "light_level": "natural", "noise_level": "loud",
                        "weather_inside": "outdoor"
                    },
                    "18:00-06:00": {
                        "light_level": "dim", "noise_level": "silent",
                        "weather_inside": "outdoor"
                    },
                },
                "npc_defaults": {
                    "merchant_goran": {
                        "position": "stall_3", "activity": "haggling", "visible": True
                    },
                },
                "connected_locations": ["city_gate", "tavern_silver_wolf"],
            },
            "inn_rooms": {
                "name": "Комнаты таверны",
                "type": "inn",
                "default_objects": {
                    "bed": {"name": "кровать", "state": "made", "interactable": True},
                    "chest": {
                        "name": "сундук", "state": "locked",
                        "hp": 20, "max_hp": 20, "interactable": True
                    },
                    "candle_bedside": {
                        "name": "свеча у кровати", "state": "unlit",
                        "count": 1, "interactable": True
                    },
                },
                "time_variants": {
                    "22:00-08:00": {
                        "light_level": "dark", "noise_level": "silent",
                        "weather_inside": "warm_quiet"
                    },
                    "08:00-22:00": {
                        "light_level": "dim", "noise_level": "low",
                        "weather_inside": "warm_quiet"
                    },
                },
                "npc_defaults": {},
                "connected_locations": ["tavern_silver_wolf"],
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # initialize_scene
    # ─────────────────────────────────────────────────────────────────────────

    def initialize_scene(
        self, campaign_id: str, location_id: str, time_of_day: str = "12:00"
    ) -> dict:
        """
        Создаёт SceneState из шаблона локации с учётом времени суток.
        Случайные вариации ±20% для count объектов.
        Сохраняет в campaign_state.json и возвращает.

        S.0: добавлены поля player_target_npc, player_target_object,
             player_position, player_distances.
        """
        templates = self._load_templates()
        template  = templates.get(location_id, {})

        objects: dict = {}
        for obj_id, obj_data in template.get("default_objects", {}).items():
            obj = dict(obj_data)
            if "count" in obj and obj.get("interactable", False):
                # Разбиваем агрегат на именованные инстансы
                base  = obj["count"]
                delta = max(1, int(base * 0.2))
                count = base + random.randint(-delta, delta)
                for i in range(1, count + 1):
                    instance = {k: v for k, v in obj.items() if k != "count"}
                    instance["instance_of"] = obj_id
                    instance["name"] = f"{obj['name']} #{i}"
                    objects[f"{obj_id}_{i}"] = instance
            else:
                # Одиночный объект — оставляем как есть
                objects[obj_id] = obj

        time_variant = self._select_time_variant(template, time_of_day)
        environment = {
            "light_level":    time_variant.get("light_level", "dim"),
            "noise_level":    time_variant.get("noise_level", "low"),
            "time_of_day":    time_of_day,
            "weather_inside": time_variant.get("weather_inside", "neutral"),
        }
        candle_data = time_variant.get("candles")
        if candle_data:
            base_count = candle_data.get("count", 0)
            if base_count > 0:
                delta = max(1, int(base_count * 0.2))
                objects["candles_main"] = {
                    "name": "свечи",
                    "state": candle_data.get("state", "unlit"),
                    "count": base_count + random.randint(-delta, delta),
                    "interactable": True,
                    "owner": None,
                }
            else:
                objects["candles_main"] = {
                    "name": "свечи", "state": "unlit",
                    "count": 0, "interactable": True, "owner": None,
                }

        npc_positions: dict = {}
        for npc_id, pos_data in template.get("npc_defaults", {}).items():
            pos_entry = dict(pos_data)
            pos_entry.setdefault("location_id", location_id)
            pos_entry.setdefault("local_position", {"x": 0.0, "y": 0.0})
            npc_positions[npc_id] = pos_entry

        scene_state = {
            "location_id":              location_id,
            "snapshot_tick":            0,
            "objects":                  objects,
            "npc_positions":            npc_positions,
            "environment":              environment,
            "player_inventory_snapshot": {},
            "active_effects":           [],

            # ── S.0: пространственный контекст игрока ────────────────────────
            # Обновляется каждый ход через update_player_target()
            # Используется в build_npc_context_block() и _build_scene_description()
            "player_position":      "стоит",     # текущая поза/позиция игрока
            "player_spatial": {
                "location_id": location_id,
                "position": "main_hall",
                "local_position": {"x": 0.0, "y": 0.0},
            },
            "player_target_npc":    None,         # id NPC к которому обращается
            "player_target_npc_name": None,       # читаемое имя (для промпта)
            "player_target_object": None,         # id объекта взаимодействия
            "player_distances":     {},           # {npc_id: float} метры
            "environment_modifiers": {
                "light": 0.5,
                "noise": 0.5,
                "density": 0.0,
                "danger": 0.0,
            },
            # ─────────────────────────────────────────────────────────────────
        }

        self.save_scene_state(campaign_id, scene_state)
        logger.info(
            f"[SCENE] Инициализирована сцена '{location_id}' "
            f"(время: {time_of_day}, объектов: {len(objects)}, NPC: {len(npc_positions)})"
        )
        return scene_state

    @staticmethod
    def _select_time_variant(template: dict, time_of_day: str) -> dict:
        try:
            h, m = map(int, time_of_day.split(":"))
            minutes = h * 60 + m
        except (ValueError, AttributeError):
            minutes = 12 * 60

        for time_range, variant in template.get("time_variants", {}).items():
            try:
                start_str, end_str = time_range.split("-")
                sh, sm = map(int, start_str.split(":"))
                eh, em = map(int, end_str.split(":"))
                start_min = sh * 60 + sm
                end_min   = eh * 60 + em
                if start_min > end_min:
                    if minutes >= start_min or minutes < end_min:
                        return variant
                else:
                    if start_min <= minutes < end_min:
                        return variant
            except (ValueError, AttributeError):
                continue

        variants = list(template.get("time_variants", {}).values())
        return variants[0] if variants else {}

    # ─────────────────────────────────────────────────────────────────────────
    # validate_change
    # ─────────────────────────────────────────────────────────────────────────

    def validate_change(
        self, scene_state: dict, change: SceneChange
    ) -> tuple[bool, str]:
        return self.validator.validate(scene_state, change)

    # ─────────────────────────────────────────────────────────────────────────
    # apply_change
    # ─────────────────────────────────────────────────────────────────────────

    def apply_change(
        self, campaign_id: str, change: SceneChange, scene_state: dict
    ) -> bool:
        """
        Применяет одно изменение к SceneState в памяти.
        Валидирует, применяет, логирует.
        НЕ сохраняет на диск — вызывающий код делает save_scene_state() сам.
        """
        valid, reason = self.validate_change(scene_state, change)
        if not valid:
            logger.warning(f"[SCENE] Отклонено: {change.type.value} '{change.target}' — {reason}")
            _log_change(change, campaign_id, applied=False)
            return False

        ct = change.type

        try:
            if ct == ChangeType.OBJECT_STATE:
                obj = scene_state["objects"][change.target]
                field = change.field
                val   = change.value
                if isinstance(val, str) and val.startswith(("+", "-")) and field in obj:
                    try:
                        obj[field] = obj[field] + int(val)
                    except (ValueError, TypeError):
                        obj[field] = val
                else:
                    obj[field] = val

            elif ct == ChangeType.OBJECT_ADD:
                scene_state["objects"][change.target] = change.value or {}

            elif ct == ChangeType.OBJECT_REMOVE:
                scene_state["objects"].pop(change.target, None)

            elif ct == ChangeType.OBJECT_MOVE:
                obj = scene_state["objects"].get(change.target, {})
                obj["location"] = change.value
                scene_state["objects"][change.target] = obj

            elif ct == ChangeType.NPC_POSITION:
                pos = scene_state.setdefault("npc_positions", {})
                entry = pos.setdefault(change.target, {})
                entry[change.field] = change.value

            elif ct == ChangeType.NPC_STATE:
                pos = scene_state.setdefault("npc_positions", {})
                entry = pos.setdefault(change.target, {})
                if change.field == "visible_markers" and isinstance(change.value, str) \
                        and change.value.startswith("+"):
                    marker = change.value[1:]
                    markers = entry.setdefault("visible_markers", [])
                    if marker not in markers:
                        markers.append(marker)
                else:
                    entry[change.field] = change.value

            elif ct == ChangeType.ENVIRONMENT:
                scene_state.setdefault("environment", {})[change.field] = change.value

            elif ct == ChangeType.INVENTORY:
                inv = scene_state.setdefault("player_inventory_snapshot", {})
                if change.field == "add" and isinstance(change.value, dict):
                    for item, qty in change.value.items():
                        if item.startswith("_"):
                            continue
                        inv[item] = inv.get(item, 0) + (qty if isinstance(qty, int) else 1)
                elif change.field == "remove" and isinstance(change.value, dict):
                    for item, qty in change.value.items():
                        if item in inv:
                            inv[item] = max(0, inv[item] - qty)
                            if inv[item] == 0:
                                del inv[item]

            elif ct == ChangeType.EFFECT_ADD:
                effects = scene_state.setdefault("active_effects", [])
                effects.append({
                    "target": change.target,
                    "field":  change.field,
                    "value":  change.value,
                    "cause":  change.cause,
                    "tick":   change.tick,
                })

            elif ct == ChangeType.EFFECT_REMOVE:
                effects = scene_state.get("active_effects", [])
                scene_state["active_effects"] = [
                    e for e in effects
                    if not (e.get("target") == change.target and
                            e.get("field") == change.field)
                ]

        except Exception as e:
            logger.error(f"[SCENE] Ошибка применения {change.type.value}: {e}")
            _log_change(change, campaign_id, applied=False)
            return False

        _log_change(change, campaign_id, applied=True)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # apply_changes — пакетное применение
    # ─────────────────────────────────────────────────────────────────────────

    def apply_changes(
        self, campaign_id: str, changes: list, scene_state: dict
    ) -> int:
        if not changes:
            return 0
        applied_count = sum(
            1 for ch in changes
            if isinstance(ch, SceneChange) and
               self.apply_change(campaign_id, ch, scene_state)
        )
        if applied_count:
            scene_state["snapshot_tick"] = scene_state.get("snapshot_tick", 0) + 1
            self.save_scene_state(campaign_id, scene_state)
            logger.info(f"[SCENE] Применено {applied_count}/{len(changes)} изменений")
        return applied_count


    # ─────────────────────────────────────────────────────────────────────────
    # R2.1 — apply_narrative_extractions: регистрирует объекты и события из DM
    # ─────────────────────────────────────────────────────────────────────────

    def apply_narrative_extractions(
        self,
        campaign_id: str,
        scene_state: dict,
        extraction_result,
    ) -> None:
        """
        R2.2.8: применяет ExtractionResult к SceneState.
        Поддерживает canonical, importance, last_tick, FSM state, NpcAction.
        """
        changed = False
        objects = scene_state.setdefault("objects", {})

        # ── Новые динамические объекты ────────────────────────────────────
        for obj in extraction_result.new_objects:
            if obj.object_id not in objects:
                objects[obj.object_id] = {
                    "name":           obj.name,
                    "raw_name":       obj.raw_name,
                    "canonical_name": obj.canonical_name,
                    "type":           obj.obj_type,
                    "state":          obj.state,
                    "importance":     obj.importance,
                    "holder":         obj.holder,
                    "created_tick":   obj.created_tick,
                    "last_tick":      obj.created_tick,
                    "dynamic":        True,
                    "interactable":   True,
                }
                print(f"[R2.1] Новый объект: {obj.object_id} ({obj.name}, {obj.obj_type})")
                changed = True

        # ── FSM: обновление состояний существующих объектов ───────────────
        from app.services.scene.narrative_extractor import STATE_PRIORITY
        for obj_id, new_state in extraction_result.updated_states:
            if obj_id in objects:
                old_state = objects[obj_id].get("state", "present")
                old_prio  = STATE_PRIORITY.get(old_state, 0)
                new_prio  = STATE_PRIORITY.get(new_state, 0)
                if new_prio >= old_prio:
                    objects[obj_id]["state"]    = new_state
                    objects[obj_id]["last_tick"] = extraction_result.new_events[0].tick if extraction_result.new_events else 0
                    print(f"[R2.1] Состояние: {obj_id} → {new_state}")
                    changed = True

        # ── События сцены (с canonical для дедупликации) ──────────────────
        events = scene_state.setdefault("scene_events", [])
        for evt in extraction_result.new_events:
            events.append({
                "event_id":   evt.event_id,
                "event_type": evt.event_type,
                "actor":      evt.actor,
                "object_name": evt.object_name,
                "canonical":  evt.canonical,
                "object_id":  evt.object_id,
                "tick":       evt.tick,
                "happened":   True,
            })
            print(f"[R2.1] Событие: {evt.event_type} / {evt.object_name} (tick={evt.tick})")
            changed = True

        if len(events) > 30:
            scene_state["scene_events"] = events[-30:]

        # ── current_action NPC (Action Persistence) ───────────────────────
        npc_positions = scene_state.setdefault("npc_positions", {})
        for npc_id, npc_action in extraction_result.npc_actions.items():
            entry = npc_positions.setdefault(npc_id, {})
            entry["current_action"]      = f"{npc_action.action}_{npc_action.object_canonical}"
            entry["action_started_tick"] = npc_action.tick
            changed = True

        if changed:
            self.save_scene_state(campaign_id, scene_state)

    # ─────────────────────────────────────────────────────────────────────────
    # R2.1 — get_scene_events_block: блок для DM промпта
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_scene_events_block(scene_state: dict) -> str:
        """R2.2.8: блок "уже произошло" для DM промпта. Canonical-aware."""
        events = scene_state.get("scene_events", [])
        if not events:
            return ""

        event_labels = {
            "drop":       "упал/уронили",
            "break":      "сломан/разбит",
            "take":       "подобран/взят",
            "use":        "используется",
            "light":      "зажжён",
            "extinguish": "потушен",
        }

        lines = ["СОБЫТИЯ УЖЕ ПРОИЗОШЛИ В ЭТОЙ СЦЕНЕ (не повторять):"]
        seen: set[tuple] = set()

        for evt in events[-10:]:
            etype     = evt.get("event_type", evt.get("type", ""))
            canonical = evt.get("canonical", evt.get("object_name", "").lower())
            actor     = evt.get("actor", "")
            key       = (etype, canonical)
            if key in seen:
                continue
            seen.add(key)

            label     = event_labels.get(etype, etype)
            obj_name  = evt.get("object_name", canonical)
            tick      = evt.get("tick", "?")
            actor_str = f" ({actor.split('_')[-1]})" if actor else ""
            lines.append(f"- {obj_name} — {label}{actor_str} [ход {tick}]")

        return "\n".join(lines) if len(lines) > 1 else ""


    def prune_dynamic_objects(
        self,
        campaign_id: str,
        scene_state: dict,
        current_tick: int,
        transient_lifetime: int = 60,
        max_objects: int = 80,
    ) -> int:
        """
        Фикс #6: удаляет старые динамические объекты по last_tick (не created_tick).
        Вызывается автоматически каждые 50 тиков.
        """
        from app.services.scene.narrative_extractor import STATE_PRIORITY
        objects = scene_state.get("objects", {})
        removed = 0

        for oid in list(objects.keys()):
            obj = objects[oid]
            if not obj.get("dynamic"):
                continue
            last_active = obj.get("last_tick", obj.get("created_tick", 0))
            age         = current_tick - last_active
            importance  = obj.get("importance", 2)

            if importance == 2 and age > transient_lifetime:
                del objects[oid]
                removed += 1
            elif importance == 1 and age > transient_lifetime * 4:
                del objects[oid]
                removed += 1

        if removed:
            self.save_scene_state(campaign_id, scene_state)
            print(f"[R2.1] prune_dynamic_objects: удалено {removed} объектов")

        return removed

    # ─────────────────────────────────────────────────────────────────────────
    # update_npc_position
    # ─────────────────────────────────────────────────────────────────────────

    def update_npc_position(
        self, campaign_id: str, npc_id: str,
        position: str, activity: str,
        scene_state: Optional[dict] = None
    ) -> None:
        save_after = scene_state is None
        if scene_state is None:
            scene_state = self.get_scene_state(campaign_id, "")
            if scene_state is None:
                return

        pos = scene_state.setdefault("npc_positions", {})
        entry = pos.setdefault(npc_id, {})
        entry["position"] = position
        entry["activity"] = activity

        if save_after:
            self.save_scene_state(campaign_id, scene_state)

    # ─────────────────────────────────────────────────────────────────────────
    # get_scene_description — для DM промпта
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_scene_description(scene_state: dict) -> str:
        """
        Формирует текстовое описание SceneState для DM промпта.
        DM получает этот блок первым — он описывает ТОЛЬКО то что существует.

        S.0: добавлены блок player_target и строгие правила реакций.
        """
        if not scene_state:
            return ""

        lines = ["Текущее состояние сцены (ТОЛЬКО ЭТИ объекты существуют в локации):"]

        # ── Объекты ──────────────────────────────────────────────────────────
        # Группируем инстансы для отображения
        groups: dict = {}
        for obj_id, obj in scene_state.get("objects", {}).items():
            instance_of = obj.get("instance_of", obj_id)
            if instance_of not in groups:
                groups[instance_of] = {"obj": obj, "ids": [], "states": set()}
            groups[instance_of]["ids"].append(obj_id)
            groups[instance_of]["states"].add(obj.get("state", ""))

        for base_id, group in groups.items():
            obj   = group["obj"]
            name  = obj.get("name", base_id)
            count = len(group["ids"])
            states = group["states"]

            state_map = {
                "intact": "цел", "damaged": "повреждён",
                "destroyed": "уничтожен", "lit": "горит",
                "unlit": "не горит", "burning": "горит",
                "open": "открыт", "locked": "заперт",
            }

            if len(states) == 1:
                state_str = state_map.get(states.pop(), "")
            else:
                state_str = ", ".join(state_map.get(s, s) for s in states)

            count_str = f" ×{count}" if count > 1 else ""
            lines.append(f"- {name}{count_str}: {state_str}".rstrip(": "))

        # ── Окружение ─────────────────────────────────────────────────────────
        env = scene_state.get("environment", {})
        if env:
            light_map = {
                "bright": "ярко освещено", "dim": "полутёмно",
                "dark": "темно", "torchlit": "освещено факелами",
                "natural": "естественный свет",
            }
            noise_map = {
                "silent": "тихо", "low": "негромкий шум",
                "moderate": "шумно", "loud": "очень шумно",
            }
            light   = light_map.get(env.get("light_level", ""), "")
            noise   = noise_map.get(env.get("noise_level", ""), "")
            weather = env.get("weather_inside", "")
            env_parts = [p for p in [light, noise, weather] if p]
            if env_parts:
                lines.append(f"Обстановка: {', '.join(env_parts)}")

        # ── Активные эффекты ──────────────────────────────────────────────────
        for effect in scene_state.get("active_effects", []):
            val = effect.get("value", {})
            if isinstance(val, dict) and val.get("type"):
                target = effect.get("target", "")
                lines.append(f"⚠ Эффект: {target} — {val['type']}")

        # ── NPC позиции ───────────────────────────────────────────────────────
        npc_positions = scene_state.get("npc_positions", {})
        if npc_positions:
            lines.append("")
            activity_map = {
                "cleaning_tables": "протирает стаканы",
                "serving_tables":  "несёт поднос",
                "behind_bar":      "стоит за стойкой",
                "observing":       "наблюдает",
                "guarding_gate":   "несёт стражу у ворот",
                "haggling":        "торгуется",
                "sleeping":        "спит",
            }
            position_map = {
                "behind_bar":      "за стойкой",
                "serving_table_3": "у третьего стола",
                "corner_table":    "в тёмном углу",
                "gate_post":       "у ворот",
                "stall_3":         "у третьего прилавка",
            }
            for npc_id, pos in npc_positions.items():
                if pos.get("state") == "dead":
                    continue
                position = position_map.get(pos.get("position", ""), pos.get("position", ""))
                activity = activity_map.get(pos.get("activity", ""), pos.get("activity", ""))
                visible  = pos.get("visible", True)
                npc_name = _npc_id_to_display(npc_id)
                hidden_tag = " [скрыт]" if not visible else ""
                desc = f"{npc_name}: {position}"
                if activity:
                    desc += f", {activity}"
                lines.append(desc + hidden_tag)

        lines.append("NPC которых нет в этом списке — в локации отсутствуют.")

        # ── S.0: пространственный контекст игрока (для DM) ────────────────────
        player_pos      = scene_state.get("player_position")
        target_npc_name = scene_state.get("player_target_npc_name")
        target_npc_id   = scene_state.get("player_target_npc")
        target_obj      = scene_state.get("player_target_object")
        distances       = scene_state.get("player_distances", {})

        lines.append("")
        lines.append("ПРОСТРАНСТВЕННЫЙ КОНТЕКСТ ИГРОКА:")
        if player_pos:
            lines.append(f"- Позиция игрока: {player_pos}")
        if target_npc_name:
            lines.append(f"- Игрок обращается к: {target_npc_name}")
        elif target_npc_id:
            lines.append(f"- Игрок обращается к: {_npc_id_to_display(target_npc_id)}")
        else:
            lines.append("- Игрок не обращается к конкретному NPC")
        if target_obj:
            lines.append(f"- Игрок взаимодействует с объектом: {target_obj}")
        if distances:
            dist_parts = [
                f"{_npc_id_to_display(nid)}: {dist:.1f}м"
                for nid, dist in distances.items()
            ]
            lines.append(f"- Расстояния: {', '.join(dist_parts)}")

        lines.append("")
        lines.append("ПРАВИЛА РЕАКЦИЙ NPC (ОБЯЗАТЕЛЬНО):")
        if target_npc_name:
            lines.append(
                f"1. Игрок обратился к {target_npc_name} — "
                f"ТОЛЬКО {target_npc_name} отвечает. Остальные NPC молчат."
            )
        else:
            lines.append("1. Игрок не назвал конкретного NPC — отвечает ближайший по контексту.")
        lines.append(
            "2. NPC не может одновременно быть рядом с игроком "
            "И делать что-то в другом месте сцены."
        )
        lines.append(
            "3. Все позиции из блока NPC выше — абсолютная правда. "
            "Не придумывай что NPC переместился если SceneState этого не зафиксировал."
        )

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция: npc_id → читаемое имя
# ──────────────────────────────────────────────────────────────────────────────

# Кэш имён NPC загружаемых из major_npcs.json
_NPC_NAME_CACHE: dict[str, str] = {}
_NPC_NAME_CACHE_LOADED = False


def _load_npc_names_cache() -> None:
    """Загружает id→name из major_npcs.json один раз."""
    global _NPC_NAME_CACHE_LOADED
    if _NPC_NAME_CACHE_LOADED:
        return
    try:
        npc_path = _DATA_DIR / "npcs" / "major_npcs.json"
        if npc_path.exists():
            npcs = json.loads(npc_path.read_text(encoding="utf-8"))
            for npc in npcs:
                nid = npc.get("id", "")
                name = npc.get("name", "")
                if nid and name:
                    _NPC_NAME_CACHE[nid] = name
    except Exception:
        pass
    _NPC_NAME_CACHE_LOADED = True


def _npc_id_to_display(npc_id: str) -> str:
    """
    Конвертирует npc_id в отображаемое имя.
    Приоритет: major_npcs.json → эвристика из id.
    Generic: работает для любого npc_id без хардкода конкретных персонажей.
    """
    _load_npc_names_cache()
    if npc_id in _NPC_NAME_CACHE:
        return _NPC_NAME_CACHE[npc_id]
    # Эвристика: последнее слово id с заглавной буквой
    # "tavern_keeper_tornin" → "Tornin" → "Торнин" (если кириллица) или "Tornin"
    parts = npc_id.split("_")
    return parts[-1].capitalize() if parts else npc_id


# ──────────────────────────────────────────────────────────────────────────────
# Глобальный синглтон
# ──────────────────────────────────────────────────────────────────────────────

_scene_state_manager: SceneStateManager | None = None


def get_scene_state_manager() -> SceneStateManager:
    global _scene_state_manager
    if _scene_state_manager is None:
        _scene_state_manager = SceneStateManager()
    return _scene_state_manager

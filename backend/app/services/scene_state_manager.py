from __future__ import annotations

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
  saves/{campaign_id}/campaign_state.json (ADR-O-146)
  ключ "scene_state" — по одному на активную локацию

Шаблоны локаций:
  backend/data/locations/location_templates.json

Лог изменений:
  backend/data/logs/scene_changes_YYYYMMDD.jsonl
"""


import json
import logging
import math
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.scene_change import ChangeType, SceneChange

# ADR-102: load_graph удалён — заменён на SpatialService
from app.services.spatial.spatial_runtime import euclidean_distance
from app.services.state.persistence_port import PersistencePort

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(settings.data_dir)
_LOG_DIR = _DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _scene_log_file() -> Path:
    return (
        _LOG_DIR / f"scene_changes_{datetime.now().strftime('%Y%m%d')}.jsonl"
    )  # §15.2: Logging/telemetry


def _log_change(change: SceneChange, campaign_id: str, applied: bool) -> None:
    """Логирует SceneChange в scene_changes_YYYYMMDD.jsonl."""
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),  # §15.2: Logging/telemetry
        "campaign_id": campaign_id,
        "applied": applied,
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
                return (
                    False,
                    f"Объект '{change.target}' не существует — нечего перемещать",
                )
            return True, ""

        if ct in (ChangeType.NPC_POSITION, ChangeType.NPC_STATE):
            return True, ""

        if ct == ChangeType.ENVIRONMENT:
            return True, ""

        return True, ""


# ---------------------------------------------------------------------------
# R4.4: производные модификаторы среды из time_variant + типа локации
# ---------------------------------------------------------------------------

_NOISE_MAP: dict[str, float] = {
    "silent": 0.0,
    "low": 0.2,
    "moderate": 0.5,
    "loud": 0.8,
}

_LIGHT_MAP: dict[str, float] = {
    "dark": 0.0,
    "torchlit": 0.2,
    "dim": 0.4,
    "natural": 0.7,
    "bright": 1.0,
}

# Базовая плотность и опасность по типу локации
_TYPE_MODIFIERS: dict[str, dict[str, float]] = {
    "dungeon": {"density": 0.6, "danger": 0.6},
    "market": {"density": 0.7, "danger": 0.1},
    "tavern": {"density": 0.3, "danger": 0.1},
    "gate": {"density": 0.2, "danger": 0.2},
    "inn": {"density": 0.1, "danger": 0.0},
}


def _derive_environment_modifiers(
    time_variant: dict,
    location_type: str,
) -> dict[str, float]:
    """
    R4.4: вычисляет environment_modifiers из time_variant и типа локации.
    Заменяет захардкоженные нули — LOS и sound_reach теперь работают реально.
    """
    base = _TYPE_MODIFIERS.get(location_type, {"density": 0.0, "danger": 0.0})
    return {
        "light": _LIGHT_MAP.get(time_variant.get("light_level", "dim"), 0.4),
        "noise": _NOISE_MAP.get(time_variant.get("noise_level", "low"), 0.2),
        "density": base["density"],
        "danger": base["danger"],
    }


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

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        persistence: Optional[PersistencePort] = None,
        saves_dir: Optional[Path] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else _DATA_DIR
        self._persistence = persistence  # PersistencePort для commit()
        self.campaigns_dir = self.data_dir / "campaigns"
        # Runtime-сохранения: пишет в saves_dir, читает с fallback в campaigns_dir
        self._saves_dir = Path(saves_dir) if saves_dir else self.campaigns_dir
        self.templates_dir = self.data_dir / "locations"
        self.validator = ChangeValidator()
        self._templates_cache: dict | None = None
        # TICK-SCOPED IDENTITY: Кэш scene_state внутри тика.
        # Гарантирует, что все подсистемы видят ОДИН и ТОТ ЖЕ dict.
        # Без этого get_scene_state() создаёт новый dict при каждом вызове → split-brain.
        self._tick_locked: bool = False
        self._tick_campaign_id: str | None = None
        self._tick_scene: dict | None = None

    # ── Tick-Scoped Identity API (ADR-SCENE-LOCK) ──────────────────────

    def lock_for_tick(self, campaign_id: str, location_id: str) -> dict | None:
        """Блокирует scene_state на время тика. Все последующие get_scene_state()
        возвращают ТОТ ЖЕ объект. Вызывать ОДИН раз в начале _run_pipeline()."""
        if self._tick_locked:
            # Уже заблокирован — возвращаем кэш (безопасно для повторного вызова)
            return self._tick_scene
        # ADR-SCENE-LOCK: Загружаем актуальное состояние (с traversals от прошлого тика)
        scene = self.get_scene_state_uncached(campaign_id, location_id)
        if scene is not None:
            self._tick_locked = True
            self._tick_campaign_id = campaign_id
            self._tick_scene = scene
            try:
                _recog = scene.get("player_recognition", {})
                print(f"[DEBUG_LOCK] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                print(f"[DEBUG_LOCK] error: {e}")
        return scene

    def unlock_tick(self, campaign_id: str) -> None:
        """Разблокирует тик. Персистит кэш.
        ADR-SCENE-LOCK: НЕ очищаем _tick_scene сразу — bridge может читать его
        в SSE-потоке после unlock. Кэш живёт до следующего lock_for_tick()."""
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # Диагностика: что мы СОХРАНЯЕМ?
            _trav_before = (
                list(self._tick_scene.get("active_traversals", {}).keys())
                if self._tick_scene
                else []
            )
            logger.debug(
                f"[UNLOCK_TRACE] BEFORE SAVE: traversals={_trav_before} locked={self._tick_locked}"
            )
            # СНИМАЕМ LOCK ДО save — иначе guard в save_scene_state() сделает return!
            self._tick_locked = False
            # Финальный персист кэшированного состояния
            if self._tick_scene is not None:
                self.save_scene_state(campaign_id, self._tick_scene)
            # Диагностика: round-trip проверка — пережил ли traversal save→load?
            if self._persistence:
                _verify = self._persistence.load_scene(campaign_id)
                _trav_after = (
                    list(_verify.get("active_traversals", {}).keys())
                    if _verify
                    else "LOAD_FAILED"
                )
                logger.debug(f"[UNLOCK_TRACE] AFTER LOAD: traversals={_trav_after}")
            # НЕ очищаем _tick_scene! Bridge может читать его в SSE-потоке.
            # Кэш будет заменён при следующем lock_for_tick().

    def commit_tick_result(self, campaign_id: str, result_snapshot: dict) -> None:
        """S83.1: Заменяет locked tick scene результатом вычисления тика.

        input_snapshot (frozen) → фазы мутируют его → result_snapshot = output.
        Этот метод обновляет persistence target БЕЗ мутации исходного scene_state.
        unlock_tick() сохранит result_snapshot на диск.

        deepcopy обязателен — иначе _tick_scene алиасит input_snapshot,
        и будущие мутации в TickContext протекут в persistence buffer (L4 temporal alias).
        """
        import copy

        _trav_keys = (
            list(result_snapshot.get("active_traversals", {}).keys())
            if isinstance(result_snapshot, dict)
            else []
        )
        logger.debug(
            f"[COMMIT_TRACE] campaign={campaign_id} tick={result_snapshot.get('tick')} trav_keys={_trav_keys} id={id(result_snapshot)}"
        )
        if self._tick_campaign_id == campaign_id:
            self._tick_scene = copy.deepcopy(result_snapshot)
            try:
                _recog = self._tick_scene.get("player_recognition", {})
                print(f"[DEBUG_COMMIT] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                print(f"[DEBUG_COMMIT] error: {e}")
            logger.debug(
                f"[COMMIT_TRACE] _tick_scene updated, trav_keys_after={list(self._tick_scene.get('active_traversals', {}).keys())}"
            )
            logger.debug(
                f"[S83.1] commit_tick_result: persistence target updated for {campaign_id}"
            )
        else:
            logger.warning(
                f"[S83.1] commit_tick_result: campaign mismatch {campaign_id} vs {self._tick_campaign_id}"
            )

    def get_scene_state_uncached(
        self, campaign_id: str, location_id: str
    ) -> dict | None:
        """Загружает scene_state из persistence БЕЗ кэша.
        Используется внутри lock_for_tick() для первичной загрузки."""
        if self._persistence:
            scene = self._persistence.load_scene(campaign_id)
            if scene:
                try:
                    _recog = scene.get("player_recognition", {})
                    print(f"[DEBUG_LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except Exception as e:
                    print(f"[DEBUG_LOAD] error: {e}")
        else:
            data = self._read_campaign_json(campaign_id)
            scene = data.get("scene_state")
        if not scene:
            return None
        # P0 FIX (S71): SceneState Contract — reject non-dict
        if not isinstance(scene, dict):
            logger.warning(
                f"[SCENE_CONTRACT] get_scene_state_uncached: тип={type(scene).__name__}, ожидается dict"
            )
            return None
        if location_id and scene.get("location_id") != location_id:
            return None
        self._enrich_local_positions(campaign_id, scene)
        self._enrich_spatial_data(campaign_id, scene)
        if "snapshot_tick" in scene:
            del scene["snapshot_tick"]
        for npc_id, pos_data in scene.get("npc_positions", {}).items():
            if isinstance(pos_data, dict) and not pos_data.get("name"):
                pos_data["name"] = _npc_id_to_display(npc_id)
        scene["campaign_id"] = campaign_id
        return scene

    # ─────────────────────────────────────────────────────────────────────────
    # Пути
    # ─────────────────────────────────────────────────────────────────────────

    def _state_file(self, campaign_id: str) -> Path:
        """Возвращает путь к campaign_state.json в saves/. Мигрирует из campaigns/ при первом доступе."""
        saves_path = self._saves_dir / campaign_id / "campaign_state.json"
        if saves_path.exists():
            return saves_path
        # Миграция: если файл в старом месте — копируем в saves/
        legacy_path = self.campaigns_dir / campaign_id / "campaign_state.json"
        if legacy_path.exists():
            saves_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(legacy_path, saves_path)
            logger.info(
                f"[SCENE] Миграция campaign_state: {legacy_path} → {saves_path}"
            )
            return saves_path
        # Новое сохранение — в saves_dir
        saves_path.parent.mkdir(parents=True, exist_ok=True)
        return saves_path

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
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[SCENE] Ошибка чтения {path}: {e}")
            return {}

    def _write_campaign_json(self, campaign_id: str, data: dict) -> None:
        path = self._state_file(campaign_id)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # get_scene_state
    # ─────────────────────────────────────────────────────────────────────────

    def get_scene_state(self, campaign_id: str, location_id: str) -> dict | None:
        # TICK-SCOPED IDENTITY: Если тик заблокирован, возвращаем ТОТ ЖЕ объект.
        # Без этого каждый вызов создаёт НОВЫЙ dict из persistence → traversals теряются.
        if (
            self._tick_locked
            and self._tick_campaign_id == campaign_id
            and self._tick_scene is not None
        ):
            return self._tick_scene
        # Устав 4.2.1: читаем из порта (SQLite) если доступен
        if self._persistence:
            scene = self._persistence.load_scene(campaign_id)
            if scene:
                try:
                    _recog = scene.get("player_recognition", {})
                    print(f"[DEBUG_LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except Exception as e:
                    print(f"[DEBUG_LOAD] error: {e}")
            if scene:
                import inspect

                _caller = inspect.currentframe().f_back
                _caller_info = (
                    f"{_caller.f_code.co_filename}:{_caller.f_lineno}"
                    if _caller
                    else "unknown"
                )
                logger.debug(
                    f"[SCENE_REHYDRATE] NEW dict id={id(scene)} from persistence caller={_caller_info} trav_keys={list(scene.get('active_traversals', {}).keys())[:5]}"
                )
        else:
            data = self._read_campaign_json(campaign_id)
            scene = data.get("scene_state")
        if not scene:
            return None
        # P0 FIX (S71): SceneState Contract — reject non-dict
        if not isinstance(scene, dict):
            logger.warning(
                f"[SCENE_CONTRACT] get_scene_state: тип={type(scene).__name__}, ожидается dict"
            )
            return None
        # Пустой location_id = без фильтра (для синхронизации позиции)
        if location_id and scene.get("location_id") != location_id:
            return None
        # Гарантируем актуальные local_position при каждой загрузке
        self._enrich_local_positions(campaign_id, scene)
        # Обогащаем spatial_walls/obstacles из editor JSON, если их нет
        self._enrich_spatial_data(campaign_id, scene)
        # Миграция: удаляем legacy snapshot_tick (Устав §3 — тик через TemporalEngine)
        if "snapshot_tick" in scene:
            del scene["snapshot_tick"]
        # ADR-046 Fix: Гарантировать наличие имени (name) в npc_positions для Target Resolution (Слой 2)
        for npc_id, pos_data in scene.get("npc_positions", {}).items():
            if isinstance(pos_data, dict) and not pos_data.get("name"):
                pos_data["name"] = _npc_id_to_display(npc_id)
        # ADR-102: Инжект campaign_id для SpatialService (замена мёртвого load_graph)
        scene["campaign_id"] = campaign_id
        return scene

    def _enrich_spatial_data(self, campaign_id: str, scene_state: dict) -> None:
        """Обогащает spatial_walls/obstacles из editor JSON, если их нет."""
        if "spatial_walls" in scene_state and "spatial_obstacles" in scene_state:
            return  # Уже обогащено

        location_id = scene_state.get("location_id", "")
        editor_data = self._find_editor_location(campaign_id, location_id)
        if not editor_data:
            return

        spatial_walls, spatial_obstacles = self._build_spatial_data(editor_data)
        scene_state["spatial_walls"] = spatial_walls
        scene_state["spatial_obstacles"] = spatial_obstacles

    # ─────────────────────────────────────────────────────────────────────────
    # save_scene_state
    # ─────────────────────────────────────────────────────────────────────────

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет SceneState через PersistencePort (Устав 4.2.1).
        ADR-SCENE-LOCK: Если тик заблокирован, обновляет кэш вместо записи на диск.
        Персист произойдёт в unlock_tick()."""
        scene_state.pop("snapshot_tick", None)
        # TICK-SCOPED IDENTITY: Внутри тика обновляем кэш, НЕ пишем на диск.
        # Запись на диск происходит один раз в unlock_tick().
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # Кэш должен ссылаться на тот же объект — просто пропускаем персист
            return
        # ДИАГНОСТИКА: Реальный персист — проверяем что traversals доходят
        _trav_keys = (
            list(scene_state.get("active_traversals", {}).keys())
            if isinstance(scene_state, dict)
            else []
        )
        logger.debug(
            f"[SAVE_TRACE] campaign={campaign_id} locked={self._tick_locked} traversals={_trav_keys}"
        )
        if self._persistence:
            try:
                _recog = scene_state.get("player_recognition", {})
                import traceback
                _stack = traceback.format_stack(limit=5)
                print(f"[DEBUG_SAVE] campaign={campaign_id} recog_keys={list(_recog.keys())} stack={_stack}")
            except Exception as e:
                print(f"[DEBUG_SAVE] error: {e}")
            self._persistence.save_scene(campaign_id, scene_state)
        else:
            # Фоллбэк: прямая запись JSON (без порта)
            data = self._read_campaign_json(campaign_id)
            data["scene_state"] = scene_state
            self._write_campaign_json(campaign_id, data)
        # TODO-A1: JSON mirror — game_screen ещё читает файлы, не API. Удалить после A1.
        data = self._read_campaign_json(campaign_id)
        if "scene_state" not in data:
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
        scene_state["player_target_npc"] = target_npc_id
        scene_state["player_target_npc_name"] = target_npc_name
        scene_state["player_target_object"] = target_object_id

        # ADR-048 Phase 3: Запись player_distances и player_spatial ЗАПРЕЩЕНА.
        # SpatialQueryService является авторитетом. player_distances — derived projection.
        # Narrative-позиция (player_position как строка "стоит") пока оставлена для DM контекста.
        if player_position is not None:
            scene_state["player_position"] = player_position

        # if player_distances is not None:
        #     scene_state["player_distances"] = player_distances

        # if player_spatial is not None:
        #     scene_state["player_spatial"] = player_spatial

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
        spatial_service: Optional[Any] = None,
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

        # ── Собственная позиция NPC ───────────────────────────────────────────
        npc_positions = scene_state.get("npc_positions", {})
        own_pos = npc_positions.get(npc_id, {})
        pos_text = own_pos.get("position", "")
        act_text = own_pos.get("activity", "")

        # SpatialService v1.2 динамически резолвит лейблы узлов
        pos_label = (
            spatial_service.get_node_label(pos_text) if spatial_service else pos_text
        )

        _activity_map = {
            "cleaning_tables": "убираешься",
            "serving_tables": "обслуживаешь зал",
            "observing": "наблюдаешь",
            "guarding_gate": "несёшь стражу",
            "sleeping": "спишь",
            "haggling": "торгуешься",
        }
        act_label = _activity_map.get(act_text, act_text)
        own_desc = ", ".join(p for p in [pos_label, act_label] if p)

        # ── Позиция и расстояние игрока (ADR-048: вычисление из npc_positions) ──
        player_pos = scene_state.get("player_position") or "рядом"
        _player_data = scene_state.get("npc_positions", {}).get("player", {})
        _npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
        distance_m = euclidean_distance(_player_data, _npc_data)
        dist_str = f"~{distance_m:.1f} м" if distance_m < 999.0 else "неизвестно"

        lines = [
            "ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ:",
            f"- Ты: {own_desc or 'в локации'}",
            f"- Игрок: {player_pos}, расстояние до тебя: {dist_str}",
        ]

        # ── Кому обращается игрок ─────────────────────────────────────────────
        target_id = scene_state.get("player_target_npc")
        target_name = scene_state.get("player_target_npc_name")
        target_obj = scene_state.get("player_target_object")

        is_addressed = target_id == npc_id

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
                raise RuntimeError(f"[SCENE] Ошибка чтения шаблонов: {e}")
        raise RuntimeError(f"[SCENE] location_templates.json не найден по пути {path}. _builtin_templates удалён (ADR-O-326).")

    def _find_editor_location(self, campaign_id: str, location_id: str) -> dict | None:
        """Ищет editor JSON с совпадающим location_id.
        Поддерживает: точное совпадение, частичное совпадение label, пустой location_id."""
        search_dirs = [
            self.campaigns_dir / campaign_id / "locations",
            Path(__file__).resolve().parent.parent.parent.parent
            / "frontend"
            / "map_editor"
            / "campaigns"
            / campaign_id
            / "locations",
        ]
        for loc_dir in search_dirs:
            if not loc_dir.exists():
                continue
            for json_file in loc_dir.glob("*.json"):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    lid = data.get("location_id", "")
                    label = data.get("label", "")
                    # Точное совпадение
                    if lid == location_id or label == location_id:
                        logger.info(
                            f"[SCENE] Найден editor JSON: {json_file} для location_id={location_id}"
                        )
                        return data
                    # Частичное совпадение label (в одну сторону)
                    if label and location_id and (location_id.lower() in label.lower()):
                        logger.info(
                            f"[SCENE] Найден editor JSON по частичному label: {json_file}"
                        )
                        return data
                    # Пустой location_id в файле — берём первую попавшуюся с rooms
                    if not lid and location_id and data.get("rooms"):
                        logger.info(
                            f"[SCENE] Fallback на первый файл с rooms: {json_file}"
                        )
                        return data
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def _find_first_editor_location(self, campaign_id: str) -> dict | None:
        """Возвращает первую найденную локацию из editor JSON — fallback при несовпадении location_id."""
        search_dirs = [
            self.campaigns_dir / campaign_id / "locations",
            Path(__file__).resolve().parent.parent.parent.parent
            / "frontend"
            / "map_editor"
            / "campaigns"
            / campaign_id
            / "locations",
        ]
        for loc_dir in search_dirs:
            if not loc_dir.exists():
                continue
            for json_file in loc_dir.glob("*.json"):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    if data.get("rooms") or data.get("walls"):
                        logger.info(f"[SCENE] Fallback: первая локация из {json_file}")
                        return data
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def find_starting_location(self, campaign_id: str) -> str:
        """Находит начальную локацию для кампании из editor JSON.
        Приоритет: player_spawn + NPC → player_spawn → rooms/walls → 'tavern'."""
        search_dirs = [
            self.campaigns_dir / campaign_id / "locations",
            Path(__file__).resolve().parent.parent.parent.parent
            / "frontend"
            / "map_editor"
            / "campaigns"
            / campaign_id
            / "locations",
        ]
        # Приоритет 1: локация с player_spawn И NPC (лучшая стартовая точка)
        for loc_dir in search_dirs:
            if not loc_dir.exists():
                continue
            for json_file in sorted(loc_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    if data.get("player_spawn") and data.get("npcs"):
                        return data.get("location_id", json_file.stem)
                except (json.JSONDecodeError, OSError):
                    continue
        # Приоритет 2: локация с player_spawn (без NPC)
        for loc_dir in search_dirs:
            if not loc_dir.exists():
                continue
            for json_file in sorted(loc_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    if data.get("player_spawn"):
                        return data.get("location_id", json_file.stem)
                except (json.JSONDecodeError, OSError):
                    continue
        # Приоритет 3: первая локация с rooms/walls/nodes
        for loc_dir in search_dirs:
            if not loc_dir.exists():
                continue
            for json_file in sorted(loc_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    if data.get("rooms") or data.get("walls") or data.get("nodes"):
                        return data.get("location_id", json_file.stem)
                except (json.JSONDecodeError, OSError):
                    continue
        return "tavern"

    def reinit_campaign(self, campaign_id: str) -> dict | None:
        """Переинициализация сцены кампании из editor JSON.
        Вызывается из new_game() ПОСЛЕ очистки persistence.
        Находит начальную локацию и создаёт свежую сцену."""
        starting_location = self.find_starting_location(campaign_id)
        scene = self.initialize_scene(campaign_id, starting_location)
        logger.info(
            f"[SCENE] Campaign '{campaign_id}' reinitialized from editor, "
            f"location={starting_location}"
        )
        return scene

    def _build_spatial_data(self, editor_data: dict) -> tuple[list[dict], list[dict]]:
        """Делегирует построение spatial_data в graph_compiler (SSOT, P4-02)."""
        from app.services.spatial.graph_compiler import _build_spatial_data
        return _build_spatial_data(editor_data)

    def _nearest_node_to_xy(self, editor_data: dict, x: float, y: float) -> str:
        """Находит ближайший навигационный узел к координате XY."""
        nodes = editor_data.get("nodes", {})
        if not nodes:
            return ""
        best_node = ""
        best_dist = float("inf")
        for node_id, node_data in nodes.items():
            nx = node_data.get("x", 0)
            ny = node_data.get("y", 0)
            dist = math.sqrt((nx - x) ** 2 + (ny - y) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_node = node_id
        return best_node

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
        template = templates.get(location_id, {})

        # === Пытаемся загрузить editor JSON с деталями карты ===
        editor_data = self._find_editor_location(campaign_id, location_id)

        objects: dict = {}
        npc_positions: dict = {}
        player_spawn_node: str = ""
        spatial_walls: list[dict] = []
        spatial_obstacles: list[dict] = []

        if editor_data:
            # --- Объекты из editor JSON ---
            for i, obj in enumerate(editor_data.get("objects", [])):
                obj_id = obj.get("id", f"obj_{i}")
                objects[obj_id] = {
                    "name": obj.get("name", obj.get("type", "объект")),
                    "type": obj.get("type", ""),
                    "state": obj.get("properties", {}).get("open", True)
                    and "intact"
                    or "closed",
                    "position": obj.get("position", {}),
                    "size": obj.get("size", {}),
                    "interactable": True,
                }

            # --- NPC из editor JSON — только те что на этой карте ---
            for npc in editor_data.get("npcs", []):
                ref_id = npc.get("ref_id", "")
                if not ref_id:
                    continue
                pos = npc.get("position", {})
                node = self._nearest_node_to_xy(
                    editor_data, pos.get("x", 0), pos.get("y", 0)
                )
                npc_positions[ref_id] = {
                    "name": _npc_id_to_display(ref_id),
                    "location_id": location_id,
                    "position": node,
                    "activity": "",
                    "visible": True,
                    "local_position": {"x": pos.get("x", 0.0), "y": pos.get("y", 0.0)},
                    "editor_room_id": npc.get("room_id", ""),
                }

            # --- Точка спавна игрока ---
            if spawn := editor_data.get("player_spawn"):
                player_spawn_node = self._nearest_node_to_xy(
                    editor_data, spawn.get("x", 0), spawn.get("y", 0)
                )

            # --- Стены и блокирующие объекты для коллизий (делегирование в GraphCompiler) ---
            spatial_walls, spatial_obstacles = self._build_spatial_data(editor_data)

            logger.info(
                f"[SCENE] Editor JSON: {len(objects)} объектов, "
                f"{len(npc_positions)} NPC, spawn_node={player_spawn_node}"
            )
        else:
            # --- Fallback: старая логика из location_templates.json ---
            for obj_id, obj_data in template.get("default_objects", {}).items():
                obj = dict(obj_data)
                if "count" in obj and obj.get("interactable", False):
                    base = obj["count"]
                    delta = max(1, int(base * 0.2))
                    count = base + random.randint(-delta, delta)
                    for i in range(1, count + 1):
                        instance = {k: v for k, v in obj.items() if k != "count"}
                        instance["instance_of"] = obj_id
                        instance["name"] = f"{obj['name']} #{i}"
                        objects[f"{obj_id}_{i}"] = instance
                else:
                    objects[obj_id] = obj

            for npc_id, pos_data in template.get("npc_defaults", {}).items():
                if npc_id in npc_positions:
                    # Дополняем editor JSON данными из шаблона (activity, visible)
                    # Но НЕ перезаписываем local_position — он уже правильный из editor
                    for k, v in pos_data.items():
                        if k not in npc_positions[npc_id]:
                            npc_positions[npc_id][k] = v
                else:
                    # NPC нет в editor JSON — создаём из шаблона
                    pos_entry = dict(pos_data)
                    pos_entry.setdefault("location_id", location_id)
                    pos_entry.setdefault("local_position", {"x": 0.0, "y": 0.0})
                    npc_positions[npc_id] = pos_entry

        # --- Среда (всегда из шаблона — время/свет/шум) ---
        time_variant = self._select_time_variant(template, time_of_day)
        environment = {
            "light_level": time_variant.get("light_level", "dim"),
            "noise_level": time_variant.get("noise_level", "low"),
            "time_of_day": time_of_day,
            "weather_inside": time_variant.get("weather_inside", "neutral"),
        }
        if candle_data := time_variant.get("candles"):
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
                    "name": "свечи",
                    "state": "unlit",
                    "count": 0,
                    "interactable": True,
                    "owner": None,
                }

        scene_state = {
            "location_id": location_id,
            "objects": objects,
            "npc_positions": npc_positions,
            "environment": environment,
            "player_inventory_snapshot": {},
            "active_effects": [],
            # ── S.0: пространственный контекст игрока ────────────────────────
            # Обновляется каждый ход через update_player_target()
            # Используется в build_npc_context_block() и _build_scene_description()
            "player_position": "стоит",  # текущая поза/позиция игрока
            "player_spatial": {
                "location_id": location_id,
                "position": player_spawn_node or "entrance",
                "local_position": {
                    "x": editor_data.get("player_spawn", {}).get("x", 0.0)
                    if editor_data
                    else 0.0,
                    "y": editor_data.get("player_spawn", {}).get("y", 0.0)
                    if editor_data
                    else 0.0,
                },
            },
            "player_target_npc": None,  # id NPC к которому обращается
            "player_target_npc_name": None,  # читаемое имя (для промпта)
            "player_target_object": None,  # id объекта взаимодействия
            "player_distances": {},  # {npc_id: float} метры
            "environment_modifiers": _derive_environment_modifiers(
                time_variant, template.get("type", "")
            ),
            # ── Пространственные данные для коллизий (из editor JSON) ─────
            "spatial_walls": spatial_walls,
            "spatial_obstacles": spatial_obstacles,
            # ── ADR-019: Traversal Registry (процесс во времени, а не стейт) ──
            "active_traversals": {},  # dict[npc_id, traversal_dict]
            # ── ADR-O-146: Новая игра начинается с tick=0, время 12:00 ──
            "tick": 0,
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
                end_min = eh * 60 + em
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
            logger.warning(
                f"[SCENE] Отклонено: {change.type.value} '{change.target}' — {reason}"
            )
            _log_change(change, campaign_id, applied=False)
            return False

        ct = change.type

        # Архитектурный guard: семантика и пространство неразделимы
        # MovementEngine меняет position → мы атомарно обновляем x,y через SpatialService
        if ct == ChangeType.NPC_POSITION and change.field == "position":
            logger.debug(
                f"[ARCH GUARD] Легитимное перемещение: npc={change.target} → {change.value}"
            )

        try:
            if ct == ChangeType.OBJECT_STATE:
                obj = scene_state["objects"][change.target]
                field = change.field
                val = change.value
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
                _old_position = entry.get("position", "")

                if (
                    change.field == "position"
                    and _old_position == change.value
                    and getattr(change, "cause", "") != "traversal_complete"
                ):
                    return True

                entry[change.field] = change.value

                if change.field == "position":
                    location_id = scene_state.get("location_id", "")
                    target_loc = (
                        getattr(change, "target_location_id", "") or location_id
                    )
                    if target_loc and change.value:
                        # Обновляем локацию NPC при кросс-локационном переходе
                        if target_loc != location_id:
                            entry["location_id"] = target_loc
                            entry["location"] = target_loc
                        try:
                            from app.services.spatial.spatial_factory import (
                                SpatialFactory,
                            )

                            svc = SpatialFactory.build_for_campaign(
                                campaign_id=campaign_id,
                                location_id=target_loc,
                                scene_state=scene_state,
                            )
                            if node := svc.get_node(change.value) or svc.get_node(
                                f"{target_loc}:{change.value}"
                            ):
                                # P2: Сохраняем старую позицию ДО перезаписи
                                from_xy = entry.get(
                                    "local_position", {"x": 0.0, "y": 0.0}
                                )
                                if not isinstance(from_xy, dict):
                                    from_xy = {"x": 0.0, "y": 0.0}

                                exact_xy = getattr(change, "target_local_xy", None)
                                if (
                                    exact_xy
                                    and isinstance(exact_xy, (tuple, list))
                                    and len(exact_xy) == 2
                                ):
                                    entry["local_position"] = {
                                        "x": float(exact_xy[0]),
                                        "y": float(exact_xy[1]),
                                    }
                                else:
                                    entry["local_position"] = {"x": node.x, "y": node.y}

                                _active_travs = scene_state.get("active_traversals", {})
                                # ADR-O-201.4 / ADR-130.2: При cause="traversal_complete" 
                                # это факт завершения перемещения (snap), а не начало нового.
                                # Создание нового TraversalState здесь запрещено.
                                # Invariant I (Causal Provenance): Traversal не может существовать без существующего пути.
                                if (
                                    getattr(change, "cause", "") != "traversal_complete"
                                    and (
                                        change.target not in _active_travs
                                        or _active_travs[change.target].get("status")
                                        != "MOVING"
                                    )
                                ):
                                    # ADR-O-323: Layer 1 Continuity. TraversalState создаётся
                                    # исключительно MovementPlanner'ом для макро-перемещений (field="position").
                                    # SceneStateManager только применяет готовый паспорт.
                                    _proposal = getattr(change, "traversal_proposal", None)
                                    if _proposal:
                                        # Проверка актуальности proposal (stale tick detection)
                                        if _proposal.planned_tick != change.tick:
                                            logger.error(
                                                f"[PIPELINE][SCENE_CHANGE][STALE_PROPOSAL_TICK] "
                                                f"npc={change.target} prop_tick={_proposal.planned_tick} change_tick={change.tick}"
                                            )
                                        else:
                                            from app.domain.traversal_schema import build_traversal_dict
                                            _traversal_dict = build_traversal_dict(_proposal)
                                            scene_state.setdefault("active_traversals", {})[
                                                change.target
                                            ] = _traversal_dict
                                    elif change.field == "position" and getattr(change, "cause", "") != "traversal_complete":
                                        # Контракт: macro relocation (field="position") обязан иметь proposal.
                                        # Исключение: traversal_complete (snap позиции, proposal не нужен).
                                        # Микро-перемещения (field="local_position") его не требуют.
                                        logger.error(
                                            f"[PIPELINE][SCENE_CHANGE][MISSING_TRAVERSAL_PROPOSAL] "
                                            f"npc={change.target} cause={change.cause} field={change.field} "
                                            f"Macro movement without proposal (ADR-O-323 violation)"
                                        )
                        except Exception as exc:
                            logger.error(
                                f"[PIPELINE][SCENE_CHANGE][APPLY_CRASH] npc={change.target} exc={exc}"
                            )

                elif change.field in (
                    "local_position",
                    "velocity",
                    "exertion_level",
                    "body_heading",
                ):
                    entry[change.field] = change.value
                    # ADR-O-315: Убрано дублирование player_spatial. Игрок читается из npc_positions["player"].

            elif ct == ChangeType.NPC_STATE:
                pos = scene_state.setdefault("npc_positions", {})
                entry = pos.setdefault(change.target, {})
                if (
                    change.field == "visible_markers"
                    and isinstance(change.value, str)
                    and change.value.startswith("+")
                ):
                    marker = change.value[1:]
                    markers = entry.setdefault("visible_markers", [])
                    if marker not in markers:
                        markers.append(marker)
                else:
                    entry[change.field] = change.value

            elif ct == ChangeType.NPC_METADATA:
                pos = scene_state.setdefault("npc_positions", {})
                entry = pos.setdefault(change.target, {})
                entry[change.field] = change.value

            elif ct == ChangeType.SCENE_METADATA:
                scene_state[change.field] = change.value

            elif ct == ChangeType.ENVIRONMENT:
                scene_state.setdefault("environment", {})[change.field] = change.value

            elif ct == ChangeType.INVENTORY:
                inv = scene_state.setdefault("player_inventory_snapshot", {})
                if change.field == "add" and isinstance(change.value, dict):
                    for item, qty in change.value.items():
                        if item.startswith("_"):
                            continue
                        inv[item] = inv.get(item, 0) + (
                            qty if isinstance(qty, int) else 1
                        )
                elif change.field == "remove" and isinstance(change.value, dict):
                    for item, qty in change.value.items():
                        if item in inv:
                            inv[item] = max(0, inv[item] - qty)
                            if inv[item] == 0:
                                del inv[item]

            elif ct == ChangeType.EFFECT_ADD:
                effects = scene_state.setdefault("active_effects", [])
                effects.append(
                    {
                        "target": change.target,
                        "field": change.field,
                        "value": change.value,
                        "cause": change.cause,
                        "tick": change.tick,
                    }
                )

            elif ct == ChangeType.EFFECT_REMOVE:
                effects = scene_state.get("active_effects", [])
                scene_state["active_effects"] = [
                    e
                    for e in effects
                    if e.get("target") != change.target
                    or e.get("field") != change.field
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

    def apply_changes(self, campaign_id: str, changes: list, scene_state: dict) -> int:
        """Применяет изменения к scene_state IN-MEMORY.

        S83.1: НЕ вызывает save_scene_state() — persist только в Phase 10.
        Mid-tick persist = crash inconsistency (L5).
        """
        if not changes:
            return 0
        applied_count = sum(
            1
            for ch in changes
            if isinstance(ch, SceneChange)
            and self.apply_change(campaign_id, ch, scene_state)
        )
        # ADR-XXX: Traversal Lifecycle — Zombie cleanup (SSOT owner).
        # После применения всех changes: удаляем terminal-статусы (COMPLETED, CANCELLED).
        from app.domain.traversal_schema import TRAVERSAL_TRANSITIONS

        _active_traversals = scene_state.get("active_traversals", {})
        _zombie_ids = [
            nid
            for nid, t in list(_active_traversals.items())
            if not TRAVERSAL_TRANSITIONS.get(t.get("status", ""), set())
        ]
        for _zid in _zombie_ids:
            del _active_traversals[_zid]
        if _zombie_ids:
            logger.debug(
                f"[GATE_ZOMBIE] SSM cleaned={len(_zombie_ids)} zombies remaining={len(_active_traversals)}"
            )
        if applied_count:
            logger.info(
                f"[SCENE] Применено {applied_count}/{len(changes)} изменений (in-memory, persist=Phase10)"
            )
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

        # ── Новые объекты из текста ЗАПРЕЩЕНЫ (TEXT→ENTITY нарушает контракт) ──
        # Объекты появляются только через carried_objects при инициализации сцены.
        # NarrativeExtractor вправе только обновлять состояния существующих объектов.
        if extraction_result.new_objects:
            logger.warning(
                f"[R2.1] Заблокировано {len(extraction_result.new_objects)} TEXT→ENTITY попыток"
            )

        # ── FSM: обновление состояний существующих объектов ───────────────
        from app.services.scene.narrative_extractor import STATE_PRIORITY

        for obj_id, new_state in extraction_result.updated_states:
            if obj_id in objects:
                old_state = objects[obj_id].get("state", "present")
                old_prio = STATE_PRIORITY.get(old_state, 0)
                new_prio = STATE_PRIORITY.get(new_state, 0)
                if new_prio >= old_prio:
                    objects[obj_id]["state"] = new_state
                    objects[obj_id]["last_tick"] = (
                        extraction_result.new_events[0].tick
                        if extraction_result.new_events
                        else 0
                    )
                    logger.debug(f"[R2.1] Состояние: {obj_id} → {new_state}")
                    changed = True

        # ── События сцены (с canonical для дедупликации) ──────────────────
        # Защитный пояс: reaction-only события не проходят из текста LLM.
        # Источник истины — REACTION_ONLY_EVENTS в narrative_extractor.py
        from app.services.scene.narrative_extractor import REACTION_ONLY_EVENTS

        events = scene_state.setdefault("scene_events", [])
        for evt in extraction_result.new_events:
            if evt.event_type in REACTION_ONLY_EVENTS:
                continue
            events.append(
                {
                    "event_id": evt.event_id,
                    "event_type": evt.event_type,
                    "actor": evt.actor,
                    "object_name": evt.object_name,
                    "canonical": evt.canonical,
                    "object_id": evt.object_id,
                    "tick": evt.tick,
                    "happened": True,
                }
            )
            logger.debug(
                f"[R2.1] Событие: {evt.event_type} / {evt.object_name} (tick={evt.tick})"
            )
            changed = True

        if len(events) > 30:
            scene_state["scene_events"] = events[-30:]

        # ── current_action NPC (Action Persistence) ───────────────────────
        npc_positions = scene_state.setdefault("npc_positions", {})
        for npc_id, npc_action in extraction_result.npc_actions.items():
            entry = npc_positions.setdefault(npc_id, {})
            entry["current_action"] = (
                f"{npc_action.action}_{npc_action.object_canonical}"
            )
            entry["action_started_tick"] = npc_action.tick
            changed = True

        if changed:
            self.save_scene_state(campaign_id, scene_state)

    # ─────────────────────────────────────────────────────────────────────────
    # Commit Boundary — атомарное сохранение состояния мира
    # ─────────────────────────────────────────────────────────────────────────

    def commit(
        self,
        campaign_id: str,
        scene_state: dict,
        npc_dicts: list[dict] | None = None,
        events: list[dict] | None = None,
        significant_events: list[dict] | None = None,
    ) -> int:
        """Единственная точка коммита состояния мира (Устав 4.2.1).

        Делегирует в PersistencePort.atomic_commit() — контракт ABC,
        обе реализации (SQLite, JSON) обязаны его иметь.

        Args:
            campaign_id: ID кампании
            scene_state: финальное состояние сцены
            npc_dicts: runtime-стейты NPC (опционально)
            events: события тика для аудита (опционально)
            significant_events: значимые события тика для WorldProjectionBuffer

        Returns:
            2 если коммит успешен, 0 если ошибка или нет PersistencePort.
        """
        if self._persistence is None:
            logger.warning("[SCENE] commit() вызван без PersistencePort — пропуск")
            return 0

        # Версия состояния — инкрементируется только при commit(), не при apply_changes()
        # Отдельно от тика: время — ось, состояние — срез (Устав §3)
        scene_state["_version"] = scene_state.get("_version", 0) + 1

        scene_state["last_save_real_time"] = (
            time.time()
        )  # §15.2: REAL_TIME_BRIDGE (ADR-047)

        # ADR-O-309: WorldProjectionBuffer (Shadow Causality).
        # Запускается внутри atomic commit boundary ДО persistence и обновления state_t-1.
        # Порядок: state_t финализирован → projection → persistence → update state_t-1.
        if not hasattr(self, "_world_proj_buffer"):
            from app.services.offscreen.world_projection_buffer import (
                WorldProjectionBuffer,
            )

            self._world_proj_buffer = WorldProjectionBuffer()

        _loc_id = scene_state.get("location_id", "")
        _tick = scene_state.get("tick", 0)
        # Запрашиваем state_t-1 (temporally sealed artifact от предыдущего тика)
        _prev_state = self.get_last_committed_npcs()

        _projections = self._world_proj_buffer.project(
            tick=_tick,
            campaign_id=campaign_id,
            location_id=_loc_id,
            all_npcs_raw=npc_dicts or [],
            significant_events=significant_events or [],
            previous_npcs_raw=_prev_state,
        )
        if _projections:
            # TODO: В будущей фазе пробросить в shared_context для DM-агента
            logger.debug(
                f"[WORLD_PROJ] Сгенерировано вторичных эффектов: {len(_projections)}"
            )

        ok = self._persistence.atomic_commit(
            campaign_id=campaign_id,
            scene_state=scene_state,
            npc_states=npc_dicts,
            events=events,
        )
        if ok:
            # ADR-O-309: SceneStateManager — единственный источник state_t-1.
            # Deep immutable snapshot: защищает от мутаций живых объектов мира в Фазе 10.
            import copy

            self._last_committed_npcs = copy.deepcopy(npc_dicts or [])
        return 2 if ok else 0

    def get_last_committed_npcs(self) -> list[dict]:
        """Возвращает state_t-1 (committed snapshot) для WorldProjectionBuffer."""
        return getattr(self, "_last_committed_npcs", [])

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
            "drop": "упал/уронили",
            "break": "сломан/разбит",
            "take": "подобран/взят",
            "use": "используется",
            "light": "зажжён",
            "extinguish": "потушен",
        }

        lines = ["СОБЫТИЯ УЖЕ ПРОИЗОШЛИ В ЭТОЙ СЦЕНЕ (не повторять):"]
        seen: set[tuple] = set()

        for evt in events[-10:]:
            etype = evt.get("event_type", evt.get("type", ""))
            canonical = evt.get("canonical", evt.get("object_name", "").lower())
            actor = evt.get("actor", "")
            key = (etype, canonical)
            if key in seen:
                continue
            seen.add(key)

            label = event_labels.get(etype, etype)
            obj_name = evt.get("object_name", canonical)
            tick = evt.get("tick", "?")
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
        objects = scene_state.get("objects", {})
        removed = 0

        for oid in list(objects.keys()):
            obj = objects[oid]
            if not obj.get("dynamic"):
                continue
            last_active = obj.get("last_tick", obj.get("created_tick", 0))
            age = current_tick - last_active
            importance = obj.get("importance", 2)

            if importance == 2 and age > transient_lifetime:
                del objects[oid]
                removed += 1
            elif importance == 1 and age > transient_lifetime * 4:
                del objects[oid]
                removed += 1

        if removed:
            self.save_scene_state(campaign_id, scene_state)
            logger.info(f"[R2.1] prune_dynamic_objects: удалено {removed} объектов")

        return removed

    # ─────────────────────────────────────────────────────────────────────────
    # _enrich_local_positions — гарантия актуальных координат
    # ─────────────────────────────────────────────────────────────────────────

    def _enrich_local_positions(self, campaign_id: str, scene_state: dict) -> None:
        """Восстанавливает local_position для NPC при загрузке scene_state.

        Источники (по приоритету):
        1. Editor JSON — если NPC на начальном узле из npc_defaults (визуальные координаты)
        2. Граф локации — если NPC двигался (координаты текущего узла)
        3. Оставляем как есть — если координаты уже корректны

        Ключевое правило: editor JSON — истина для НАЧАЛЬНЫХ позиций,
        граф — истина для позиций ПОСЛЕ ДВИЖЕНИЯ.
        """
        location_id = scene_state.get("location_id", "")
        npc_positions = scene_state.get("npc_positions", {})
        if not npc_positions or not location_id:
            return

        # Начальные узлы из npc_defaults — определяют, двигался ли NPC
        templates = self._load_templates()
        template = templates.get(location_id, {})
        initial_nodes: dict[str, str] = {}
        for npc_id, pos_data in template.get("npc_defaults", {}).items():
            if node := pos_data.get("position", ""):
                initial_nodes[npc_id] = node

        # Editor JSON — визуальные координаты для начальных позиций
        editor_coords: dict[str, dict] = {}
        editor_data = self._find_editor_location(campaign_id, location_id)
        if editor_data:
            for npc in editor_data.get("npcs", []):
                ref_id = npc.get("ref_id", "")
                pos = npc.get("position", {})
                if ref_id and pos:
                    editor_coords[ref_id] = {
                        "x": pos.get("x", 0.0),
                        "y": pos.get("y", 0.0),
                    }

        # SpatialService — единый источник координат узлов (ADR-0006)
        svc = None
        try:
            from app.services.spatial.spatial_factory import SpatialFactory

            svc = SpatialFactory.build_for_campaign(
                campaign_id=campaign_id,
                location_id=location_id,
                scene_state=scene_state,
            )
        except Exception as e:
            logger.error(
                f"[SPATIAL_ENFORCEMENT] Ошибка сборки SpatialService для location_id={location_id}: {e}"
            )

        for npc_id, entry in npc_positions.items():
            # Миграция имени: в старых сохранениях отсутствует поле name (Баг 3)
            if "name" not in entry:
                entry["name"] = _npc_id_to_display(npc_id)

            # ADR-048 FIX: Синхронизация позиционной истины игрока.
            # Фронтенд пишет в player_spatial, бэкенд читает npc_positions.
            # Без этого макро-узел игрока всегда "entrance", и NPC идут ко входу.
            if npc_id == "player":
                _ps = scene_state.get("player_spatial", {})
                _plp = _ps.get("local_position", {})
                if isinstance(_plp, dict) and isinstance(_plp.get("x"), (int, float)):
                    entry["local_position"] = _plp
                    if svc:
                        _px, _py = _plp.get("x", 0.0), _plp.get("y", 0.0)
                        _p_node_ref = svc.get_nearest(
                            zone_id=location_id, origin_xy=(_px, _py)
                        )
                        if _p_node_ref:
                            _p_node_id = getattr(
                                _p_node_ref, "node_id", str(_p_node_ref)
                            )
                            if _p_node_id.startswith(f"{location_id}:"):
                                _p_node_id = _p_node_id.split(":")[-1]
                            entry["position"] = _p_node_id
                continue  # Игрок не нуждается в enrichment из editor_coords

            current_node = entry.get("position", "")
            initial_node = initial_nodes.get(npc_id)

            # NPC двигался, если есть начальный узел и текущий не совпадает
            npc_moved = initial_node is not None and current_node != initial_node

            # STL: Финализация транзитов перенесена в TickOrchestrator._process_traversals (STL Phase 1).
            # Система №2 (очистка при enrichment) отключена во избежание Double Truth.
            active_traversals = scene_state.get("active_traversals", {})
            current_tick = scene_state.get("tick", 0)

            # GAP12 FIX: Призрачная Позиция. Если NPC в LOD1-транзите, бэкенд-сервисы (CFRM/ImpactEngine)
            # видят его в стартовом узле. Это ложь. Вычисляем интерполированную позицию.
            if (
                npc_id in active_traversals
                and active_traversals[npc_id].get("status") == "MOVING"
            ):
                trav = active_traversals[npc_id]
                wp = trav.get("path_waypoints", [])
                if len(wp) >= 2:
                    # CEI-2b: Tick-based multi-waypoint интерполяция — синхронно с frontend CEI-3b
                    _trav_started = int(trav.get("started_tick", 0))
                    _trav_dur = max(1, int(trav.get("duration_ticks", 1)))
                    _trav_prog = (
                        min(1.0, max(0.0, (current_tick - _trav_started) / _trav_dur))
                        if _trav_dur > 0
                        else 1.0
                    )
                    _num_seg = len(wp) - 1
                    _seg_prog = _trav_prog * _num_seg
                    _seg_idx = min(int(_seg_prog), _num_seg - 1)
                    _seg_frac = _seg_prog - _seg_idx
                    x1, y1 = wp[_seg_idx]
                    x2, y2 = wp[_seg_idx + 1]
                    ix = x1 + (x2 - x1) * _seg_frac
                    iy = y1 + (y2 - y1) * _seg_frac
                    entry["local_position"] = {"x": ix, "y": iy}
                    entry["in_transit"] = (
                        True  # Флаг для сервисов: координаты в движении
                    )
                    continue
                # Фоллбэк, если waypoints нет или структура битая
                lp = entry.get("local_position", {})
                if isinstance(lp, dict) and isinstance(lp.get("x"), (int, float)):
                    continue
                logger.warning(
                    f"[SPATIAL_ENFORCEMENT] NPC '{npc_id}' в транзите без координат! Пробуем восстановить."
                )

            if not npc_moved and npc_id in editor_coords:
                # LOD0: Не перезаписываем микро-перемещения, если координаты уже валидны
                lp = entry.get("local_position", {})
                if not isinstance(lp, dict) or not isinstance(
                    lp.get("x"), (int, float)
                ):
                    entry["local_position"] = dict(editor_coords[npc_id])
            elif svc and current_node:
                # ADR-072 FIX: Жёсткий LOD0 Guard.
                # Если local_position уже валиден (из пайплайна или сохранения), НЕ перезаписываем его координатами узла.
                # Перезапись разрешена ТОЛЬКО если local_position отсутствует или битый.
                lp = entry.get("local_position", {})
                if isinstance(lp, dict) and isinstance(lp.get("x"), (int, float)):
                    continue  # Координаты уже есть, не трогаем!

                if node := svc.get_node(current_node):
                    entry["local_position"] = {"x": node.x, "y": node.y}

            # АРХИТЕКТУРНОЕ ПРИНУЖДЕНИЕ: NPC не может существовать без координат.
            # ADR-121: (0,0) ЗАПРЕЩЁН — это за пределами карты, вызывает телепортацию.
            # Используем начальный узел NPC → вход → первый доступный узел графа.
            local_pos = entry.get("local_position", {})
            if not isinstance(local_pos, dict) or not isinstance(
                local_pos.get("x"), (int, float)
            ):
                _fallback_node = None
                if svc:
                    # 1. Начальный узел NPC из npc_defaults
                    _init = initial_nodes.get(npc_id, "")
                    if _init:
                        _fallback_node = svc.get_node(_init) or svc.get_node(
                            f"{location_id}:{_init}"
                        )
                    # B2-FIX: убрать fallback на entrance (телепортация к двери).
                    # No fallback reality principle — если нет ноды, fail-fast к центру графа.
                    if not _fallback_node:
                        _central = (
                            svc.get_central_node()
                            if hasattr(svc, "get_central_node")
                            else None
                        )
                        if _central:
                            _fallback_node = _central
                        else:
                            logger.error(
                                f"[SPATIAL_ENRICH] CRITICAL: no fallback node for npc={npc_id}. "
                                f"Graph is broken. NPC skipped (no local_position assigned)."
                            )
                            continue
                if _fallback_node:
                    entry["local_position"] = {
                        "x": _fallback_node.x,
                        "y": _fallback_node.y,
                    }
                    logger.warning(
                        f"[SPATIAL_ENFORCEMENT] NPC '{npc_id}' размещён на fallback-узле "
                        f"'{_fallback_node.node_id}' ({_fallback_node.x}, {_fallback_node.y})"
                    )
                else:
                    logger.error(
                        f"[SPATIAL_ENFORCEMENT] NPC '{npc_id}' — ГРАФ ПУСТ! NPC skipped."
                    )

    def update_npc_position(
        self,
        campaign_id: str,
        npc_id: str,
        position: str,
        activity: str,
        scene_state: Optional[dict] = None,
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

        # ADR-092: Синхронизация local_position через канонический SpatialService.
        # Легаси load_graph() (Double Truth) удалён — он не знал про центроиды и ADR-091.
        if location_id := scene_state.get("location_id", ""):
            try:
                svc = self._ensure_spatial_service(location_id, scene_state)
                if svc:
                    node = svc.get_node(position) or svc.get_node(
                        f"{location_id}:{position}"
                    )
                    if node:
                        entry["local_position"] = {"x": node.x, "y": node.y}
                    else:
                        logger.warning(
                            f"[SPATIAL] Узел '{position}' не найден в SpatialService '{location_id}' "
                            f"для NPC {npc_id} — local_position не обновлён"
                        )
            except Exception as exc:
                logger.warning(
                    f"[SPATIAL] Ошибка SpatialService для NPC {npc_id}: {exc} "
                    f"— local_position не обновлён"
                )

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

        # ── Объекты (Salience Engine: фильтрация по важности) ─────────────
        from app.models.scene_mode import determine_scene_mode
        from app.services.scene.salience_engine import SalienceEngine

        _raw_objects = scene_state.get("objects", {})
        _sal_event = scene_state.get("_salience_event_type", "player_interacts")
        _sal_stress = scene_state.get("_salience_max_stress", 0.0)
        _sal_target = scene_state.get("_salience_target_object")

        _filtered = SalienceEngine().get_filtered_objects(
            objects=_raw_objects,
            event_type=_sal_event,
            max_npc_stress=_sal_stress,
            player_target_object=_sal_target,
        )

        _scene_mode = determine_scene_mode(_sal_event, _sal_stress)
        state_map = {
            "intact": "цел",
            "damaged": "повреждён",
            "destroyed": "уничтожен",
            "lit": "горит",
            "unlit": "не горит",
            "burning": "горит",
            "open": "открыт",
            "locked": "заперт",
        }

        # Группируем только отфильтрованные объекты
        groups: dict = {}
        for obj_id, obj in _filtered:
            instance_of = obj.get("instance_of", obj_id)
            if instance_of not in groups:
                groups[instance_of] = {"obj": obj, "ids": [], "states": set()}
            groups[instance_of]["ids"].append(obj_id)
            groups[instance_of]["states"].add(obj.get("state", ""))

        for base_id, group in groups.items():
            obj = group["obj"]
            name = obj.get("name", base_id)
            count = len(group["ids"])
            states = group["states"]

            if len(states) == 1:
                state_str = state_map.get(states.pop(), "")
            else:
                state_str = ", ".join(state_map.get(s, s) for s in states)

            count_str = f" ×{count}" if count > 1 else ""
            lines.append(f"- {name}{count_str}: {state_str}".rstrip(": "))

        # Индикатор режима для отладки
        logger.debug(
            f"[SALIENCE_DEBUG] режим={_scene_mode.value}, объектов_до={len(_raw_objects)}, объектов_после={len(_filtered)}"
        )

        # ── Окружение ─────────────────────────────────────────────────────────
        env = scene_state.get("environment", {})
        if env:
            light_map = {
                "bright": "ярко освещено",
                "dim": "полутёмно",
                "dark": "темно",
                "torchlit": "освещено факелами",
                "natural": "естественный свет",
            }
            noise_map = {
                "silent": "тихо",
                "low": "негромкий шум",
                "moderate": "шумно",
                "loud": "очень шумно",
            }
            light = light_map.get(env.get("light_level", ""), "")
            noise = noise_map.get(env.get("noise_level", ""), "")
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
            position_map = {
                "behind_bar": "за стойкой",
                "bar_area": "у стойки",
                "main_hall": "в центре зала",
                "fireplace": "у камина",
                # ADR-0010: corner_table удалена. Микро-зоны не существуют в макро-графе.
                "entrance": "у входа",
                "kitchen": "на кухне",
                "gate_post": "у ворот",
                "stall_3": "у третьего прилавка",
            }
            for npc_id, pos in npc_positions.items():
                if pos.get("state") == "dead":
                    continue
                position = position_map.get(
                    pos.get("position", ""), pos.get("position", "")
                )
                visible = pos.get("visible", True)
                npc_name = _npc_id_to_display(npc_id)
                hidden_tag = "" if visible else " [скрыт]"
                desc = f"{npc_name}: {position}"
                lines.append(desc + hidden_tag)

        lines.append("NPC которых нет в этом списке — в локации отсутствуют.")

        # ── S.0: пространственный контекст игрока (для DM) ────────────────────
        player_pos = scene_state.get("player_position")
        target_npc_name = scene_state.get("player_target_npc_name")
        target_npc_id = scene_state.get("player_target_npc")
        target_obj = scene_state.get("player_target_object")
        # ADR-048 Phase 3: Вычисляем дистанции из авторитетного словаря npc_positions
        _player_data = scene_state.get("npc_positions", {}).get("player", {})
        distances = {
            nid: euclidean_distance(_player_data, ndata)
            for nid, ndata in scene_state.get("npc_positions", {}).items()
            if nid != "player" and euclidean_distance(_player_data, ndata) < 999.0
        }

        lines.append("")
        lines.append("ПРОСТРАНСТВЕННЫЙ КОНТЕКСТ ИГРОКА:")
        if player_pos:
            lines.append(f"- Позиция игрока: {player_pos}")
        if target_npc_name:
            lines.append(f"- Игрок обращается к: {target_npc_name}")
        elif target_npc_id:
            lines.append(f"- Игрок обращается к: {_npc_id_to_display(target_npc_id)}")
        # else: не показываем ложь "не обращается" — может быть имя в тексте действия
        if target_obj:
            lines.append(f"- Игрок взаимодействует с объектом: {target_obj}")
        if distances:
            # Интерпретация расстояния в слово (инвариант: LLM не видит координаты)
            def _dist_to_word(d: float) -> str:
                if d < 1.0:
                    return "вплотную"
                if d < 3.0:
                    return "рядом"
                if d < 6.0:
                    return "близко"
                return "в нескольких шагах" if d < 10.0 else "далеко"

            dist_parts = [
                f"{_npc_id_to_display(nid)}: {_dist_to_word(dist)}"
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
        # else: не показываем ложное правило "не назвал" — имя может быть в тексте действия
        lines.append(
            "2. NPC не может одновременно быть рядом с игроком "
            "И делать что-то в другом месте сцены."
        )
        lines.append(
            "3. Все позиции из блока NPC выше — абсолютная правда. "
            "Не придумывай что NPC переместился если SceneState этого не зафиксировал."
        )

        return "\n".join(lines)


def enrich_scene_spatial(scene_state: dict, campaign_folder: str) -> None:
    """Обогащает spatial_walls/obstacles из editor JSON.

    Решает проблему устаревшего campaign_state.json: новый код ожидает
    поля passability/blocks_los, которых нет в старом кэше.
    """
    manager = SceneStateManager()
    location_id = scene_state.get("location_id", "")
    editor_data = manager._find_editor_location(campaign_folder, location_id)
    if not editor_data:
        return

    spatial_walls, spatial_obstacles = manager._build_spatial_data(editor_data)
    scene_state["spatial_walls"] = spatial_walls
    scene_state["spatial_obstacles"] = spatial_obstacles


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция: npc_id → читаемое имя
# ──────────────────────────────────────────────────────────────────────────────

# Кэш имён NPC загружаемых из config/npc/individuals/
_NPC_NAME_CACHE: dict[str, str] = {}
_NPC_NAME_CACHE_LOADED = False


def _load_npc_names_cache() -> None:
    """Загружает id→name из config/npc/individuals/ один раз."""
    global _NPC_NAME_CACHE_LOADED
    if _NPC_NAME_CACHE_LOADED:
        return
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()
        for npc in npcs:
            nid = npc.get("id", "")
            name = npc.get("name", "")
            if nid and name:
                _NPC_NAME_CACHE[nid] = name
    except Exception as e:
        logger.debug(f"[SCENE_MGR] Ошибка загрузки кэша NPC: {e}")
    _NPC_NAME_CACHE_LOADED = True


def _npc_id_to_display(npc_id: str) -> str:
    """
    Конвертирует npc_id в отображаемое имя.
    Приоритет: config/npc → эвристика из id.
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

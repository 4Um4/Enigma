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


from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.log_gate import file_logs_enabled
from app.services.scene_change import ChangeType, SceneChange
from app.services.spatial.geometry_kernel import point_in_rect
from app.services.state.persistence_port import PersistencePort

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(settings.data_dir)
# Защита от относительного пути: если data_dir="data", привязываем к backend/
if not _DATA_DIR.is_absolute():
    _DATA_DIR = Path(__file__).resolve().parents[2] / _DATA_DIR
_LOG_DIR = _DATA_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _scene_log_file() -> Path:
    return (
        _LOG_DIR / "scene_changes.jsonl"
    )  # §15.2: Logging/telemetry


def _log_change(change: SceneChange, campaign_id: str, applied: bool) -> None:
    """Логирует SceneChange в scene_changes_YYYYMMDD.jsonl."""
    # LOG-GATE: при ENIGMA_DISABLE_FILE_LOGS=1 (тесты из git-хуков) файл молчит.
    if not file_logs_enabled():
        logger.debug(
            "File logs disabled (%s) — SceneChange не записан в файл: %s/%s",
            "ENIGMA_DISABLE_FILE_LOGS",
            campaign_id,
            change.type,
        )
        return
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),  # §15.2: Logging/telemetry
        "campaign_id": campaign_id,
        "applied": applied,
        **change.to_dict(),
    }
    # P0-14 FIX: Атомарная запись строки для предотвращения truncated JSON при краше.
    _line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(_scene_log_file(), "a", encoding="utf-8") as f:
        f.write(_line)
        f.flush()
        os.fsync(f.fileno())


# ──────────────────────────────────────────────────────────────────────────────
# DEGOD ITER2: ChangeValidator и editor-locator экстрагированы в пакет
# app/services/scene_state/ (change_validator.py, editor_locator.py).
# Re-export сохраняет import-поверхность; call-sites self.validator / методы
# класса не меняются.
# ──────────────────────────────────────────────────────────────────────────────
from app.services.scene_state.change_validator import ChangeValidator
from app.services.scene_state.environment_modifiers import (
    _derive_environment_modifiers as _derive_environment_modifiers,
)
from app.services.scene_state.editor_locator import (
    _find_editor_location as _find_editor_location_impl,
)
from app.services.scene_state.editor_locator import (
    _find_first_editor_location as _find_first_editor_location_impl,
)
from app.services.scene_state.editor_locator import (
    _find_starting_location as _find_starting_location_impl,
)
from app.services.scene_state.editor_locator import (
    _nearest_node_to_xy as _nearest_node_to_xy_impl,
)

# ---------------------------------------------------------------------------
# R4.4: производные модификаторы среды — экстрагированы в
# app/services/scene_state/environment_modifiers.py (DEGOD S3 ITER1).
# Re-export сохраняет import-поверхность (внешний test-import:
# tests/test_spatial_runtime_r4.py:10) и call-site initialize_scene.
# ---------------------------------------------------------------------------

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
        life_engine: Optional[Any] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else _DATA_DIR
        self._persistence = persistence  # PersistencePort для commit()
        self._life_engine = life_engine
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
        # Дополнение Б (п. Б.6.1): Словарь сцен вместо одиночного слота
        self._tick_scenes: dict[str, dict] = {}

    # ── Tick-Scoped Identity API (ADR-SCENE-LOCK) ──────────────────────

    def lock_for_tick(self, campaign_id: str, location_id: str) -> dict | None:
        """Блокирует scene_state на время тика. Все последующие get_scene_state()
        возвращают ТОТ ЖЕ объект. Вызывать ОДИН раз в начале _run_pipeline()."""
        if self._tick_locked:
            # Уже заблокирован — возвращаем кэш (безопасно для повторного вызова)
            return self._tick_scenes.get(location_id)
        # ADR-SCENE-LOCK: Загружаем актуальное состояние (с traversals от прошлого тика)
        scene = self.get_scene_state_uncached(campaign_id, location_id)
        if scene is not None:
            self._tick_locked = True
            self._tick_campaign_id = campaign_id
            self._tick_scenes[location_id] = scene
            try:
                _recog = scene.get("player_recognition", {})
                logger.debug(f"[LOCK] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except (AttributeError, TypeError) as e:
                logger.warning(f"[LOCK] error reading recog_keys: {e}")
        return scene

    def lock_all_for_tick(self, campaign_id: str, location_ids: list[str]) -> None:
        """Дополнение Б (п. Б.6.1): Загружает и блокирует несколько локаций разом."""
        if self._tick_locked:
            return
        self._tick_locked = True
        self._tick_campaign_id = campaign_id
        self._tick_scenes = {}
        for _loc_id in location_ids:
            scene = self.get_scene_state_uncached(campaign_id, _loc_id)
            if scene is not None:
                self._tick_scenes[_loc_id] = scene

    def unlock_tick(self, campaign_id: str) -> None:
        """Разблокирует тик. Персистит кэш.
        ADR-SCENE-LOCK: НЕ очищаем _tick_scene сразу — bridge может читать его
        в SSE-потоке после unlock. Кэш живёт до следующего lock_for_tick()."""
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # СНИМАЕМ LOCK ДО save — иначе guard в save_scene_state() сделает return!
            self._tick_locked = False
            # S1-FIX (INV-COMMIT-CARDINALITY): 1 атомарный коммит для всех локаций.
            _valid_scenes = {k: v for k, v in self._tick_scenes.items() if v is not None}
            if self._persistence and _valid_scenes:
                # M1b.4.2: directed-поддерево обязано быть идентичным во всех
                # локациях кампании (отношения переживают смену локации) —
                # синхронизация ДО транзакции, консистентность — транзакцией.
                self._sync_relationship_directed(_valid_scenes)
                self._persistence.atomic_commit_all(
                    campaign_id=campaign_id,
                    all_scenes=_valid_scenes,
                )
                # M1b.4.2: маркер .migrated только ПОСЛЕ успешного коммита
                # (ратифицировано: истина cutover — сохранённый v2, не маркер)
                self._confirm_v2_migration(campaign_id)
            # Диагностика: round-trip проверка — пережил ли traversal save→load?
            if self._persistence and self._tick_scenes:
                # Проверяем первую попавшуюся сцену из кэша
                _verify = self._persistence.load_scene(campaign_id)
                _trav_after = (
                    list(_verify.get("active_traversals", {}).keys())
                    if _verify
                    else "LOAD_FAILED"
                )
                logger.debug(f"[UNLOCK_TRACE] AFTER LOAD: traversals={_trav_after}")
            # НЕ очищаем _tick_scenes! Bridge может читать их в SSE-потоке.
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
        _time_in = result_snapshot.get("game_time_seconds", "MISSING")
        logger.debug(
            f"[COMMIT_TRACE] campaign={campaign_id} tick={result_snapshot.get('tick')} trav_keys={_trav_keys} id={id(result_snapshot)}"
        )
        if self._tick_campaign_id == campaign_id:
            # Дополнение Б: Обновляем словарь сцен, а не одиночный слот
            _loc_id = result_snapshot.get("location_id", "default")
            self._strip_husk_npcs(result_snapshot)
            # PR-7/S268 (ADR-TEMPORAL-EPOCH): deepcopy = броня до-эпохи против
            # temporal alias (до PR-6b result_snapshot мог алиасить мутируемый
            # input). Теперь result_snapshot = overlay.commit() — свежесобранный
            # dict; overlay умирает с execute(), epoch иммутабелен → алиас-
            # протечка невозможна ПО ПОСТРОЕНИЮ. EPOCH_OWNERSHIP_ENFORCEMENT:
            # OFF = legacy-броня (поведение байт-в-байт); ON = 0 копий
            # (ownership-move; доказанная миграция → дефолт ON, мандат XIII)
            import os as _os
            if _os.environ.get("EPOCH_OWNERSHIP_ENFORCEMENT", "0") == "1":
                self._tick_scenes[_loc_id] = result_snapshot
            else:
                self._tick_scenes[_loc_id] = copy.deepcopy(result_snapshot)
            # S266-ОТКАТ: несущий deepcopy (Temporal alias, класс A).
            # PR-5 только после полной Epoch-границы.
            try:
                _recog = self._tick_scenes[_loc_id].get("player_recognition", {})
                _time_out = self._tick_scenes[_loc_id].get("game_time_seconds", "MISSING")
                logger.debug(f"[COMMIT] campaign={campaign_id} loc={_loc_id} recog_keys={list(_recog.keys())}")
            except (AttributeError, TypeError) as e:
                logger.warning(f"[COMMIT] error reading recog_keys: {e}")
            logger.debug(
                f"[COMMIT_TRACE] _tick_scenes[{_loc_id}] updated, trav_keys_after={list(self._tick_scenes[_loc_id].get('active_traversals', {}).keys())}"
            )
            logger.debug(
                f"[S83.1] commit_tick_result: persistence target updated for {campaign_id}:{_loc_id}"
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
            # V8-SP-29 FIX: используем load_scene_at для правильной per-location загрузки
            if location_id:
                scene = self._persistence.load_scene_at(campaign_id, location_id)
            else:
                scene = self._persistence.load_scene(campaign_id)
            if scene:
                try:
                    _recog = scene.get("player_recognition", {})
                    logger.debug(f"[LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except (AttributeError, TypeError) as e:
                    logger.warning(f"[LOAD] error reading recog_keys: {e}")
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
            and location_id in self._tick_scenes
        ):
            return self._tick_scenes[location_id]
        # Устав 4.2.1: читаем из порта (SQLite) если доступен
        if self._persistence:
            # V8-SP-29 FIX: используем load_scene_at для правильной per-location загрузки
            if location_id:
                scene = self._persistence.load_scene_at(campaign_id, location_id)
            else:
                scene = self._persistence.load_scene(campaign_id)
            if scene:
                try:
                    _recog = scene.get("player_recognition", {})
                    logger.debug(f"[LOAD] campaign={campaign_id} recog_keys={list(_recog.keys())}")
                except (AttributeError, TypeError) as e:
                    logger.warning(f"[LOAD] error reading recog_keys: {e}")
            if scene:
                import inspect

                _frame = inspect.currentframe()
                _caller = _frame.f_back if _frame else None  # noqa: ENIGMA001
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
        # FIX-RC2-v2: оболочки не попадают в RAM при загрузке
        self._strip_husk_npcs(scene)
        # Гарантируем актуальные local_position при каждой загрузке
        self._enrich_local_positions(campaign_id, scene)
        # Обогащаем spatial_walls/obstacles из editor JSON, если их нет
        self._enrich_spatial_data(campaign_id, scene)
        # Миграция: удаляем legacy snapshot_tick (Устав §3 — тик через TemporalEngine)
        if "snapshot_tick" in scene:
            del scene["snapshot_tick"]
        # ADR-046 Fix: Гарантировать наличие имени (name) в npc_positions для Target Resolution (Слой 2)
        _loc_id = scene.get("location_id", "")
        for npc_id, pos_data in scene.get("npc_positions", {}).items():
            if isinstance(pos_data, dict):
                if not pos_data.get("name"):
                    pos_data["name"] = _npc_id_to_display(npc_id)

                # SC-3 FIX: Сбрасываем position, если она содержит префикс другой локации.
                _pos = pos_data.get("position", "")
                if _pos and ":" in str(_pos):
                    _prefix = str(_pos).split(":")[0]
                    if _prefix != _loc_id:
                        logger.warning(f"[SC-3-LOAD] NPC '{npc_id}' has foreign node '{_pos}' in loc '{_loc_id}'. Resetting.")
                        pos_data["position"] = ""
                        pos_data["current_node"] = ""
        # ADR-102: Инжект campaign_id для SpatialService (замена мёртвого load_graph)
        scene["campaign_id"] = campaign_id
        return scene

    def _enrich_spatial_data(self, campaign_id: str, scene_state: dict) -> None:
        """Обогащает spatial_walls/obstacles из editor JSON.
        S143 FIX: Всегда пересобираем стены из JSON, чтобы гарантировать авто-резку дверями (DOUBLE TRUTH fix).
        """
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

    @staticmethod
    def _strip_foreign_npcs(scene_state: dict) -> None:
        """FIX-RC2: сцена не персистит чужих NPC (double presence).

        Извлечение (S186) чистит RAM, но призрак успевал вернуться в коммит
        (стале-порядок фаз / write-back) — NPC жил в двух сценах сразу
        и вечно оставался видим в исходной локации. Владелец NPC — сцена
        его location_id (S186_INJECT); чужие записи удаляются на границе
        персистентности.
        """
        _loc = scene_state.get("location_id", "")
        _positions = scene_state.get("npc_positions")
        if not _loc or not isinstance(_positions, dict):
            return
        for _nid in list(_positions.keys()):
            _entry = _positions.get(_nid)
            _entry_loc = _entry.get("location_id") if isinstance(_entry, dict) else None
            if _entry_loc and _entry_loc != _loc:
                del _positions[_nid]

    @staticmethod
    def _strip_husk_npcs(scene_state: dict) -> int:
        """FIX-RC2-v2: пустые записи-оболочки переноса (loc/pos/local = None).

        Реальный NPC всегда имеет пространственные данные (SC-1..SC-5).
        Оболочка без всего — призрак S186-переноса: заморожена на рендере
        и создаёт double presence в персистенте.
        """
        _positions = scene_state.get("npc_positions")
        if not isinstance(_positions, dict):
            return 0
        _removed = 0
        for _nid in list(_positions.keys()):
            _e = _positions.get(_nid)
            if not isinstance(_e, dict):
                continue
            _lp = _e.get("local_position")
            _has_xy = isinstance(_lp, dict) and _lp.get("x") is not None
            if not (_e.get("location_id") or _e.get("position") or _has_xy):
                del _positions[_nid]
                _removed += 1
        return _removed

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет SceneState через PersistencePort (Устав 4.2.1).
        ADR-SCENE-LOCK: Если тик заблокирован, обновляет кэш вместо записи на диск.
        Персист произойдёт в unlock_tick()."""
        scene_state.pop("snapshot_tick", None)
        self._strip_husk_npcs(scene_state)
        # TICK-SCOPED IDENTITY: Внутри тика обновляем кэш, НЕ пишем на диск.
        # Запись на диск происходит один раз в unlock_tick().
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # Дополнение Б: обновляем кэш для конкретной локации
            _loc_id = scene_state.get("location_id", "default")
            self._tick_scenes[_loc_id] = scene_state
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
            # Stage 0 Task 0.3: JSON as runtime truth FORBIDDEN.
            # Делегируем в atomic_commit_all (Устав §4.2.1) — единственный write-path.
            _loc_id = scene_state.get("location_id", "default")
            self._persistence.atomic_commit_all(
                campaign_id=campaign_id,
                all_scenes={_loc_id: scene_state}
            )
        else:
            logger.error("[SCENE] PersistencePort missing! Cannot save scene state.")
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

        # ADR-048 Phase 3: Запись player_distances ЗАПРЕЩЕНА.
        # SpatialQueryService является авторитетом. player_distances — derived projection.
        # Narrative-позиция (player_position как строка "стоит") пока оставлена для DM контекста.
        if player_position is not None:
            scene_state["player_position"] = player_position

        # if player_distances is not None:
        #     scene_state["player_distances"] = player_distances

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
        """DEGOD ITER3: делегат — тело в scene_state/dm_presentation.py."""
        from app.services.scene_state.dm_presentation import build_npc_context_block

        return build_npc_context_block(scene_state, npc_id, npc_name, spatial_service)

    # ─────────────────────────────────────────────────────────────────────────
    # Загрузка шаблонов
    # ─────────────────────────────────────────────────────────────────────────

    def _load_templates(self) -> dict:
        if self._templates_cache is not None:
            return self._templates_cache
        path = self._templates_file()
        if path.exists():
            try:
                self._templates_cache = json.loads(path.read_text(encoding="utf-8-sig"))
                return self._templates_cache
            except (json.JSONDecodeError, OSError) as e:
                raise RuntimeError(f"[SCENE] Ошибка чтения шаблонов: {e}")
        # FIX: Если шаблонов нет — возвращаем пустой словарь. Крашим только при ошибке чтения.
        logger.warning(f"[SCENE] location_templates.json не найден по пути {path}. Возвращаю пустой словарь.")
        self._templates_cache = {}
        return self._templates_cache

    def _find_editor_location(self, campaign_id: str, location_id: str) -> dict | None:
        """DEGOD ITER2: делегат — тело в scene_state/editor_locator.py."""
        return _find_editor_location_impl(self.campaigns_dir, campaign_id, location_id)


    def _find_first_editor_location(self, campaign_id: str) -> dict | None:
        """DEGOD ITER2: делегат — тело в scene_state/editor_locator.py."""
        return _find_first_editor_location_impl(self.campaigns_dir, campaign_id)


    def find_starting_location(self, campaign_id: str) -> str:
        """DEGOD ITER2: делегат — тело в scene_state/editor_locator.py."""
        return _find_starting_location_impl(self.campaigns_dir, campaign_id)


    def reinit_campaign(self, campaign_id: str) -> dict | None:
        """Переинициализация сцены кампании из editor JSON.
        Вызывается из new_game() ПОСЛЕ очистки persistence.
        Находит начальную локацию и создаёт свежую сцену."""
        # V8-SP-26 FIX: инвалидируем все кэши при переинициализации
        from app.services.spatial.spatial_factory import SpatialFactory
        from app.services.spatial.spatial_registry import SpatialRegistry
        SpatialFactory.invalidate_cache(campaign_id)
        if self._life_engine:
            self._life_engine.invalidate_cache(campaign_id)
        SpatialRegistry.invalidate_cache(campaign_id)
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
        """DEGOD ITER2: делегат — тело в scene_state/editor_locator.py."""
        return _nearest_node_to_xy_impl(editor_data, x, y)

    # initialize_scene
    # ─────────────────────────────────────────────────────────────────────────

    def initialize_scene(
        self, campaign_id: str, location_id: str, time_of_day: str = "12:00"
    ) -> dict:
        """DEGOD ITER4: делегат — тело в scene_state/scene_factory.py."""
        from app.services.scene_state.scene_factory import build_initial_scene

        templates = self._load_templates()
        template = templates.get(location_id, {})
        editor_data = self._find_editor_location(campaign_id, location_id)
        scene_state = build_initial_scene(
            campaign_id=campaign_id,
            location_id=location_id,
            time_of_day=time_of_day,
            template=template,
            editor_data=editor_data,
            build_spatial_data=self._build_spatial_data,
        )
        self.save_scene_state(campaign_id, scene_state)
        logger.info(
            f"[SCENE] Инициализирована сцена '{location_id}' "
            f"(время: {time_of_day}, объектов: {len(scene_state.get('objects', {}))}, NPC: {len(scene_state.get('npc_positions', {}))})"
        )
        return scene_state

    @staticmethod
    def _select_time_variant(template: dict, time_of_day: str) -> dict:
        """DEGOD ITER4: делегат — тело в scene_state/scene_factory.py (внешний потребитель: time_advance.py:98)."""
        from app.services.scene_state.scene_factory import select_time_variant

        return select_time_variant(template, time_of_day)

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
                # FIX-ATOMIC (приказ Мастера, forensic bsf_trace): SceneChange
                # для NPC, ОТСУТСТВУЮЩЕГО в этой сцене, = источник torn-state
                # (thief_shadow: копия с city_gate-координатами в tavern при
                # живой копии в city_gate, тики 33+). Легальный вход в новую
                # локацию — только cross_loc_materialize (S186 INJECT пишет
                # entry напрямую). Остальное — громкий отказ, NPC не трогаем.
                if (
                    change.target not in pos
                    and not getattr(change, "cause", "").startswith(
                        ("cross_loc_materialize", "boundary_arrival")
                    )
                ):
                    logger.error(
                        f"[ATOMIC_GUARD] npc={change.target} отсутствует в сцене "
                        f"'{scene_state.get('location_id', '?')}'; field={change.field} "
                        f"cause='{getattr(change, 'cause', '')}' — отклонено (torn-write)"
                    )
                    return True
                entry = pos.setdefault(change.target, {})
                _old_position = entry.get("position", "")

                if (
                    change.field == "position"
                    and _old_position == change.value
                    and getattr(change, "cause", "") != "traversal_complete"  # noqa: ENIGMA002
                ):
                    return True

                entry[change.field] = change.value

                if change.field == "position":
                    location_id = scene_state.get("location_id", "")
                    target_loc = (
                        getattr(change, "target_location_id", "") or location_id  # noqa: ENIGMA002
                    )
                    if target_loc and change.value:
                        # Обновляем локацию NPC ТОЛЬКО при фактическом материализации (cross_loc_materialize).
                        # Простое перемещение к boundary node не должно менять location_id,
                        # иначе NPC выпадает из scene_state текущей локации на следующем тике.
                        if target_loc != location_id and getattr(change, "cause", "").startswith("cross_loc_materialize"):  # noqa: ENIGMA002
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
                            if svc and (node := svc.get_node(change.value) or svc.get_node(
                                f"{target_loc}:{change.value}"
                            )):
                                # P2: Сохраняем старую позицию ДО перезаписи
                                from_xy = entry.get(
                                    "local_position", {"x": 0.0, "y": 0.0}
                                )
                                if not isinstance(from_xy, dict):
                                    from_xy = {"x": 0.0, "y": 0.0}

                                exact_xy = getattr(change, "target_local_xy", None)  # noqa: ENIGMA002
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
                                    getattr(change, "cause", "") != "traversal_complete"  # noqa: ENIGMA002
                                    and (
                                        change.target not in _active_travs
                                        or _active_travs[change.target].get("status")
                                        != "MOVING"
                                    )
                                ):
                                    # ADR-O-323: Layer 1 Continuity. TraversalState создаётся
                                    # исключительно MovementPlanner'ом для макро-перемещений (field="position").
                                    # SceneStateManager только применяет готовый паспорт.
                                    _proposal = getattr(change, "traversal_proposal", None)  # noqa: ENIGMA002
                                    if _proposal:
                                        # Проверка актуальности proposal (stale tick detection)
                                        if _proposal.planned_tick != change.tick:
                                            logger.error(
                                                f"[PIPELINE][SCENE_CHANGE][STALE_PROPOSAL_TICK] "
                                                f"npc={change.target} prop_tick={_proposal.planned_tick} change_tick={change.tick}"
                                            )
                                            # N-31 FIX: Отбрасываем устаревшее предложение (возврат False), чтобы предотвратить inconsistent state
                                            return False
                                        else:
                                            from app.domain.traversal_schema import build_traversal_dict
                                            _traversal_dict = build_traversal_dict(_proposal)
                                            _active_travs = scene_state.setdefault("active_traversals", {})
                                            _existing_trav = _active_travs.get(change.target)
                                            # SLEEP_FIX #1: НЕ перезаписывать in-flight транзит.
                                            # Если NPC уже в MOVING-транзите с той же целью — сохраняем оригинальный
                                            # started_tick, иначе транзит никогда не завершится (expected_arrival_tick
                                            # всегда будет current_tick + duration_ticks).
                                            if (
                                                _existing_trav
                                                and _existing_trav.get("status") == "MOVING"
                                                and _existing_trav.get("target_node") == _traversal_dict.get("target_node")
                                            ):
                                                logger.debug(
                                                    f"[SSM] Traversal NEW suppressed (in-flight): "
                                                    f"npc={change.target} target={_traversal_dict.get('target_node')} "
                                                    f"(preserving started_tick={_existing_trav.get('started_tick')})"
                                                )
                                            else:
                                                _active_travs[change.target] = _traversal_dict
                                                # S203.1 (Stage 2A, ADR-O-363): FALLBACK-зеркало.
                                                # В dual-rail compiled-изменения пишет ProjectionEngine
                                                # РАНЬШЕ (ADR-O-204) — тогда traversal уже MOVING,
                                                # guard выше блокирует эту ветку, и зеркало не
                                                # срабатывает (двойной commit исключён guard'ом).
                                                # Здесь — материализации, миновавшие shadow-компиляцию.
                                                from app.services.action.commitment_registry import CommitmentRegistry
                                                CommitmentRegistry.mirror_traversal_materialized(
                                                    scene_state=scene_state,
                                                    tick=change.tick,
                                                    npc_id=change.target,
                                                    cause=getattr(change, "cause", ""),
                                                    target_node=_traversal_dict.get("target_node"),
                                                )
                                    elif change.field == "position" and getattr(change, "cause", "") != "traversal_complete" and not getattr(change, "cause", "").startswith("cross_loc_materialize"):  # noqa: ENIGMA002
                                        # Контракт: macro relocation (field="position") обязан иметь proposal.
                                        # Исключение: traversal_complete и cross_loc_materialize (snap позиции, proposal не нужен).
                                        # Микро-перемещения (field="local_position") его не требуют.
                                        logger.error(
                                            f"[PIPELINE][SCENE_CHANGE][MISSING_TRAVERSAL_PROPOSAL] "
                                            f"npc={change.target} cause={change.cause} field={change.field} "
                                            f"Macro movement without proposal (ADR-O-323 violation)"
                                        )
                        except (KeyError, ValueError, TypeError, AttributeError) as exc:
                            logger.error(
                                f"[PIPELINE][SCENE_CHANGE][APPLY_CRASH] npc={change.target} exc={exc}"
                            )
                            raise

                elif change.field in (
                    "local_position",
                    "velocity",
                    "exertion_level",
                    "body_heading",
                ):
                    entry[change.field] = change.value
                    # ADR-O-315: Игрок читается из npc_positions["player"].

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
                from app.domain.body import Item
                from app.services.body.body_topology_service import BodyTopologyService

                topo_data = scene_state.get("player_body_topology")
                if not topo_data:
                    topo = BodyTopologyService.create_topology("player")
                else:
                    topo = BodyTopologyService.deserialize(topo_data)

                if change.field == "add" and isinstance(change.value, dict):
                    for item_id, slot_id in change.value.items():
                        if item_id.startswith("_"):
                            continue
                        item = Item(item_id=item_id, name=item_id)
                        BodyTopologyService.add_item(topo, slot_id, item)
                elif change.field == "remove" and isinstance(change.value, dict):
                    for item_id, slot_id in change.value.items():
                        BodyTopologyService.remove_item(topo, slot_id, item_id)

                scene_state["player_body_topology"] = BodyTopologyService.serialize(topo)

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

        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"[SCENE] Ошибка применения {change.type.value}: {e}")
            _log_change(change, campaign_id, applied=False)
            raise

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
        # ADR-O-363 (S203.3, Ц1): zombie cleanup — SSM = SSOT owner.
        self.gc_traversals(scene_state)
        if applied_count:
            logger.info(
                f"[SCENE] Применено {applied_count}/{len(changes)} изменений (in-memory, persist=Phase10)"
            )
        return applied_count

    def gc_traversals(self, scene_state: dict) -> int:
        """S203.3 (ADR-O-363, Ц1): SSM — ЕДИНСТВЕННЫЙ GC-владелец traversals.

        Удаляет terminal-статусы (COMPLETED/CANCELLED). Вызывается:
        (а) из apply_changes — историческая точка;
        (б) из TickOrchestrator после Фазы 0.5 — гарантия одного GC-прохода
        на тик (Ц1 убрал самоудаление TES; без гарантии терминальная запись
        живёт до следующего apply_changes — окно, ловимое INV-TRAV-ZOMBIE).
        """
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
        return len(_zombie_ids)

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
        # IPT-CLEANUP: Сброс dedup-set для SPATIAL_ENFORCEMENT на границе тика.
        if hasattr(self, "_spatial_enforcement_logged"):
            self._spatial_enforcement_logged.clear()
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
            0.0  # BUG-WALL-CLOCK FIX: Убираем wall-clock time из simulation layer (§15.1)
        )

        # ADR-O-309: WorldProjectionBuffer (Shadow Causality).
        # Запускается внутри atomic commit boundary ДО persistence и обновления state_t-1.
        # Порядок: state_t финализирован → projection → persistence → update state_t-1.
        _loc_id = scene_state.get("location_id", "")
        _tick = scene_state.get("tick", 0)

        # AUDIT #10 VERDICT=OFF (2026-08): генерация WorldProjectionEvent
        # отключена — потребителей в продукте нет, события создавались и
        # умирали каждый коммит. Концепт сохранён в
        # app/services/offscreen/world_projection_buffer.py; возврат — при
        # появлении реального consumer (DM-агент, слухи).
        # _SHADOW_CAUSALITY_DISABLED

        # S1-FIX (INV-COMMIT-CARDINALITY): Фаза 10 не пишет в БД напрямую.
        # Она только обновляет кэш в RAM. Запись на диск происходит 1 раз в unlock_tick().
        if self._tick_campaign_id == campaign_id:
            _loc_id = scene_state.get("location_id", "default")
            import copy

            # PR-7/S268: тот же паттерн ownership-move (см. commit_tick_result)
            import os as _os
            if _os.environ.get("EPOCH_OWNERSHIP_ENFORCEMENT", "0") == "1":
                self._tick_scenes[_loc_id] = scene_state
            else:
                self._tick_scenes[_loc_id] = copy.deepcopy(scene_state)
            # ADR-O-309: SceneStateManager — единственный источник state_t-1.
            # S266-ОТКАТ: deepcopy ЗДЕСЬ несущий (класс A) — docstring
            # commit_tick_result предупреждал: без копии alias протекает
            # (Temporal Isolation, L4). Удаляется только в PR-5, когда
            # Epoch-граница построена полностью (WorldView в TickState).
            # S269-C2 (AUDIT #10): _last_committed_npcs потребляется только
            # WorldProjectionBuffer — консюмер ОТКЛЮЧЁН (VERDICT=OFF,
            # _SHADOW_CAUSALITY_DISABLED, :1702-1707). Копия за тик ради
            # мёртвого читателя = чистый расход. Ленивость: храним ссылку,
            # deepcopy переносится в get_last_committed_npcs() при первом
            # чтении. Если buffer вернут — семантика сохранится (геттер
            # вернёт независимую копию), перф-потеря вернётся только
            # с живым потребителем.
            self._last_committed_npcs_src = npc_dicts or []
            self._last_committed_npcs = None
        return 2

    def get_last_committed_npcs(self) -> list[dict]:
        """Возвращает state_t-1 (committed snapshot) для WorldProjectionBuffer.

        S269-C2: ленивая deepcopy — копия создаётся при первом чтении,
        не на каждом коммите (потребитель выключен AUDIT #10)."""
        _cached = getattr(self, "_last_committed_npcs", None)
        if _cached is not None:
            return _cached
        import copy as _copy
        _copy_list = _copy.deepcopy(getattr(self, "_last_committed_npcs_src", []))
        object.__setattr__(self, "_last_committed_npcs", _copy_list) if hasattr(self, "__slots__") else setattr(self, "_last_committed_npcs", _copy_list)
        self._last_committed_npcs = _copy_list
        return _copy_list

    # ─────────────────────────────────────────────────────────────────────────
    # R2.1 — get_scene_events_block: блок для DM промпта
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_scene_events_block(scene_state: dict) -> str:
        """DEGOD ITER3: делегат — тело в scene_state/dm_presentation.py."""
        from app.services.scene_state.dm_presentation import get_scene_events_block

        return get_scene_events_block(scene_state)

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
            raise

        for npc_id, entry in npc_positions.items():
            # Миграция имени: в старых сохранениях отсутствует поле name (Баг 3)
            if "name" not in entry:
                entry["name"] = _npc_id_to_display(npc_id)

            # BUG-SPATIAL-004 FIX: Блок пространственного контекста удалён (ADR-O-314).
            # Игрок течёт через тот же path, что и NPC (editor_coords / svc.get_node).
            current_node = entry.get("position", "")

            # SC-3 FIX: Если current_node содержит префикс другой локации (например, после load),
            # сбрасываем его, чтобы SpatialService мог пересчитать позицию в текущей локации.
            if current_node and ":" in current_node:
                _node_prefix = current_node.split(":")[0]
                if _node_prefix != location_id:
                    logger.warning(f"[SC-3] NPC '{npc_id}' has foreign node '{current_node}' in loc '{location_id}'. Resetting position.")
                    entry["position"] = ""
                    entry["current_node"] = ""
                    current_node = ""
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
                    # S273-GAP12 (root-cause fix, вердикт Мастера: только А2):
                    # xy НЕ пишем. TES (traversal_execution_system, Фаза 0.5,
                    # tick_orchestrator:2270) — единственный владелец производной
                    # координаты MOVING-NPC (ADR-O-315: «координата — производная»).
                    # Этот второй вычислитель читал scene["tick"] вне tick-лока:
                    # при elapsed<0 clamp(:1925) давал wp[0] — NPC навсегда
                    # закреплялся в стартовом waypoint (RCB v3: 133 итераций
                    # xy≡wp[0] до float-знака, relocation-петля). Потребителей
                    # GAP12-интерполяции нет (аудит: GAP12 MOVING consumer =
                    # NONE FOUND; заявленный контракт CFRM/ImpactEngine —
                    # фантом, слои xy не читают). Флаг in_transit сохранён —
                    # единственный живой потребитель:
                    # behavior_manifestation_service:154 (флаг-семантика, не xy).
                    entry["in_transit"] = True
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
                # S-03.2 FIX: ADR-121 запрещает (0,0). Старые сейвы могут содержать (0,0) — считаем их невалидными.
                _is_valid = (
                    isinstance(lp, dict) and isinstance(lp.get("x"), (int, float))
                    and not (lp.get("x") == 0.0 and lp.get("y") == 0.0)
                )
                if _is_valid:
                    # S-03 FIX: Проверка, не оказался ли NPC внутри препятствия
                    _lx = lp.get("x", 0.0)
                    _ly = lp.get("y", 0.0)
                    _inside_obstacle = False
                    for obs in scene_state.get("spatial_obstacles", []):
                        if point_in_rect((_lx, _ly), obs.get("x", 0), obs.get("y", 0), obs.get("w", 0), obs.get("h", 0)):
                            _inside_obstacle = True
                            break
                    if not _inside_obstacle:
                        continue  # Координаты валидны и вне препятствий, не трогаем!
                    logger.warning(f"[SCENE] NPC {npc_id} inside obstacle at ({_lx},{_ly}), relocating to node center")

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
                            svc.get_central_node()  # noqa: ENIGMA001
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
                    # IPT-CLEANUP: WARNING → INFO + deduplication по (npc_id, fallback_node).
                    # Логировать только первый раз для каждого NPC на каждом fallback-узле.
                    _dedup_key = (npc_id, _fallback_node.node_id)
                    if not hasattr(self, "_spatial_enforcement_logged"):
                        self._spatial_enforcement_logged: set = set()
                    if _dedup_key not in self._spatial_enforcement_logged:
                        logger.info(
                            f"[SPATIAL_ENFORCEMENT] NPC '{npc_id}' размещён на fallback-узле "
                            f"'{_fallback_node.node_id}' ({_fallback_node.x}, {_fallback_node.y})"
                        )
                        self._spatial_enforcement_logged.add(_dedup_key)
                else:
                    logger.error(
                        f"[SPATIAL_ENFORCEMENT] NPC '{npc_id}' — ГРАФ ПУСТ! NPC skipped."
                    )

            # S-03: NPC Position Validation — если NPC оказался внутри walk=False объекта, вытаскиваем его
            _lp = entry.get("local_position", {})
            if isinstance(_lp, dict) and isinstance(_lp.get("x"), (int, float)) and editor_data:
                _px, _py = _lp.get("x", 0.0), _lp.get("y", 0.0)
                _is_stuck = False
                for obj in editor_data.get("objects", []):
                    _pass = obj.get("passability", {})
                    if not _pass.get("walk", True):
                        _pos = obj.get("position", {})
                        _size = obj.get("size", {})
                        _ox, _oy = _pos.get("x", 0.0), _pos.get("y", 0.0)
                        _ow, _oh = _size.get("w", 0.0), _size.get("h", 0.0)
                        if _ox <= _px <= _ox + _ow and _oy <= _py <= _oy + _oh:
                            _is_stuck = True
                            _stuck_obj_id = obj.get("id", "unknown")
                            break

                if _is_stuck and svc:
                    # S-03.1: Ищем действительно безопасный узел через SpatialService API
                    _safe_node = svc.get_nearest_safe_node(zone_id=location_id, origin_xy=(_px, _py))
                    if _safe_node:
                        entry["local_position"] = {"x": _safe_node.x, "y": _safe_node.y}
                        logger.warning(
                            f"[S-03_OBSTACLE_RECOVERY] NPC '{npc_id}' застрял внутри препятствия '{_stuck_obj_id}'. "
                            f"Перемещён на безопасный узел '{_safe_node.node_id}'."
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
                from app.services.spatial.spatial_factory import SpatialFactory
                svc = SpatialFactory.build_for_campaign(
                    campaign_id=campaign_id,
                    location_id=location_id,
                    scene_state=scene_state,
                )
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
            except (KeyError, ValueError, AttributeError) as exc:
                logger.error(
                    f"[SPATIAL] Ошибка SpatialService для NPC {npc_id}: {exc} "
                    f"— local_position не обновлён"
                )
                raise

        if save_after:
            self.save_scene_state(campaign_id, scene_state)

    # ─────────────────────────────────────────────────────────────────────────
    # get_scene_description — для DM промпта
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_scene_description(scene_state: dict) -> str:
        """DEGOD ITER3: делегат — тело в scene_state/dm_presentation.py."""
        from app.services.scene_state.dm_presentation import get_scene_description

        return get_scene_description(scene_state)


    def _sync_relationship_directed(self, scenes: Dict[str, Dict[str, Any]]) -> None:
        """M1b.4.2: копия directed-поддерева из сцены-источника во все сцены.
        Источник: первая сцена с непустым relationship_state.directed
        (все копии идентичны транзакцией — выбор источника детерминирован
        порядком dict, самосогласован внутри тика)."""

        def _get_directed(scene: Dict[str, Any]) -> Any:
            _rs = scene.get("relationship_state") if isinstance(scene, dict) else None
            if not isinstance(_rs, dict):
                return None
            _d = _rs.get("directed")
            return _d if isinstance(_d, dict) and _d else None

        _source = next((_get_directed(s) for s in scenes.values() if _get_directed(s)), None)
        if _source is None:
            return
        import copy as _copy

        for scene in scenes.values():
            if isinstance(scene, dict):
                _rs = scene.setdefault("relationship_state", {})
                if isinstance(_rs, dict):
                    _rs["directed"] = _copy.deepcopy(_source)

    def _confirm_v2_migration(self, campaign_id: str) -> None:
        """M1b.4.2: .migrated после успешного atomic_commit_all. Безопасный
        no-op при отсутствии legacy-файла (новые кампании)."""
        try:
            from app.services.social.relationship_state_store import (
                RelationshipStateStore,
            )

            _saves = getattr(self, "_saves_dir", None)
            if _saves:
                RelationshipStateStore.confirm_migration(campaign_id, str(_saves))
        except Exception as e:
            logger.warning(f"[M1b.4.2] confirm_migration: {e}")


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
# DEGOD ITER2: npc_id → читаемое имя экстрагировано в
# app/services/scene_state/npc_display_name.py. Re-export сохраняет
# import-поверхность (dm_agent, recognition_layer, diagnose_spatial).
# ──────────────────────────────────────────────────────────────────────────────
from app.services.scene_state.npc_display_name import _npc_id_to_display

# ──────────────────────────────────────────────────────────────────────────────
# Глобальный синглтон
# ──────────────────────────────────────────────────────────────────────────────

_scene_state_manager: SceneStateManager | None = None


def get_scene_state_manager() -> SceneStateManager:
    global _scene_state_manager
    if _scene_state_manager is None:
        _scene_state_manager = SceneStateManager()
    return _scene_state_manager


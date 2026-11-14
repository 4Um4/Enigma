# path: backend/tests/test_p1_04_save_migration_w5.py
# Назначение: P1-04 (ADR-O-439 W5) — unit-тесты одноразовой миграции
#     local_position NPC в мировой фрейм при загрузке сейва.
#     Контракт: ROADMAP §P1-04 (W5: версия < W → сдвиг на origin location_id,
#     идемпотентность, node_17 не роняет загрузку; §19 Устава — не удалять сейвы;
#     S354 — исходные байты — единственная правда, .bak.pre-p1-04 внешний).
# Зависимости: pytest, unittest.mock, SceneStateManager (mock persistence +
#     monkeypatch _find_editor_location), реальные координаты из легаси-сейва
#     и реальный origin tavern из compiled/spatial_registry.json.
# Основные сущности:
#     - test_w5_migration_shifts_local_position — версия < W + world frame → сдвиг
#     - test_w5_idempotent_on_repeated_load — версия == W → no-op, persist не вызван
#     - test_w5_node_17_does_not_raise — B-15: висячая ссылка не роняет
#     - test_w5_local_frame_file_no_shift — global_coords=False → только версия
#     - test_w5_no_persistence_graceful — persistence=None → RAM-only, no crash
#     - test_w5_skips_zero_zero — ADR-121: (0,0) битая → пропускается
#     - test_w5_editor_not_found_deferred — editor JSON недоступен → отложена
"""
P1-04 (ADR-O-439 W5): миграция существующих сейвов под единый мировой фрейм.

После P1-03 (tavern.json переведён в мировой фрейм) легаси-сейвы хранят
local_position NPC в ЛОКАЛЬНОМ фрейме (например maid_lusya x=7.987, y=1.826).
При первой загрузке после P1-03 _migrate_coord_frame_W5 сдвигает координаты
на origin их location_id и ставит coord_frame_version='W'. Повторная загрузка
идемпотентна. Висячая ссылка maid_lusya.position='node_17' (B-15) не роняет
миграцию — метод работает с local_position, не с position (node-id); node_17
обрабатывается существующей fallback-цепочкой _enrich_local_positions.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.scene_state.scene_factory import build_initial_scene
from app.services.scene_state_manager import SceneStateManager


# ─────────────────────────────────────────────────────────────────────────────
# Реальные данные из археологии (campaign_state.json + compiled/spatial_registry.json)
# ─────────────────────────────────────────────────────────────────────────────

# tavern origin из compiled/spatial_registry.json (post-P1-03)
_TAVERN_ORIGIN_X = 25.03333333333332
_TAVERN_ORIGIN_Y = 5.018000000000007

# maid_lusya local_position из легаси-сейва (campaign_state.json:515-518)
_MAID_LUSYA_X = 7.98736111111111
_MAID_LUSYA_Y = 1.8263888888888888


# ─────────────────────────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def manager(tmp_path: Path) -> SceneStateManager:
    """SceneStateManager с tmp data_dir и mock persistence."""
    persistence = MagicMock()
    persistence.atomic_commit_all = MagicMock()
    return SceneStateManager(data_dir=tmp_path, persistence=persistence)


@pytest.fixture
def tavern_editor_world() -> dict:
    """Editor JSON таверны — мировой фрейм (post-P1-03).

    Соответствует tavern.json после P1-03: global_coords=true,
    origin=(25.0333, 5.018).
    """
    return {
        "location_id": "tavern",
        "global_coords": True,
        "origin": {"x": _TAVERN_ORIGIN_X, "y": _TAVERN_ORIGIN_Y},
    }


@pytest.fixture
def tavern_editor_local() -> dict:
    """Editor JSON таверны — локальный фрейм (легаси, до P1-03)."""
    return {
        "location_id": "tavern",
        "global_coords": False,
        "origin": {"x": 0.0, "y": 0.0},
    }


def _make_lusya_scene(extra: dict | None = None) -> dict:
    """Сцена с maid_lusya — реальная структура из легаси-сейва."""
    scene = {
        "location_id": "tavern",
        "npc_positions": {
            "maid_lusya": {
                "name": "Люся",
                "position": "node_5",
                "local_position": {"x": _MAID_LUSYA_X, "y": _MAID_LUSYA_Y},
            },
        },
    }
    if extra:
        scene.update(extra)
    return scene


# ─────────────────────────────────────────────────────────────────────────────
# Тест 1 (контракт I): сейв с локальными local_position + версия < W → мировые
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_migration_shifts_local_position(
    manager: SceneStateManager, tavern_editor_world: dict
) -> None:
    """W5: версия < W + world frame → сдвиг local_position на origin.

    Реальные данные: maid_lusya local_position=(7.987, 1.826) — ЛОКАЛЬНЫЕ
    (campaign_state.json:515-518). Origin tavern=(25.0333, 5.018).
    Ожидание: после миграции x≈33.0207, y≈6.8444; version='W'; persist вызван.
    """
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    scene = _make_lusya_scene()
    # coord_frame_version отсутствует — триггер миграции

    manager._migrate_coord_frame_W5("Open_road", scene)

    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    expected_x = _MAID_LUSYA_X + _TAVERN_ORIGIN_X
    expected_y = _MAID_LUSYA_Y + _TAVERN_ORIGIN_Y
    assert lp["x"] == pytest.approx(expected_x, abs=1e-9), f"x={lp['x']}"
    assert lp["y"] == pytest.approx(expected_y, abs=1e-9), f"y={lp['y']}"
    assert scene["coord_frame_version"] == "W"
    # position (node-id) НЕ тронут — чужая зона (SC-3 логика в _enrich)
    assert scene["npc_positions"]["maid_lusya"]["position"] == "node_5"
    # persist вызван — версия сохранена на диск
    manager._persistence.atomic_commit_all.assert_called_once()
    call_kwargs = manager._persistence.atomic_commit_all.call_args
    assert call_kwargs.kwargs["campaign_id"] == "Open_road"
    assert "tavern" in call_kwargs.kwargs["all_scenes"]


# ─────────────────────────────────────────────────────────────────────────────
# Тест 2 (контракт I): идемпотентность — повторная загрузка не сдвигает
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_idempotent_on_repeated_load(
    manager: SceneStateManager, tavern_editor_world: dict
) -> None:
    """W5: coord_frame_version='W' → no-op, persist НЕ вызван."""
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    # local_position уже мировой (после первой миграции)
    scene = _make_lusya_scene(extra={"coord_frame_version": "W"})
    scene["npc_positions"]["maid_lusya"]["local_position"] = {
        "x": _MAID_LUSYA_X + _TAVERN_ORIGIN_X,
        "y": _MAID_LUSYA_Y + _TAVERN_ORIGIN_Y,
    }

    manager._migrate_coord_frame_W5("Open_road", scene)

    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    assert lp["x"] == pytest.approx(_MAID_LUSYA_X + _TAVERN_ORIGIN_X)
    assert lp["y"] == pytest.approx(_MAID_LUSYA_Y + _TAVERN_ORIGIN_Y)
    # persist НЕ вызван (no-op)
    manager._persistence.atomic_commit_all.assert_not_called()


def test_w5_new_scene_global_positions_survive_repeated_restore(
    manager: SceneStateManager, tavern_editor_world: dict
) -> None:
    """New authored world coordinates are not mistaken for legacy local saves."""
    player_xy = {"x": 33.24, "y": 15.184}
    npc_xy = {"x": 37.75, "y": 7.8}
    editor_data = {
        **tavern_editor_world,
        "nodes": {"spawn": {"x": player_xy["x"], "y": player_xy["y"]}},
        "player_spawn": player_xy,
        "npcs": [{"ref_id": "maid_lusya", "position": npc_xy}],
    }
    scene = build_initial_scene(
        campaign_id="Open_road",
        location_id="tavern",
        time_of_day="12:00",
        template={},
        editor_data=editor_data,
        build_spatial_data=lambda _: ([], []),
    )
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    manager._enrich_local_positions = lambda cid, state: None
    manager._enrich_spatial_data = lambda cid, state: None

    persisted_scenes: dict[str, dict] = {}

    def persist_scenes(*, all_scenes: dict[str, dict], **kwargs: object) -> None:
        persisted_scenes.update(
            {location_id: deepcopy(state) for location_id, state in all_scenes.items()}
        )

    manager._persistence.atomic_commit_all.side_effect = persist_scenes
    manager._persistence.load_scene_at.side_effect = (
        lambda campaign_id, location_id: deepcopy(persisted_scenes.get(location_id))
    )

    assert scene["coord_frame_version"] == "W"
    manager.save_scene_state("Open_road", scene)

    # Ordinary restore runs W5; the frame marker makes it a no-op.
    restored_scene = manager.get_scene_state("Open_road", "tavern")
    assert restored_scene is not None
    assert restored_scene["npc_positions"]["player"]["local_position"] == player_xy
    assert restored_scene["npc_positions"]["maid_lusya"]["local_position"] == npc_xy

    # Saving on Escape and restoring on Back must not shift either position.
    manager.save_scene_state("Open_road", restored_scene)
    restored_again = manager.get_scene_state("Open_road", "tavern")
    assert restored_again is not None
    assert restored_again["npc_positions"]["player"]["local_position"] == player_xy
    assert restored_again["npc_positions"]["maid_lusya"]["local_position"] == npc_xy
    assert manager._persistence.load_scene_at.call_count == 2
    # Only the two explicit saves occurred; W5 did not commit a migration.
    assert manager._persistence.atomic_commit_all.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Тест 3 (контракт I): node_17 не вызывает исключений (B-15)
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_node_17_does_not_raise(
    manager: SceneStateManager, tavern_editor_world: dict
) -> None:
    """B-15: висячая ссылка maid_lusya.position='node_17' не роняет миграцию.

    Миграция работает с local_position, не с position (node-id). Node_17
    обрабатывается существующей fallback-цепочкой _enrich_local_positions
    (svc.get_node → None → central_node fallback).
    """
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    scene = _make_lusya_scene()
    scene["npc_positions"]["maid_lusya"]["position"] = "node_17"  # B-15

    # НЕ должно упасть
    manager._migrate_coord_frame_W5("Open_road", scene)

    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    assert lp["x"] == pytest.approx(_MAID_LUSYA_X + _TAVERN_ORIGIN_X)
    assert lp["y"] == pytest.approx(_MAID_LUSYA_Y + _TAVERN_ORIGIN_Y)
    # position (node_17) НЕ тронут — миграция не лезет в node-id
    assert scene["npc_positions"]["maid_lusya"]["position"] == "node_17"
    assert scene["coord_frame_version"] == "W"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 4: локальный фрейм файла — только версия, без сдвига
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_local_frame_file_no_shift(
    manager: SceneStateManager, tavern_editor_local: dict
) -> None:
    """W5: global_coords=False → файл локальный, самосогласован; только версия."""
    manager._find_editor_location = lambda cid, lid: tavern_editor_local
    scene = _make_lusya_scene()

    manager._migrate_coord_frame_W5("Open_road", scene)

    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    # Координаты НЕ сдвинуты (файл локальный)
    assert lp["x"] == _MAID_LUSYA_X
    assert lp["y"] == _MAID_LUSYA_Y
    # Версия установлена — миграция завершена
    assert scene["coord_frame_version"] == "W"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 5: persistence=None — graceful degradation
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_no_persistence_graceful(
    tmp_path: Path, tavern_editor_world: dict
) -> None:
    """W5: PersistencePort=None → версия в RAM, no crash, warning logged."""
    manager = SceneStateManager(data_dir=tmp_path, persistence=None)
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    scene = _make_lusya_scene()

    # НЕ должно упать
    manager._migrate_coord_frame_W5("Open_road", scene)

    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    assert lp["x"] == pytest.approx(_MAID_LUSYA_X + _TAVERN_ORIGIN_X)
    assert lp["y"] == pytest.approx(_MAID_LUSYA_Y + _TAVERN_ORIGIN_Y)
    # Версия в RAM (persist пропущен, но миграция завершена)
    assert scene["coord_frame_version"] == "W"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 6: (0,0) битая координата (ADR-121) — пропускается
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_skips_zero_zero(
    manager: SceneStateManager, tavern_editor_world: dict
) -> None:
    """ADR-121: (0,0) трактуется как битая координата → пропускается.

    _enrich_local_positions восстановит её из fallback-цепочки
    (initial_node → central_node → skip с error-логом).
    """
    manager._find_editor_location = lambda cid, lid: tavern_editor_world
    scene = _make_lusya_scene()
    scene["npc_positions"]["broken_npc"] = {
        "name": "Битый",
        "local_position": {"x": 0.0, "y": 0.0},
    }

    manager._migrate_coord_frame_W5("Open_road", scene)

    # broken_npc НЕ сдвинут (останется для _enrich fallback)
    assert scene["npc_positions"]["broken_npc"]["local_position"] == {
        "x": 0.0,
        "y": 0.0,
    }
    # maid_lusya сдвинута
    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    assert lp["x"] == pytest.approx(_MAID_LUSYA_X + _TAVERN_ORIGIN_X)
    assert lp["y"] == pytest.approx(_MAID_LUSYA_Y + _TAVERN_ORIGIN_Y)
    # Версия установлена несмотря на пропуск (миграция завершена)
    assert scene["coord_frame_version"] == "W"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 7: editor JSON недоступен — миграция отложена
# ─────────────────────────────────────────────────────────────────────────────


def test_w5_editor_not_found_deferred(manager: SceneStateManager) -> None:
    """W5: editor JSON недоступен → версия НЕ ставится (повторим при след. загрузке).

    Защита от преждевременной маркировки: если мы не можем прочитать фрейм файла,
    мы не можем гарантировать корректность сдвига. Версия НЕ ставится →
    миграция повторится при следующей загрузке, когда editor JSON будет доступен.
    """
    manager._find_editor_location = lambda cid, lid: None
    scene = _make_lusya_scene()

    manager._migrate_coord_frame_W5("Open_road", scene)

    # Миграция отложена — версия НЕ установлена
    assert "coord_frame_version" not in scene
    # Координаты НЕ тронуты
    lp = scene["npc_positions"]["maid_lusya"]["local_position"]
    assert lp["x"] == _MAID_LUSYA_X
    assert lp["y"] == _MAID_LUSYA_Y
    # persist НЕ вызван
    manager._persistence.atomic_commit_all.assert_not_called()
    
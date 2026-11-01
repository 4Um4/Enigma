"""ME-2.1-G-5: Categories multiselect tests.

Tests (ТЗ Master, 12 обязательных проверок):
1. Открытие дерева — источник CatalogIndex
2. Одиночный выбор — категория записана
3. Множественный выбор — все категории сохранены
4. Дочерняя категория — корректная иерархия
5. Legacy category — детерминированная проекция
6. Снятие checkbox — категория удалена
7. Неизвестная категория — сохранена, не потеряна
8. Cancel — все изменения отменены
9. VersionConflict — рабочая копия сохранена
10. Save — только через session.save()
11. Повторное открытие — выбор восстановлен
12. Несколько категорий одного родителя — нет дублирования родителя
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from assets.asset_store import AssetStore  # noqa: E402
from assets.blueprint_editor import BlueprintEditor, SessionState  # noqa: E402
from assets.catalog_index import CatalogIndex  # noqa: E402
from assets.resource_validator import ResourceValidator  # noqa: E402


@pytest.fixture
def isolated_assets(tmp_path):
    """Изолированный assets/ с одним blueprint (door.json) + pixels/ для L2."""
    src = map_editor_root / "assets" / "catalogs" / "base" / "blueprints" / "door.json"
    assets_dir = tmp_path / "assets"
    bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
    bp_dir.mkdir(parents=True)

    pixels_dir = tmp_path / "pixels"
    pixels_dir.mkdir()
    (pixels_dir / "Deadbeat").mkdir()
    (pixels_dir / "Deadbeat" / "deadbeat_b.png").write_bytes(b"")

    shutil.copy(src, bp_dir / "door.json")

    store = AssetStore(assets_dir)
    store.load()
    validator = ResourceValidator(pixels_dir)
    index = CatalogIndex(store)

    return {
        "store": store,
        "validator": validator,
        "index": index,
        "assets_dir": assets_dir,
        "bp_path": bp_dir / "door.json",
        "pixels_dir": pixels_dir,
    }


@pytest.fixture
def editor(isolated_assets):
    return BlueprintEditor(
        asset_store=isolated_assets["store"],
        validator=isolated_assets["validator"],
    )


def _make_panel(editor, catalog_index=None, x=300, y=50, w=420, h=700):
    """Создать BlueprintInspectorPanel (без pygame display)."""
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except Exception:
        pass
    from ui.blueprint_inspector import BlueprintInspectorPanel

    return BlueprintInspectorPanel(x, y, w, h, editor, catalog_index=catalog_index)


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


def _get_categories_control(panel):
    """Найти _CategoriesField в controls."""
    return next(c for c in panel._controls if c.path == "categories")


class TestTreeSource:
    def test_tree_source_is_catalog_index(self, isolated_assets, editor):
        """1. Открытие дерева — источник CatalogIndex."""
        index = isolated_assets["index"]
        panel = _make_panel(editor, catalog_index=index)
        panel.open("door")

        control = _get_categories_control(panel)
        control._rebuild_tree()

        # Tree должен содержать parents из CatalogIndex
        tree = control._tree
        assert "wall_object" in tree  # door belongs to wall_object/opening
        assert "transition" in tree  # door belongs to transition/portal
        assert "opening" in tree.get("wall_object", [])
        assert "portal" in tree.get("transition", [])


class TestSingleSelect:
    def test_single_category_selected(self, isolated_assets, editor):
        """2. Одиночный выбор — категория записана."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        # Очистить все, выбрать одну
        control._selected = {"furniture/indoor"}
        control._unknown = set()
        panel._on_field_changed(control)

        cats = panel._session.get_field("categories")
        assert cats == ["furniture/indoor"]


class TestMultiSelect:
    def test_multiple_categories_selected(self, isolated_assets, editor):
        """3. Множественный выбор — все категории сохранены."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor", "nature/plant"}
        control._unknown = set()
        panel._on_field_changed(control)

        cats = panel._session.get_field("categories")
        assert "furniture/indoor" in cats
        assert "nature/plant" in cats
        assert len(cats) == 2


class TestChildHierarchy:
    def test_child_category_hierarchy(self, isolated_assets, editor):
        """4. Дочерняя категория — корректная иерархия."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._rebuild_tree()

        # door.json: wall_object/opening + transition/portal
        # Tree должен содержать эти children
        assert "opening" in control._tree.get("wall_object", [])
        assert "portal" in control._tree.get("transition", [])

        # Full paths are known
        assert "wall_object/opening" in control._known_paths
        assert "transition/portal" in control._known_paths


class TestLegacyProjection:
    def test_legacy_category_projection(self, isolated_assets, editor):
        """5. Legacy category — детерминированная проекция.

        При наличии нескольких категорий legacy-поле получает родительскую
        категорию первого элемента канонически упорядоченного списка.
        """
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        # Выбрать: transition/portal, wall_object/opening
        # sorted: ["transition/portal", "wall_object/opening"]
        # first: "transition/portal" → parent: "transition"
        control._selected = {"transition/portal", "wall_object/opening"}
        control._unknown = set()
        panel._on_field_changed(control)

        legacy = panel._session.get_field("category")
        assert legacy == "transition", "Legacy category = parent первого sorted элемента"

    def test_legacy_projection_single_category(self, isolated_assets, editor):
        """Доп: одна категория — legacy = её parent."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor"}
        control._unknown = set()
        panel._on_field_changed(control)

        assert panel._session.get_field("category") == "furniture"


class TestUncheck:
    def test_uncheck_removes_category(self, isolated_assets, editor):
        """6. Снятие checkbox — категория удалена из списка."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        # door изначально имеет wall_object/opening + transition/portal
        original_cats = panel._session.get_field("categories")
        assert "wall_object/opening" in original_cats

        # Снять wall_object/opening
        control._selected.discard("wall_object/opening")
        panel._on_field_changed(control)

        cats = panel._session.get_field("categories")
        assert "wall_object/opening" not in cats
        assert "transition/portal" in cats


class TestUnknownCategory:
    def test_unknown_category_preserved(self, isolated_assets, editor):
        """7. Неизвестная категория — сохранена, не потеряна.

        Если Blueprint содержит категорию, которой CatalogIndex не знает,
        нельзя молча удалить её при открытии или сохранении.
        """
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        # Добавить неизвестную категорию через session
        panel._session.set_field("categories", ["wall_object/opening", "custom/unknown"])

        control = _get_categories_control(panel)
        control.set_value(panel._session.get_field("categories"))

        # Unknown категория должна быть в _unknown
        assert "custom/unknown" in control._unknown
        assert "custom/unknown" not in control._known_paths

        # get_value сохраняет unknown
        value = control.get_value()
        assert "custom/unknown" in value

    def test_unknown_category_survives_save(self, isolated_assets, editor):
        """Доп: unknown категория переживает save + reload."""
        store = isolated_assets["store"]
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        panel._session.set_field("categories", ["wall_object/opening", "custom/unknown"])
        result = panel._session.save()
        assert result.ok

        store.load()
        data = store.get_blueprint("door").data
        assert "custom/unknown" in data["categories"]


class TestCancel:
    def test_cancel_reverts_categories(self, isolated_assets, editor):
        """8. Cancel — все изменения отменены."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")
        original_cats = _deep_copy(panel._session.get_field("categories"))

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor"}
        control._unknown = set()
        panel._on_field_changed(control)

        # Cancel
        panel._on_cancel()

        # Повторное открытие — оригинальные categories
        panel.open("door")
        assert panel._session.get_field("categories") == original_cats


class TestVersionConflict:
    def test_version_conflict_preserves_working_copy(self, isolated_assets, editor):
        """9. VersionConflict — рабочая копия сохранена."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor", "nature/plant"}
        control._unknown = set()
        panel._on_field_changed(control)

        # Внешнее изменение version
        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        panel._on_save()

        # Рабочая копия цела
        assert panel._session.state == SessionState.OPEN
        cats = panel._session.get_field("categories")
        assert "furniture/indoor" in cats
        assert "nature/plant" in cats


class TestSaveThroughSession:
    def test_save_through_session(self, isolated_assets, editor, monkeypatch):
        """10. Save — только через session.save()."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor", "wall_object/opening"}
        control._unknown = set()
        panel._on_field_changed(control)

        calls = []
        original_save = panel._session.save

        def spy_save(on_cache_refresh=None):
            calls.append(True)
            return original_save(on_cache_refresh=on_cache_refresh)

        monkeypatch.setattr(panel._session, "save", spy_save)

        panel._on_save()

        assert len(calls) == 1, "session.save() должен быть вызван 1 раз"


class TestReopen:
    def test_reopen_restores_selection(self, isolated_assets, editor):
        """11. Повторное открытие — выбор восстановлен."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._selected = {"furniture/indoor", "nature/plant"}
        control._unknown = set()
        panel._on_field_changed(control)
        panel._on_save()

        # Закрыть и открыть
        panel.close()
        panel.open("door")

        cats = panel._session.get_field("categories")
        assert "furniture/indoor" in cats
        assert "nature/plant" in cats


class TestNoParentDuplication:
    def test_no_parent_duplication_in_tree(self, isolated_assets, editor):
        """12. Несколько категорий одного родителя — нет дублирования родителя."""
        panel = _make_panel(editor, catalog_index=isolated_assets["index"])
        panel.open("door")

        control = _get_categories_control(panel)
        control._rebuild_tree()

        # door.json: wall_object/opening — parent в дереве один раз
        assert control._tree["wall_object"].count("opening") == 1
        # transition/portal — parent в дереве один раз
        assert control._tree["transition"].count("portal") == 1
        # Родитель не дублируется
        parents = list(control._tree.keys())
        assert parents.count("wall_object") == 1
        assert parents.count("transition") == 1

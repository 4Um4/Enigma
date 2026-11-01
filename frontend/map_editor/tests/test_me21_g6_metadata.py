"""ME-2.1-G-6: Metadata + default_properties tests.

Tests (ТЗ Master, 14 обязательных проверок):
1. Чтение и изменение metadata
2. Валидный raw JSON
3. Невалидный JSON блокирует сохранение
4. Неизвестные ключи сохраняются
5. Пустой default_properties
6. Cross-check обнаруживает дублирование
7. Cross-check не изменяет данные
8. Нет автоматической синхронизации
9. Cancel восстанавливает исходное состояние
10. VersionConflict сохраняет рабочую копию
11. Сохранение проходит через EditSession
12. Подтверждённая формализация обратима
13. Неподтверждённые ключи остаются нетронутыми
14. Старые Blueprint продолжают загружаться
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
from assets.resource_validator import ResourceValidator  # noqa: E402


@pytest.fixture
def isolated_assets(tmp_path):
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

    return {
        "store": store,
        "validator": validator,
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


def _make_panel(editor, x=300, y=50, w=420, h=800):
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except Exception:
        pass
    from ui.blueprint_inspector import BlueprintInspectorPanel

    return BlueprintInspectorPanel(x, y, w, h, editor)


def _get_dp_control(panel):
    """Найти _DefaultPropertiesField в controls."""
    return next(c for c in panel._controls if c.path == "metadata.default_properties")


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


class TestMetadataEditing:
    def test_metadata_label_editable(self, isolated_assets, editor):
        """1. Чтение и изменение metadata (label уже редактируется в G-4)."""
        panel = _make_panel(editor)
        panel.open("door")

        label_control = next(c for c in panel._controls if c.path == "metadata.label")
        label_control.widget.text = "New Label"
        panel._on_field_changed(label_control)

        assert panel._session.get_field("metadata.label") == "New Label"


class TestValidRawJson:
    def test_valid_json_accepted(self, isolated_assets, editor):
        """2. Валидный raw JSON принимается."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = '{"open": false, "custom": "test"}'
        control._validate_json()

        assert control._error is None
        assert control.get_value() == {"open": False, "custom": "test"}


class TestInvalidJsonBlocks:
    def test_invalid_json_blocks_save(self, isolated_assets, editor):
        """3. Невалидный JSON блокирует сохранение."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = '{"open": broken'
        control._validate_json()

        assert control._error is not None
        assert panel._can_save() is False, "Save должен быть заблокирован при JSON ошибке"


class TestUnknownKeysPreserved:
    def test_unknown_keys_preserved(self, isolated_assets, editor):
        """4. Неизвестные ключи сохраняются."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = '{"open": true, "custom_unknown": 42}'
        panel._on_field_changed(control)

        result = panel._session.save()
        assert result.ok

        panel.open("door")
        dp = panel._session.get_field("metadata.default_properties")
        assert dp.get("custom_unknown") == 42


class TestEmptyDefaultProperties:
    def test_empty_default_properties(self, isolated_assets, editor):
        """5. Пустой default_properties."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = "{}"
        control._validate_json()

        assert control._error is None
        assert control.get_value() == {}


class TestCrossCheck:
    def test_cross_check_detects_duplication(self, isolated_assets, editor):
        """6. Cross-check обнаруживает дублирование (durability в dp + physics)."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        # door.json имеет durability в default_properties И в physics.durability
        control._validate_json()

        warnings_text = " ".join(control._warnings)
        assert "durability" in warnings_text, "Cross-check должен обнаружить durability дубликат"
        assert "visibility_through" in warnings_text, "Cross-check должен обнаружить visibility_through дубликат"

    def test_cross_check_does_not_change_data(self, isolated_assets, editor):
        """7. Cross-check не изменяет данные."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        original_value = control.get_value()
        control._validate_json()

        assert control.get_value() == original_value, "Cross-check не должен менять данные"


class TestNoAutoSync:
    def test_no_automatic_synchronization(self, isolated_assets, editor):
        """8. Нет автоматической синхронизации между dp и physics/semantics."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        # Изменить durability в default_properties
        control._text = '{"durability": 99}'
        panel._on_field_changed(control)

        # physics.durability НЕ должен измениться
        assert panel._session.get_field("physics.durability") == 20, (
            "Автоматическая синхронизация запрещена — physics.durability не должен меняться"
        )
        # default_properties.durability изменён
        dp = panel._session.get_field("metadata.default_properties")
        assert dp["durability"] == 99


class TestCancel:
    def test_cancel_restores_original(self, isolated_assets, editor):
        """9. Cancel восстанавливает исходное состояние."""
        panel = _make_panel(editor)
        panel.open("door")
        original_dp = _deep_copy(panel._session.get_field("metadata.default_properties"))

        control = _get_dp_control(panel)
        control._text = '{"custom": "changed"}'
        panel._on_field_changed(control)

        panel._on_cancel()
        panel.open("door")

        assert panel._session.get_field("metadata.default_properties") == original_dp


class TestVersionConflict:
    def test_version_conflict_preserves_working_copy(self, isolated_assets, editor):
        """10. VersionConflict сохраняет рабочую копию."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = '{"custom": "my_edit"}'
        panel._on_field_changed(control)

        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        panel._on_save()

        assert panel._session.state == SessionState.OPEN
        dp = panel._session.get_field("metadata.default_properties")
        assert dp.get("custom") == "my_edit"


class TestSaveThroughSession:
    def test_save_through_session(self, isolated_assets, editor, monkeypatch):
        """11. Сохранение проходит через EditSession."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        control._text = '{"test": true}'
        panel._on_field_changed(control)

        calls = []
        original_save = panel._session.save

        def spy_save(on_cache_refresh=None):
            calls.append(True)
            return original_save(on_cache_refresh=on_cache_refresh)

        monkeypatch.setattr(panel._session, "save", spy_save)

        panel._on_save()

        assert len(calls) == 1


class TestFormalizationReversible:
    def test_formalized_keys_reversible(self, isolated_assets, editor):
        """12. Подтверждённая формализация обратима — durability можно убрать из dp."""
        panel = _make_panel(editor)
        panel.open("door")

        control = _get_dp_control(panel)
        # Убрать durability из default_properties
        control._text = '{"open": true, "locked": false, "visibility_through": 0.1}'
        panel._on_field_changed(control)

        result = panel._session.save()
        assert result.ok

        # physics.durability не изменился (не зависит от dp)
        panel.open("door")
        assert panel._session.get_field("physics.durability") == 20


class TestUnformalizedKeysUntouched:
    def test_unformalized_keys_untouched(self, isolated_assets, editor):
        """13. Неподтверждённые ключи (open/locked) остаются нетронутыми."""
        panel = _make_panel(editor)
        panel.open("door")

        original_dp = panel._session.get_field("metadata.default_properties")
        assert "open" in original_dp
        assert "locked" in original_dp

        # Сохранить без изменений
        result = panel._session.save()
        assert result.ok

        panel.open("door")
        dp = panel._session.get_field("metadata.default_properties")
        assert "open" in dp
        assert "locked" in dp


class TestOldBlueprintsLoad:
    def test_old_blueprints_load(self, isolated_assets, editor):
        """14. Старые Blueprint продолжают загружаться."""
        panel = _make_panel(editor)
        panel.open("door")

        dp = panel._session.get_field("metadata.default_properties")
        assert dp is not None
        assert isinstance(dp, dict)
        assert "open" in dp
        assert "durability" in dp

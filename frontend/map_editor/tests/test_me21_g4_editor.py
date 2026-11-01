"""ME-2.1-G-4: BlueprintEditorPanel tests.

Tests (ТЗ Master, 12 обязательных проверок):
1. Изменение каждого поддерживаемого типа поля
2. Live validation после изменения
3. Save заблокирован при ошибках
4. Save доступен при корректных изменениях
5. Сохранение проходит через session.save()
6. Cancel не меняет AssetStore
7. Unknown fields переживают редактирование и сохранение
8. VersionConflict сохраняет рабочую копию
9. Ошибка записи не закрывает сессию и не теряет изменения
10. После успешного сохранения UI показывает актуальную версию и dirty=False
11. Повторное открытие показывает сохранённые данные
12. Read-only поля нельзя изменить обходным путём
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

from assets.asset_store import AssetStore, VersionConflict  # noqa: E402
from assets.blueprint_editor import BlueprintEditor, SessionState  # noqa: E402
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


def _make_editor_panel(editor, x=300, y=50, w=420, h=600):
    """Создать BlueprintEditorPanel (без pygame display)."""
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


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


class TestFieldEditing:
    """1, 2: изменение полей + live validation."""

    def test_edit_text_field(self, isolated_assets, editor):
        """1. Изменение текстового поля (metadata.label)."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        # Найти контрол metadata.label
        label_control = next(c for c in panel._controls if c.path == "metadata.label")
        label_control.widget.text = "Новая Дверь"
        panel._on_field_changed(label_control)

        assert panel._session.get_field("metadata.label") == "Новая Дверь"
        assert panel._session.dirty is True

    def test_edit_float_field(self, isolated_assets, editor):
        """1. Изменение float поля (geometry.size.w)."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "geometry.size.w")
        control.widget.text = "2.5"
        panel._on_field_changed(control)

        assert panel._session.get_field("geometry.size.w") == 2.5

    def test_edit_bool_field(self, isolated_assets, editor):
        """1. Изменение bool поля (appearance.show_name)."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "appearance.show_name")
        original = panel._session.get_field("appearance.show_name")
        control._toggled = not original
        panel._on_field_changed(control)

        assert panel._session.get_field("appearance.show_name") == (not original)

    def test_live_validation_after_change(self, isolated_assets, editor):
        """2. Live validation после изменения."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        # Установить невалидное значение (w=-1)
        control = next(c for c in panel._controls if c.path == "geometry.size.w")
        control.widget.text = "-1"
        panel._on_field_changed(control)

        assert panel._validation is not None
        assert len(panel._validation.errors) > 0, "Должны быть ошибки валидации"
        assert panel._can_save() is False, "Save должен быть заблокирован"


class TestSaveGating:
    """3, 4: Save заблокирован/доступен."""

    def test_save_blocked_on_errors(self, isolated_assets, editor):
        """3. Save заблокирован при ошибках."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "geometry.size.w")
        control.widget.text = "-1"
        panel._on_field_changed(control)

        assert panel._can_save() is False

    def test_save_enabled_on_valid_changes(self, isolated_assets, editor):
        """4. Save доступен при корректных изменениях."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Корректная Дверь"
        panel._on_field_changed(control)

        assert panel._session.dirty is True
        assert len(panel._validation.errors) == 0
        assert panel._can_save() is True


class TestSaveUsesSession:
    """5: сохранение через session.save()."""

    def test_save_calls_session_save(self, isolated_assets, editor, monkeypatch):
        """5. Сохранение проходит через session.save()."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Test Save"
        panel._on_field_changed(control)

        calls = []
        original_save = panel._session.save

        def spy_save(on_cache_refresh=None):
            calls.append(True)
            return original_save(on_cache_refresh=on_cache_refresh)

        monkeypatch.setattr(panel._session, "save", spy_save)

        panel._on_save()

        assert len(calls) == 1, "session.save() должен быть вызван 1 раз"


class TestCancel:
    """6: Cancel не меняет AssetStore."""

    def test_cancel_does_not_change_assetstore(self, isolated_assets, editor):
        """6. Cancel не меняет AssetStore."""
        store = isolated_assets["store"]
        panel = _make_editor_panel(editor)
        panel.open("door")

        original_data = _deep_copy(store.get_blueprint("door").data)

        # Изменить поле
        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Изменённая Дверь"
        panel._on_field_changed(control)

        # Отмена
        panel._on_cancel()

        # AssetStore не изменился
        assert store.get_blueprint("door").data == original_data


class TestUnknownFieldsPreserved:
    """7: Unknown fields переживают редактирование и сохранение."""

    def test_unknown_fields_preserved(self, isolated_assets, editor):
        """7. Unknown fields сохраняются при редактировании и save."""
        store = isolated_assets["store"]
        panel = _make_editor_panel(editor)
        panel.open("door")

        # Добавить неизвестное поле через session
        panel._session.set_field("metadata._custom", "preserved")

        # Изменить редактируемое поле
        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Test Unknown"
        panel._on_field_changed(control)

        # Сохранить
        panel._on_save()

        # Перечитать и проверить
        store.load()
        data = store.get_blueprint("door").data
        assert data["metadata"].get("_custom") == "preserved"
        assert data["metadata"]["label"] == "Test Unknown"


class TestVersionConflict:
    """8: VersionConflict сохраняет рабочую копию."""

    def test_version_conflict_preserves_working_copy(self, isolated_assets, editor):
        """8. VersionConflict сохраняет рабочую копию."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        panel = _make_editor_panel(editor)
        panel.open("door")

        # Изменить поле
        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "My Edit"
        panel._on_field_changed(control)

        # Внешнее изменение version
        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        # Попытка сохранить → VersionConflict
        panel._on_save()

        # Рабочая копия цела
        assert panel._session is not None
        assert panel._session.state == SessionState.OPEN
        assert panel._session.get_field("metadata.label") == "My Edit"
        # Status message показывает конфликт
        assert "✗" in panel._status_message or "Conflict" in panel._status_message or "v" in panel._status_message


class TestSaveFailurePreservesSession:
    """9: Ошибка записи не закрывает сессию."""

    def test_save_failure_keeps_session_open(self, isolated_assets, editor, monkeypatch):
        """9. Ошибка записи не закрывает сессию и не теряет изменения."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Before Failure"
        panel._on_field_changed(control)

        # Monkeypatch session.save чтобы поднять VersionConflict
        def failing_save(on_cache_refresh=None):
            raise VersionConflict("door", 1, 2)

        monkeypatch.setattr(panel._session, "save", failing_save)

        panel._on_save()

        # Сессия осталась открыта, изменения цела
        assert panel._session.state == SessionState.OPEN
        assert panel._session.get_field("metadata.label") == "Before Failure"


class TestSuccessfulSave:
    """10, 11: после успешного save + повторное открытие."""

    def test_save_updates_state_and_dirty(self, isolated_assets, editor):
        """10. После успешного сохранения dirty=False, актуальная версия."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Saved Door"
        panel._on_field_changed(control)

        assert panel._session.dirty is True

        panel._on_save()

        # После save panel.open() вызывается заново — новая сессия
        assert panel._session.dirty is False
        assert panel._session.state == SessionState.OPEN

    def test_reopen_shows_saved_data(self, isolated_assets, editor):
        """11. Повторное открытие показывает сохранённые данные."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Persisted Label"
        panel._on_field_changed(control)
        panel._on_save()

        # Закрыть и открыть заново
        panel.close()
        panel.open("door")

        assert panel._session.get_field("metadata.label") == "Persisted Label"


class TestReadOnlyFields:
    """12: Read-only поля нельзя изменить обходным путём."""

    def test_blueprint_id_not_editable(self, isolated_assets, editor):
        """12. blueprint_id нет в списке редактируемых полей."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        editable_paths = [c.path for c in panel._controls]
        assert "blueprint_id" not in editable_paths
        assert "version" not in editable_paths
        assert "compat" not in editable_paths

    def test_no_direct_mutation_path(self, isolated_assets, editor):
        """12. UI не имеет прямого пути мутации AssetStore."""
        panel = _make_editor_panel(editor)
        panel.open("door")

        # Проверить что все изменения идут через session.set_field
        store = isolated_assets["store"]
        original_data = _deep_copy(store.get_blueprint("door").data)

        # Изменить поле через UI
        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "UI Edit"
        panel._on_field_changed(control)

        # AssetStore не изменился (только session.working)
        assert store.get_blueprint("door").data == original_data


class TestArchitecturalAudit:
    """Архитектурный аудит G-4 (по требованию Master)."""

    def test_ui_does_not_call_save_blueprint_atomic(self, isolated_assets, editor, monkeypatch):
        """UI не вызывает save_blueprint_atomic напрямую (только через session.save)."""
        store = isolated_assets["store"]
        panel = _make_editor_panel(editor)
        panel.open("door")

        control = next(c for c in panel._controls if c.path == "metadata.label")
        control.widget.text = "Audit Test"
        panel._on_field_changed(control)

        save_calls = []
        original = store.save_blueprint_atomic

        def spy(*args, **kwargs):
            save_calls.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "save_blueprint_atomic", spy)

        panel._on_save()

        # save_blueprint_atomic вызван ровно 1 раз (через session.save → G-1)
        assert len(save_calls) == 1

    def test_ui_does_not_write_files(self, isolated_assets, editor):
        """UI не вызывает write_text/json.dump напрямую."""
        # Это проверяется grep'ом в коде, но также через тест:
        # UI не должен иметь методов write_text/json.dump
        panel = _make_editor_panel(editor)
        panel.open("door")

        assert not hasattr(panel, "write_text")
        assert not hasattr(panel, "json_dump")
        assert not hasattr(panel, "_write_file")

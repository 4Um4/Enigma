"""ME-2.1-G-3: BlueprintInspectorPanel tests.

Tests (ТЗ Master, 8 обязательных проверок):
1. Double-click открывает правильный Blueprint
2. Открытие создаёт EditSession
3. Инспектор не изменяет AssetStore
4. Отображаются ошибки и предупреждения валидатора
5. Dirty indicator отражает реальное состояние сессии
6. Закрытие панели завершает сессию
7. Повторное открытие получает актуальные данные
8. UI не имеет прямого пути сохранения

Доп:
- F4 / Esc закрывают инспектор
- inspector не содержит set_field/save (read-only)
- session.close() вызывается при закрытии
- BlueprintEditor создаётся через catalog_panel (переиспользование store/validator)
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
    """BlueprintEditor поверх изолированного AssetStore + validator."""
    return BlueprintEditor(
        asset_store=isolated_assets["store"],
        validator=isolated_assets["validator"],
    )


def _make_inspector(editor, x=300, y=50, w=400, h=600):
    """Создать BlueprintInspectorPanel (без pygame display)."""
    # Импорт здесь — чтобы pytest без display не падал на import pygame
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


class TestOpenBlueprint:
    def test_open_creates_session(self, isolated_assets, editor):
        """2. Открытие создаёт EditSession."""
        inspector = _make_inspector(editor)
        assert inspector.active is False
        assert inspector._session is None

        inspector.open("door")

        assert inspector.active is True
        assert inspector._session is not None
        assert inspector._session.blueprint_id == "door"
        assert inspector._session.state == SessionState.OPEN

    def test_open_correct_blueprint(self, isolated_assets, editor):
        """1. Double-click открывает правильный Blueprint (симуляция через open)."""
        inspector = _make_inspector(editor)
        inspector.open("door")

        # Проверяем, что сессия указывает на правильный blueprint
        assert inspector._session.blueprint_id == "door"
        # Данные соответствуют door.json
        data = inspector._session.get_data()
        assert data["blueprint_id"] == "door"
        assert data["type"] == "door"
        assert data["metadata"]["label"] == "Дверь"


class TestDoesNotMutateAssetStore:
    def test_inspector_does_not_change_assetstore(self, isolated_assets, editor):
        """3. Инспектор не изменяет AssetStore."""
        store = isolated_assets["store"]
        original_data = _deep_copy(store.get_blueprint("door").data)
        original_version = store.get_blueprint("door").version
        original_fingerprint = store.get_blueprint("door").fingerprint

        inspector = _make_inspector(editor)
        inspector.open("door")

        # Читаем данные через инспектор
        _ = inspector._session.get_data()

        # AssetStore не изменился
        after_data = store.get_blueprint("door").data
        assert after_data == original_data
        assert store.get_blueprint("door").version == original_version
        assert store.get_blueprint("door").fingerprint == original_fingerprint


class TestValidationDisplay:
    def test_validation_errors_and_warnings_shown(self, isolated_assets, editor):
        """4. Отображаются ошибки и предупреждения валидатора."""
        inspector = _make_inspector(editor)
        inspector.open("door")

        # door.json валиден — errors пуст, warnings могут быть
        assert inspector._validation is not None
        assert len(inspector._validation.errors) == 0

        # Проверяем, что errors/warnings свойства доступны (для draw)
        _ = inspector._validation.errors
        _ = inspector._validation.warnings


class TestDirtyIndicator:
    def test_dirty_reflects_session_state(self, isolated_assets, editor):
        """5. Dirty indicator отражает реальное состояние сессии."""
        inspector = _make_inspector(editor)
        inspector.open("door")

        # Сессия только открыта — dirty=False (read-only, нет set_field в G-3)
        assert inspector._session.dirty is False
        assert inspector._session.state == SessionState.OPEN


class TestCloseSession:
    def test_close_terminates_session(self, isolated_assets, editor):
        """6. Закрытие панели завершает сессию."""
        inspector = _make_inspector(editor)
        inspector.open("door")
        assert inspector._session is not None
        assert inspector.active is True

        # Spy на session.close
        session = inspector._session
        close_called = []
        original_close = session.close

        def spy_close():
            close_called.append(True)
            original_close()

        session.close = spy_close

        inspector.close()

        assert inspector.active is False
        assert inspector._session is None
        assert len(close_called) == 1, "session.close() должен быть вызван"

    def test_esc_closes_inspector(self, isolated_assets, editor):
        """Доп: Esc закрывает инспектор."""
        import os

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        pygame.init()
        try:
            pygame.display.set_mode((1, 1))
        except Exception:
            pass

        inspector = _make_inspector(editor)
        inspector.open("door")

        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        consumed = inspector.handle_event(event)

        assert consumed is True
        assert inspector.active is False

    def test_f4_closes_inspector(self, isolated_assets, editor):
        """Доп: F4 закрывает инспектор."""
        import os

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        pygame.init()
        try:
            pygame.display.set_mode((1, 1))
        except Exception:
            pass

        inspector = _make_inspector(editor)
        inspector.open("door")

        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F4)
        consumed = inspector.handle_event(event)

        assert consumed is True
        assert inspector.active is False


class TestReopenFreshState:
    def test_reopen_gets_fresh_data(self, isolated_assets, editor):
        """7. Повторное открытие получает актуальные данные."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        inspector = _make_inspector(editor)
        inspector.open("door")

        # Внешнее изменение
        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["appearance"]["color"] = "#CHANGED_EXTERNAL"
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        # Повторное открытие
        inspector.open("door")

        assert inspector._session.get_field("appearance.color") == "#CHANGED_EXTERNAL", (
            "Повторное открытие должно получить актуальное состояние AssetStore"
        )


class TestNoDirectSavePath:
    def test_ui_has_no_direct_save_path(self, isolated_assets, editor):
        """8. UI не имеет прямого пути сохранения.

        Проверяем, что inspector не вызывает save_blueprint_atomic и не имеет
        методов save/cancel/set_field (read-only G-3).
        """
        inspector = _make_inspector(editor)
        inspector.open("door")

        # Inspector не имеет методов save/cancel/set_field (read-only)
        assert not hasattr(inspector, "save"), "Inspector не должен иметь save (G-4)"
        assert not hasattr(inspector, "set_field"), "Inspector не должен иметь set_field (G-4)"

        # Spy на store.save_blueprint_atomic — не должен вызываться
        store = isolated_assets["store"]
        save_calls = []
        original = store.save_blueprint_atomic

        def spy(*args, **kwargs):
            save_calls.append(True)
            return original(*args, **kwargs)

        store.save_blueprint_atomic = spy

        # Выполняем все возможные операции inspector
        inspector.handle_event(
            type("E", (), {"type": 0})  # dummy event
        )
        inspector.close()

        assert len(save_calls) == 0, "Inspector не должен вызывать save_blueprint_atomic (read-only G-3)"


class TestSessionLifecycle:
    def test_open_replaces_previous_session(self, isolated_assets, editor):
        """Доп: повторное open закрывает предыдущую сессию."""
        inspector = _make_inspector(editor)
        inspector.open("door")
        session1 = inspector._session

        inspector.open("door")
        session2 = inspector._session

        assert session1 is not session2, "Повторное open должно создать новую сессию"
        assert session1.state == SessionState.CANCELLED, "Предыдущая сессия должна быть закрыта (state=CANCELLED)"

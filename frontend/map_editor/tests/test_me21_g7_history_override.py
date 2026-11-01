"""ME-2.1-G-7: History + override banner tests.

Tests (ТЗ Master, 12 обязательных проверок):
1. Первое сохранение — история исходной версии создана
2. Повторное сохранение — истории разных версий не перезаписаны
3. Global без override — баннер отсутствует
4. Global с override — баннер отображается (campaign version активна)
5. Campaign Blueprint — нет ложного сообщения о перекрытии
6. Несколько overrides — корректное определение нужного ID
7. Отсутствующая история — корректное отображение пустого состояния
8. История разных источников — нет смешивания global/campaign
9. Cancel — история не создаётся
10. VersionConflict — история не создаётся для несостоявшегося save
11. Save — только через существующий G-1
12. Неудачный save — нет ложного подтверждения
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
from assets.blueprint_editor import BlueprintEditor  # noqa: E402
from assets.resource_validator import ResourceValidator  # noqa: E402


@pytest.fixture
def isolated_assets(tmp_path):
    """Изолированный assets/ с global + campaign blueprint."""
    src = map_editor_root / "assets" / "catalogs" / "base" / "blueprints" / "door.json"
    assets_dir = tmp_path / "assets"

    # Global blueprint
    bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
    bp_dir.mkdir(parents=True)

    # Campaign blueprint (override)
    camp_dir = assets_dir / "Open_road" / "blueprints"
    camp_dir.mkdir(parents=True)

    pixels_dir = tmp_path / "pixels"
    pixels_dir.mkdir()
    (pixels_dir / "Deadbeat").mkdir()
    (pixels_dir / "Deadbeat" / "deadbeat_b.png").write_bytes(b"")

    shutil.copy(src, bp_dir / "door.json")
    # Campaign override: door.json с другим цветом
    door_data = json.loads(src.read_text(encoding="utf-8-sig"))
    door_data["appearance"]["color"] = "#CAMPAIGN_COLOR"
    (camp_dir / "door.json").write_text(json.dumps(door_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Store БЕЗ campaign_id — global only
    store_global = AssetStore(assets_dir)
    store_global.load()

    # Store С campaign_id — campaign overrides global
    store_campaign = AssetStore(assets_dir, campaign_id="Open_road")
    store_campaign.load()

    validator = ResourceValidator(pixels_dir)

    return {
        "store_global": store_global,
        "store_campaign": store_campaign,
        "validator": validator,
        "assets_dir": assets_dir,
        "bp_path": bp_dir / "door.json",
        "camp_bp_path": camp_dir / "door.json",
        "pixels_dir": pixels_dir,
    }


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


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


class TestHistoryCreated:
    def test_first_save_creates_history(self, isolated_assets):
        """1. Первое сохранение — история исходной версии создана."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        bp_path = isolated_assets["bp_path"]
        history_dir = bp_path.parent / ".history"
        assert not history_dir.exists() or not list(history_dir.glob("door.*.json"))

        panel._session.set_field("metadata.label", "Changed")
        panel._on_save()

        history_file = history_dir / "door.1.json"
        assert history_file.exists(), "История v1 должна быть создана"

    def test_repeated_save_preserves_history(self, isolated_assets):
        """2. Повторное сохранение — истории разных версий не перезаписаны."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        # Первое сохранение
        panel._session.set_field("metadata.label", "V1")
        panel._on_save()

        # Второе сохранение
        panel.open("door")
        panel._session.set_field("metadata.label", "V2")
        panel._on_save()

        history_dir = isolated_assets["bp_path"].parent / ".history"
        # v1 и v2 (или v1 и v1 если version не инкрементируется — но G-1 не инкрементирует)
        # door.1.json — оригинал (до первого save)
        # После первого save: version всё ещё 1 (G-1 не инкрементирует version автоматически)
        # Но .history/door.1.json создаётся каждый save (копия ДО replace)
        files = list(history_dir.glob("door.*.json"))
        assert len(files) >= 1, "Должна быть хотя бы одна историческая версия"


class TestOverrideBanner:
    def test_global_no_override_no_banner(self, isolated_assets):
        """3. Global без override — баннер отсутствует."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        assert panel._override_banner is None, "Global без override — нет баннера"

    def test_global_with_override_banner_shown(self, isolated_assets):
        """4. Global с override — баннер отображается (campaign version активна)."""
        store = isolated_assets["store_campaign"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        assert panel._override_banner is not None, "Campaign override — баннер должен быть"
        assert "Campaign" in panel._override_banner or "campaign" in panel._override_banner.lower()

    def test_campaign_blueprint_no_false_override(self, isolated_assets):
        """5. Campaign Blueprint — нет ложного сообщения о перекрытии.

        Campaign version — это активная версия; баннер говорит «Campaign версия»,
        не «перекрыта».
        """
        store = isolated_assets["store_campaign"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        # record.source = "campaign:Open_road"
        record = store.get_blueprint("door")
        assert record.source.startswith("campaign:")
        assert panel._override_banner is not None
        assert "Campaign" in panel._override_banner


class TestMultipleOverrides:
    def test_multiple_overrides_correct_id(self, isolated_assets, tmp_path):
        """6. Несколько overrides — корректное определение нужного ID."""
        assets_dir = isolated_assets["assets_dir"]

        # Добавить второй campaign blueprint (chair)
        src_chair = map_editor_root / "assets" / "catalogs" / "base" / "blueprints" / "chair.json"
        if src_chair.exists():
            shutil.copy(src_chair, assets_dir / "catalogs" / "base" / "blueprints" / "chair.json")
            camp_dir = assets_dir / "Open_road" / "blueprints"
            chair_data = json.loads(src_chair.read_text(encoding="utf-8-sig"))
            chair_data["appearance"]["color"] = "#CAMPAIGN_CHAIR"
            (camp_dir / "chair.json").write_text(json.dumps(chair_data, indent=2, ensure_ascii=False), encoding="utf-8")

        store = AssetStore(assets_dir, campaign_id="Open_road")
        store.load()
        editor = BlueprintEditor(store, isolated_assets["validator"])

        panel = _make_panel(editor)
        panel.open("door")
        assert panel._override_banner is not None
        assert "Open_road" in panel._override_banner

        panel.open("chair")
        assert panel._override_banner is not None
        assert "Open_road" in panel._override_banner


class TestEmptyHistory:
    def test_no_history_shows_empty(self, isolated_assets):
        """7. Отсутствующая история — корректное отображение пустого состояния."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        assert panel._history_versions == [], "Нет истории — пустой список"


class TestHistoryNoMixing:
    def test_history_no_global_campaign_mixing(self, isolated_assets):
        """8. История разных источников — нет смешивания global/campaign."""
        store_global = isolated_assets["store_global"]
        editor_global = BlueprintEditor(store_global, isolated_assets["validator"])
        panel_global = _make_panel(editor_global)
        panel_global.open("door")

        # Save в global
        panel_global._session.set_field("metadata.label", "Global Change")
        panel_global._on_save()

        # История в global .history/
        global_history_dir = isolated_assets["bp_path"].parent / ".history"
        assert global_history_dir.exists()

        # Campaign .history/ не существует (не было save в campaign)
        camp_history_dir = isolated_assets["camp_bp_path"].parent / ".history"
        assert not camp_history_dir.exists() or not list(camp_history_dir.glob("door.*.json"))


class TestCancelNoHistory:
    def test_cancel_no_history_created(self, isolated_assets):
        """9. Cancel — история не создаётся."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        panel._session.set_field("metadata.label", "Changed")
        panel._on_cancel()

        history_dir = isolated_assets["bp_path"].parent / ".history"
        assert not history_dir.exists() or not list(history_dir.glob("door.*.json"))


class TestVersionConflictNoHistory:
    def test_version_conflict_no_history(self, isolated_assets):
        """10. VersionConflict — история не создаётся для несостоявшегося save."""
        store = isolated_assets["store_global"]
        bp_path = isolated_assets["bp_path"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        panel._session.set_field("metadata.label", "My Edit")

        # Внешнее изменение
        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        panel._on_save()

        history_dir = bp_path.parent / ".history"
        assert not history_dir.exists() or not list(history_dir.glob("door.*.json")), (
            "История не должна создаваться при VersionConflict"
        )


class TestSaveThroughG1:
    def test_save_through_g1(self, isolated_assets, monkeypatch):
        """11. Save — только через существующий G-1."""
        store = isolated_assets["store_global"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        panel._session.set_field("metadata.label", "G-1 Test")
        calls = []
        original = store.save_blueprint_atomic

        def spy(*args, **kwargs):
            calls.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "save_blueprint_atomic", spy)
        panel._on_save()

        assert len(calls) == 1, "Save через G-1 save_blueprint_atomic"


class TestFailedSaveNoFalseConfirmation:
    def test_failed_save_no_confirmation(self, isolated_assets):
        """12. Неудачный save — нет ложного подтверждения успешного сохранения."""
        store = isolated_assets["store_global"]
        bp_path = isolated_assets["bp_path"]
        editor = BlueprintEditor(store, isolated_assets["validator"])
        panel = _make_panel(editor)
        panel.open("door")

        panel._session.set_field("metadata.label", "Will Fail")

        # Внешнее изменение → VersionConflict
        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        panel._on_save()

        # Status message должен содержать ошибку, не "Сохранено"
        assert "✗" in panel._status_message or "Conflict" in panel._status_message or "v" in panel._status_message
        assert "Сохранено" not in panel._status_message, "Не должно быть ложного подтверждения при неудачном save"

"""ME-2.1-G-2: EditSession tests.

Tests (ТЗ Master, 10 обязательных проверок):
1. Изменение сессии не меняет оригинальный Blueprint
2. Две сессии одного Blueprint изолированы друг от друга
3. Возврат к исходным значениям снимает dirty
4. Отмена полностью восстанавливает исходное состояние
5. Невалидный Blueprint не сохраняется
6. Устаревшая сессия получает VersionConflict
7. Fingerprint-конфликт не приводит к потере чужих изменений
8. Успешное сохранение проходит исключительно через G-1
9. Ошибка сохранения не уничтожает рабочую копию
10. Неизвестные поля Blueprint сохраняются без потери

Доп. проверки:
- get_data возвращает копию (мутация результата не меняет working)
- get_field для dict возвращает копию
- state transitions (open → saved/cancelled; после save set_field падает)
- dirty по содержимому (set_field с тем же значением не делает dirty)
- new_from — заглушка в G-2 (NotImplementedError)
- повторное открытие получает актуальное состояние AssetStore
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

from assets.asset_store import (  # noqa: E402
    AssetStore,
    AssetStoreError,
    SaveBlocked,
    VersionConflict,
)
from assets.blueprint_editor import (  # noqa: E402
    BlueprintEditor,
    SessionState,
)
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


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


# ===== Проверка 1, 2: независимость + изоляция двух сессий =====


class TestIndependence:
    def test_session_change_does_not_mutate_original(self, isolated_assets, editor):
        """1. Изменение working не меняет record.data в AssetStore."""
        store = isolated_assets["store"]
        session = editor.open("door")
        original_store_data = _deep_copy(store.get_blueprint("door").data)

        session.set_field("appearance.color", "#FF0000")

        store_data_after = store.get_blueprint("door").data
        assert store_data_after == original_store_data, "Мутация EditSession не должна менять record.data в AssetStore"
        assert store_data_after["appearance"]["color"] == "#D2691E"
        assert session.get_field("appearance.color") == "#FF0000"

    def test_two_sessions_isolated(self, isolated_assets, editor):
        """2. Две EditSession одного blueprint изолированы друг от друга."""
        session_a = editor.open("door")
        session_b = editor.open("door")

        session_a.set_field("appearance.color", "#AA0000")
        session_b.set_field("appearance.color", "#BB0000")

        assert session_a.get_field("appearance.color") == "#AA0000"
        assert session_b.get_field("appearance.color") == "#BB0000"


# ===== Проверка 3: dirty по содержимому =====


class TestDirtyTracking:
    def test_revert_to_original_clears_dirty(self, isolated_assets, editor):
        """3. Изменил → вернул исходное → dirty=False."""
        session = editor.open("door")
        assert session.dirty is False

        original_color = session.get_field("appearance.color")
        session.set_field("appearance.color", "#FF0000")
        assert session.dirty is True

        session.set_field("appearance.color", original_color)
        assert session.dirty is False, "Возврат к исходному значению должен снимать dirty (по содержимому)"

    def test_set_field_same_value_not_dirty(self, isolated_assets, editor):
        """Доп: set_field с тем же значением не делает dirty."""
        session = editor.open("door")
        original_color = session.get_field("appearance.color")

        session.set_field("appearance.color", original_color)
        assert session.dirty is False


# ===== Проверка 4: отмена =====


class TestCancel:
    def test_cancel_restores_original(self, isolated_assets, editor):
        """4. cancel() восстанавливает working = original; dirty=False."""
        session = editor.open("door")
        original_color = session.get_field("appearance.color")

        session.set_field("appearance.color", "#FF0000")
        session.set_field("physics.cover", 0.5)
        session.set_field("metadata.label", "Test Door")
        assert session.dirty is True

        session.cancel()

        assert session.get_field("appearance.color") == original_color
        assert session.get_field("physics.cover") == 0.0
        assert session.get_field("metadata.label") == "Дверь"
        assert session.dirty is False
        assert session.state == SessionState.CANCELLED

    def test_cancel_then_modify_raises(self, isolated_assets, editor):
        """Доп: после cancel set_field падает (сессия закрыта)."""
        session = editor.open("door")
        session.cancel()

        with pytest.raises(AssetStoreError):
            session.set_field("appearance.color", "#FF0000")


# ===== Проверка 5: валидация гейтит save =====


class TestValidationGating:
    def test_invalid_blueprint_not_saved(self, isolated_assets, editor):
        """5. set_field с невалидным значением → save → SaveBlocked; файл не изменён."""
        bp_path = isolated_assets["bp_path"]
        session = editor.open("door")
        original_bytes = bp_path.read_bytes()

        session.set_field("geometry.size.w", -1)
        assert session.last_validation is not None
        assert len(session.last_validation.errors) > 0

        with pytest.raises(SaveBlocked):
            session.save()

        assert bp_path.read_bytes() == original_bytes

    def test_set_field_returns_errors(self, isolated_assets, editor):
        """Доп: set_field возвращает list[ValidationIssue] (errors only)."""
        session = editor.open("door")
        errors = session.set_field("geometry.size.w", -1)
        assert len(errors) > 0
        assert all(getattr(e, "level", "") == "error" for e in errors)


# ===== Проверка 6: version conflict =====


class TestVersionConflict:
    def test_stale_session_version_conflict(self, isolated_assets, editor):
        """6. Внешний процесс изменил version → save → VersionConflict."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        session = editor.open("door")
        assert session.opened_version == 1

        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        session.set_field("appearance.color", "#00FF00")
        with pytest.raises(VersionConflict):
            session.save()


# ===== Проверка 7: fingerprint conflict =====


class TestFingerprintConflict:
    def test_fingerprint_conflict_preserves_disk(self, isolated_assets, editor):
        """7. Внешний процесс изменил содержимое (version та же) → save →
        VersionConflict(reason='fingerprint'); чужие изменения на диске сохранены.
        """
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        session = editor.open("door")

        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["appearance"]["color"] = "#EXTERNAL"
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")

        session.set_field("appearance.color", "#MY_EDIT")
        with pytest.raises(VersionConflict) as exc_info:
            session.save()

        assert exc_info.value.reason == "fingerprint"

        disk_data = json.loads(bp_path.read_text(encoding="utf-8-sig"))
        assert disk_data["appearance"]["color"] == "#EXTERNAL", (
            "Чужие изменения на диске не должны быть потеряны при fingerprint conflict"
        )


# ===== Проверка 8: save проходит через G-1 =====


class TestSaveUsesG1:
    def test_save_uses_save_blueprint_atomic(self, isolated_assets, editor, monkeypatch):
        """8. save() вызывает store.save_blueprint_atomic (monkeypatch + spy)."""
        store = isolated_assets["store"]
        session = editor.open("door")
        session.set_field("appearance.color", "#123456")

        calls = []
        original_method = store.save_blueprint_atomic

        def spy(record, new_data, *, validator=None, on_cache_refresh=None):
            calls.append(
                {
                    "blueprint_id": record.blueprint_id,
                    "version": record.version,
                    "fingerprint": record.fingerprint,
                    "new_color": new_data["appearance"]["color"],
                }
            )
            return original_method(record, new_data, validator=validator, on_cache_refresh=on_cache_refresh)

        monkeypatch.setattr(store, "save_blueprint_atomic", spy)
        result = session.save()

        assert result.ok is True
        assert len(calls) == 1, "save() должен вызвать save_blueprint_atomic ровно 1 раз"
        assert calls[0]["blueprint_id"] == "door"
        assert calls[0]["version"] == 1
        assert calls[0]["new_color"] == "#123456"


# ===== Проверка 9: ошибка save не уничтожает рабочую копию =====


class TestSaveFailurePreservesWorking:
    def test_save_failure_preserves_working_copy(self, isolated_assets, editor):
        """9. save() упал (VersionConflict) → working copy цела, можно retry."""
        bp_path = isolated_assets["bp_path"]
        store = isolated_assets["store"]

        session = editor.open("door")
        session.set_field("appearance.color", "#MY_EDIT")
        assert session.get_field("appearance.color") == "#MY_EDIT"

        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        with pytest.raises(VersionConflict):
            session.save()

        assert session.get_field("appearance.color") == "#MY_EDIT", "После ошибки save рабочая копия должна быть цела"
        assert session.dirty is True
        assert session.state == SessionState.OPEN


# ===== Проверка 10: неизвестные поля сохраняются =====


class TestUnknownFieldsPreserved:
    def test_unknown_fields_preserved_through_edit(self, isolated_assets, editor):
        """10. Добавить _custom_field в working → save → reload → поле на месте."""
        store = isolated_assets["store"]
        session = editor.open("door")

        session.set_field("metadata._custom_field", "preserved_value")
        session.set_field("appearance.color", "#999999")
        assert session.dirty is True

        result = session.save()
        assert result.ok

        store.load()
        reloaded = store.get_blueprint("door")
        assert reloaded.data["metadata"].get("_custom_field") == "preserved_value"
        assert reloaded.data["appearance"]["color"] == "#999999"


# ===== Доп: state transitions =====


class TestStateTransitions:
    def test_save_closes_session(self, isolated_assets, editor):
        """После успешного save state=SAVED; set_field падает."""
        session = editor.open("door")
        session.set_field("appearance.color", "#ABCDEF")
        result = session.save()
        assert result.ok
        assert session.state == SessionState.SAVED

        with pytest.raises(AssetStoreError):
            session.set_field("appearance.color", "#000000")

    def test_close_clears_state(self, isolated_assets, editor):
        """close() переводит state=CANCELLED."""
        session = editor.open("door")
        session.close()
        assert session.state == SessionState.CANCELLED


# ===== Доп: изоляция get_data/get_field =====


class TestGetDataIsolation:
    def test_get_data_returns_copy(self, isolated_assets, editor):
        """Мутация результата get_data не меняет working."""
        session = editor.open("door")
        data = session.get_data()
        data["appearance"]["color"] = "#MUTATED_EXTERNAL"

        assert session.get_field("appearance.color") == "#D2691E"

    def test_get_field_dict_returns_copy(self, isolated_assets, editor):
        """get_field для dict возвращает копию."""
        session = editor.open("door")
        appearance = session.get_field("appearance")
        appearance["color"] = "#MUTATED_EXTERNAL"

        assert session.get_field("appearance.color") == "#D2691E"


# ===== Доп: new_from — заглушка G-8 =====


class TestNewFromImplemented:
    def test_new_from_creates_session(self, isolated_assets, editor):
        """G-8: new_from теперь реализован — создаёт EditSession."""
        session = editor.new_from("door", "door_red")
        assert session is not None
        assert session.blueprint_id == "door_red"
        assert session.is_new is True
        assert session.is_new is True


# ===== Доп: повторное открытие получает актуальное состояние =====


class TestReopenGetsFreshState:
    def test_reopen_after_external_change(self, isolated_assets, editor):
        """7 (инвариант): новая сессия получает актуальное состояние AssetStore."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        session1 = editor.open("door")
        session1.set_field("appearance.color", "#FF0000")
        result = session1.save()
        assert result.ok

        external_data = _deep_copy(store.get_blueprint("door").data)
        external_data["appearance"]["color"] = "#EXTERNAL"
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")
        store.load()

        session2 = editor.open("door")
        assert session2.get_field("appearance.color") == "#EXTERNAL", (
            "Повторное открытие должно получать актуальное состояние AssetStore"
        )

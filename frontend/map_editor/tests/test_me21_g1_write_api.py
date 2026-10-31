"""ME-2.1-G-1: AssetStore write-API tests.

Tests (ТЗ Master, Architecture Review §6):
- T1: atomicity — validate failure → SaveBlocked → original byte-identical
- T2: round-trip — unknown fields preserved (load → save → load → deep-equal)
- T3: validate-blocks — missing sprite → SaveBlocked
- T3b: structural error (geometry.size.w=0) → SaveBlocked
- T4: version conflict — external change → VersionConflict
- T4b: same version → save succeeds
- T5: cancel cleanliness — tmp removed after SaveBlocked
- T6: cache coherence — on_cache_refresh called after successful save
- T6d: cache refresh failure → SaveResult.cache_stale=True, file still saved
- T7: instance isolation — save doesn't touch location.json
- T8: broken-load isolation — test-load failure → original intact
- T10: blueprint_id rename forbidden
- T13: history — .history/<id>.<old_version>.json created, AssetStore.load() ignores .history/
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
    SaveResult,
    VersionConflict,
)
from assets.resource_validator import ResourceValidator  # noqa: E402


@pytest.fixture
def isolated_assets(tmp_path):
    """Изолированный assets/ с одним blueprint (door.json) + pixels/ для L2."""
    src = map_editor_root / "assets" / "catalogs" / "base" / "blueprints" / "door.json"
    assets_dir = tmp_path / "assets"
    bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
    bp_dir.mkdir(parents=True)

    # pixels_dir для L2 validation (sprite file exists)
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


def _deep_copy(data: dict) -> dict:
    """json round-trip для deepcopy (без зависимости от copy)."""
    return json.loads(json.dumps(data))


class TestAtomicity:
    """T1, T8: validate failure / broken-load → original byte-identical."""

    def test_validate_failure_preserves_original(self, isolated_assets):
        """T1: SaveBlocked не трогает оригинал (byte-compare)."""
        store = isolated_assets["store"]
        validator = isolated_assets["validator"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        original_bytes = bp_path.read_bytes()

        bad_data = _deep_copy(record.data)
        bad_data["geometry"]["size"]["w"] = -1

        with pytest.raises(SaveBlocked):
            store.save_blueprint_atomic(record, bad_data, validator=validator)

        assert bp_path.read_bytes() == original_bytes, "Оригинал должен быть byte-identical после SaveBlocked"

    def test_broken_json_in_tmp_preserves_original(self, isolated_assets):
        """T8: test-load tmp падает (blueprint_id != stem) → original intact, tmp удалён."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        original_bytes = bp_path.read_bytes()

        bad_data = _deep_copy(record.data)
        bad_data["blueprint_id"] = "not_door"  # != path.stem "door"

        with pytest.raises(AssetStoreError):
            store.save_blueprint_atomic(record, bad_data)

        assert bp_path.read_bytes() == original_bytes
        tmp_path = bp_path.with_suffix(".json.tmp")
        assert not tmp_path.exists(), "tmp должен быть удалён после test-load failure"

    def test_load_failure_restores_original(self, isolated_assets, monkeypatch):
        """T1b (R1): load() падает после replace → оригинал восстановлен,
        реестр в pre-save состоянии."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        original_bytes = bp_path.read_bytes()
        pre_save_keys = set(store._blueprints.keys())

        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#FF0000"

        # Monkeypatch load: имитировать начало реального load (clear) + падение
        def failing_load():
            store._blueprints.clear()
            store._resources.clear()
            store._overrides.clear()
            raise RuntimeError("simulated load failure after clear")

        monkeypatch.setattr(store, "load", failing_load)

        with pytest.raises(AssetStoreError) as exc_info:
            store.save_blueprint_atomic(record, new_data)

        assert "Reload упал" in str(exc_info.value)
        # Оригинал восстановлен побайтно
        assert bp_path.read_bytes() == original_bytes, "Оригинал должен быть восстановлен после load() failure"
        # Реестр восстановлен из snapshot (pre-save состояние)
        assert set(store._blueprints.keys()) == pre_save_keys, "Реестр должен быть в pre-save состоянии после recovery"
        assert "door" in store._blueprints


class TestRoundTrip:
    """T2: unknown fields preserved."""

    def test_unknown_fields_preserved(self, isolated_assets):
        """T2: load → save → load → unknown fields intact."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")

        data_with_unknown = _deep_copy(record.data)
        data_with_unknown["_custom_field"] = "preserved"
        data_with_unknown["metadata"]["_another_unknown"] = 42

        result = store.save_blueprint_atomic(record, data_with_unknown)
        assert result.ok

        # Reload и проверка
        store2 = AssetStore(isolated_assets["assets_dir"])
        store2.load()
        reloaded = store2.get_blueprint("door")

        assert reloaded.data.get("_custom_field") == "preserved"
        assert reloaded.data["metadata"].get("_another_unknown") == 42


class TestValidationGating:
    """T3, T3b: validate-blocks."""

    def test_missing_sprite_blocks_save(self, isolated_assets):
        """T3: appearance.sprite → несуществующий sheet → SaveBlocked."""
        store = isolated_assets["store"]
        validator = isolated_assets["validator"]

        record = store.get_blueprint("door")
        bad_data = _deep_copy(record.data)
        bad_data["appearance"]["sprite"] = ["Nonexistent/sheet", 0, 0]

        with pytest.raises(SaveBlocked) as exc_info:
            store.save_blueprint_atomic(record, bad_data, validator=validator)

        assert any(i.level == "error" for i in exc_info.value.issues)

    def test_structural_error_blocks_save(self, isolated_assets):
        """T3b: geometry.size.w=0 → SaveBlocked (L1 structural)."""
        store = isolated_assets["store"]
        validator = isolated_assets["validator"]

        record = store.get_blueprint("door")
        bad_data = _deep_copy(record.data)
        bad_data["geometry"]["size"]["w"] = 0

        with pytest.raises(SaveBlocked):
            store.save_blueprint_atomic(record, bad_data, validator=validator)

    def test_no_validator_skips_validation(self, isolated_assets):
        """Без validator save не валидирует (только test-load)."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#FF0000"

        result = store.save_blueprint_atomic(record, new_data)
        assert result.ok


class TestVersionConflict:
    """T4, T4b: version conflict."""

    def test_external_change_raises_conflict(self, isolated_assets):
        """T4: файл изменён снаружи (version 1→2) → VersionConflict."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        # 1. Открываем record (version=1)
        record_v1 = store.get_blueprint("door")
        assert record_v1.version == 1

        # 2. Внешнее изменение: перезаписываем файл с version=2
        external_data = _deep_copy(record_v1.data)
        external_data["version"] = 2
        bp_path.write_text(json.dumps(external_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 3. store пересобирает реестр — теперь видит version=2
        store.load()

        # 4. Пытаемся save со старым record (version=1)
        new_data = _deep_copy(record_v1.data)
        new_data["appearance"]["color"] = "#00FF00"

        with pytest.raises(VersionConflict) as exc_info:
            store.save_blueprint_atomic(record_v1, new_data)

        assert exc_info.value.expected_version == 1
        assert exc_info.value.actual_version == 2

    def test_same_version_succeeds(self, isolated_assets):
        """T4b: same version → save succeeds, version preserved."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#0000FF"

        result = store.save_blueprint_atomic(record, new_data)
        assert result.ok
        assert result.version == record.version

    def test_disk_version_conflict_without_reload(self, isolated_assets):
        """T4c (R2): внешний процесс изменил файл, store ещё не load →
        VersionConflict через disk check (дополняет memory check)."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        # 1. Открываем record (version=1)
        record_v1 = store.get_blueprint("door")
        assert record_v1.version == 1

        # 2. Внешнее изменение файла с version=2 (БЕЗ store.load())
        external_data = _deep_copy(record_v1.data)
        external_data["version"] = 2
        bp_path.write_text(
            json.dumps(external_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 3. store.current.version всё ещё 1 (memory не обновлена)
        current = store._blueprints.get("door")
        assert current.version == 1

        # 4. save(record_v1) — memory check проходит (1==1), но disk check ловит
        new_data = _deep_copy(record_v1.data)
        new_data["appearance"]["color"] = "#00FF00"

        with pytest.raises(VersionConflict) as exc_info:
            store.save_blueprint_atomic(record_v1, new_data)

        assert exc_info.value.expected_version == 1
        assert exc_info.value.actual_version == 2

    def test_disk_content_change_same_version_detected(self, isolated_assets):
        """T4d (R2-уточнение Master): внешнее изменение содержимого при
        неизменной version → fingerprint ловит → VersionConflict.

        Сценарий lost update:
        1. EditSession загрузила Blueprint version=1 (fingerprint=A).
        2. Внешний процесс изменил цвет в JSON, оставил version=1 (fingerprint=B).
        3. EditSession пытается сохранить свою старую копию.
        4. Disk version check (version 1==1) пропустил бы.
        5. Fingerprint check (A!=B) ловит → VersionConflict(reason='fingerprint').
        """
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        # 1. Открываем record (version=1, fingerprint=A)
        record_v1 = store.get_blueprint("door")
        assert record_v1.version == 1
        assert record_v1.fingerprint  # fingerprint вычислен при load

        # 2. Внешнее изменение содержимого, version та же (fingerprint=B)
        external_data = _deep_copy(record_v1.data)
        external_data["appearance"]["color"] = "#EXTERNAL_CHANGE"
        external_data["version"] = 1  # НЕ инкрементируем!
        bp_path.write_text(
            json.dumps(external_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 3. store.current.version всё ещё 1 (memory не обновлена)
        current = store._blueprints.get("door")
        assert current.version == 1

        # 4. save(record_v1) — memory check проходит (1==1),
        #    fingerprint check ловит (A!=B)
        new_data = _deep_copy(record_v1.data)
        new_data["appearance"]["color"] = "#MY_EDIT"

        with pytest.raises(VersionConflict) as exc_info:
            store.save_blueprint_atomic(record_v1, new_data)

        assert exc_info.value.reason == "fingerprint", "Должен сработать fingerprint check, не version check"
        assert exc_info.value.expected_version == 1
        assert exc_info.value.actual_version == 1, "version на диске та же — fingerprint ловит содержимое"


class TestCancelCleanliness:
    """T5: tmp cleanup after SaveBlocked."""

    def test_tmp_removed_after_save_blocked(self, isolated_assets):
        """T5: SaveBlocked → tmp удалён."""
        store = isolated_assets["store"]
        validator = isolated_assets["validator"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        bad_data = _deep_copy(record.data)
        bad_data["geometry"]["size"]["w"] = -1

        tmp_path = bp_path.with_suffix(".json.tmp")

        with pytest.raises(SaveBlocked):
            store.save_blueprint_atomic(record, bad_data, validator=validator)

        assert not tmp_path.exists()


class TestCacheCoherence:
    """T6, T6d: cache coherence."""

    def test_cache_refresh_called_after_save(self, isolated_assets):
        """T6: on_cache_refresh вызывается один раз после успешного save."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#123456"

        refresh_calls: list[bool] = []

        def refresh() -> None:
            refresh_calls.append(True)

        result = store.save_blueprint_atomic(record, new_data, on_cache_refresh=refresh)
        assert result.ok
        assert len(refresh_calls) == 1
        assert not result.cache_stale

    def test_cache_refresh_failure_sets_stale(self, isolated_assets):
        """T6d: refresh raises → cache_stale=True, file saved."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#ABCDEF"

        def failing_refresh() -> None:
            raise RuntimeError("cache refresh failed")

        result = store.save_blueprint_atomic(record, new_data, on_cache_refresh=failing_refresh)
        assert result.ok
        assert result.cache_stale

        # Файл всё равно сохранён
        saved = json.loads(bp_path.read_text(encoding="utf-8-sig"))
        assert saved["appearance"]["color"] == "#ABCDEF"


class TestInstanceIsolation:
    """T7: save doesn't touch location.json."""

    def test_save_does_not_touch_location_json(self, isolated_assets, tmp_path):
        """T7: правка door.json не меняет размещённые экземпляры (R4 — дизайн)."""
        store = isolated_assets["store"]

        # Создаём фиктивный location.json с экземпляром door
        loc_dir = tmp_path / "campaigns" / "Open_road" / "locations"
        loc_dir.mkdir(parents=True)
        loc_path = loc_dir / "tavern.json"
        instance_data = {
            "objects": [
                {
                    "id": "obj_door_1",
                    "type": "door",
                    "name": "Дверь #1",
                    "position": {"x": 1.0, "y": 2.0},
                    "size": {"w": 1.0, "h": 0.2, "d": 2.2},
                    "color": "#D2691E",
                }
            ]
        }
        loc_path.write_text(json.dumps(instance_data, indent=2), encoding="utf-8")
        original_loc = loc_path.read_bytes()

        # Меняем цвет door blueprint
        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#FF0000"

        store.save_blueprint_atomic(record, new_data)

        # location.json не изменился
        assert loc_path.read_bytes() == original_loc


class TestBlueprintIdRename:
    """T10: blueprint_id rename forbidden."""

    def test_rename_blueprint_id_raises(self, isolated_assets):
        """T10: изменение blueprint_id → AssetStoreError (rename запрещён в v1)."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["blueprint_id"] = "door_renamed"

        with pytest.raises(AssetStoreError):
            store.save_blueprint_atomic(record, new_data)


class TestHistory:
    """T13: .history/<id>.<old_version>.json."""

    def test_history_created_on_save(self, isolated_assets):
        """T13: save → .history/door.1.json создан = копия оригинала."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        original_bytes = bp_path.read_bytes()

        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#999999"

        store.save_blueprint_atomic(record, new_data)

        history_path = bp_path.parent / ".history" / "door.1.json"
        assert history_path.exists()
        assert history_path.read_bytes() == original_bytes

    def test_load_ignores_history(self, isolated_assets):
        """T13b: AssetStore.load() игнорирует .history/ (count unchanged)."""
        store = isolated_assets["store"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#666666"

        assert len(store.list_blueprints()) == 1

        store.save_blueprint_atomic(record, new_data)

        # .history создан, но load() его не читает
        store.load()
        assert len(store.list_blueprints()) == 1


class TestSaveResultContract:
    """SaveResult fields."""

    def test_save_result_has_all_fields(self, isolated_assets):
        """SaveResult: ok, blueprint_id, version, path, cache_stale."""
        store = isolated_assets["store"]
        bp_path = isolated_assets["bp_path"]

        record = store.get_blueprint("door")
        new_data = _deep_copy(record.data)
        new_data["appearance"]["color"] = "#333333"

        result = store.save_blueprint_atomic(record, new_data)

        assert isinstance(result, SaveResult)
        assert result.ok is True
        assert result.blueprint_id == "door"
        assert result.version == 1
        assert result.path == bp_path
        assert result.cache_stale is False

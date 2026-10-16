"""Тесты COV-D59 / ADR-O-426 Шаг 2: save-версионирование «детект-и-мигрировать».

Обязательные негативные сценарии Мастера (GO-вердикт, №1-№7) + матрица
детектора + чистые миграторы + version-aware ридеры (В4).
"""

import json
from types import SimpleNamespace

import pytest

from app.services.game_loop.campaign_lifecycle import CampaignLifecycle
from app.services.state import save_migrations as sm
from app.services.state.save_format_detector import (
    CURRENT,
    MIGRABLE,
    REASON_CORRUPT_JSON,
    REASON_INCONSISTENT_V1,
    REASON_INVALID_SCENES,
    REASON_INVALID_V0,
    REASON_NEWER_VERSION,
    REASON_NOT_DICT,
    REASON_UNKNOWN_FORMAT,
    REASON_UNKNOWN_VERSION,
    SOURCE_V0_SINGLE,
    SOURCE_V1_UNSTAMPED,
    UNMIGRABLE,
    classify_parsed_save,
    detect_save_format,
)

V0_SCENE = {"location_id": "tavern", "npc_positions": {"goran": {"x": 1}}}
V0_META = {"current_location": "tavern", "day": 3}


def _write(tmp_path, payload, campaign="c"):
    p = tmp_path / "saves" / campaign / "campaign_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return p


def _bak(state_file):
    return state_file.with_name(state_file.name + ".pre-migration.bak")


class TestDetector:
    @pytest.mark.parametrize("payload,status,source,reason", [
        ({"scene_state": {"location_id": "t"}}, MIGRABLE, SOURCE_V0_SINGLE, None),
        ({"scene_state": "junk"}, UNMIGRABLE, None, REASON_INVALID_V0),
        ({"scenes": {"t": {}}}, MIGRABLE, SOURCE_V1_UNSTAMPED, None),
        ({"scenes": {"t": {}}, "scene_state": {"x": 1}}, MIGRABLE, SOURCE_V1_UNSTAMPED, None),
        ({"scenes": {"t": "junk"}}, UNMIGRABLE, None, REASON_INVALID_SCENES),
        ({"schema_version": 1, "scenes": {"t": {}}}, CURRENT, None, None),
        ({"schema_version": 1, "scenes": {"t": {}}, "scene_state": {}}, UNMIGRABLE, None, REASON_INCONSISTENT_V1),
        ({"schema_version": 1}, UNMIGRABLE, None, REASON_INCONSISTENT_V1),
        ({"schema_version": 0, "scene_state": {}}, UNMIGRABLE, None, REASON_UNKNOWN_VERSION),
        ({"schema_version": 2, "scenes": {}}, UNMIGRABLE, None, REASON_NEWER_VERSION),
        ({"schema_version": "1", "scenes": {}}, UNMIGRABLE, None, REASON_UNKNOWN_VERSION),
        ({"schema_version": True, "scenes": {}}, UNMIGRABLE, None, REASON_UNKNOWN_VERSION),
        ({}, UNMIGRABLE, None, REASON_UNKNOWN_FORMAT),
        (["list"], UNMIGRABLE, None, REASON_NOT_DICT),
    ])
    def test_classifier(self, payload, status, source, reason):
        v = classify_parsed_save(payload)
        assert (v.status, v.source, v.reason) == (status, source, reason)

    def test_corrupt_json_file(self, tmp_path):
        p = _write(tmp_path, {"x": 1})
        p.write_bytes(b"{not json")
        v = detect_save_format(p)
        assert (v.status, v.reason) == (UNMIGRABLE, REASON_CORRUPT_JSON)


class TestMigratorPure:
    def test_v0_to_v1(self):
        out = sm.migrate_payload_to_v1({"scene_state": V0_SCENE, "metadata": V0_META}, SOURCE_V0_SINGLE)
        assert out == {"metadata": V0_META, "scenes": {"tavern": V0_SCENE}, "schema_version": 1}

    def test_v0_without_location_defaults(self):
        out = sm.migrate_payload_to_v1({"scene_state": {"a": 1}}, SOURCE_V0_SINGLE)
        assert out["scenes"] == {"default": {"a": 1}}

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError):
            sm.migrate_payload_to_v1({}, "V9")


class TestFileProcedure:
    def test_v0_roundtrip_with_backup(self, tmp_path):
        p = _write(tmp_path, {"scene_state": V0_SCENE, "metadata": V0_META})
        original = p.read_bytes()
        out = sm.migrate_save_file_if_needed(p)
        assert out.status == "migrated"
        data = json.loads(p.read_bytes().decode("utf-8-sig"))
        assert data["schema_version"] == 1
        assert data["scenes"] == {"tavern": V0_SCENE}
        assert data["metadata"] == V0_META
        assert "scene_state" not in data
        assert out.backup_file is not None and out.backup_file.read_bytes() == original

    def test_scenario1_v1_reload_noop(self, tmp_path):
        p = _write(tmp_path, {"scene_state": V0_SCENE})
        assert sm.migrate_save_file_if_needed(p).status == "migrated"
        v1_bytes = p.read_bytes()
        out = sm.migrate_save_file_if_needed(p)
        assert out.status == "current"
        assert p.read_bytes() == v1_bytes
        assert len(list(p.parent.glob("*.pre-migration.bak"))) == 1

    def test_scenario2_failure_midway_keeps_original(self, tmp_path, monkeypatch):
        p = _write(tmp_path, {"scene_state": V0_SCENE})
        original = p.read_bytes()

        def _bad_dumps(obj, **kwargs):
            raise RuntimeError("mid-migration crash")

        monkeypatch.setattr(sm, "json", SimpleNamespace(dumps=_bad_dumps))
        with pytest.raises(RuntimeError):
            sm.migrate_save_file_if_needed(p)
        assert p.read_bytes() == original
        assert not list(p.parent.glob("*.migration-tmp"))

    def test_scenario3_crash_between_bak_and_replace(self, tmp_path, monkeypatch):
        p = _write(tmp_path, {"scene_state": V0_SCENE})
        original = p.read_bytes()

        def _boom(src, dst):
            raise OSError("kill -9 simulation")

        monkeypatch.setattr(sm, "os", SimpleNamespace(replace=_boom))
        with pytest.raises(OSError):
            sm.migrate_save_file_if_needed(p)
        assert p.read_bytes() == original
        assert _bak(p).read_bytes() == original

    def test_scenario4_unknown_version_refused(self, tmp_path):
        p = _write(tmp_path, {"schema_version": 0, "scene_state": {}})
        original = p.read_bytes()
        out = sm.migrate_save_file_if_needed(p)
        assert (out.status, out.reason) == ("refused", REASON_UNKNOWN_VERSION)
        assert p.read_bytes() == original
        assert not _bak(p).exists()
        assert out.refusal_text and "сохранён" in out.refusal_text

    def test_scenario5_not_found_creates_nothing(self, tmp_path):
        saves = tmp_path / "saves"
        out = sm.migrate_save_file_if_needed(saves / "ghost" / "campaign_state.json")
        assert out.status == "not_found"
        assert not saves.exists()

    def test_scenario6_metadata_as_is_and_meta_untouched(self, tmp_path):
        p = _write(tmp_path, {"scene_state": V0_SCENE, "metadata": V0_META})
        sm.migrate_save_file_if_needed(p)
        data = json.loads(p.read_bytes().decode("utf-8-sig"))
        assert data["metadata"] == V0_META
        assert not (p.parent / "campaign_meta.json").exists()

    def test_bak_conflict_refused(self, tmp_path):
        p = _write(tmp_path, {"scene_state": V0_SCENE})
        original = p.read_bytes()
        _bak(p).write_bytes(b"foreign")
        out = sm.migrate_save_file_if_needed(p)
        assert (out.status, out.reason) == ("refused", "BACKUP_CONFLICT")
        assert p.read_bytes() == original
        assert _bak(p).read_bytes() == b"foreign"

    def test_retry_after_crash_reuses_equal_bak(self, tmp_path):
        p = _write(tmp_path, {"scene_state": V0_SCENE})
        original = p.read_bytes()
        _bak(p).write_bytes(original)
        out = sm.migrate_save_file_if_needed(p)
        assert out.status == "migrated"
        assert _bak(p).read_bytes() == original


def _make_lifecycle(tmp_path):
    events = []
    mm = SimpleNamespace(
        persist_campaign_event=lambda cid, event, world_id, data: events.append(event),
        persist_world_canon=lambda *a, **k: None,
    )
    lc = CampaignLifecycle(
        scene_manager=object(), rel_store=object(), memory_manager=mm,
        tick_orch=object(), avatar_service=object(), mvp_controller=object(),
        get_life_engine=lambda: None, load_npcs=lambda: [],
        saves_dir=tmp_path / "saves",
    )
    return lc, events


class TestLifecycle:
    def test_scenario7_api_distinguishes_outcomes(self, tmp_path):
        lc, events = _make_lifecycle(tmp_path)
        r1 = lc.load_campaign("ghost", "w")
        assert (r1.status, r1.load_refusal_reason) == ("not_found", None)
        _write(tmp_path, {"scene_state": V0_SCENE}, campaign="old")
        r2 = lc.load_campaign("old", "w")
        assert (r2.status, r2.load_refusal_reason) == ("migrated", None)
        _write(tmp_path, {"schema_version": 0, "scene_state": {}}, campaign="bad")
        r3 = lc.load_campaign("bad", "w")
        assert r3.status == "refused" and r3.load_refusal_reason
        assert events == ["campaign_loaded", "campaign_loaded", "campaign_load_refused"]
        assert not (tmp_path / "saves" / "ghost").exists()


class TestReaders:
    def test_extract_scene_payload(self):
        v1 = {"scenes": {"tavern": {"location_id": "tavern"}, "street": {"location_id": "street"}}}
        assert sm.extract_scene_payload(v1, "street") == {"location_id": "street"}
        assert sm.extract_scene_payload({"scenes": {"t": {"x": 1}}}) == {"x": 1}
        assert sm.extract_scene_payload(v1) is None
        assert sm.extract_scene_payload({"scene_state": {"x": 1}}) == {"x": 1}
        assert sm.extract_scene_payload({"scenes": {"t": {}}}, "missing") is None

    def test_resolve_current_location(self):
        assert sm.resolve_current_location({"scenes": {"t": {"location_id": "tavern"}}}) == "tavern"
        assert sm.resolve_current_location({"scene_state": {"location_id": "tavern"}}) == "tavern"
        assert sm.resolve_current_location({"scenes": {"t": {}}, "metadata": {"current_location": "street"}}) == "street"
        assert sm.resolve_current_location({}) is None

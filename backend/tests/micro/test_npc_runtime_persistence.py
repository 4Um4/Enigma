"""NPC Runtime Persistence — сквозной round-trip через production-путь.

Дефект: SSM.commit() принимает npc_dicts, но кладёт их только в
_last_committed_npcs_src (мёртвый снапшот). unlock_tick() коммитит сцены
без NPC. Итог: runtime не переживает рестарт.

Контракт: PERSIST-RECOVERY R1-R5.
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest

from app.services.scene_state_manager import SceneStateManager
from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter

CAMPAIGN = "persist_test"
LOC_A = "tavern"
LOC_B = "market"


def _scene(loc, tick=1):
    return {
        "location_id": loc,
        "campaign_id": CAMPAIGN,
        "tick": tick,
        "game_time_seconds": 10.0 * tick,
        "npc_positions": {"npc_a": {"position": loc + ":node_1", "name": "A"}},
    }


def _npc(loc=LOC_A):
    return {
        "id": "npc_a",
        "npc_id": "npc_a",
        "location_id": loc,
        "body_state": {"injuries": ["cut_left_arm"], "blood_loss": 0.35, "pain": 12.0},
        "psyche": {"stress": 47.5},
        "drives": {"hunger": 0.62},
        "intent": "TRADE",
        "intent_target": "player",
        "narrative_cache": [{"summary": "saw the blade", "tags": ["violence"]}],
    }


def _mk(tmp_path, name="runtime.db"):
    db = tmp_path / name
    adapter = SqlitePersistenceAdapter(db)
    ssm = SceneStateManager(
        data_dir=tmp_path / "data", persistence=adapter, saves_dir=tmp_path / "saves"
    )
    return db, adapter, ssm


def test_t1_npc_runtime_roundtrip_production_path(tmp_path):
    """T1: мутация -> commit -> unlock_tick -> закрытие conn -> новый адаптер -> load."""
    db, adapter, ssm = _mk(tmp_path)
    scene = _scene(LOC_A)
    ssm.lock_all_for_tick(CAMPAIGN, [LOC_A])
    ssm.adopt_scene_for_tick(CAMPAIGN, LOC_A, scene)

    npc = _npc()
    ssm.commit(campaign_id=CAMPAIGN, scene_state=scene, npc_dicts=[npc])

    # Мутация ПОСЛЕ commit: снимок не должен её видеть (поправка A Мастера)
    npc["body_state"]["blood_loss"] = 0.99
    npc["body_state"]["injuries"].append("AFTER_COMMIT")
    npc["psyche"]["stress"] = 0.0
    npc["drives"]["hunger"] = 0.0

    ssm.unlock_tick(CAMPAIGN)
    adapter.close()

    # Adapter-level persistence round-trip: прежний адаптер закрыт, его RAM
    # уничтожена; новый экземпляр читает только с диска. Full process restart
    # — отдельный E2E-контроль, не этот тест.
    reader = SqlitePersistenceAdapter(db)
    try:
        loaded_scene = reader.load_scene_at(CAMPAIGN, LOC_A)
        assert loaded_scene, "SETUP FAIL: сцена не сохранена — tick-путь не отработал"

        loaded = reader.load_npc_runtime(CAMPAIGN)
        assert loaded is not None, (
            "DEFECT: NPC runtime не персистится — сцена сохранена, runtime отсутствует"
        )
        rec = next((r for r in loaded if r.get("id") == "npc_a"), None)
        assert rec is not None, "DEFECT: npc_a отсутствует в runtime"

        assert rec["body_state"]["blood_loss"] == 0.35, "blood_loss не пережил round-trip"
        assert rec["body_state"]["injuries"] == ["cut_left_arm"], (
            "injuries не пережили round-trip либо снимок разделяет ссылку"
        )
        assert rec["psyche"]["stress"] == 47.5, "psyche.stress не пережил round-trip"
        assert rec["drives"]["hunger"] == 0.62, "drives не пережили round-trip"
        assert rec["location_id"] == LOC_A, "location_id не пережил round-trip"
        assert rec["intent"] == "TRADE", "intent не пережил round-trip"
        assert rec["narrative_cache"][0]["summary"] == "saw the blade"
    finally:
        reader.close()


def test_t2_commit_false_is_not_silent(tmp_path, caplog):
    """T2: atomic_commit_all -> False не должен исчезать бесследно."""
    import logging

    _db, adapter, ssm = _mk(tmp_path)
    scene = _scene(LOC_A)
    ssm.lock_all_for_tick(CAMPAIGN, [LOC_A])
    ssm.adopt_scene_for_tick(CAMPAIGN, LOC_A, scene)
    ssm.commit(campaign_id=CAMPAIGN, scene_state=scene, npc_dicts=[_npc()])

    def _fail(*a, **kw):
        return False

    adapter.atomic_commit_all = _fail
    with caplog.at_level(logging.ERROR):
        ssm.unlock_tick(CAMPAIGN)
    adapter.close()

    _errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert _errs, "DEFECT: atomic_commit_all вернул False — ERROR не залогирован"
    assert any(CAMPAIGN in r.getMessage() for r in _errs), "ERROR без campaign_id"


def test_t3_abort_no_commit_no_leak(tmp_path):
    """T3: aborted tick — ни сцен, ни NPC; снимок не протекает в следующий тик."""
    db, adapter, ssm = _mk(tmp_path)
    scene = _scene(LOC_A)
    ssm.lock_all_for_tick(CAMPAIGN, [LOC_A])
    ssm.adopt_scene_for_tick(CAMPAIGN, LOC_A, scene)
    ssm.commit(campaign_id=CAMPAIGN, scene_state=scene, npc_dicts=[_npc()])
    ssm.mark_tick_aborted(CAMPAIGN)
    ssm.unlock_tick(CAMPAIGN)

    assert getattr(ssm, "_tick_npc_runtime", None) is None, (
        "DEFECT: снимок NPC пережил границу тика"
    )
    adapter.close()

    reader = SqlitePersistenceAdapter(db)
    try:
        assert reader.load_npc_runtime(CAMPAIGN) is None, "abort: NPC всё равно записан"
    finally:
        reader.close()


def test_t6_multi_location_single_payload(tmp_path):
    """T6: два тика локаций — один коммит, NPC-пейлоад не задвоен."""
    db, adapter, ssm = _mk(tmp_path)
    ssm.lock_all_for_tick(CAMPAIGN, [LOC_A, LOC_B])
    sa, sb = _scene(LOC_A), _scene(LOC_B)
    ssm.adopt_scene_for_tick(CAMPAIGN, LOC_A, sa)
    ssm.adopt_scene_for_tick(CAMPAIGN, LOC_B, sb)

    npcs = [_npc(LOC_A)]
    ssm.commit(campaign_id=CAMPAIGN, scene_state=sa, npc_dicts=npcs)
    ssm.commit(campaign_id=CAMPAIGN, scene_state=sb, npc_dicts=npcs)
    ssm.unlock_tick(CAMPAIGN)
    adapter.close()

    reader = SqlitePersistenceAdapter(db)
    try:
        assert reader.load_scene_at(CAMPAIGN, LOC_A), "SETUP FAIL: сцена A не сохранена"
        assert reader.load_scene_at(CAMPAIGN, LOC_B), "SETUP FAIL: сцена B не сохранена"
        loaded = reader.load_npc_runtime(CAMPAIGN)
        assert loaded is not None, "DEFECT: NPC runtime отсутствует при multi-location"
        ids = [r.get("id") for r in loaded]
        assert ids.count("npc_a") == 1, "NPC задвоен: " + str(ids)
    finally:
        reader.close()
"""Migration Marker Commit Guard (ADR-O-441).

Дефект: _confirm_v2_migration вызывался безусловно после atomic_commit_all.
При False (rollback) маркер .migrated ставился, а v2 на диске отсутствовал →
migrate_legacy:318-319 навсегда скипает импорт legacy-пар.
"""
import sys
from pathlib import Path

_B = Path(__file__).resolve().parents[2]
if str(_B) not in sys.path:
    sys.path.insert(0, str(_B))

import pytest

from app.services.scene_state_manager import SceneStateManager
from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter

CAMP = "marker_test"
LOC = "tavern"


def _mk(tmp_path, legacy=True, premarked=False):
    db = tmp_path / "runtime.db"
    ad = SqlitePersistenceAdapter(db)
    saves = tmp_path / "saves"
    ssm = SceneStateManager(data_dir=tmp_path / "data", persistence=ad, saves_dir=saves)
    d = saves / CAMP
    d.mkdir(parents=True, exist_ok=True)
    if legacy:
        (d / "npc_relationships.json").write_text('{"a\u2192b": {"trust": 0.5}}', encoding="utf-8")
    marker = d / "npc_relationships.json.migrated"
    if premarked:
        marker.write_text("migrated\n", encoding="utf-8")
    return ad, ssm, marker


def _tick(ssm, ad, fail=False):
    sc = {"location_id": LOC, "campaign_id": CAMP, "tick": 1, "npc_positions": {}}
    ssm.lock_all_for_tick(CAMP, [LOC])
    ssm.adopt_scene_for_tick(CAMP, LOC, sc)
    ssm.commit(campaign_id=CAMP, scene_state=sc, npc_dicts=[{"id": "a", "npc_id": "a"}])
    if fail:
        ad.atomic_commit_all = lambda *a, **k: False
    ssm.unlock_tick(CAMP)


def test_marker_not_created_on_failed_commit(tmp_path):
    """T-M1: atomic_commit_all -> False => маркер НЕ создан."""
    ad, ssm, marker = _mk(tmp_path)
    _tick(ssm, ad, fail=True)
    ad.close()
    assert not marker.exists(), "DEFECT: маркер поставлен при неуспешном коммите"


def test_marker_created_on_successful_commit(tmp_path):
    """T-M2: реальный успешный коммит => маркер создан."""
    ad, ssm, marker = _mk(tmp_path)
    _tick(ssm, ad, fail=False)
    ad.close()
    assert marker.exists(), "маркер не создан при успешном коммите"


def test_existing_marker_idempotent(tmp_path):
    """T-M3: маркер уже есть => не перезаписывается."""
    ad, ssm, marker = _mk(tmp_path, premarked=True)
    before = marker.read_bytes()
    _tick(ssm, ad, fail=False)
    ad.close()
    assert marker.read_bytes() == before, "существующий маркер перезаписан"


@pytest.mark.xfail(reason="KNOWN DEFECT вне скоупа ADR-O-441: confirm_migration не проверяет существование legacy-файла, противореча migrate_legacy:320-323. Правка в relationship_state_store.py запрещена заданием.", strict=False)
def test_no_legacy_file_no_marker(tmp_path):
    """T-M4: legacy отсутствует => маркер не ставится (новая кампания)."""
    ad, ssm, marker = _mk(tmp_path, legacy=False)
    _tick(ssm, ad, fail=False)
    ad.close()
    assert not marker.exists(), "маркер поставлен без legacy-файла"
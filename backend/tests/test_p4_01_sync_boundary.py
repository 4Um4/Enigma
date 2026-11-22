# path: backend/tests/test_p4_01_sync_boundary.py
"""P4-01 · T9 — доказательства безопасного зеркального sync (контракт D.3)."""

import sys
import json
import shutil
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "map_editor"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from campaign_manager import CampaignManager
from data_manager import DataManager


@pytest.fixture
def temp_campaign(tmp_path):
    camp_dir = tmp_path / "campaigns" / "test_camp" / "locations"
    camp_dir.mkdir(parents=True)
    src_file = camp_dir / "loc1.json"
    src_file.write_text(json.dumps({"location_id": "loc1", "test": "data"}))

    dm = DataManager()
    dm.set_base_dir(camp_dir.parent.parent)

    cm = CampaignManager(dm)
    cm.current_campaign_name = "test_camp"
    cm._campaign_dir = camp_dir.parent
    return cm, camp_dir, src_file


def test_t9_cwd_independence(temp_campaign, tmp_path, monkeypatch):
    cm, camp_dir, src_file = temp_campaign
    monkeypatch.chdir(tmp_path)
    res = cm._sync_to_runtime()
    assert res["failed"] == 0
    assert res["copied"] >= 1


def test_t9_mirror_delete_only_json(temp_campaign, tmp_path):
    cm, camp_dir, src_file = temp_campaign
    target_dir = Path(__file__).resolve().parents[2] / "saves" / "test_camp" / "locations"
    target_dir.mkdir(parents=True, exist_ok=True)

    orphan_json = target_dir / "orphan.json"
    orphan_json.write_text('{"deleted": true}')

    keep_txt = target_dir / "keep_me.txt"
    keep_txt.write_text("do not delete")

    res = cm._sync_to_runtime()

    assert res["deleted"] >= 1
    assert not orphan_json.exists()
    assert keep_txt.exists()
    assert keep_txt.read_text() == "do not delete"
    assert res["failed"] == 0

    shutil.rmtree(target_dir.parent)


def test_t9_no_campaign_dir(temp_campaign):
    cm, camp_dir, src_file = temp_campaign
    cm._campaign_dir = None
    res = cm._sync_to_runtime()
    assert res["copied"] == 0 and res["deleted"] == 0 and res["failed"] == 0

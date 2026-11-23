# path: backend/tests/test_p4_02_sync_containment.py
"""P4-02 - T20..T29: Containment / Isolation зеркального sync (P4-01).

Containment: ни одна запись или удаление не выходит за разрешённые корни.
Isolation:   отказ одной операции не повреждает файлы вне её области.
"""

import json
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
MAP_EDITOR_DIR = FRONTEND_DIR / "map_editor"
for _p in (str(FRONTEND_DIR), str(MAP_EDITOR_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from campaign_manager import CampaignManager
from data_manager import DataManager

MIRROR_RELS = (
    "saves",
    "build/staging/saves",
    "build/staging/frontend/map_editor/campaigns",
)


@pytest.fixture
def orchestrator(monkeypatch):
    """Изолируем пересборку реестра: она не предмет P4-02."""
    import spatial_compilation_orchestrator as sco

    state = {"calls": [], "fail": False}

    class _Stub:
        def rebuild_if_needed(self, name):
            state["calls"].append(name)
            if state["fail"]:
                raise RuntimeError("stub rebuild failure")

    monkeypatch.setattr(sco, "SpatialCompilationOrchestrator", _Stub)
    return state


@pytest.fixture
def campaign(tmp_path, orchestrator, caplog):
    caplog.set_level(logging.CRITICAL, logger="data_manager")
    name = "p402_" + uuid.uuid4().hex[:8]
    camp = tmp_path / "campaigns" / name
    (camp / "locations").mkdir(parents=True)
    (camp / "locations" / "loc1.json").write_text(
        json.dumps({"location_id": "loc1"}), encoding="utf-8"
    )

    cm = CampaignManager(DataManager())
    cm.current_campaign_name = name
    cm._campaign_dir = camp

    yield cm, name, camp

    for rel in MIRROR_RELS:
        p = REPO_ROOT / rel / name
        if p.is_symlink() or p.is_file():
            p.unlink(missing_ok=True)
        elif p.exists():
            shutil.rmtree(p, ignore_errors=True)


def _outside_zone(tmp_path, label):
    """Зона ВНЕ репозитория. Sync не должен ничего здесь трогать."""
    zone = tmp_path / ("outside_" + label)
    zone.mkdir(parents=True, exist_ok=True)
    precious = zone / "precious.txt"
    precious.write_text("DO NOT TOUCH", encoding="utf-8")
    return zone, precious


def test_t20_traversal_one_level(campaign, tmp_path):
    """T20: '../<zone>' остаётся внутри корня - ловится проверкой имени."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t20")
    cm.current_campaign_name = "../" + zone.name

    res = cm._sync_to_runtime()

    assert res["errors"], "traversal обязан быть отклонён"
    assert res["copied"] == 0, "копирование не должно было состояться"
    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
    assert not (REPO_ROOT / zone.name).exists(), "создан каталог вне whitelist"


def test_t21_traversal_two_levels(campaign, tmp_path):
    """T21: '../../<zone>' уходит за корень - ловится is_relative_to."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t21")
    cm.current_campaign_name = "../../" + zone.name

    res = cm._sync_to_runtime()

    assert res["errors"]
    assert res["copied"] == 0
    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
    assert not (REPO_ROOT.parent / zone.name).exists()


def test_t22_absolute_campaign_name(campaign, tmp_path):
    """T22: абсолютный путь сбрасывает базу в pathlib - должен быть отклонён."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t22")
    cm.current_campaign_name = str(zone)

    res = cm._sync_to_runtime()

    assert res["errors"]
    assert res["copied"] == 0
    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
    assert not (zone / "locations").exists(), "создан каталог по абсолютному пути"


def test_t23_windows_separators(campaign, tmp_path):
    """T23: Windows-разделители не должны обходить нормализацию."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t23")
    cm.current_campaign_name = "..\\..\\" + zone.name

    res = cm._sync_to_runtime()

    assert res["errors"]
    assert res["copied"] == 0
    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
    assert not (REPO_ROOT.parent / zone.name).exists()


def test_t24_nested_escape(campaign, tmp_path):
    """T24: вложенный путь с попыткой выхода."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t24")
    cm.current_campaign_name = "x/../../../" + zone.name

    res = cm._sync_to_runtime()

    assert res["errors"]
    assert res["copied"] == 0
    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
    assert not (REPO_ROOT.parent / zone.name).exists()


def test_t25_symlinked_mirror_dir(campaign, tmp_path):
    """T25: каталог зеркала - symlink наружу. resolve() обязан его раскрыть."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t25")
    link = REPO_ROOT / "saves" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(zone, link, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip("symlink недоступен на этой машине: %s" % e)

    try:
        res = cm._sync_to_runtime()
        assert res["errors"], "symlink наружу обязан быть отклонён"
        assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH"
        assert not (zone / "locations").exists()
    finally:
        if link.is_symlink():
            link.unlink()


def test_t26_hardlink_write_through(campaign, tmp_path):
    """T26: приёмник - hardlink на внешний файл. copy2 не должен писать сквозь."""
    cm, name, camp = campaign
    zone, precious = _outside_zone(tmp_path, "t26")
    target_dir = REPO_ROOT / "saves" / name / "locations"
    target_dir.mkdir(parents=True, exist_ok=True)
    link = target_dir / "loc1.json"
    try:
        os.link(precious, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip("hardlink недоступен на этой машине: %s" % e)

    cm._sync_to_runtime()

    assert precious.read_text(encoding="utf-8") == "DO NOT TOUCH", (
        "CONTAINMENT BREACH: copy2 перезаписал внешний файл через hardlink"
    )


def test_t27_registry_failure_keeps_artifact(campaign, orchestrator):
    """T27: отказ пересборки не должен уничтожать рабочий реестр."""
    cm, name, camp = campaign
    compiled = camp / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    artifact = compiled / "spatial_registry.json"
    artifact.write_text('{"working":"registry"}', encoding="utf-8")

    orchestrator["fail"] = True
    res = cm._sync_to_runtime()

    assert any("Registry rebuild failed" in e for e in res["errors"])
    for rel in MIRROR_RELS:
        assert (REPO_ROOT / rel / name / "locations" / "loc1.json").exists(), (
            "отказ реестра повредил зеркала: %s" % rel
        )
    assert artifact.exists(), (
        "DATA LOSS: рабочий реестр удалён до неудачной пересборки"
    )
    assert artifact.read_text(encoding="utf-8") == '{"working":"registry"}'


def test_t28_one_mirror_blocked_isolated(campaign):
    """T28: одно зеркало заблокировано файлом - отказ локален."""
    cm, name, camp = campaign
    blocker = REPO_ROOT / "build/staging/saves" / name
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("i am a file, not a dir", encoding="utf-8")

    try:
        res = cm._sync_to_runtime()
        assert res["errors"], "заблокированное зеркало должно дать ошибку"
        assert (REPO_ROOT / "saves" / name / "locations" / "loc1.json").exists()
        assert (
            REPO_ROOT / MIRROR_RELS[2] / name / "locations" / "loc1.json"
        ).exists()
        assert blocker.read_text(encoding="utf-8") == "i am a file, not a dir"
    finally:
        blocker.unlink(missing_ok=True)


def test_t29_happy_path_foreign_cwd(campaign, tmp_path, monkeypatch):
    """T29: регрессия - штатный sync, mirror-delete, absolute paths."""
    cm, name, camp = campaign
    monkeypatch.chdir(tmp_path)

    d = REPO_ROOT / "saves" / name / "locations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "orphan.json").write_text("{}", encoding="utf-8")
    (d / "keep.txt").write_text("keep", encoding="utf-8")

    res = cm._sync_to_runtime()

    assert res["errors"] == [], "штатный путь не должен давать ошибок: %s" % res["errors"]
    assert res["copied"] == 3
    assert res["deleted"] == 1
    assert res["failed"] == 0
    for rel in MIRROR_RELS:
        assert (REPO_ROOT / rel / name / "locations" / "loc1.json").exists()
    assert not (d / "orphan.json").exists()
    assert (d / "keep.txt").read_text(encoding="utf-8") == "keep"

def test_t30_overwrite_existing_regular_file(campaign):
    """T30: штатная перезапись обычного файла обновляет содержимое, tmp убран."""
    cm, name, camp = campaign
    d = REPO_ROOT / "saves" / name / "locations"
    d.mkdir(parents=True, exist_ok=True)
    existing = d / "loc1.json"
    existing.write_text('{"stale":true}', encoding="utf-8")

    res = cm._sync_to_runtime()

    assert res["errors"] == [], "ошибки: %s" % res["errors"]
    assert json.loads(existing.read_text(encoding="utf-8")) == {"location_id": "loc1"}
    assert not (d / "loc1.json.p402tmp").exists(), "временный файл не убран"
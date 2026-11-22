# path: backend/tests/test_p3_01_save_result.py
"""P3-01 · T7 — доказательства честного контракта сохранения.

Три группы:
  A. SaveResult (чистый unit, без импортов редактора) — T7-6
  B. DataManager / CampaignManager (реальные объекты, tmp_path) — T7-1..5, 7, 8
  C. Source-инспекция UI (без pygame) — T7-9, T7-10

Read-only сценарий строится через __new__ + ручные атрибуты, чтобы НЕ
provocировать load_all() на пользовательских шаблонах. Writable-сценарии
идут штатным путём редактора: DataManager() → set_base_dir(tmp_path),
после чего в памяти только созданные тестом локации.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
ME = ROOT / "frontend" / "map_editor"


def _ensure_editor_path():
    if str(ME) not in sys.path:
        sys.path.insert(0, str(ME))


@pytest.fixture(scope="module")
def mods():
    _ensure_editor_path()
    import campaign_manager
    import data_manager
    import save_result

    return SimpleNamespace(
        DataManager=data_manager.DataManager,
        CampaignManager=campaign_manager.CampaignManager,
        SaveResult=save_result.SaveResult,
    )


@pytest.fixture
def dm(mods, tmp_path):
    """Writable DataManager, изолированный в tmp_path (штатный путь редактора)."""
    obj = mods.DataManager()
    obj.set_base_dir(tmp_path)
    return obj


def _mk(dm, name="t.json"):
    ok, err = dm.create_location(name, 20, 15, "Test", False)
    assert ok, f"create_location не сработал: {err}"
    return name


def _method_src(path: Path, name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith(f"def {name}("):
            base = len(ln) - len(ln.lstrip())
            out = [ln]
            for j in range(i + 1, len(lines)):
                cur = lines[j]
                if cur.strip():
                    ind = len(cur) - len(cur.lstrip())
                    if ind <= base and cur.lstrip().startswith(("def ", "class ", "@")):
                        break
                out.append(cur)
            return "\n".join(out)
    raise AssertionError(f"метод {name} не найден в {path}")


def _block_after(path: Path, marker: str, n: int = 8) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if marker in ln:
            return "\n".join(lines[i : i + n])
    raise AssertionError(f"маркер {marker!r} не найден в {path}")


# ───────────────────────── A. SaveResult (T7-6) ─────────────────────────


def test_t7_6_truthiness_failure_is_false(mods):
    """T7-6: защита от F-10 — отказной результат ложен в bool-контексте."""
    SR = mods.SaveResult
    assert bool(SR.failure(["причина"])) is False
    assert bool(SR.failure(["x"], failed=["a.json"], count=2)) is False
    assert bool(SR(ok=False, errors=["e"], count=5, failed=["a"])) is False


def test_t7_6_truthiness_success_is_true(mods):
    SR = mods.SaveResult
    assert bool(SR.success()) is True
    assert bool(SR.success(count=3)) is True
    assert SR.success(count=3).count == 3


def test_t7_6_reason_text_limits(mods):
    SR = mods.SaveResult
    r = SR.failure(["e1", "e2", "e3", "e4"])
    txt = r.reason_text(limit=3)
    assert "e1" in txt and "e3" in txt and "e4" not in txt
    assert "ещё 1" in txt
    assert SR.failure([]).reason_text() == "причина не указана"


# ─────────────────── B. DataManager / CampaignManager ───────────────────


def test_t7_1_readonly_refusal_with_reason(mods, tmp_path):
    """T7-1: _writable=False → отказ с причиной, файл не создан."""
    dm = mods.DataManager.__new__(mods.DataManager)
    dm.base_dir = tmp_path
    dm._writable = False
    dm.locations = {"x.json": {"label": "X", "location_id": "x"}}
    dm._instance_refs = {}

    res = dm.save("x.json")
    assert not res, "read-only save обязан быть отказом"
    assert res.errors, "причина отказа обязательна (F-1)"
    assert any("read-only" in e for e in res.errors)
    assert not (tmp_path / "x.json").exists()


def test_t7_1_missing_location_has_reason(mods, tmp_path):
    """T7-1: ветка 'нет в памяти' теперь тоже с причиной (была без лога)."""
    dm = mods.DataManager.__new__(mods.DataManager)
    dm.base_dir = tmp_path
    dm._writable = True
    dm.locations = {}
    dm._instance_refs = {}
    res = dm.save("ghost.json")
    assert not res and res.errors


def test_t7_2_schema_error_keeps_file_untouched(dm, tmp_path):
    """T7-2: schema-ошибка → отказ, байты файла не изменились."""
    name = _mk(dm)
    assert dm.save(name), "валидная локация обязана сохраняться (позитивный контроль)"
    path = tmp_path / name
    before = path.read_bytes()

    dm.locations[name]["label"] = ""
    res = dm.save(name)
    assert not res
    assert res.errors
    assert path.read_bytes() == before, "файл не должен быть перезаписан при отказе"


def test_t7_3_oserror_is_refusal_not_exception(dm, tmp_path):
    """T7-3 (F-2/F-18): отказ ФС → результат, а не необработанное исключение."""
    name = _mk(dm)
    assert dm.save(name)
    blocker = tmp_path / "blocker.bin"
    blocker.write_text("not a directory", encoding="utf-8")
    dm.base_dir = blocker  # base_dir — файл: open() обязан упасть OSError

    res = dm.save(name)  # не должно бросить
    assert not res
    assert any("ошибка записи" in e for e in res.errors)


def test_t7_4_rollback_on_schema_failure(dm):
    """T7-4 (F-3/F-24): modified_at/location_id откатаны при schema-отказе."""
    name = _mk(dm)
    assert dm.save(name)
    loc = dm.locations[name]
    snap_mod = loc["modified_at"]
    snap_id = loc["location_id"]

    loc["label"] = ""
    assert not dm.save(name)
    assert loc["modified_at"] == snap_mod
    assert loc["location_id"] == snap_id


def test_t7_4_rollback_on_oserror(dm, tmp_path):
    name = _mk(dm)
    assert dm.save(name)
    loc = dm.locations[name]
    snap_mod = loc["modified_at"]
    blocker = tmp_path / "blocker.bin"
    blocker.write_text("x", encoding="utf-8")
    dm.base_dir = blocker
    assert not dm.save(name)
    assert loc["modified_at"] == snap_mod


def test_t7_4_rollback_removes_inferred_location_id(dm):
    """Откат обязан убрать location_id, которого до вызова не было."""
    name = _mk(dm)
    assert dm.save(name)
    loc = dm.locations[name]
    del loc["location_id"]
    loc["label"] = ""
    assert not dm.save(name)
    assert "location_id" not in loc, "инференс не должен переживать отказ"


def test_t7_5_batch_partial_failure_visible(dm, mods):
    """T7-5 (F-5): 2 из 3 → ok=False, count=2, failed=[битый]."""
    for n in ("a.json", "b.json", "c.json"):
        _mk(dm, n)
    dm.locations["b.json"]["label"] = ""
    cm = mods.CampaignManager(dm)

    res = cm.save_all_locations()
    assert not res
    assert res.count == 2
    assert res.failed == ["b.json"]
    assert res.errors


def test_t7_5_no_modified_mark_when_nothing_written(dm, mods, monkeypatch):
    """T7-5: _update_modified не вызывается при count==0."""
    _mk(dm, "a.json")
    dm.locations["a.json"]["label"] = ""
    cm = mods.CampaignManager(dm)
    calls = []
    monkeypatch.setattr(cm, "_update_modified", lambda: calls.append(1))

    res = cm.save_all_locations()
    assert not res and res.count == 0
    assert calls == [], "кампания не помечается сохранённой при нуле записей"


def test_t7_7_save_as_no_orphan_on_failure(dm, mods):
    """T7-7 (F-11): отказ save_as → сироты в памяти нет."""
    src = _mk(dm, "src.json")
    dm.locations[src]["label"] = ""
    cm = mods.CampaignManager(dm)

    ok, err = cm.save_location_as(src, "dst.json")
    assert ok is False
    assert err
    assert "dst.json" not in dm.locations, "незаписанная копия не остаётся в памяти"


def test_t7_7_save_as_success(dm, mods, tmp_path):
    src = _mk(dm, "src.json")
    cm = mods.CampaignManager(dm)
    ok, err = cm.save_location_as(src, "dst.json")
    assert ok is True, err
    assert "dst.json" in dm.locations
    assert (tmp_path / "dst.json").exists()


def test_t7_8_dm_save_all_returns_result(dm, mods):
    """T7-8 (F-14): save_all возвращает результат, а не None."""
    _mk(dm, "a.json")
    res = dm.save_all()
    assert res is not None
    assert bool(res) is True
    assert res.count == 1

    dm.locations["a.json"]["label"] = ""
    res2 = dm.save_all()
    assert res2 is not None
    assert not res2
    assert res2.failed == ["a.json"]


def test_t7_8_dm_save_all_readonly_result(mods, tmp_path):
    dm = mods.DataManager.__new__(mods.DataManager)
    dm.base_dir = tmp_path
    dm._writable = False
    dm.locations = {"x.json": {"label": "X"}}
    dm._instance_refs = {}
    res = dm.save_all()
    assert res is not None and not res
    assert res.failed == ["x.json"]


# ───────────────────── C. Source-инспекция UI (T7-9/10) ─────────────────────


def test_t7_9_report_save_helper_exists():
    src = _method_src(ME / "editor_core.py", "_report_save")
    assert "_show_toast" in src
    assert "Ошибка сохранения" in src


def test_t7_9_quick_save_uses_result_and_conditional_rebuild():
    src = _method_src(ME / "editor_core.py", "_quick_save")
    assert "_report_save" in src, "фиктивный тост успеха запрещён"
    assert "if self._report_save" in src
    assert "self._rebuild_spatial_registry()" in src
    idx_guard = src.index("if self._report_save")
    idx_rebuild = src.index("self._rebuild_spatial_registry()")
    assert idx_rebuild > idx_guard, "rebuild только после подтверждённой записи (F-7)"


def test_t7_9_save_campaign_and_save_all_use_result():
    for name in ("_save_campaign", "_save_all"):
        src = _method_src(ME / "editor_core.py", name)
        assert "_report_save" in src, f"{name} игнорирует результат"
        assert "result.count" in src


def test_t7_9_new_location_reports_unsaved():
    src = _method_src(ME / "editor_core.py", "_dialog_new_location")
    assert "не сохранена" in src
    assert "result.reason_text()" in src


def test_t7_9_ctrl_s_delegates_to_quick_save():
    block = _block_after(ME / "core" / "event_handler.py", "pygame.K_s and", n=6)
    assert "core._quick_save()" in block
    assert "core.dm.save(" not in block
    assert "core.cm.save_location(" not in block


def test_t7_9_world_drag_release_uses_helper():
    block = _block_after(ME / "core" / "event_handler.py", "core._dragging_location = None", n=6)
    assert "core._report_save" in block


def test_t7_10_save_as_validates_and_folds():
    """T7-10 (F-15/F-16): Save As валидирует и пишет свёрнутый payload."""
    src = _method_src(ME / "editor_core.py", "_dialog_save_as")
    assert "validate_location(" in src
    assert "_fold_for_save(" in src
    assert "_report_save(" in src
    assert "self.dm.locations[self.current_file]," not in src, "сырой payload запрещён"

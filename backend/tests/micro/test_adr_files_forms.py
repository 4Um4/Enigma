# path: /backend/tests/micro/test_adr_files_forms.py
"""B1 (S315): парсер Files — 4 реальные формы документов (DEBT-ADR-NET-FILES-EXTRACTION)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.adr_net.adr_parser import _FILES_REGEX, parse_impact_audit


def _parse(tmp_path, body: str):
    # parse_impact_audit требует шапку _ADR_LINE_REGEX: `ADR-X` [TYPE] **Title**
    f = tmp_path / "X_IMPACT.md"
    f.write_text(
        "`ADR-9001` [FIX] **Parse Forms Test**\n\n" + body + "\n",
        encoding="utf-8",
    )
    node = parse_impact_audit(str(f))
    assert node is not None, "шапка ADR обязана резолвиться (регресс _ADR_LINE_REGEX)"
    return node


def test_files_na_becomes_empty(tmp_path):
    node = _parse(tmp_path, "Files: N/A")
    assert node is not None and node.files == []


def test_files_backtick_relative(tmp_path):
    node = _parse(tmp_path, "Files: `domain/events.py`, `services/npc/perception_filter.py`")
    assert node.files == ["domain/events.py", "services/npc/perception_filter.py"]


def test_files_csv_full_paths(tmp_path):
    node = _parse(tmp_path, "Files: backend/app/a.py, backend/app/b.py")
    assert node.files == ["backend/app/a.py", "backend/app/b.py"]


def test_files_atlas_full_form(tmp_path):
    node = _parse(tmp_path, "Files (full: ADR-X_IMPACT.md): dom/x.py, svc/y.py")
    assert node.files == ["dom/x.py", "svc/y.py"]


def test_regex_matches_atlas_form_directly():
    assert _FILES_REGEX.search("Files (full: A-1.md): a.py, b.py") is not None
    assert _FILES_REGEX.search("Files: a.py") is not None
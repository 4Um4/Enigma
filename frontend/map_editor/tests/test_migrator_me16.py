"""path: /frontend/map_editor/tests/test_migrator_me16.py

Назначение: ME-1.7 autotests — migrator script invariants.
    backend/scripts/me16_migrate_location_templates.py — migrator для разрешения
    двойного хранения location_templates/ vs campaigns/<id>/locations/.
    Тесты доказывают: (1) dry-run сообщает конфликты для Open_road; (2) dry-run
    не меняет файлы; (3) migrator идемпотентен; (4) --apply без --apply-templates-edits
    — no-op для shared files.
Зависимости: pytest, subprocess, backend/scripts/me16_migrate_location_templates.py.
Основные сущности:
    - test_migrator_exists — скрипт существует
    - test_dry_run_reports_conflicts — 3 conflicts / 3 orphaned / 0 actions
    - test_dry_run_no_file_changes — campaigns файлы не модифицированы
    - test_idempotent — повторный dry-run = идентичный stdout
    - test_apply_noop_for_shared_files — --apply не меняет shared files
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MIGRATOR = (
    _PROJECT_ROOT / "backend" / "scripts" / "me16_migrate_location_templates.py"
)
_CAMPAIGN_DIR = (
    _PROJECT_ROOT / "frontend" / "map_editor" / "campaigns" / "Open_road" / "locations"
)


def _run_migrator(*args: str) -> subprocess.CompletedProcess[str]:
    """Run migrator with args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(_MIGRATOR), *args],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )


def _hash_campaign_files() -> dict[str, str]:
    """Hash all campaign location files (md5 of bytes)."""
    return {
        f.name: hashlib.md5(f.read_bytes()).hexdigest()
        for f in sorted(_CAMPAIGN_DIR.glob("*.json"))
    }


def test_migrator_exists():
    """Migrator script exists at expected path."""
    assert _MIGRATOR.exists(), f"migrator not found: {_MIGRATOR}"


def test_dry_run_reports_conflicts():
    """Dry-run for Open_road: 3 conflicts, 3 orphaned, 0 actions."""
    result = _run_migrator("--campaign", "Open_road")
    assert result.returncode == 0, f"migrator failed: {result.stderr}"
    assert "total conflicts: 3" in result.stdout, (
        f"expected 3 conflicts, got stdout:\n{result.stdout}"
    )
    assert "total orphaned template edits: 3" in result.stdout
    assert "total actions: 0 (dry-run)" in result.stdout


def test_dry_run_no_file_changes():
    """Dry-run must not modify any campaign files."""
    before = _hash_campaign_files()
    _run_migrator("--campaign", "Open_road")
    after = _hash_campaign_files()
    assert before == after, (
        f"dry-run modified files:\nbefore: {before}\nafter: {after}"
    )


def test_idempotent():
    """Running dry-run twice produces identical output."""
    r1 = _run_migrator("--campaign", "Open_road")
    r2 = _run_migrator("--campaign", "Open_road")
    assert r1.stdout == r2.stdout, (
        "migrator not idempotent: different output on repeated dry-run"
    )


def test_apply_noop_for_shared_files():
    """--apply (without --apply-templates-edits) doesn't modify shared files."""
    before = _hash_campaign_files()
    result = _run_migrator("--campaign", "Open_road", "--apply")
    assert result.returncode == 0, f"--apply failed: {result.stderr}"
    after = _hash_campaign_files()
    assert before == after, (
        f"--apply modified shared files (should be no-op):\n"
        f"before: {before}\nafter: {after}"
    )

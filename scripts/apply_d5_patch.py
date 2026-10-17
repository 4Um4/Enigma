#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D-5 patch applyer — применяет БЫЛО/СТАЛО к behavior_mask_closure_test.py.

Запуск (из корня репо, на машине Мастера):
    python scripts/apply_d5_patch.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path.cwd()
TARGET = REPO_ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX" / "scenarios" / "behavior_mask_closure_test.py"
BACKUP = TARGET.with_suffix(".py.bak_d5")

OLD_BLOCK = '''        # AC-2 ур.3: скоры по тикам; rel-слой — вход-траектория (форма снимка
        # не предполагается — пишем как есть, анализ данными)
        "scores_per_tick": (etap.scores_per_tick() if etap is not None else []),
        "rel_goran_per_tick": [
            (snap.get(_NPC) if isinstance(snap, dict) else None)
            for snap in (getattr(result, "rel_captures", None) or [])
        ],'''

NEW_BLOCK = '''        # AC-2 ур.3: скоры по тикам; rel-слой — вход-траектория.
        # D-5 fix (E-BM1 B'): V2RelationshipBackend.get_all() возвращает directed-ключи
        # формата "source→target" (не {source: {target: ...}}). Старое чтение
        # snap.get(_NPC) всегда возвращало None — capture-слепота, не дефект системы.
        # Новый формат: per-tick dict с двумя directed-парами + schema_version.
        # None для пары = пара отсутствует в V2 RAM (Vacuum); не путать с нулём.
        # Исторические артефакты B' (result_raw_off/on.json) сохраняют старый формат.
        "scores_per_tick": (etap.scores_per_tick() if etap is not None else []),
        "rel_goran_schema_version": 2,
        "rel_goran_per_tick": [
            {
                "goran_to_player": (
                    dict(snap[f"{_NPC}→player"])
                    if isinstance(snap, dict) and isinstance(snap.get(f"{_NPC}→player"), dict)
                    else None
                ),
                "player_to_goran": (
                    dict(snap[f"player→{_NPC}"])
                    if isinstance(snap, dict) and isinstance(snap.get(f"player→{_NPC}"), dict)
                    else None
                ),
            }
            for snap in (getattr(result, "rel_captures", None) or [])
        ],'''


def main() -> int:
    print(f"[INFO] target: {TARGET}")
    print(f"[INFO] target exists: {TARGET.exists()}")

    if not TARGET.exists():
        print("[FAIL] target file not found", file=sys.stderr)
        return 2

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"[OK] backup created: {BACKUP.name} ({BACKUP.stat().st_size} bytes)")
    else:
        print(f"[WARN] backup already exists: {BACKUP.name} (not overwritten)")

    content = TARGET.read_text(encoding="utf-8")

    occurrences = content.count(OLD_BLOCK)
    print(f"[INFO] OLD block occurrences: {occurrences} (expected: 1)")

    if occurrences == 0:
        if "rel_goran_schema_version" in content:
            print("[WARN] OLD block not found, but NEW marker present — patch already applied?")
            return 0
        print("[FAIL] OLD block not found and NEW marker not present", file=sys.stderr)
        return 1

    if occurrences > 1:
        print(f"[FAIL] OLD block found {occurrences} times — not unique", file=sys.stderr)
        return 1

    new_content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)
    TARGET.write_text(new_content, encoding="utf-8")
    print(f"[OK] patch applied: {TARGET.name}")

    new_content_check = TARGET.read_text(encoding="utf-8")
    new_marker_count = new_content_check.count("rel_goran_schema_version")
    old_marker_count = new_content_check.count("snap.get(_NPC) if isinstance(snap, dict)")
    print(f"[INFO] NEW marker 'rel_goran_schema_version': {new_marker_count} (expected: 1)")
    print(f"[INFO] OLD marker 'snap.get(_NPC)...': {old_marker_count} (expected: 0)")

    if new_marker_count != 1 or old_marker_count != 0:
        print("[FAIL] marker counts mismatch", file=sys.stderr)
        return 1

    print("[INFO] running py_compile...")
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TARGET)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[FAIL] py_compile error:\n{result.stderr}", file=sys.stderr)
        return 1
    print("[OK] syntax valid")

    print()
    print("=== D-5 PATCH APPLIED SUCCESSFULLY ===")
    print(f"  target: {TARGET}")
    print(f"  backup: {BACKUP}")
    print(f"  size: {TARGET.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
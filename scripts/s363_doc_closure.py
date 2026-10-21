"""S363 doc-closure: append MUTATIONS.md line (precedent s365_finish.py)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
mut_path = ROOT / "docs" / "MUTATIONS.md"
text = mut_path.read_text(encoding="utf-8")

S363 = (
    "- **S363** INV-SC-1-8 blacksmith_orm spatial — статус после археологии: UNVERIFIED → не воспроизведён в проверенных сценариях. "
    "Источник первичного дефекта не найден (не существовал как `INV-SC-1-8` в коде/IPT/MUTATIONS/audits; closest = probe name `INV-SC-1-8-SPATIAL-COHERENCE` в `backend/app/services/probes/probes/spatial_coherence_probe.py:11`). "
    "SC-4 (torn-state boundary-dwell) устранён в историческом коммите `cb81ce83` (Sep 18, 2026). "
    "SC-1..SC-5 проверены через `SpatialCoherenceProbe` (wire-up: `tick_orchestrator.py:1098-1102` post-commit ProbeRunner) на 30 тиках с пресетом `golden_social_z0` (6 NPC tavern, включает blacksmith_orm) — 0 failures (артефакт `reports/lab_r004_spatial_coherence.json`: ticks_run=53, total_sc_failures=0, dashboard.total_failed_probes=0). "
    "SC-6..SC-8 не реализованы в коде probe — остаются непроверенными. "
    "Статус: ограниченный результат проверки, не «исторический баг исправлен» (вердикт Мастера п.5: «Если старый тест не найден, а новый probe проходит, статус — не воспроизведён в проверенных сценариях, а не исторический баг исправлен»). "
    "Не патчил пространственную логику; не объявлял исправленным сессией А; причинная связь CCH-4 (хроника blacksmith_orm) с предполагаемым дефектом не установлена. "
    "Прецедент: lab_r003 (ExperimentRunner + ScenarioPlayer + per-tick captures). "
    "Гейты: ruff 1 auto-fixable (split imports) → 0; IPT 53/0/0 CRITICAL=0. "
    "· ✅ · без ADR (read-only archaeology + targeted probe); артефакты `backend/tests/sandbox/lab_r004_spatial_coherence.py` + `reports/lab_r004_spatial_coherence.json`"
)

if "S363" in text:
    print("ABORT: S363 already in MUTATIONS")
else:
    # Append before METa-счётчик section if any, else simple append
    # Прецедент s365_finish.py: ищем последний "- **SXXX**" и добавляем после
    lines = text.splitlines(keepends=True)
    insert_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("- **S3"):
            insert_idx = i + 1
            break
    new_lines = lines[:insert_idx] + [S363 + "\n"] + lines[insert_idx:]
    mut_path.write_text("".join(new_lines), encoding="utf-8")
    print(f"APPENDED S363 at line {insert_idx + 1}")
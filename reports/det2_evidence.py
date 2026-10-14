from __future__ import annotations

# reports/det2_evidence.py
"""
DET-2, приёмка п.3 вердикта: машинно-проверяемое свидетельство 1/1 —
живой прогон 20 тиков production-пути; счётчик _state_hash_ticks обязан
равняться числу тиков. Артефакт: reports/det2_evidence.json. Одноразовый;
после коммита закрытия DET-2 удалить.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    print("[DET-2/приёмка-3] Свидетельство 1/1 (живой прогон)")
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    loop = build_game_loop(Path(settings.data_dir))
    orch = loop._tick_orch  # game_loop.py:193

    N = 20
    before = getattr(orch, "_state_hash_ticks", 0)
    for _ in range(N):
        loop.idle_tick("tavern_silver_wolf")
    after = getattr(orch, "_state_hash_ticks", 0)

    evidence = {
        "ticks": N,
        "hash_ticks_before": before,
        "hash_ticks_after": after,
        "delta": after - before,
        "ratio_1of1": (after - before) == N,
        "note": "probe INV-TEMPORAL-ISOLATION исполнен на каждом тике; 1/1 — частота, НЕ полнота инварианта (вердикт п.3)",
    }
    out = ROOT / "reports" / "det2_evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    if not evidence["ratio_1of1"]:
        print("[FAIL] Счётчик не 1/1 — СТОП, разбор")
        return 1
    print("[OK] Свидетельство 1/1 зафиксировано:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

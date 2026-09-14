"""
path: backend/tests/calibration_lab/e1_intent_liveness_check.py
[GC-I01-E1] Acceptance: intent projection liveness on golden run.
(1) NPC with intent per tick [WAS=0, S213 verdict]; (2) max intent_duration
[inertia: pre-fix every hydration = intent=None -> _apply_intent saw a
"change" -> duration stuck at 0; >1 = inertia alive].
Run: cd backend; python tests/calibration_lab/e1_intent_liveness_check.py [ticks]; cd ..
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    result = ExperimentRunner().run(
        ExperimentConfig(
            preset_path=str(
                _REPO_ROOT / "config" / "calibration" / "test_presets" / "enigma_golden.yaml"
            ),
            duration_ticks=ticks,
        )
    )
    per_tick = [
        sum(1 for n in tick if n.get("intent") is not None)
        for tick in result.npc_captures
    ]
    total = sum(per_tick)
    max_dur = 0
    dur_owner = ""
    for tick in result.npc_captures:
        for n in tick:
            d = n.get("intent_duration")
            if isinstance(d, int) and d > max_dur:
                max_dur = d
                dur_owner = n.get("npc_id") or n.get("id") or "?"
    print(f"[E1-CHECK] ticks={len(result.npc_captures)}")
    print(f"[E1-CHECK] NPC with intent, first 20 ticks: {per_tick[:20]}")
    print(f"[E1-CHECK] total intents={total}  [WAS=0, S213 verdict]")
    print(f"[E1-CHECK] max intent_duration={max_dur} (owner={dur_owner})  [inertia alive if >1]")
    print(f"[E1-CHECK] STAGE-1 VERDICT: {'GREEN' if total > 0 and max_dur > 1 else 'RED'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H1b-mini2 тест нейтральности.

Доказывает: H1b-mini2 (строковые поля) НЕ изменяет base = sum(...).
Сравнивает _score_components с H1b-mini2 и без него на одинаковом входе.

Запуск:
    python backend/tests/sandbox/SUPERBOX/scenarios/_h1b2_neutrality_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

# Bootstrap
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_BACKEND = _HERE.parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models.npc_state import Intent


def make_mock_state():
    state = MagicMock()
    state.npc_id = "test_npc"
    state.intent = None
    state.behavior_mask = MagicMock()
    state.behavior_mask.mask = "fake_submission"
    state.behavior_mask.intensity = 0.7
    state.emotion = None
    state.relationship_cache = {"player": {"fear": 70.0, "trust": -60.0, "recent_pressure": 0.0}}
    state.perceptual_kernel = None
    state.narrative_cache = []
    return state


def make_mock_event():
    event = MagicMock()
    event.event_type = "idle"
    event.payload = {}
    event.witness_count = 0
    event.distance = 3.0
    event.success = True
    event.visible_threat_markers = []
    event.scene_flags = set()
    event.target_id = None
    return event


def call_score_components(dh, state, event):
    personality = MagicMock()
    opportunity = MagicMock()
    opportunity.unlocked_intents = []
    opportunity.score = 0.0
    active_traits = {}
    effective_drives = MagicMock()
    effective_drives.values = {"fear": 0.4, "control": 0.3}

    return dh._score_components(
        Intent.ATTACK.value, state, personality, event, opportunity,
        active_traits, decision_ctx=None, effective_drives=effective_drives,
    )


def main() -> int:
    print("=== H1b-mini2 Neutrality Test ===")
    print()

    # === Шаг 1: _score_components БЕЗ патча (оригинал) ===
    print("--- Step 1: _score_components WITHOUT patch (original) ---")
    from app.services.npc.decision_hub import DecisionHub
    dh_orig = DecisionHub(seed=42)
    dh_orig._rel_store = None
    dh_orig._campaign_id = "test"

    state1 = make_mock_state()
    event1 = make_mock_event()
    comps_orig = call_score_components(dh_orig, state1, event1)

    base_orig = sum(v for k, v in comps_orig.items() if isinstance(v, (int, float)))
    print(f"  original components keys: {list(comps_orig.keys())}")
    print(f"  original base (sum of numerics): {base_orig}")
    print()

    # === Шаг 2: Применить H1b-mini патч ===
    print("--- Step 2: apply H1b-mini ON patch ---")
    import bm_bprime_framework as bpf
    bpf.install_h1b_mini_capture("on")
    print()

    # === Шаг 3: _score_components С патчем ===
    print("--- Step 3: _score_components WITH patch ---")
    del sys.modules["app.services.npc.decision_hub"]
    from app.services.npc.decision_hub import DecisionHub as DecisionHubPatched
    dh_patched = DecisionHubPatched(seed=42)
    dh_patched._rel_store = None
    dh_patched._campaign_id = "test"

    state2 = make_mock_state()
    event2 = make_mock_event()
    comps_patched = call_score_components(dh_patched, state2, event2)

    base_patched = sum(v for k, v in comps_patched.items() if isinstance(v, (int, float)))
    print(f"  patched components keys: {list(comps_patched.keys())}")
    print(f"  patched base (sum of numerics): {base_patched}")
    print()

    # === Шаг 4: Сравнить base ===
    print("--- Step 4: compare base ---")
    print(f"  original base:  {base_orig}")
    print(f"  patched base:   {base_patched}")
    diff = abs(base_orig - base_patched)
    print(f"  |diff|:         {diff}")

    if diff < 1e-9:
        print("  PASS: base identical (H1b-mini2 is neutral)")
    else:
        print("  FAIL: base differs — H1b-mini2 contaminates computation!")
        return 1

    print()

    # === Шаг 5: Проверить, что _h1b2_* поля — строки ===
    print("--- Step 5: verify _h1b2_* fields are strings ---")
    h1b2_fields = [k for k in comps_patched if k.startswith("_h1b2")]
    all_strings = True
    for k in h1b2_fields:
        v = comps_patched[k]
        is_str = isinstance(v, str) or v is None
        print(f"  {k}: {v!r} ({type(v).__name__}) - {'string/None (OK)' if is_str else 'NUMERIC (BAD!)'}")
        if not is_str:
            all_strings = False

    if all_strings:
        print("  PASS: all _h1b2_* fields are strings or None")
    else:
        print("  FAIL: some _h1b2_* fields are numeric!")
        return 1

    print()

    # === Шаг 6: Проверить игровые компоненты ===
    print("--- Step 6: verify game components unchanged ---")
    game_keys = ["drive", "emotion", "relationship", "risk_penalty", "trait", "opportunity", "social", "redirect"]
    all_match = True
    for k in game_keys:
        v_o = comps_orig.get(k)
        v_p = comps_patched.get(k)
        match = v_o == v_p
        print(f"  {k}: orig={v_o} patched={v_p} - {'MATCH' if match else 'DIFFER!'}")
        if not match:
            all_match = False

    if all_match:
        print("  PASS: all game components identical")
    else:
        print("  FAIL: game components differ!")
        return 1

    print()
    print("=== ALL NEUTRALITY CHECKS PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
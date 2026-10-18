#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H1b-mini минимальная проверка захвата components_trace.

Вызывает пропатченный DecisionHub._score_all с mock-данными и проверяет,
что возвращаемый components_trace содержит _h1b_* поля.

Запуск:
    python backend/tests/sandbox/SUPERBOX/scenarios/_h1b_mini_capture_test.py
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

import bm_bprime_framework as bpf
from app.models.npc_state import Intent, NPCState, NPCStateAdapter


def test_h1b_capture_in_components_trace():
    """Минимальный тест: пропатченный _score_all возвращает _h1b_* поля."""
    print("=== H1b-mini capture test ===")
    print()

    # 1. Применить ON patch (ДО импорта DecisionHub — патч ложится в namespace модуля)
    print("--- Step 1: apply ON patch ---")
    bpf.install_h1b_mini_capture("on")
    print("  ON patch applied")
    print()

    # 2. Импортировать DecisionHub ПОСЛЕ патча (получить пропатченный класс)
    print("--- Step 2: import DecisionHub (after patch) ---")
    from app.services.npc.decision_hub import DecisionHub
    print(f"  DecisionHub imported: {DecisionHub}")
    print()

    # 3. Проверить co_consts — патч в коде функции?
    print("--- Step 3: check func.__code__.co_consts ---")
    consts = DecisionHub._score_all.__code__.co_consts
    has_h1b_const = any("_h1b_base_before" in str(c) for c in consts)
    has_enabled_const = any("_h1b_mask_application_enabled" in str(c) for c in consts)
    print(f"  _h1b_base_before in co_consts: {has_h1b_const}")
    print(f"  _h1b_mask_application_enabled in co_consts: {has_enabled_const}")
    if has_h1b_const and has_enabled_const:
        print("  PASS: patch constants in code object")
    else:
        print("  FAIL: patch constants not found")
        return 1
    print()

    # 4. Создать минимальный DecisionHub и mock-state
    print("--- Step 4: create DecisionHub + mock state ---")
    dh = DecisionHub(seed=42)
    # _score_components читает self._rel_store (нормально устанавливается в compute())
    dh._rel_store = None
    dh._campaign_id = "test"

    # Monkey-patch _score_components: вернуть простой dict, изолировать от сложной логики.
    # H1b-mini тестирует захват base до/после mask, а не _score_components.
    dh._score_components = lambda *a, **k: {"drive": -1.5, "risk": -0.2}
    print("  _score_components monkey-patched to return {'drive': -1.5, 'risk': -0.2}")

    # Mock state с behavior_mask = FAKE_SUBMISSION
    state = MagicMock()
    state.npc_id = "test_npc"
    state.intent = None  # no inertia
    state.behavior_mask = MagicMock()
    state.behavior_mask.mask = "fake_submission"
    state.behavior_mask.intensity = 0.7

    # Mock other args (не используются из-за monkey-patch, но нужны как позиционные)
    personality = MagicMock()
    event = MagicMock()
    possible = [Intent.ATTACK.value, Intent.FLEE.value, Intent.IDLE.value]
    opportunity = MagicMock()
    opportunity.unlocked_intents = []
    active_traits = {}

    print(f"  state.npc_id={state.npc_id}")
    print(f"  state.behavior_mask.mask={state.behavior_mask.mask}")
    print(f"  possible={possible}")
    print()

    # 5. Вызвать _score_all
    print("--- Step 5: call _score_all ---")
    try:
        scores, components_trace = dh._score_all(
            state, personality, event, possible, opportunity,
            active_traits, decision_ctx=None, effective_drives=None,
        )
        print(f"  scores keys: {list(scores.keys())}")
        print(f"  components_trace keys: {list(components_trace.keys())}")
        print()
    except Exception as e:
        print(f"  FAIL: _score_all raised: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 6. Проверить _h1b_* поля в components_trace
    print("--- Step 6: check _h1b_* fields in components_trace ---")
    attack_comps = components_trace.get("attack", {})
    print(f"  attack components keys: {list(attack_comps.keys())}")

    required_fields = [
        "_h1b_base_before_mask",
        "_h1b_mask_mod",
        "_h1b_base_after_mask",
        "_h1b_mask_application_enabled",
    ]
    all_present = True
    for field in required_fields:
        present = field in attack_comps
        value = attack_comps.get(field)
        print(f"  {field}: present={present}, value={value}")
        if not present:
            all_present = False

    print()
    if all_present:
        print("=== PASS: all _h1b_* fields captured in components_trace ===")
        print()
        print("--- Verification ---")
        print(f"  _h1b_mask_mod = {attack_comps['_h1b_mask_mod']}")
        print(f"  _h1b_base_before_mask = {attack_comps['_h1b_base_before_mask']}")
        print(f"  _h1b_base_after_mask = {attack_comps['_h1b_base_after_mask']}")
        print(f"  _h1b_mask_application_enabled = {attack_comps['_h1b_mask_application_enabled']}")

        # Проверить: ON mode → mask_application_enabled should be True
        if attack_comps["_h1b_mask_application_enabled"] is True:
            print("  PASS: mask_application_enabled=True (ON mode)")
        else:
            print(f"  FAIL: mask_application_enabled should be True for ON, got {attack_comps['_h1b_mask_application_enabled']}")
            return 1

        # Проверить: base_after = base_before * mask_mod (если base_before != 0)
        bb = attack_comps["_h1b_base_before_mask"]
        ba = attack_comps["_h1b_base_after_mask"]
        mm = attack_comps["_h1b_mask_mod"]
        if bb != 0:
            expected = round(bb * mm, 4)
            if abs(ba - expected) < 0.001:
                print(f"  PASS: base_after ({ba}) = base_before ({bb}) * mask_mod ({mm}) = {expected}")
            else:
                print(f"  FAIL: base_after ({ba}) != base_before ({bb}) * mask_mod ({mm}) = {expected}")
                return 1
        else:
            print("  NOTE: base_before=0, cannot verify multiplication (but mask_application_enabled=True confirms application)")

        return 0
    else:
        print("=== FAIL: not all _h1b_* fields captured ===")
        return 1


def main() -> int:
    try:
        return test_h1b_capture_in_components_trace()
    finally:
        # Восстановить оригинальный _score_all (перезагрузить модуль)
        print()
        print("--- Cleanup: reload decision_hub module ---")
        import importlib
        import app.services.npc.decision_hub
        importlib.reload(app.services.npc.decision_hub)
        print("  module reloaded (patch cleared)")


if __name__ == "__main__":
    sys.exit(main())
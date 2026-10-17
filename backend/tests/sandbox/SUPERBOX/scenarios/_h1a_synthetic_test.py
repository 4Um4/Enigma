#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H1a синтетические тесты — 6 сценариев для _ExecuteTap.

Запуск (из корня репо):
    python backend/tests/sandbox/SUPERBOX/scenarios/_h1a_synthetic_test.py

Реальная сигнатура _score_all:
    _score_all(self, state, personality, event, possible, opportunity,
               active_traits=None, decision_ctx=None, effective_drives=None)
    -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]

Все моки передают обязательные позиционные аргументы. Wrapper не зависит
от их типов — он только читает state.npc_id из args[0] и stash-ит результат.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Bootstrap: добавить scenarios/ и backend/ в sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_BACKEND = _HERE.parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from behavior_mask_closure_test import _ExecuteTap


# === Mock objects ===

class MockState:
    """Мок NPCState с минимальным набором полей для _score_all.

    Реальный _score_all вызывает self._intent_inertia(state) и читает
    state.intent, state.npc_id. Остальные поля не используются в самом
    методе _score_all (но используются в _score_components, который мы
    не вызываем — поведение подменяется wrapper-ом на мок-функцию).
    """
    def __init__(self, npc_id: str):
        self.npc_id = npc_id
        self.intent = None  # _intent_inertia читает state.intent

def _make_decision_hub_with_behavior(behavior_fn):
    """Создаёт НАСТОЯЩИЙ DecisionHub instance, но подменяет его _score_all
    на behavior_fn. Это позволяет wrapper-у _ExecuteTap перехватить вызов,
    а behavior_fn — вернуть предсказуемый (scores, components_trace).

    DecisionHub.__init__ требует rng или seed. Используем seed=42 для детерминизма.
    """
    from app.services.npc.decision_hub import DecisionHub
    dh = DecisionHub(seed=42)
    # Подменяем _score_all на уровне instance (не класса!) —
    # wrapper _ExecuteTap патчит _score_all на уровне класса, поэтому
    # instance-override имеет приоритет (Python method resolution order).
    # НО: wrapper ставится на класс, а instance-атрибут перекрывает класс.
    # Поэтому behavior_fn будет вызван ДО wrapper-а.
    #
    # Альтернатива: не подменять _score_all на instance, а положиться на то,
    # что wrapper на классе вызовет _orig_score_all (реальный), который
    # обратится к self._intent_inertia. Чтобы это сработало, MockState должен
    # иметь все поля, которые читает реальный _score_all + _score_components.
    #
    # Проще: создать реальный DecisionHub и реальный state с нужными полями,
    # а behavior_fn подменить через monkey-patch на instance.
    dh._score_all = behavior_fn  # instance override
    return dh

class MockTickOrchestrator:
    def __init__(self, execute_behavior):
        self._execute_behavior = execute_behavior
        self.execute = self._execute_behavior


class MockGameLoop:
    def __init__(self, orch):
        self._tick_orch = orch


# === Установка DecisionHub._score_all (мок) ===
from app.services.npc import decision_hub as dh_module

_orig_score_all_real = dh_module.DecisionHub._score_all


class MockState:
    """Мок NPCState с npc_id (всё, что читает wrapper из args[0])."""
    def __init__(self, npc_id: str):
        self.npc_id = npc_id


class _AnyObject:
    """Универсальный заглушка-объект для self в _score_all.

    Wrapper _ExecuteTap читает только args[0].npc_id (state) и вызывает
    tap._orig_score_all(dh_self, *a, **k). Если tap._orig_score_all
    подменён на мок-функцию (см. ниже), dh_self не используется.
    """
    pass


def _call_score_all_on_mock(npc_id: str, tap, behavior):
    """Вызывает DecisionHub._score_all (через wrapper) с mock-аргументами.

    КЛЮЧЕВОЙ ТРЮК: временно подменяем tap._orig_score_all на behavior,
    вызываем _score_all (через wrapper на классе), восстанавливаем оригинал.
    Без восстановления detach() запишет behavior как 'оригинал' и сломает
    восстановление DecisionHub._score_all.

    dh_self — _AnyObject() (не используется behavior-функцией).
    state — MockState(npc_id) (wrapper читает state.npc_id).
    Остальные аргументы — mock-строки (wrapper их не валидирует).
    """
    real_orig = tap._orig_score_all
    tap._orig_score_all = behavior
    try:
        state = MockState(npc_id)
        dh_self = _AnyObject()
        dh_module.DecisionHub._score_all(
            dh_self, state,
            "personality_mock",
            "event_mock",
            ["attack", "flee"],
            "opportunity_mock",
        )
    finally:
        tap._orig_score_all = real_orig


def main() -> int:
    print("=== H1a synthetic tests: 6 scenarios ===")
    print()

    # === Сценарий 1: целевой NPC вызван ===
    print("=== Scenario 1: target NPC called ===")

    def behavior_1(dh_self, *a, **k):
        return (
            {"attack": -1.5, "flee": 0.6},
            {
                "attack": {"base": -1.5, "mask": 0.155, "noise": 0.01},
                "flee": {"base": 0.6, "mask": 0.155, "noise": -0.003},
            },
        )

    def execute_1():
        _call_score_all_on_mock("merchant_goran", tap1, behavior_1)
        return "tick_result_1"

    orch1 = MockTickOrchestrator(execute_1)
    gl1 = MockGameLoop(orch1)
    tap1 = _ExecuteTap("merchant_goran")
    tap1.attach(gl1)
    try:
        r = orch1.execute()
        print(f"  execute returned: {r}")
        print(f"  results length: {len(tap1.results)}")
        cpt = tap1.components_per_tick()
        print(f"  components_per_tick length: {len(cpt)}")
        print(f"  components_per_tick[0] is None: {cpt[0] is None}")
        if cpt[0] is not None:
            print(f"  components_per_tick[0] keys: {list(cpt[0].keys())}")
            attack_comps = cpt[0].get("attack")
            print(f"  attack components: {attack_comps}")
        print(f"  integrity_violations: {tap1.integrity_violations()}")
        assert len(tap1.results) == 1, f"expected 1 result, got {len(tap1.results)}"
        assert len(cpt) == 1, f"expected 1 components entry, got {len(cpt)}"
        assert cpt[0] is not None, "expected dict, got None"
        assert "attack" in cpt[0], "attack missing"
        assert cpt[0]["attack"]["mask"] == 0.155, f"mask mismatch: {cpt[0]['attack']['mask']}"
        print("  PASS: Scenario 1")
    finally:
        tap1.detach(gl1)
    print()

    # === Сценарий 2: целевой NPC НЕ вызван (другой NPC) ===
    print("=== Scenario 2: target NPC NOT called (different NPC) ===")

    def behavior_2(dh_self, *a, **k):
        return ({"attack": -1.0}, {"attack": {"base": -1.0}})

    def execute_2():
        _call_score_all_on_mock("guard_borko", tap2, behavior_2)  # НЕ целевой
        return "tick_result_2"

    orch2 = MockTickOrchestrator(execute_2)
    gl2 = MockGameLoop(orch2)
    tap2 = _ExecuteTap("merchant_goran")
    tap2.attach(gl2)
    try:
        r = orch2.execute()
        cpt = tap2.components_per_tick()
        print(f"  results length: {len(tap2.results)}")
        print(f"  components_per_tick length: {len(cpt)}")
        print(f"  components_per_tick[0] is None: {cpt[0] is None}")
        assert len(tap2.results) == 1
        assert len(cpt) == 1
        assert cpt[0] is None, "expected None for non-target NPC"
        print("  PASS: Scenario 2")
    finally:
        tap2.detach(gl2)
    print()

    # === Сценарий 3: двойной вызов _score_all за один execute ===
    print("=== Scenario 3: double _score_all in one execute ===")
    call_count = [0]

    def behavior_3(dh_self, *a, **k):
        call_count[0] += 1
        return ({"attack": -1.5}, {"attack": {"base": -1.5, "call": call_count[0]}})

    def execute_3():
        _call_score_all_on_mock("merchant_goran", tap3, behavior_3)  # первый — заполнит слот
        _call_score_all_on_mock("merchant_goran", tap3, behavior_3)  # второй — violation
        return "tick_result_3"

    orch3 = MockTickOrchestrator(execute_3)
    gl3 = MockGameLoop(orch3)
    tap3 = _ExecuteTap("merchant_goran")
    tap3.attach(gl3)
    try:
        r = orch3.execute()
        cpt = tap3.components_per_tick()
        iv = tap3.integrity_violations()
        print(f"  results length: {len(tap3.results)}")
        print(f"  components_per_tick length: {len(cpt)}")
        print(f"  components_per_tick[0] is None: {cpt[0] is None}")
        print(f"  integrity_violations: {iv}")
        assert len(cpt) == 1
        assert cpt[0] is not None, "first call should fill slot"
        assert len(iv) == 1, f"expected 1 violation, got {len(iv)}"
        assert iv[0]["reason"] == "double_score_all_in_one_execute"
        assert iv[0]["tick_index"] == 0
        print("  PASS: Scenario 3")
    finally:
        tap3.detach(gl3)
    print()

    # === Сценарий 4: исключение внутри _score_all ===
    print("=== Scenario 4: exception inside _score_all ===")

    def behavior_4(dh_self, *a, **k):
        raise RuntimeError("score_all failed")

    def execute_4():
        try:
            _call_score_all_on_mock("merchant_goran", tap4, behavior_4)
        except RuntimeError:
            pass  # проглатываем, чтобы execute завершился
        return "tick_result_4"

    orch4 = MockTickOrchestrator(execute_4)
    gl4 = MockGameLoop(orch4)
    tap4 = _ExecuteTap("merchant_goran")
    tap4.attach(gl4)
    try:
        r = orch4.execute()
        cpt = tap4.components_per_tick()
        print(f"  results length: {len(tap4.results)}")
        print(f"  components_per_tick length: {len(cpt)}")
        print(f"  components_per_tick[0] is None: {cpt[0] is None}")
        assert len(tap4.results) == 1
        assert len(cpt) == 1
        assert cpt[0] is None, "expected None (score_all raised, slot not filled)"
        print("  PASS: Scenario 4")
    finally:
        tap4.detach(gl4)
    print()

    # === Сценарий 5: исключение внутри execute() ===
    print("=== Scenario 5: exception inside execute() ===")

    def execute_5():
        raise RuntimeError("execute failed")

    orch5 = MockTickOrchestrator(execute_5)
    gl5 = MockGameLoop(orch5)
    tap5 = _ExecuteTap("merchant_goran")
    tap5.attach(gl5)
    try:
        try:
            orch5.execute()
            print("  FAIL: expected RuntimeError")
            return 1
        except RuntimeError as e:
            print(f"  exception caught: {e}")
        cpt = tap5.components_per_tick()
        print(f"  results length: {len(tap5.results)}")
        print(f"  components_per_tick length: {len(cpt)}")
        print(f"  components_per_tick[0] is None: {cpt[0] is None}")
        assert len(tap5.results) == 0, f"expected 0 results, got {len(tap5.results)}"
        assert len(cpt) == 1, f"expected 1 slot, got {len(cpt)}"
        assert cpt[0] is None, "expected None (execute raised)"
        print("  PASS: Scenario 5")
    finally:
        tap5.detach(gl5)
    print()

    # === Сценарий 6: восстановление DecisionHub._score_all после detach ===
    print("=== Scenario 6: DecisionHub._score_all restored after detach ===")
    current_after_detach = dh_module.DecisionHub._score_all
    is_original = current_after_detach is _orig_score_all_real
    print(f"  DecisionHub._score_all is original: {is_original}")
    print(f"  original id: {id(_orig_score_all_real)}")
    print(f"  current id:  {id(current_after_detach)}")
    assert is_original, "DecisionHub._score_all not restored after detach"
    print("  PASS: Scenario 6")
    print()

    print("=== ALL 6 SCENARIOS PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

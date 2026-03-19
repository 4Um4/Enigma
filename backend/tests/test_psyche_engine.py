# -*- coding: utf-8 -*-
"""Тесты PsycheEngine"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.npc.psyche_engine import (
    apply_stress, recover_stress, resolve_coercion,
    check_loyalty_break, get_behavior_hint
)

def make_npc(willpower=60, stress=20, breakpoint=80, state="free"):
    return {
        "name": "Тест",
        "drives": {"control": 0.4, "significance": 0.2, "fear": 0.3, "desire": 0.1},
        "psyche": {
            "willpower": willpower, "stress": stress, "breakpoint": breakpoint,
            "loyalty_true": 50, "loyalty_fake": 50,
            "state": state, "trauma_flags": []
        },
        "social_stats": {"trust": 0.5, "fear_of_player": 0.1},
        "routine": {"current": "working"},
    }

def test_stress_normal():
    npc = make_npc(stress=20)
    r = apply_stress(npc, 30)
    assert npc["psyche"]["stress"] == 50
    assert r["state_changed"] == False
    print("✅ apply_stress (нормальный стресс)")

def test_stress_breaks_will():
    npc = make_npc(willpower=60, stress=70, breakpoint=80)
    r = apply_stress(npc, 20)  # 70+20=90 > 80
    assert npc["psyche"]["state"] == "broken"
    assert r["state_changed"] == True
    print("✅ apply_stress (breakpoint → state=broken)")

def test_stress_capped_at_100():
    npc = make_npc(stress=90)
    apply_stress(npc, 50)
    assert npc["psyche"]["stress"] == 100
    print("✅ apply_stress (capped at 100)")

def test_recover_stress():
    npc = make_npc(stress=80)
    recover_stress(npc, ticks_safe=2)
    assert npc["psyche"]["stress"] <= 70
    print("✅ recover_stress")

def test_coercion_threat_submit():
    npc = make_npc(willpower=30, stress=50)
    r = resolve_coercion(npc, "threat", intensity=60)
    assert r["outcome"] in ("submit", "broken")
    print(f"✅ resolve_coercion (threat) → {r['outcome']}")

def test_coercion_resist():
    npc = make_npc(willpower=90, stress=5)
    r = resolve_coercion(npc, "threat", intensity=20)
    assert r["outcome"] == "resist"
    print("✅ resolve_coercion (высокая воля → resist)")

def test_loyalty_break():
    npc = make_npc(state="broken")
    npc["psyche"]["loyalty_true"] = -70
    # Запускаем несколько раз — вероятностная функция
    results = [check_loyalty_break(npc) for _ in range(20)]
    assert any(results), "При loyalty_true=-70 должно быть хоть одно предательство из 20"
    print("✅ check_loyalty_break (низкая лояльность → вероятность предательства)")

def test_behavior_hint_broken():
    npc = make_npc(state="broken", stress=90)
    hint = get_behavior_hint(npc)
    assert len(hint) > 5
    print(f"✅ get_behavior_hint (broken): {hint}")

if __name__ == "__main__":
    test_stress_normal()
    test_stress_breaks_will()
    test_stress_capped_at_100()
    test_recover_stress()
    test_coercion_threat_submit()
    test_coercion_resist()
    test_loyalty_break()
    test_behavior_hint_broken()
    print("\n✅✅✅ Все тесты PsycheEngine прошли!")
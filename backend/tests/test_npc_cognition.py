# -*- coding: utf-8 -*-
"""Тесты NPCCognition"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.npc.npc_cognition import (
    normalize_drives, get_dominant_drive, get_speech_style,
    process_player_action, build_npc_prompt, get_inner_thought,
)

def make_npc():
    return {
        "id": "test_npc",
        "name": "Тестовый NPC",
        "tier": "minor",
        "status_profile": {"freedom": 50, "wealth": 20, "power": 10, "title": "Стражник"},
        "visible_markers": ["armor"],
        "drives": {"control": 0.6, "significance": 0.2, "fear": 0.15, "desire": 0.05},
        "psyche": {"willpower": 60, "stress": 20, "breakpoint": 80,
                   "loyalty_true": 50, "loyalty_fake": 50, "state": "free", "trauma_flags": []},
        "social_stats": {"trust": 0.5, "affection": 0.4, "fear_of_player": 0.1, "debt": 0},
        "memory_trace": [],
        "location": "city_gate",
        "abilities": {"strength": 12, "dexterity": 10, "constitution": 11,
                      "intelligence": 9, "wisdom": 10, "charisma": 9},
    }

def test_normalize():
    d = {"control": 3, "significance": 1, "fear": 0, "desire": 0}
    n = normalize_drives(d)
    assert abs(sum(n.values()) - 1.0) < 0.001, "Сумма должна быть 1.0"
    print("✅ normalize_drives")

def test_dominant():
    d = {"control": 0.6, "significance": 0.2, "fear": 0.1, "desire": 0.1}
    assert get_dominant_drive(d) == "control"
    print("✅ get_dominant_drive")

def test_speech_style():
    s = get_speech_style("control")
    assert len(s) > 10
    print("✅ get_speech_style")

def test_process_action_combat():
    npc = make_npc()
    before_trust = npc["social_stats"]["trust"]
    result = process_player_action(npc, "COMBAT", {}, 80)
    assert npc["social_stats"]["trust"] < before_trust, "COMBAT должен снизить доверие"
    assert result["delta_trust"] < 0
    print("✅ process_player_action (COMBAT снижает trust)")

def test_process_action_bribery():
    npc = make_npc()
    before_trust = npc["social_stats"]["trust"]
    result = process_player_action(npc, "BRIBERY", {}, 5)
    assert npc["social_stats"]["trust"] > before_trust, "BRIBERY должен повысить доверие"
    print("✅ process_player_action (BRIBERY повышает trust)")

def test_build_prompt():
    npc = make_npc()
    prompt = build_npc_prompt(npc, {}, {})
    assert "Тестовый NPC" in prompt
    assert "control" in prompt
    print("✅ build_npc_prompt (содержит имя и драйв)")

def test_inner_thought():
    npc = make_npc()
    thought = get_inner_thought(npc)
    assert "Тестовый NPC" in thought
    assert "control" in thought
    print("✅ get_inner_thought")

if __name__ == "__main__":
    test_normalize()
    test_dominant()
    test_speech_style()
    test_process_action_combat()
    test_process_action_bribery()
    test_build_prompt()
    test_inner_thought()
    print("\n✅✅✅ Все тесты NPCCognition прошли!")

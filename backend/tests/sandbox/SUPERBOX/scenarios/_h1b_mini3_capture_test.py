#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
H1b-mini3 проверка фактического вызова инструментированной функции.

Проверяет:
1. co_consts — маркер в коде функции
2. Реальный вызов get_weights_for_decision — _h1b3_pressure_events в результате
3. Production-файл memory_manager.py не изменён на диске

Запуск:
    python backend/tests/sandbox/SUPERBOX/scenarios/_h1b_mini3_capture_test.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Bootstrap
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_BACKEND = _HERE.parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Запомнить SHA-256 memory_manager.py ДО патча
_mm_path = _BACKEND / "app" / "services" / "memory" / "memory_manager.py"
_mm_sha_before = hashlib.sha256(_mm_path.read_bytes()).hexdigest()

import bm_bprime_framework as bpf
from app.models.npc_state import Intent


def main() -> int:
    print("=== H1b-mini3 capture test ===")
    print()

    # 1. Применить ON patch
    print("--- Step 1: apply ON patch ---")
    bpf.install_h1b_mini_capture("on")
    print()

    # 2. Импортировать MemoryManager ПОСЛЕ патча
    print("--- Step 2: import MemoryManager (after patch) ---")
    from app.services.memory.memory_manager import MemoryManager
    print()

    # 3. Проверить co_consts
    print("--- Step 3: check co_consts ---")
    consts = MemoryManager.get_weights_for_decision.__code__.co_consts
    has_marker = any("_h1b3_pressure_events" in str(c) for c in consts)
    print(f"  _h1b3_pressure_events in co_consts: {has_marker}")
    if not has_marker:
        print("  FAIL: marker not found in code object")
        return 1
    print("  PASS: marker in code object")
    print()

    # 4. Создать MemoryManager с mock Working Memory
    print("--- Step 4: create MemoryManager + mock ---")
    mm = MemoryManager.__new__(MemoryManager)
    mm._relationships = MagicMock()
    mm._relationships.get_pair = MagicMock(return_value={"trust": -60.0, "fear": 70.0, "debt": 0.0})

    # Mock Working Memory с событиями
    class MockEvent:
        def __init__(self, event_type, actor_id, target_id, importance):
            self.event_type = event_type
            self.actor_id = actor_id
            self.target_id = target_id
            self.importance = importance

    class MockWorkingMemory:
        def __init__(self, events):
            self._events = events
        def get(self, key):
            return self._events.get(key, [])

    mock_events = [
        MockEvent("npc_moved", "merchant_goran", "player", 0.4),
        MockEvent("npc_proximity_close", "guard_borko", "merchant_goran", 0.3),
        MockEvent("player_interacts", "player", "merchant_goran", 0.5),
    ]
    mm._working = MockWorkingMemory({"Open_road:merchant_goran": mock_events})
    print(f"  Working Memory events: {len(mock_events)}")
    print()

    # 5. Вызвать get_weights_for_decision
    print("--- Step 5: call get_weights_for_decision ---")
    try:
        result = mm.get_weights_for_decision(
            campaign_id="Open_road",
            npc_id="merchant_goran",
            target_ids=["player"],
        )
        print(f"  result keys: {list(result.keys())}")
        player_weights = result.get("player", {})
        print(f"  player weights keys: {list(player_weights.keys())}")
        print()

        # 6. Проверить _h1b3_pressure_events
        print("--- Step 6: check _h1b3_pressure_events ---")
        pe = player_weights.get("_h1b3_pressure_events")
        if pe is None:
            print("  FAIL: _h1b3_pressure_events not in result")
            return 1
        print(f"  _h1b3_pressure_events count: {len(pe)}")
        for i, e in enumerate(pe):
            print(f"    [{i}] type={e.get('type')} actor={e.get('actor')} target={e.get('target')} importance={e.get('importance')}")

        # Ожидание: 2 события (npc_moved с target=player, player_interacts с actor=player)
        # npc_proximity_close не проходит фильтр (actor=guard_borko, target=merchant_goran, ни один != player)
        if len(pe) != 2:
            print(f"  FAIL: expected 2 events, got {len(pe)}")
            return 1
        print("  PASS: 2 events captured (filter works)")
        print()

        # 7. Проверить recent_pressure
        rp = player_weights.get("recent_pressure")
        print(f"  recent_pressure: {rp}")
        expected_rp = 0.4 + 0.5  # npc_moved (0.4) + player_interacts (0.5)
        if abs(rp - expected_rp) > 0.001:
            print(f"  FAIL: recent_pressure ({rp}) != expected ({expected_rp})")
            return 1
        print(f"  PASS: recent_pressure ({rp}) = sum of importances ({expected_rp})")
        print()

    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 8. Проверить, что production-файл не изменён
    print("--- Step 8: verify production file unchanged ---")
    _mm_sha_after = hashlib.sha256(_mm_path.read_bytes()).hexdigest()
    print(f"  SHA-256 before: {_mm_sha_before[:16]}...")
    print(f"  SHA-256 after:  {_mm_sha_after[:16]}...")
    if _mm_sha_before != _mm_sha_after:
        print("  FAIL: memory_manager.py changed on disk!")
        return 1
    print("  PASS: production file unchanged")
    print()

    print("=== ALL CHECKS PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

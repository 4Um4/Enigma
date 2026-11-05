"""S415.1a MEM-1 probe v2: что _apply_cch4_seed реально делает.

Зонд: вызывает _apply_cch4_seed напрямую с maid_lusya NPC dict,
проверяет narrative_cache до/после.
"""
import sys
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.npc.life_engine import LifeEngine

# Создаём минимальный NPC dict (как _load_npcs отдаёт)
_test_npc = {
    "id": "maid_lusya",
    "npc_id": "maid_lusya",
    "psyche": {},
    "narrative_cache": [],  # ПУСТОЙ — gate должен сработать
}

print("[PROBE2] === _apply_cch4_seed прямой вызов ===")
print(f"[PROBE2] ДО: narrative_cache={len(_test_npc['narrative_cache'])} entries")
print(f"[PROBE2] ДО: psyche.beliefs={_test_npc['psyche'].get('beliefs')}")

_result = LifeEngine._apply_cch4_seed([_test_npc])

_npc_after = _result[0]
_cache = _npc_after.get("narrative_cache", [])
_beliefs = _npc_after.get("psyche", {}).get("beliefs")

print(f"\n[PROBE2] ПОСЛЕ: narrative_cache={len(_cache)} entries")
print(f"[PROBE2] ПОСЛЕ: psyche.beliefs keys={list(_beliefs.keys()) if isinstance(_beliefs, dict) else _beliefs}")

if _cache:
    print(f"\n[PROBE2] narrative_cache samples (первые 5):")
    for i, m in enumerate(_cache[:5]):
        _tid = m.get("target_id", "<MISSING>")
        _sum = str(m.get("summary", ""))[:70]
        print(f"  [{i}] target_id={_tid!r}, summary={_sum!r}")

    _non_empty = [m for m in _cache if m.get("target_id")]
    print(f"\n[PROBE2] memories with non-empty target_id: {len(_non_empty)} / {len(_cache)}")
    if _non_empty:
        print("  ✅ _apply_cch4_seed правильно заполняет target_id")
    else:
        print("  ❌ _apply_cch4_seed НЕ заполняет target_id (баг в STEP C)")
else:
    print("[PROBE2] ❌ narrative_cache ПУСТОЙ после _apply_cch4_seed")
"""S415.1a MEM-1 probe v4: load_npcs_merged напрямую (БЕЗ harness).

Простой и быстрый зонд: вызывает load_npcs_merged() без harness.new_game(),
dump maid_lusya narrative_cache с типами entries.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.npc.npc_loader import load_npcs_merged

print("[PROBE4] === load_npcs_merged() напрямую ===")
npcs = load_npcs_merged()
print(f"[PROBE4] Загружено NPC: {len(npcs)}")

for n in npcs:
    _id = n.get("id") or n.get("npc_id")
    if _id == "maid_lusya":
        cache = n.get("narrative_cache", [])
        psyche = n.get("psyche", {})
        beliefs = psyche.get("beliefs", {})
        imprints = n.get("affective_imprints", [])
        print(f"\n[PROBE4] maid_lusya:")
        print(f"  narrative_cache: {len(cache)} entries")
        print(f"  psyche.beliefs: {list(beliefs.keys()) if isinstance(beliefs, dict) else beliefs}")
        print(f"  affective_imprints: {len(imprints) if imprints else 0}")
        print(f"\n[PROBE4] Все entries narrative_cache:")
        for i, m in enumerate(cache):
            _tid = m.get("target_id", "<MISSING>") if isinstance(m, dict) else getattr(m, "target_id", "<OBJ>")
            _mt = m.get("_memory_type", "<NO_TYPE>") if isinstance(m, dict) else type(m).__name__
            _sum = (m.get("summary", "") if isinstance(m, dict) else getattr(m, "summary", ""))[:80]
            _sid = m.get("secret_id", "") if isinstance(m, dict) else getattr(m, "secret_id", "")
            _is_sec = m.get("is_secret", False) if isinstance(m, dict) else getattr(m, "is_secret", False)
            _etype = m.get("event_type", "") if isinstance(m, dict) else getattr(m, "event_type", "")
            print(f"  [{i}] target_id={_tid!r}, type={_mt}, event_type={_etype}, is_secret={_is_sec}, secret_id={_sid!r}")
            print(f"       summary={_sum!r}")

        _with_target = [m for m in cache if (m.get("target_id") if isinstance(m, dict) else getattr(m, "target_id", ""))]
        _secrets = [m for m in cache if (m.get("is_secret") if isinstance(m, dict) else getattr(m, "is_secret", False))]
        _events = [m for m in cache if (m.get("_memory_type") == "EventMemory" if isinstance(m, dict) else type(m).__name__ == "EventMemory") and not (m.get("is_secret") if isinstance(m, dict) else getattr(m, "is_secret", False))]
        print(f"\n[PROBE4] Статистика:")
        print(f"  Всего: {len(cache)}")
        print(f"  С target_id: {len(_with_target)}")
        print(f"  Secrets: {len(_secrets)}")
        print(f"  Pure EVENT (не secret): {len(_events)}")

        _tornin = [m for m in cache if (m.get("target_id") if isinstance(m, dict) else getattr(m, "target_id", "")) == "tavern_keeper_tornin"]
        print(f"\n[PROBE4] Entries о Торнине: {len(_tornin)}")
        if _tornin:
            print("  ✅ MEM-1 работает — target_id резолвится в production")
        else:
            print("  ❌ MEM-1 НЕ работает — canon secrets вытеснили EVENT entries")
        break
else:
    print("[PROBE4] maid_lusya НЕ НАЙДЕН в load_npcs_merged()")
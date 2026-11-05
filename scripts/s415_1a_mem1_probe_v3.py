"""S415.1a MEM-1 probe v3: полная картина production narrative_cache.

Вызывает harness.new_game() + idle_tick, выводит ВСЕ entries narrative_cache
с типом (EVENT/secrets/origin) и target_id.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests.gameplay.harness import TavernGameplayHarness

print("[PROBE3] === Production narrative_cache full dump ===")
harness = TavernGameplayHarness(seed=42)
try:
    harness.new_game()
    harness.game_loop.idle_tick(harness.campaign_id)
    harness.counters.ticks += 1

    npc = harness.inspect_npc("maid_lusya")
    if npc is None:
        print("[PROBE3] FAIL: maid_lusya not found")
        sys.exit(1)

    cache = npc.get("narrative_cache", [])
    print(f"\n[PROBE3] narrative_cache count: {len(cache)}")
    print(f"[PROBE3] Все entries (index, target_id, memory_type, summary[:80]):")
    for i, m in enumerate(cache):
        _tid = m.get("target_id", "<MISSING>")
        _mt = m.get("_memory_type", "<NO_TYPE>")
        _sum = str(m.get("summary", ""))[:80]
        _sid = m.get("secret_id", "")
        _tags = m.get("tags", [])
        _is_secret = m.get("is_secret", False)
        print(f"  [{i}] target_id={_tid!r}, type={_mt}, is_secret={_is_secret}, secret_id={_sid!r}")
        print(f"       summary={_sum!r}")
        if _tags:
            print(f"       tags={_tags}")

    # Статистика
    _with_target = [m for m in cache if m.get("target_id")]
    _secrets = [m for m in cache if m.get("is_secret") or m.get("secret_id")]
    _events = [m for m in cache if m.get("_memory_type") == "EventMemory" and not m.get("is_secret")]
    print(f"\n[PROBE3] Статистика:")
    print(f"  Всего: {len(cache)}")
    print(f"  С target_id: {len(_with_target)}")
    print(f"  Secrets (is_secret или secret_id): {len(_secrets)}")
    print(f"  Pure EVENT (EventMemory, не secret): {len(_events)}")

    if _with_target:
        print(f"\n[PROBE3] Entries с target_id:")
        for m in _with_target:
            print(f"  target_id={m.get('target_id')!r}, summary={str(m.get('summary',''))[:60]!r}")

    # Проверка: есть ли EVENT entries о Торнине (target_id=tavern_keeper_tornin)
    _tornin = [m for m in cache if m.get("target_id") == "tavern_keeper_tornin"]
    print(f"\n[PROBE3] Entries о Торнине (target_id=tavern_keeper_tornin): {len(_tornin)}")
    if _tornin:
        print("  ✅ MEM-1 работает в production — target_id резолвится")
    else:
        print("  ❌ MEM-1 НЕ работает в production — target_id пустой для всех")
        print("  -> canon secrets перезаписывают EVENT entries")

finally:
    harness.dispose()
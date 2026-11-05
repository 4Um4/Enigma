import sys
sys.path.insert(0, 'backend')
from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness()
h.new_game()

# 1. Проверяем кэш LifeEngine сразу после new_game
npcs = h.game_loop._get_life_engine().get_npc_states(h.campaign_id)
print(f"[P3-TRACE] After new_game, cache has {len(npcs) if npcs else 0} NPCs")
if npcs:
    for n in npcs:
        if n.get('id') == 'maid_lusya':
            print(f"[P3-TRACE] maid_lusya beliefs in cache: {n.get('psyche', {}).get('beliefs')}")
            break

# 2. Прогон 1 тика
h.advance_ticks(1)
npcs2 = h.game_loop._get_life_engine().get_npc_states(h.campaign_id)
print(f"[P3-TRACE] After 1 tick, cache has {len(npcs2) if npcs2 else 0} NPCs")
if npcs2:
    for n in npcs2:
        if n.get('id') == 'maid_lusya':
            print(f"[P3-TRACE] maid_lusya beliefs in cache after tick: {n.get('psyche', {}).get('beliefs')}")
            break
h.dispose()

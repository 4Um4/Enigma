import sys
sys.path.insert(0, 'backend')
from app.services.npc.npc_loader import load_npcs_merged
npcs = load_npcs_merged()
for n in npcs:
    npc_id = n.get('id') or n.get('npc_id')
    if npc_id == 'maid_lusya':
        psyche = n.get('psyche', {})
        print('psyche keys:', list(psyche.keys()))
        print('beliefs:', psyche.get('beliefs'))
        print('narrative_cache:', len(n.get('narrative_cache', [])))
        break

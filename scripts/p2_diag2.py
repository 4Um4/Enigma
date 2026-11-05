import sys
sys.path.insert(0, 'backend')

# 1. Проверка canonical_chronicle
from app.services.chronicle import chronicle_seeder as _cseed
doc = _cseed.canonical_chronicle('maid_lusya')
print('1. doc found:', doc is not None)
if doc:
    print('   doc entries:', len(doc.entries))
    beliefs = _cseed.build_seed_beliefs(doc)
    print('   seed beliefs:', beliefs)

# 2. Проверка load_npcs_merged + Фикс C
from app.services.npc.npc_loader import load_npcs_merged
npcs = load_npcs_merged()
for n in npcs:
    npc_id = n.get('id') or n.get('npc_id')
    if npc_id == 'maid_lusya':
        psyche = n.get('psyche', {})
        print('2. npc_id:', npc_id)
        print('   psyche before:', list(psyche.keys()))
        print('   beliefs before:', psyche.get('beliefs'))
        
        # Прямой вызов _apply_chronicle_seed_to_dict
        from app.services.npc.npc_loader import _apply_chronicle_seed_to_dict
        _apply_chronicle_seed_to_dict(n, psyche)
        print('   beliefs after:', psyche.get('beliefs'))
        print('   npc beliefs after:', n.get('psyche', {}).get('beliefs'))
        break

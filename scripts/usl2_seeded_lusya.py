"""USL-2 SEEDED-фаза — maid_lusya через chronicle_seeder.

Цель: доказать, что 59 entries канона доходят до когнитивных структур NPC.
Проверка звена SEEDED → COGNITIVELY AVAILABLE статусной цепочки.

Диагностический скрипт — не запускает игру, использует прямые вызовы seeder.
"""
import sys, json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.chronicle.chronicle_store import document_from_dict
from app.services.chronicle import chronicle_seeder

canon_path = ROOT / 'config/npc/chronicles/maid_lusya.json'
canon_raw = json.loads(canon_path.read_text(encoding='utf-8'))
doc = document_from_dict(canon_raw)
print(f'[DOC] {doc.chronicle_id}: {len(doc.entries)} entries, game_start_age={doc.game_start_age}')

# 1. Seed memories (EventMemory)
print()
print('=== build_seed_memories ===')
try:
    memories = chronicle_seeder.build_seed_memories(doc.npc_ref, doc)
    print(f'[SEEDED] EventMemory count: {len(memories)}')
    # Анализ: какие имеют честный day, какие — SENTINEL
    sentinel_count = 0
    real_day_count = 0
    days = []
    for m in memories:
        # EventMemory может быть dict или dataclass — пробуем оба
        day = None
        if hasattr(m, 'day'):
            day = m.day
        elif isinstance(m, dict):
            day = m.get('day')
        if day is not None:
            if day == -1000:
                sentinel_count += 1
            else:
                real_day_count += 1
                days.append(day)
    print(f'  EventMemory с SENTINEL_DAY=-1000 (age=null): {sentinel_count}')
    print(f'  EventMemory с реальным day (age known):      {real_day_count}')
    if days:
        print(f'  days range: min={min(days)}, max={max(days)}')
        for d in sorted(set(days)):
            cnt = days.count(d)
            print(f'    day={d}: {cnt} memories')
except Exception as e:
    print(f'[ERROR] build_seed_memories: {type(e).__name__}: {e}')

# 2. Seed relationships
print()
print('=== build_seed_relationships ===')
try:
    rels = chronicle_seeder.build_seed_relationships(doc.npc_ref, doc)
    print(f'[SEEDED] relationship_cache entries: {len(rels)}')
    for target_id, rel_data in list(rels.items())[:10]:
        if isinstance(rel_data, dict):
            trust = rel_data.get('trust', '?')
            nature = rel_data.get('nature', '?')
            print(f'  {target_id}: trust={trust}, nature={nature}')
        else:
            print(f'  {target_id}: {type(rel_data).__name__}')
except Exception as e:
    print(f'[ERROR] build_seed_relationships: {type(e).__name__}: {e}')

# 3. Seed beliefs
print()
print('=== build_seed_beliefs ===')
try:
    beliefs = chronicle_seeder.build_seed_beliefs(doc)
    print(f'[SEEDED] BeliefState entries: {len(beliefs) if hasattr(beliefs, "__len__") else "?"}')
    if isinstance(beliefs, dict):
        for k, v in list(beliefs.items())[:10]:
            v_str = str(v)[:80] if not isinstance(v, (list, dict)) else f'{type(v).__name__}(len={len(v) if hasattr(v, "__len__") else "?"})'
            print(f'  {k}: {v_str}')
    else:
        print(f'  type: {type(beliefs).__name__}')
        print(f'  value: {str(beliefs)[:200]}')
except Exception as e:
    print(f'[ERROR] build_seed_beliefs: {type(e).__name__}: {e}')

# 4. Seed imprints (травмы)
print()
print('=== build_seed_imprints ===')
try:
    imprints = chronicle_seeder.build_seed_imprints(doc)
    print(f'[SEEDED] affective_imprints: {len(imprints)}')
    for imp in imprints[:5]:
        if isinstance(imp, dict):
            tag = imp.get('tag', '?')
            decay = imp.get('decay_rate', '?')
            print(f'  tag={tag}, decay_rate={decay}')
        else:
            print(f'  {type(imp).__name__}: {str(imp)[:100]}')
except Exception as e:
    print(f'[ERROR] build_seed_imprints: {type(e).__name__}: {e}')

# 5. Замок равенства: entries → memories (примерное соответствие)
print()
print('=== Замок равенства SEEDED ===')
print(f'  canon entries:        {len(doc.entries)}')
print(f'  seeded EventMemory:   {len(memories) if "memories" in dir() else "?"}')
print(f'  seeded relationships: {len(rels) if "rels" in dir() else "?"}')
print(f'  seeded beliefs:       {len(beliefs) if "beliefs" in dir() and hasattr(beliefs, "__len__") else "?"}')
print(f'  seeded imprints:      {len(imprints) if "imprints" in dir() else "?"}')

"""USL-2 пилот — maid_lusya через biography_to_usl (исправленные контракты).

Фабрика: document_from_dict (chronicle_store.py:330) — production WARA-пара.
USL:     biography_to_usl (biography_adapter.py:318) — свободная функция, не класс.

Диагностический скрипт — read-only над каноном, не персистит.
"""
import sys, json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

canon_path = ROOT / 'config/npc/chronicles/maid_lusya.json'
canon_raw = json.loads(canon_path.read_text(encoding='utf-8'))
print(f'[CANON] loaded: {canon_path.name}')
print(f'[CANON] entries: {len(canon_raw["entries"])}')
print(f'[CANON] game_start_age: {canon_raw.get("game_start_age")}')
print(f'[CANON] white_spots: {len(canon_raw.get("white_spots", []))}')

# Production factory: document_from_dict (WARA-пара, §12.2)
from app.services.chronicle.chronicle_store import document_from_dict
doc = document_from_dict(canon_raw)
print(f'[DOC] ChronicleDocument loaded: {doc.chronicle_id}')
print(f'[DOC] entries: {len(doc.entries)}')
print(f'[DOC] game_start_age: {doc.game_start_age}')
print(f'[DOC] canonical: {doc.canonical}')

# USL projection — свободная функция biography_to_usl (НЕ BiographyAdapter.to_usl)
from app.services.chronicle.biography_adapter import biography_to_usl
units = biography_to_usl(doc)
print(f'[USL] USLUnit count: {len(units)}')

# Замок равенства: entries == units (1:1 по построению адаптера, biography_adapter.py:324)
assert len(units) == len(doc.entries), f'LOSS: {len(doc.entries)} entries -> {len(units)} units'
print(f'[LOCK] entries==units: {len(doc.entries)}=={len(units)} GREEN')

# Анализ проекции
pred_counter = Counter()
temporal_counter = Counter()
source_counter = Counter()
units_with_temporal = 0
units_with_relations = 0
units_with_causes = 0

for u in units:
    pred = u.events[0].predicate.value if u.events else 'NONE'
    pred_counter[pred] += 1
    temporal_counter[len(u.temporal)] += 1
    source_counter[u.epistemics.source_kind.value] += 1
    if u.temporal:
        units_with_temporal += 1
    if u.relations:
        units_with_relations += 1
    if u.causal:
        units_with_causes += 1

print()
print('=== USL Predicate distribution ===')
for k, v in pred_counter.most_common():
    print(f'  {k}: {v}')

print()
print('=== Temporal distribution (units per temporal-count) ===')
for k, v in sorted(temporal_counter.items()):
    print(f'  units with {k} temporal expressions: {v}')

print()
print('=== Source kind distribution ===')
for k, v in source_counter.most_common():
    print(f'  {k}: {v}')

print()
print('=== Coverage ===')
n = len(units)
print(f'  units with temporal:  {units_with_temporal}/{n} ({100*units_with_temporal//n}%)')
print(f'  units with relations: {units_with_relations}/{n} ({100*units_with_relations//n}%)')
print(f'  units with causal:    {units_with_causes}/{n} ({100*units_with_causes//n}%)')

# Детализация: какие entries имеют temporal, какие — нет
print()
print('=== Temporal coverage detail ===')
for i, u in enumerate(units):
    span = (u.text_span or '')
    if u.temporal:
        ev = u.events[0] if u.events else None
        t = u.temporal[0]
        anchor_kind = t.anchor.value if t.anchor else None
        ev_pred = ev.predicate.value if ev else 'NONE'
        print(f'  [{i}] {ev_pred:12s} | temporal={t.kind.value} anchor={anchor_kind} value={t.value} | text={span[:60]}')
    elif any(w in span.lower() for w in ['лет', 'год', 'возраст', 'назад', 'неделю']):
        ev = u.events[0] if u.events else None
        ev_pred = ev.predicate.value if ev else 'NONE'
        print(f'  [{i}] {ev_pred:12s} | temporal=() BUT age-marker in text | text={span[:60]}')

# Инварианты USL-1..USL-6
print()
print('=== USL Invariants check ===')
# USLSourceKind.AUTHOR_CANON.value = "author_canon" (lowercase, domain/usl.py).
# Сравнение с uppercase 'AUTHOR_CANON' всегда ложно → баг USL-2 check (работа 6.2).
from app.domain.usl import USLSourceKind
_author_canon_val = USLSourceKind.AUTHOR_CANON.value
non_author = [u for u in units if u.epistemics.source_kind.value != _author_canon_val]
print(f'  USL-2 (source kind): {len(non_author)} non-{_author_canon_val} (expected 0)')
no_span = [u for u in units if not u.text_span]
print(f'  USL-5 (text_span):   {len(no_span)} units without span (expected 0)')
units2 = biography_to_usl(doc)
ids1 = [u.unit_id for u in units]
ids2 = [u.unit_id for u in units2]
print(f'  USL-6 (determinism): re-run identical = {ids1 == ids2}')

# Sample USLUnit — первый с temporal или первый overall
print()
print('=== Sample USLUnit (first with temporal, or first overall) ===')
sample = next((u for u in units if u.temporal), units[0] if units else None)
if sample:
    print(f'  unit_id: {sample.unit_id}')
    print(f'  text_span: {(sample.text_span or "")[:120]}')
    print(f'  source_kind: {sample.epistemics.source_kind.value}')
    if sample.events:
        ev = sample.events[0]
        print(f'  event.predicate: {ev.predicate.value}')
        print(f'  event.subject: {ev.subject}')
        print(f'  event.object: {ev.object}')
    if sample.temporal:
        for t in sample.temporal:
            ak = t.anchor.value if t.anchor else None
            print(f'  temporal: kind={t.kind.value} anchor={ak} value={t.value}')
    if sample.relations:
        for r in sample.relations:
            print(f'  relation: {r}')
    if sample.entities:
        for e in sample.entities:
            print(f'  entity: {e}')

# Сравнение: что было в каноне (1 entry с historical_age=5) vs что в USL temporal
print()
print('=== Canon vs USL temporal comparison ===')
canon_with_age = sum(1 for e in doc.entries if e.historical_age is not None)
usl_with_temporal = sum(1 for u in units if u.temporal)
print(f'  canon entries with historical_age: {canon_with_age}/{len(doc.entries)}')
print(f'  usl units with temporal:           {usl_with_temporal}/{len(units)}')
print(f'  match: {canon_with_age == usl_with_temporal}')

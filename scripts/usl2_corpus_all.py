"""USL-2 корпус — все 6 NPC через biography_to_usl.

Цель: доказать замок равенства на полном корпусе + собрать материал для отчёта:
- какие NPC имеют game_start_age (§2.1: только Люси=14)
- temporal coverage по каждому NPC
- список entries с age-marker в text_span, но temporal=() (материал для USL-1.5+)
- общий счётчик по EntryKind → USLPredicate

Диагностический скрипт — read-only над канонами, не персистит.
"""
import sys, json
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.services.chronicle.chronicle_store import document_from_dict
from app.services.chronicle.biography_adapter import biography_to_usl

CANON_DIR = ROOT / 'config/npc/chronicles'
AGE_MARKERS = ['лет', 'год', 'возраст', 'назад', 'неделю', 'месяц', 'день']

# Сбор по корпусу
corpus = []
for canon_file in sorted(CANON_DIR.glob('*.json')):
    canon_raw = json.loads(canon_file.read_text(encoding='utf-8'))
    doc = document_from_dict(canon_raw)
    units = biography_to_usl(doc)

    # Замок равенства
    assert len(units) == len(doc.entries), f'{canon_file.name}: LOSS {len(doc.entries)} -> {len(units)}'

    # Метрики
    units_with_temporal = sum(1 for u in units if u.temporal)
    units_with_relations = sum(1 for u in units if u.relations)
    units_with_causes = sum(1 for u in units if u.causal)
    canon_with_age = sum(1 for e in doc.entries if e.historical_age is not None)

    # USL-2: source kind (регистронезависимо)
    non_author = sum(1 for u in units if u.epistemics.source_kind.value.lower() != 'author_canon')

    # USL-6: детерминизм
    units2 = biography_to_usl(doc)
    det = [u.unit_id for u in units] == [u.unit_id for u in units2]

    # Age-marker в text_span, но temporal=()
    age_marker_lost = []
    for i, u in enumerate(units):
        span = (u.text_span or '').lower()
        if not u.temporal and any(w in span for w in AGE_MARKERS):
            age_marker_lost.append((i, (u.text_span or '')[:80]))

    corpus.append({
        'name': canon_file.stem,
        'doc': doc,
        'units': units,
        'entries': len(doc.entries),
        'game_start_age': doc.game_start_age,
        'canon_with_age': canon_with_age,
        'units_with_temporal': units_with_temporal,
        'units_with_relations': units_with_relations,
        'units_with_causes': units_with_causes,
        'non_author': non_author,
        'det': det,
        'age_marker_lost': age_marker_lost,
    })

# === Сводный отчёт ===
print('=' * 70)
print('USL-2 КОРПУС — 6 NPC через biography_to_usl')
print('=' * 70)
print()

print('=== Замок равенства ===')
total_entries = sum(c['entries'] for c in corpus)
total_units = sum(len(c['units']) for c in corpus)
print(f'  Всего entries: {total_entries}')
print(f'  Всего USLUnit: {total_units}')
print(f'  Замок: {total_entries}=={total_units} {"GREEN" if total_entries == total_units else "RED"}')
print()

print('=== По каждому NPC ===')
print(f'  {"NPC":<25} {"entries":>8} {"gs_age":>7} {"canon_age":>10} {"usl_temp":>9} {"rel":>5} {"caus":>5} {"non_auth":>9} {"det":>5} {"age_lost":>9}')
for c in corpus:
    gsa = c['game_start_age'] if c['game_start_age'] is not None else '-'
    print(f'  {c["name"]:<25} {c["entries"]:>8} {str(gsa):>7} {c["canon_with_age"]:>10} {c["units_with_temporal"]:>9} {c["units_with_relations"]:>5} {c["units_with_causes"]:>5} {c["non_author"]:>9} {str(c["det"]):>5} {len(c["age_marker_lost"]):>9}')
print(f'  {"TOTAL":<25} {total_entries:>8} {"":>7} {sum(c["canon_with_age"] for c in corpus):>10} {sum(c["units_with_temporal"] for c in corpus):>9} {sum(c["units_with_relations"] for c in corpus):>5} {sum(c["units_with_causes"] for c in corpus):>5} {sum(c["non_author"] for c in corpus):>9} {"":>5} {sum(len(c["age_marker_lost"]) for c in corpus):>9}')
print()

print('=== USL-2 (source kind) — должен быть 0 non-AUTHOR_CANON ===')
total_non_author = sum(c['non_author'] for c in corpus)
print(f'  non-AUTHOR_CANON units: {total_non_author}/{total_units} (expected 0)')
print(f'  USL-2: {"GREEN" if total_non_author == 0 else "RED"}')
print()

print('=== USL-6 (детерминизм) — все NPC должны быть True ===')
all_det = all(c['det'] for c in corpus)
print(f'  Все NPC детерминированы: {all_det}')
print(f'  USL-6: {"GREEN" if all_det else "RED"}')
print()

print('=== game_start_age distribution (§2.1: только Люси=14) ===')
gsa_count = sum(1 for c in corpus if c['game_start_age'] is not None)
print(f'  NPC с game_start_age: {gsa_count}/6')
for c in corpus:
    if c['game_start_age'] is not None:
        print(f'    {c["name"]}: game_start_age={c["game_start_age"]}')
print()

print('=== Temporal coverage (главная находка USL-2) ===')
total_canon_age = sum(c['canon_with_age'] for c in corpus)
total_usl_temp = sum(c['units_with_temporal'] for c in corpus)
print(f'  canon entries with historical_age: {total_canon_age}/{total_entries} ({100*total_canon_age//total_entries}%)')
print(f'  usl units with temporal:           {total_usl_temp}/{total_units} ({100*total_usl_temp//total_units}%)')
print(f'  match (USL не теряет/не галлюцинирует): {total_canon_age == total_usl_temp}')
print()

print('=== AGE-MARKER IN TEXT, BUT temporal=() — материал для USL-1.5+ ===')
total_lost = sum(len(c['age_marker_lost']) for c in corpus)
print(f'  Всего entries с age-marker в span, но пустым temporal: {total_lost}')
print()
for c in corpus:
    if c['age_marker_lost']:
        print(f'  --- {c["name"]} ({len(c["age_marker_lost"])} entries) ---')
        for idx, span in c['age_marker_lost'][:10]:
            print(f'    [{idx}] {span}')
        if len(c['age_marker_lost']) > 10:
            print(f'    ... и ещё {len(c["age_marker_lost"]) - 10}')
        print()

print('=== USLPredicate distribution (весь корпус) ===')
pred_total = Counter()
for c in corpus:
    for u in c['units']:
        pred = u.events[0].predicate.value if u.events else 'NONE'
        pred_total[pred] += 1
for k, v in pred_total.most_common():
    print(f'  {k}: {v}')
print()

print('=== ИТОГОВЫЙ ВЕРДИКТ ===')
lock = total_entries == total_units
usl2 = total_non_author == 0
usl6 = all_det
usl_temporal_match = total_canon_age == total_usl_temp
print(f'  Замок равенства:    {"GREEN" if lock else "RED"} ({total_entries}=={total_units})')
print(f'  USL-2 source kind:  {"GREEN" if usl2 else "RED"} ({total_non_author} non-author)')
print(f'  USL-6 determinism:  {"GREEN" if usl6 else "RED"}')
print(f'  Temporal match:     {"GREEN" if usl_temporal_match else "RED"} (canon {total_canon_age} == usl {total_usl_temp})')
print(f'  age-marker lost:    {total_lost} entries (материал для USL-1.5+ Temporal Extractor)')
all_green = lock and usl2 and usl6 and usl_temporal_match
print(f'  Корпус USL-2:       {"ALL GREEN" if all_green else "HAS RED"}')

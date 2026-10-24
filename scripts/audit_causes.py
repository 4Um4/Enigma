import json, glob, sys
from collections import Counter
from pathlib import Path

stats = Counter()
issues = []
per_file = {}
for fp in sorted(glob.glob('config/npc/chronicles/*.json')):
    doc = json.loads(Path(fp).read_text(encoding='utf-8'))
    name = Path(fp).name
    entries = doc.get('entries', [])
    if not entries:
        per_file[name] = {'total': 0}
        continue
    entry_ids = {x.get('entry_id') for x in entries if x.get('entry_id')}
    file_stats = Counter()
    for e in entries:
        ord_ = e.get('ordinal')
        if 'causes' not in e:
            stats['missing_key'] += 1
            file_stats['missing_key'] += 1
            continue
        c = e['causes']
        if c is None:
            stats['null'] += 1
            file_stats['null'] += 1
        elif isinstance(c, list) and len(c) == 0:
            stats['empty_list'] += 1
            file_stats['empty_list'] += 1
        elif isinstance(c, list) and len(c) > 0:
            stats['has_elements'] += 1
            file_stats['has_elements'] += 1
            for cause in c:
                if not isinstance(cause, dict):
                    issues.append(f"{name}[{ord_}]: cause not dict: {type(cause).__name__}")
                    continue
                oref = cause.get('origin_ref')
                if not oref:
                    issues.append(f"{name}[{ord_}]: cause без origin_ref: {cause!r}")
                elif oref not in entry_ids:
                    issues.append(f"{name}[{ord_}]: origin_ref={oref!r} не в entry_id документа ({len(entry_ids)} ids)")
        else:
            stats[f'unknown_type:{type(c).__name__}'] += 1
    per_file[name] = {'total': len(entries), **file_stats}

print("=== ПОФАЙЛОВАЯ СТАТИСТИКА ===")
for name, s in per_file.items():
    print(f"\n{name} (total={s.get('total', 0)}):")
    for k in ('missing_key', 'null', 'empty_list', 'has_elements'):
        if k in s:
            print(f"  {k}: {s[k]}")

print("\n=== ИТОГО ===")
for k, v in stats.most_common():
    print(f"  {k}: {v}")

print(f"\n=== ВАЛИДАЦИОННЫЕ ПРОБЛЕМЫ: {len(issues)} ===")
for i in issues[:30]:
    print(f"  - {i}")

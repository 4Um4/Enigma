# -*- coding: utf-8 -*-
"""S368: применить патч к routes_chronicle.py — добавить EntryKind в импорт
и блок детерминированного fallback age_anchors[0] -> EVENT.

Устойчив к line endings: использует newline='' для сохранения оригинальных
переводов строк. Idempotent: если патч уже применён — выводит 'ALREADY APPLIED'.
"""
from pathlib import Path
import re

p = Path("backend/app/api/routes_chronicle.py")
src = p.read_text(encoding="utf-8", newline="")

# ── 1. Добавить EntryKind в импорт ──────────────────────────────────────
import_re = re.compile(
    r'from app\.domain\.chronicle import \(\s*'
    r'ChronicleDocument,\s*'
    r'ChronicleEntry,\s*'
    r'EntityRef,\s*'
    r'EntityRefKind,\s*'
    r'(?!EntryKind,)  # negative lookahead — если уже есть, не трогаем'
    r'EntryProvenance,\s*'
    r'make_entry_id,\s*'
    r'\)',
    re.MULTILINE | re.DOTALL
)
import_new = (
    'from app.domain.chronicle import (\n'
    '    ChronicleDocument,\n'
    '    ChronicleEntry,\n'
    '    EntityRef,\n'
    '    EntityRefKind,\n'
    '    EntryKind,\n'
    '    EntryProvenance,\n'
    '    make_entry_id,\n'
    ')'
)
if 'EntryKind,' in src and src.count('EntryKind,') >= 1 and 'EntryKind,\n    EntryProvenance' in src:
    print("IMPORT: ALREADY APPLIED (EntryKind уже в импорте)")
elif import_re.search(src):
    src = import_re.sub(lambda m: import_new, src, count=1)
    print("IMPORT: replaced via regex")
else:
    # Fallback: простая замена первой подходящей позиции
    simple_old = (
        'from app.domain.chronicle import (\n'
        '    ChronicleDocument,\n'
        '    ChronicleEntry,\n'
        '    EntityRef,\n'
        '    EntityRefKind,\n'
        '    EntryProvenance,\n'
        '    make_entry_id,\n'
        ')'
    )
    simple_old_crlf = simple_old.replace('\n', '\r\n')
    if simple_old in src:
        src = src.replace(simple_old, import_new, 1)
        print("IMPORT: replaced via simple LF")
    elif simple_old_crlf in src:
        src = src.replace(simple_old_crlf, import_new.replace('\n', '\r\n'), 1)
        print("IMPORT: replaced via simple CRLF")
    else:
        print("IMPORT: NOT FOUND — нужен ручной просмотр импорта")
        print("Первые 80 символов импорта:")
        idx = src.find('from app.domain.chronicle import')
        print(repr(src[idx:idx+250]))
        raise SystemExit(1)

# ── 2. Заменить блок age-логики на блок с fallback ──────────────────────
block_re = re.compile(
    r'        _age = _it\.draft_payload\.get\("age", _it\.draft_payload\.get\("historical_age"\)\)\s*\n'
    r'        # §1\.1: однострочное.*?тихий отказ — развёрнуто\s*\n'
    r'        _age_value = None\s*\n'
    r'        if isinstance\(_age, int\):\s*\n'
    r'            _age_value = _age\s*\n',
    re.DOTALL
)
block_new = (
    '        _age = _it.draft_payload.get("age", _it.draft_payload.get("historical_age"))\n'
    '        # §1.1: однострочное «X if cond else None» = тихий отказ — развёрнуто\n'
    '        _age_value = None\n'
    '        if isinstance(_age, int):\n'
    '            _age_value = _age\n'
    '\n'
    '        # §S368: детерминированный fallback. Контракт (chronicle_decompose_system.txt:39)\n'
    '        # требует age=атрибут СОБЫТИЯ. Если LLM не проставила age явно (регулярно\n'
    '        # наблюдается в дампе s368_age_dump.txt при anchors=[8] и age=None в payload),\n'
    '        # а препарсер извлёк ровно один якорь и в декомпозиции ровно одно EVENT —\n'
    '        # якорь принадлежит этому событию (фраза «В N лет <событие>»).\n'
    '        # Множественность якорей или событий → неопределённость, не выдумываем\n'
    '        # (§ENIGMA-003). Не применяется к RELATIONSHIP/EFFECT (контракт: age только\n'
    '        # для событий). Не использует day/строки — отдельная дыра, не S368.\n'
    '        if (\n'
    '            _age_value is None\n'
    '            and _it.kind is EntryKind.EVENT\n'
    '            and result.age_anchors\n'
    '            and len(result.age_anchors) == 1\n'
    '        ):\n'
    '            _event_count = sum(1 for x in result.items if x.kind is EntryKind.EVENT)\n'
    '            if _event_count == 1:\n'
    '                _age_value = result.age_anchors[0]\n'
)
if '§S368: детерминированный fallback' in src:
    print("BLOCK: ALREADY APPLIED (§S368 уже в файле)")
elif block_re.search(src):
    src = block_re.sub(lambda m: block_new, src, count=1)
    print("BLOCK: replaced via regex")
else:
    print("BLOCK: NOT FOUND — нужен ручной просмотр блока age-логики")
    idx = src.find('_age = _it.draft_payload.get("age"')
    print(repr(src[idx:idx+400]))
    raise SystemExit(1)

p.write_text(src, encoding="utf-8", newline="")
print("DONE — файл сохранён")

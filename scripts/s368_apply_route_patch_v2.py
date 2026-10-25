# -*- coding: utf-8 -*-
"""S368: применить патч к routes_chronicle.py — v2.
Корректно обходит существующие импорты (SCHEMA_VERSION, BeliefGroup и др.):
ищет ТОЧНЫЙ блок 'from app.domain.chronicle import (ChronicleDocument, ...)'
и заменяет его на расширенный с EntryKind.
"""
from pathlib import Path
import re

p = Path("backend/app/api/routes_chronicle.py")
src = p.read_text(encoding="utf-8", newline="")

# ── 1. Импорт EntryKind ────────────────────────────────────────────────
# Точный блок внутри decompose_fragment (с 4-пробельным отступом).
# Устойчив к LF/CRLF — используем \r?\n в regex.
import_re = re.compile(
    r'(    from app\.domain\.chronicle import \(\r?\n'
    r'        ChronicleDocument,\r?\n'
    r'        ChronicleEntry,\r?\n'
    r'        EntityRef,\r?\n'
    r'        EntityRefKind,\r?\n'
    r'        )EntryProvenance,\r?\n'
    r'        make_entry_id,\r?\n'
    r'    \)'
)
import_new = (
    '\\1EntryKind,\r\n'
    '        EntryProvenance,\r\n'
    '        make_entry_id,\r\n'
    '    )'
)
if 'EntryKind,\n        EntryProvenance' in src or 'EntryKind,\r\n        EntryProvenance' in src:
    print("IMPORT: ALREADY APPLIED")
elif import_re.search(src):
    src = import_re.sub(import_new, src, count=1)
    print("IMPORT: replaced via regex v2")
else:
    print("IMPORT: NOT FOUND — показываю контекст")
    # Найти первое вхождение 'ChronicleDocument'
    idx = src.find('ChronicleDocument')
    if idx >= 0:
        print(repr(src[max(0,idx-100):idx+250]))
    raise SystemExit(1)

# ── 2. Блок age-логики с fallback ──────────────────────────────────────
# Устойчив к LF/CRLF. Точное совпадение 6 строк блока.
block_re = re.compile(
    r'        _age = _it\.draft_payload\.get\("age", _it\.draft_payload\.get\("historical_age"\)\)\r?\n'
    r'        # §1\.1: однострочное.*?тихий отказ — развёрнуто\r?\n'
    r'        _age_value = None\r?\n'
    r'        if isinstance\(_age, int\):\r?\n'
    r'            _age_value = _age\r?\n',
    re.DOTALL
)
block_new_lf = (
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
    print("BLOCK: ALREADY APPLIED")
elif block_re.search(src):
    src = block_re.sub(lambda m: block_new_lf, src, count=1)
    print("BLOCK: replaced via regex v2")
else:
    print("BLOCK: NOT FOUND — показываю контекст")
    idx = src.find('_age = _it.draft_payload.get("age"')
    if idx >= 0:
        print(repr(src[idx:idx+400]))
    raise SystemExit(1)

p.write_text(src, encoding="utf-8", newline="")
print("DONE — файл сохранён")

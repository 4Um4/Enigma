"""
Назначение: разовый диагностический дамп event_memories кампании (зонд Части VIII.5 для Шага 4.5: какие строки, чьи id, где пустой summary)
Зависимости: app.services.memory.sqlite_store
Основные сущности: SqliteMemoryStore

# 1. Дамп (если путь не найдётся — скажет сам, поправим)
python backend/tests/sandbox/db_dump_probe.py Open_road
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR = _BACKEND_DIR.parent
for _p in (str(_BACKEND_DIR / "app"), str(_BACKEND_DIR), str(_ROOT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.services.memory.sqlite_store import SqliteMemoryStore

campaign_id = sys.argv[1] if len(sys.argv) > 1 else "Open_road"

# Кандидаты пути БД: settings.saves_dir может вести в backend/saves или корень/saves
_candidates = [
    _ROOT_DIR / "saves" / "enigma_memory.db",
    _ROOT_DIR / "saves" / campaign_id / "enigma_memory.db",
    _BACKEND_DIR / "saves" / campaign_id / "enigma_memory.db",
    _ROOT_DIR / "data" / campaign_id / "enigma_memory.db",
]
db_path = next((p for p in _candidates if p.exists()), None)
if db_path is None:
    print(f"[DB_DUMP] БД не найдена ни по одному пути: {[str(c) for c in _candidates]}")
    sys.exit(1)

print(f"[DB_DUMP] {db_path}")
s = SqliteMemoryStore(db_path)
rows = s.query(
    "SELECT npc_id, event_type, summary, importance, day, is_secret, id "
    "FROM event_memories ORDER BY npc_id, importance DESC"
)
print(f"[DB_DUMP] total rows: {len(rows)}")
for r in rows:
    summary = (r["summary"] or "")
    print(
        f"{r['npc_id'][:22]:22} | {r['event_type'][:20]:20} | "
        f"imp={r['importance']:.3f} | secret={int(r['is_secret'])} | "
        f"id={r['id']} | '{summary[:60]}'"
    )
empty = sum(1 for r in rows if not (r["summary"] or "").strip())
print(f"[DB_DUMP] пустых summary: {empty}/{len(rows)}")
s.close()
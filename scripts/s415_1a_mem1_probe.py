"""S415.1a MEM-1 probe: что реально лежит в EventMemory после seeder.

Цель: проверить, работает ли target_id-атрибуция для EVENT entries
с object_id.ref_kind=RESOLVED, npc_id=tavern_keeper_tornin.

Гипотезы:
  H1: EventMemory — frozen dataclass без __slots__ -> __dict__ работает
  H2: _resolved_npc_id возвращает npc_id для RESOLVED refs
  H3: {**_item.__dict__} разворачивает target_id

Если target_id непустой для entries о Торнине -> MEM-1 работает,
баг в life_engine._apply_cch4_seed ( losing target_id при сериализации).
Если target_id пустой -> баг в seeder (_resolved_npc_id или EntityRef парсинг).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.chronicle.chronicle_seeder import (
    build_seed_memories,
    canonical_chronicle,
    _resolved_npc_id,
)
from app.domain.chronicle import EntityRef, EntityRefKind
import dataclasses

print("[PROBE] === MEM-1 target_id атрибуция ===")

# Шаг 1: прямой вызов _resolved_npc_id для EntityRef RESOLVED
print("\n[PROBE] Шаг 1: _resolved_npc_id для EntityRef RESOLVED(tavern_keeper_tornin)")
_ref = EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="tavern_keeper_tornin")
_resolved = _resolved_npc_id(_ref)
print(f"  EntityRef(ref_kind=RESOLVED, npc_id='tavern_keeper_tornin')")
print(f"  _resolved_npc_id -> {_resolved!r}")
print(f"  is None? {_resolved is None}")

# Шаг 2: canonical_chronicle + build_seed_memories
print("\n[PROBE] Шаг 2: build_seed_memories('maid_lusya', doc)")
_doc = canonical_chronicle("maid_lusya")
if not _doc:
    print("  NO DOC")
    sys.exit(1)

print(f"  doc.chronicle_id={_doc.chronicle_id}")
print(f"  doc.entries count={len(_doc.entries)}")
print(f"  doc.game_start_age={_doc.game_start_age}")

_event_entries = [e for e in _doc.entries if e.kind.value == "EVENT"]
print(f"  EVENT entries: {len(_event_entries)}")

print("\n[PROBE] EVENT entries object_id + _resolved_npc_id:")
for i, e in enumerate(_event_entries):
    _oid = e.object_id
    if _oid is not None:
        _rk = _oid.ref_kind
        _npc_id = _oid.npc_id
        _resolved_for_entry = _resolved_npc_id(_oid)
        print(f"  [{i}] ordinal={e.ordinal}, entry_id={e.entry_id}")
        print(f"       object_id: ref_kind={_rk!r} (type={type(_rk).__name__}), npc_id={_npc_id!r}")
        print(f"       _resolved_npc_id(object_id) -> {_resolved_for_entry!r}")
        print(f"       is RESOLVED? {_rk is EntityRefKind.RESOLVED}")
        print(f"       == RESOLVED? {_rk == EntityRefKind.RESOLVED}")
    else:
        print(f"  [{i}] ordinal={e.ordinal}, object_id=None")

# Шаг 3: build_seed_memories — что реально в EventMemory.target_id
print("\n[PROBE] Шаг 3: build_seed_memories — EventMemory.target_id")
_mems = build_seed_memories("maid_lusya", _doc)
print(f"  memories count: {len(_mems)}")
for i, m in enumerate(_mems):
    _has_dict = hasattr(m, "__dict__")
    _has_slots = hasattr(m, "__slots__")
    _is_dc = dataclasses.is_dataclass(m)
    _fields = [f.name for f in dataclasses.fields(m)] if _is_dc else []
    print(f"  [{i}] target_id={m.target_id!r}, summary={m.summary[:70]!r}")
    if i == 0:
        print(f"       is_dataclass={_is_dc}, has __dict__={_has_dict}, has __slots__={_has_slots}")
        print(f"       __dict__ keys (first 8): {list(m.__dict__.keys())[:8] if _has_dict else 'N/A'}")
        print(f"       dataclass fields (first 8): {_fields[:8]}")
        # Проверка: что в __dict__
        if _has_dict:
            print(f"       __dict__['target_id'] = {m.__dict__.get('target_id')!r}")
        # Проверка: dataclasses.asdict
        try:
            _asdict = dataclasses.asdict(m)
            print(f"       asdict()['target_id'] = {_asdict.get('target_id')!r}")
        except Exception as _e:
            print(f"       asdict() ERROR: {_e}")

print("\n[PROBE] === ВЕРДИКТ ===")
_non_empty = [m for m in _mems if m.target_id]
print(f"  memories with non-empty target_id: {len(_non_empty)} / {len(_mems)}")
if _non_empty:
    print("  ✅ MEM-1 работает в seeder — target_id резолвится")
    print("  -> баг в life_engine._apply_cch4_seed (serialisation теряет target_id)")
else:
    print("  ❌ MEM-1 НЕ работает в seeder — target_id пустой для ВСЕХ memories")
    print("  -> баг в _resolved_npc_id или EntityRef парсинге")
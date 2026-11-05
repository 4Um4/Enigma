import sys, json
sys.path.insert(0, ".")
from app.services.chronicle.chronicle_seeder import canonical_chronicle

doc = canonical_chronicle("guard_borko")
if doc is None:
    print("doc is None")
    sys.exit(1)

print(f"chronicle_id: {doc.chronicle_id}")
print(f"game_start_age: {doc.game_start_age}")
print(f"entries: {len(doc.entries)}")

# Count historical_age
anchors = 0
for e in doc.entries:
    if e.historical_age is not None:
        anchors += 1
        print(f"  ANCHOR: entry_id={e.entry_id[:12]}... historical_age={e.historical_age} kind={e.kind}")
print(f"Total anchors: {anchors}")
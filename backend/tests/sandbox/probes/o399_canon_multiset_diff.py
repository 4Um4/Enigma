# path: backend/tests/sandbox/probes/o399_canon_multiset_diff.py
# Назначение: O399 — мультивест-диф recent_dialogues A2 vs B (real_ts вычищен).
# Ответ на вопрос: расхождение канонов = только хвостовые записи B, или есть содержательное?
# Временный зонд, удалить с зонтом. Запуск: cd backend; python tests/sandbox/probes/o399_canon_multiset_diff.py; cd ..
import hashlib
import json
from collections import Counter
from pathlib import Path

base = Path(__file__).parent.parent / "SUPERBOX" / "reports" / "o399_snaps"


def canon_records(tag: str) -> list:
    d = json.loads((base / f"scene_{tag}.json").read_text(encoding="utf-8"))
    rd = d["scene_a"].get("recent_dialogues", [])
    recs = []
    for e in rd:
        e = {k: v for k, v in e.items() if k != "real_ts"}  # real_ts вне канона
        recs.append((
            e.get("timestamp", 0), e.get("game_time", 0),
            e.get("speaker_id", ""), e.get("target_id", ""),
            e.get("text", ""),
        ))
    return recs


a = canon_records("A2")
b = canon_records("B")
ca, cb = Counter(a), Counter(b)
only_a, only_b = ca - cb, cb - ca

print(f"A2: {len(a)} | B: {len(b)}")
print(f"A-only: {sum(only_a.values())} | B-only: {sum(only_b.values())}")
print()
print("=== ТОЛЬКО В B (до 10) ===")
for r, n in list(only_b.items())[:10]:
    print(f"  x{n}: ts={r[0]} game={r[1]} {r[2]} -> {r[3]}")
    print(f"      text: {r[4][:80]}")
print()
print("=== ТОЛЬКО В A (до 10) ===")
for r, n in list(only_a.items())[:10]:
    print(f"  x{n}: ts={r[0]} game={r[1]} {r[2]} -> {r[3]}")
    print(f"      text: {r[4][:80]}")

# Финал (исправленная логика): общее мультимножество = ca ∩ cb.
# Прежняя версия сравнивала B-minus-B-only с ПОЛНЫМ A2 — обязана была
# отличаться на 2 A-only записи. Корректно: минус A-only с обеих сторон.
common_a = sorted((ca - only_a).elements())
common_b = sorted((cb - only_b).elements())
ha = hashlib.sha256(json.dumps(common_a, ensure_ascii=False).encode()).hexdigest()[:16]
hb = hashlib.sha256(json.dumps(common_b, ensure_ascii=False).encode()).hexdigest()[:16]
print()
print(f"canon(A minus A-only) = {ha}")
print(f"canon(B minus B-only) = {hb}")
print("ОБЩЕЕ МУЛЬТИМНОЖЕСТВО СОВПАДАЕТ — вся разница = 2 A-only + 5 B-only"
      if ha == hb else "ОБЩЕЕ МУЛЬТИМНОЖЕСТВО РАЗЛИЧАЕТСЯ — диф неполон")
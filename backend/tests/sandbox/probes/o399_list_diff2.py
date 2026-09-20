# path: backend/tests/sandbox/probes/o399_list_diff2.py
# Назначение: O399 — автодиф пары L0'/L1' (состав/порядок/датировка). Временный, удалить с зонтом.
# Зависимости: stdlib. Запуск: cd backend; python tests/sandbox/probes/o399_list_diff2.py; cd ..
import re
from collections import Counter
from pathlib import Path

txt = Path(r"C:\Users\lipir\AppData\Local\Temp\drift_diff_scene.txt").read_text(encoding="utf-8")
a_raw, b_raw = txt.split("B = [")[0], "B = [" + txt.split("B = [")[1]

pat = re.compile(
    r'"speaker_id":\s*"([^"]*)",\s*'
    r'"target_id":\s*"([^"]*)",\s*'
    r'"text":\s*"([^"]*)",\s*'
    r'"timestamp":\s*(\d+)'
)
pa = [tuple(m) for m in pat.findall(a_raw)]
pb = [tuple(m) for m in pat.findall(b_raw)]

print("lenA =", len(pa), " lenB =", len(pb))
print("positional equal:", pa == pb)
if pa != pb:
    i = next((i for i in range(min(len(pa), len(pb))) if pa[i] != pb[i]), None)
    print("first mismatch @", i)
    if i is not None:
        print("A[i]:", pa[i])
        print("B[i]:", pb[i])

ca, cb = Counter(pa), Counter(pb)
oa, ob = ca - cb, cb - ca
print("A-only:", sum(oa.values()), " B-only:", sum(ob.values()))
for x in list(ob)[:5]:
    print("B-only:", x)
for x in list(oa)[:5]:
    print("A-only:", x)
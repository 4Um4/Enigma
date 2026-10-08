"""
path: /project/reports/s339_renumber.py
Назначение: Продолжение ренумбер-цепочки (Устав 11.1.1): S338 занят параллельной
    S338-fix-серией (284ef784 уже в origin/main — неизменяемо) → S330-probe
    уходит на первый номер, свободный в ОБОИХ пространствах: реестр MUTATIONS
    + git log --all. Урок s338_renumber.py: коммит-проверка была информационной,
    здесь — ГЕЙТ (аналог I.2: аномалия = СТОП). Одноразовый.
Запуск: python reports/s339_renumber.py
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "docs" / "MUTATIONS.md"
_raw = F.read_bytes()
_bom = _raw.startswith(b"\xef\xbb\xbf")
text = _raw.decode("utf-8-sig" if _bom else "utf-8")

# 1. Моя строка: маркер S338 + контент S330-probe
lines = text.splitlines(keepends=True)
_idx = [i for i, _l in enumerate(lines) if _l.startswith("- **S338**")]
assert len(_idx) == 1, f"count(S338-row)={len(_idx)} — СТОП"
assert "S330-probe" in lines[_idx[0]], "S338-строка чужая — СТОП"

# 2. ГЕЙТ: первый номер, свободный в реестре И в коммит-сообщениях (--all)
chosen = None
for _n in range(339, 346):
    _reg_free = not re.search(rf"^- \*\*S{_n}\*\*", text, re.M)
    _out = subprocess.run(["git", "log", "--all", "--format=%s", f"--grep=S{_n}"],
                          capture_output=True, text=True, check=True,
                          cwd=str(ROOT)).stdout.strip()
    _msg_free = _out == ""
    _ev = "" if _msg_free else f"  [занят: {_out.splitlines()[0][:58]}...]"
    print(f"S{_n}: registry_free={_reg_free} commitmsg_free={_msg_free}{_ev}")
    if _reg_free and _msg_free:
        chosen = _n
        break
assert chosen, "339-345 заняты — СТОП, эскалация Мастеру"

# 3. Замена маркера + МЕТА-нота сразу после ноты «Дубль S337»
lines[_idx[0]] = lines[_idx[0]].replace("- **S338**", f"- **S{chosen}**", 1)
_d = [i for i, _l in enumerate(lines) if _l.lstrip().startswith("- Дубль S337:")]
assert len(_d) == 1, f"count(нота S337)={len(_d)}"
_NOTE = (f"- Дубль S{chosen - 1}: параллельная S{chosen - 1}-fix-серия "
         f"(ecdf26d5/97b49c27/284ef784 «S{chosen - 1}-fix: фиксы CI/тестов…», "
         f"284ef784 уже в origin/main — сообщения неизменяемы; своей "
         f"реестр-строки у серии нет) vs ренумбер-строка S330-probe. Канон: "
         f"S{chosen - 1} = S{chosen - 1}-fix, S330-probe → S{chosen}. Итог цепочки "
         f"гонки трёх серий: S337=CCH-3 (d85ef720), S{chosen - 1}=S{chosen - 1}-fix, "
         f"S{chosen}=S330-probe. Урок: проверка коллизий = гейт исполнения "
         f"(реестр + git log --all), не информационный шаг.")
lines.insert(_d[0] + 1, _NOTE + "\n")
text2 = "".join(lines)

# 4. Верификации: маркеры, счётчик, число строк
assert text2.count(f"- **S{chosen}**") == 1
assert re.search(r"^- \*\*S338\*\*", text2, re.M) is None
_m = re.search(r"^Записей: (\d+)", text2, re.M)
assert _m and _m.group(1) == "221", f"МЕТА дрейф: {(_m.group(1) if _m else '?')} — СТОП"
assert len(text2.splitlines()) == len(text.splitlines()) + 1

F.write_bytes((b"\xef\xbb\xbf" if _bom else b"") + text2.encode("utf-8"))
print(f"OK: S330-probe → S{chosen}; МЕТА-нота добавлена; счётчик 221 неизменен")
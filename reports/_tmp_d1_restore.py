import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
mp = os.path.join(ROOT, "docs", "MUTATIONS.md")

# 1. Археология: вербатим-строка из последнего до-мутационного коммита
out = subprocess.run(["git", "show", "b01b444b:docs/MUTATIONS.md"], capture_output=True)
orig = out.stdout.decode("utf-8-sig")
cands = [L for L in orig.splitlines() if "DEBT-ADR-CLI-QUIET" in L]
print("в b01b444b найдено вхождений CLI-QUIET: %d" % len(cands))
if len(cands) != 1:
    raise SystemExit("STOP: ожидалась ровно 1 строка, см. выше")
restored = cands[0]
print("RESTORE: %r" % restored[:130])

# 2. Текущее состояние
raw = open(mp, "rb").read()
bom = raw[:3] == b"\xef\xbb\xbf"
text = raw.decode("utf-8-sig")
nl = "\r\n" if "\r\n" in text else "\n"
lines = text.split(nl)
if any("DEBT-ADR-CLI-QUIET" in L for L in lines):
    raise SystemExit("STOP: CLI-QUIET уже присутствует — повторный запуск? (идемпотентность)")
net_idx = [k for k, L in enumerate(lines) if "~~DEBT-ADR-NET-N/A-FILL~~" in L]
if len(net_idx) != 1:
    raise SystemExit("STOP: strikethrough-NET не уникальна (%d)" % len(net_idx))

# 3. Вставка на исходное место: ПЕРЕД закрытием NET (исходный порядок секции)
lines.insert(net_idx[0], restored)
text2 = nl.join(lines)

# 4. Пост-верификация: греп не тронут (строка без S-префикса), МЕТА, счётчики
g = len(re.findall(r"^- \*\*S[0-9]", text2, re.M))
m = re.search(r"Записей: (\d+)", text2).group(1)
c_cli = text2.count("DEBT-ADR-CLI-QUIET")
c_net = text2.count("DEBT-ADR-NET-N/A-FILL")
print("пост: греп=%d МЕТА=%s CLI-QUIET=%d NET=%d (ожидание 206/206/1/2)" % (g, m, c_cli, c_net))
if not (g == 206 and m == "206" and c_cli == 1 and c_net == 2):
    raise SystemExit("STOP: пост-верификация не сошлась — файл НЕ записан")
open(mp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(text2)

# 5. Полный аудит мутаций vs до-мутационный базлайн: дифф обязан содержать ровно 4 намеренных изменения
d = subprocess.run(["git", "diff", "b01b444b", "--", "docs/MUTATIONS.md"],
                    capture_output=True).stdout.decode("utf-8-sig", errors="replace")
adds = [L for L in d.splitlines() if L.startswith("+") and not L.startswith("+++")]
dels = [L for L in d.splitlines() if L.startswith("-") and not L.startswith("---")]
print("дифф vs b01b444b: +%d/-%d (ожидание +4/-2: S325, эскалация, восстановление, "
      "strikethrough / открытая NET, ..." % (len(adds), len(dels)))
for L in dels:
    print("  DEL: %s" % L[:100])

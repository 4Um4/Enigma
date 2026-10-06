import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
mp = os.path.join(ROOT, "docs", "MUTATIONS.md")
raw = open(mp, "rb").read()
bom = raw[:3] == b"\xef\xbb\xbf"
text = raw.decode("utf-8-sig")

# --- ДИАГНОСТИКА (факты: окончания строк + невидимые символы) ---
print(
    "bom=%s  crlf=%d  lf_all=%d  (lf_all > crlf => смешанные окончания)"
    % (bom, text.count("\r\n"), text.count("\n"))
)
logical = text.splitlines()
hits = [(i, L) for i, L in enumerate(logical) if "DEBT-ADR-NET-N/A-FILL" in L]
for i, L in hits:
    print("logical line %d: %r" % (i + 1, L[:110]))

# --- Классификация: S325-запись и закрытие остаются, всё прочее = residual ---
resid = [L for _, L in hits if not L.startswith("- **S325") and "~~DEBT-ADR-NET-N/A-FILL~~" not in L]
if len(resid) != 1:
    raise SystemExit("STOP: residual != 1 (%d) — ручной разбор по repr выше" % len(resid))
victim = resid[0]
print("VICTIM: %r" % victim[:140])
if text.count(victim) != 1:
    raise SystemExit("STOP: victim не уникален в тексте (%d)" % text.count(victim))

# --- Хирургия: удалить ровно строку + её окончание (CRLF / LF / конец файла) ---
for tail in ("\r\n", "\n", ""):
    if victim + tail in text:
        text2 = text.replace(victim + tail, "", 1)
        break
else:
    raise SystemExit("STOP: victim не найден с окончанием")

# --- Пост-верификация (обязательная тройка) ---
g = len(re.findall(r"^- \*\*S[0-9]", text2, re.M))
m = re.search(r"Записей: (\d+)", text2).group(1)
n = text2.count("DEBT-ADR-NET-N/A-FILL")
print("пост: греп=%d МЕТА=%s substring=%d (ожидание 206/206/2)" % (g, m, n))
if not (g == 206 and m == "206" and n == 2):
    raise SystemExit("STOP: пост-верификация не сошлась — файл НЕ записан" if False else "STOP")
open(mp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(text2)
open(os.path.join(ROOT, "reports", "d1_close2_log.txt"), "w", encoding="utf-8").write(
    "S325-followup: удалена выжившая открытая строка долга (дубль закрытия в той же секции).\n"
    "Содержимое сохранено:\n" + victim + "\n")
print("OK — записано; удалённая строка сохранена в reports/d1_close2_log.txt")

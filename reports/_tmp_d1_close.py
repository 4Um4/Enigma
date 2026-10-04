import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
mp = os.path.join(ROOT, "docs", "MUTATIONS.md")
raw = open(mp, "rb").read(); bom = raw[:3] == b"\xef\xbb\xbf"
text = raw.decode("utf-8-sig"); nl = "\r\n" if "\r\n" in text else "\n"

if re.search(r"^- \*\*S325\b", text, re.M):
    raise SystemExit("STOP: S325 занят — Anti-Race, перенумеровать (Устав 11.1.1)")

kr_old = os.path.isfile(os.path.join(ROOT, "backend", "app", "services", "kernel_rng.py"))
kr_npc = os.path.isfile(os.path.join(ROOT, "backend", "app", "services", "npc", "kernel_rng.py"))
if not kr_old and kr_npc:
    s831 = "S83.1: svc/kernel_rng.py — stale-путь атласа (факт: файл = svc/npc/kernel_rng.py);"
elif kr_old:
    s831 = "S83.1: svc/kernel_rng.py существует на диске (DROP = иной дефект);"
else:
    s831 = "S83.1: svc/kernel_rng.py НЕ найден ни в одной форме (stale);"
print("kernel_rng факт:", s831)

old_meta = "Записей: 205 (канон-греп правила 5 по живому файлу;"
if text.count(old_meta) != 1: raise SystemExit("STOP: МЕТА-якорь не уникален (%d)" % text.count(old_meta))

anchor1 = "· ✅ · ea655cdb"
if text.count(anchor1) != 1: raise SystemExit("STOP: якорь S324-хвоста не уникален (%d)" % text.count(anchor1))

# --- ТОЧНЫЙ якорь долга: строка, НАЧИНАЮЩАЯСЯ с записи долга ---
lines_probe = text.split(nl)
debt_idx = [k for k, L in enumerate(lines_probe) if L.startswith("- **DEBT-ADR-NET-N/A-FILL**")]
if len(debt_idx) != 1:
    print("== ALL occurrences (диагностика):")
    for k, L in enumerate(lines_probe):
        if "DEBT-ADR-NET-N/A-FILL" in L:
            print("  line %d: %s" % (k + 1, L[:170]))
    raise SystemExit("STOP: точный DEBT-якорь не уникален (%d) — см. распечатку выше" % len(debt_idx))
print("DEBT-якорь: line %d OK" % (debt_idx[0] + 1))

orac_idx = [k for k, L in enumerate(lines_probe) if L.startswith("- **DEBT-IDLE-ORACLE**")]
if len(orac_idx) != 1: raise SystemExit("STOP: якорь эскалации не уникален (%d)" % len(orac_idx))

# --- Все проверки зелёные: мутируем ---
text = text.replace(old_meta, "Записей: 206 (канон-греп правила 5 по живому файлу;")
s325 = ("- **S325** D1 DEBT-ADR-NET-N/A-FILL исполнен (ветка долгов, продолжение S324): ценз-методология 4 стадии"
        " (regex → SSOM-парсер → xref → волны); батч1: 50 FILLABLE из атласа (Test-Path от ROOT; алиасы svc/dom/mod;"
        " wildcard scene_state/* развёрнут); батч2: 12 NO_HEADER канонизированы (бэктик-шапки по _ADR_LINE_REGEX;"
        " TYPE/Title из атласа как SSOT; O-417 in-place) + волна 1b: 8×Files/29 путей; 2b: iron_river×5/O-414/O-416"
        " (идемпотентный повтор +0); волна3: 19 из law-📁 атласа (семантика law→members = парсерная); гигиена: .pyc"
        " вычищен (мой недосмотр: bounded_search не исключил __pycache__, O-414). Итог: filled 1→78, no_header 12→0,"
        " empty=94 — атлас исчерпан, остаток = пер-файловая археология тел (reports/d1_disposition.txt). Находки:"
        " F1 конвенция S311 «шапки без бэктиков» vs парсер/тест (12 аудитов были невидимы графу), F2 📁-строки невидимы"
        " law-ветке (ищет литерал Files), stale-атлас O-367/O-414/S199(prose-comma в 📁). IPT-гейт: сессия закрывается"
        " при неразрешимом состоянии — SyntaxError state_applicator.py:185 = незакоммиченный WIP M2/D параллельной ветки"
        " (не мой контур); валидные прогоны: 51/51 pre-WIP, 50/1 = их WIP; мои коммиты doc-only, дельта-метод ×3."
        " Коммиты: bd00aa93, c7da6443, 519cb602, b01b444b · ✅ · артефакты reports/d1_*")
i = text.index(anchor1); j = text.index(nl, i)
text = text[:j] + nl + s325 + text[j:]

lines = text.split(nl)
lines[debt_idx[0]] = ("- [x] ~~DEBT-ADR-NET-N/A-FILL~~ ✅ закрыт S325: атлас-источники исчерпаны"
                      " (Files: 1→78 filled, 12 шапок канонизированы, no_header 0). Остаток → новый хвост: 94 empty"
                      " = пер-файловая археология тел аудитов (атлас-источника нет) — reports/d1_disposition.txt;"
                      " отдельная сессия по санкции.")
esc = ("- **ADR-Net структурные находки** (S325 → Мастеру): F1 — конвенция S311 «IMPACT-шапки без бэктиков»"
       " противоречит _ADR_LINE_REGEX + micro-тесту (12 аудитов S316–S322 были невидимы графу ЦЕЛИКОМ;"
       " канонизированы; §13.5: прав код) — ратифицировать бэктик-канон в атласе или parser-fallback;"
       " F2 — 📁-строки законов невидимы law-ветке парсера (ищет литерал \"Files\") — Wave3 перенесла в IMPACT,"
       " генерация из 📁 так и не парсится; stale-атлас: O-367 test_m1 (ветка-only, S320), O-414"
       " consumer_gap_debts.py (удалён S321), " + s831 + " S199 — проза-с-запятой внутри 📁-строки L14.2 рвёт CSV-токен."
       " Артефакт: reports/d1_disposition.txt.")
lines.insert(orac_idx[0], esc)
text = nl.join(lines)

open(mp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(text)
g = len(re.findall(r"^- \*\*S[0-9]", text, re.M))
print("греп после записи: %d (ожидание 206 == МЕТА)" % g)
if g != 206: raise SystemExit("STOP: греп != МЕТА после записи — правило 5 нарушено, откатить вручную")

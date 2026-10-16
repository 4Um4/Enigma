# -*- coding: utf-8 -*-
"""reports/d59_doc_close.py - S354: доковое закрытие D59 (Шаг 2 COV-1, ADR-O-426).

Одноразовый, fail-before-write: ВСЕ проверки до первой записи; любой сбой = [ABORT],
exit(1), файлы не тронуты. BOM и переводы строк каждого файла сохраняются как в исходе.

Правки:
  docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md:
    1) трек COV: «Шаги 2-5 D59/D60/D70/D72» -> «Шаг 2 D59 OK (...) -> Шаги 3-5 ...»
    2) COV-D59: «| открыт |» -> «закрыт (Шаг 2: ADR-O-426, S354 ...)»
    3) §10: строка S354 перед «### 10.1.»
    4) §17.8: запись Шага 2 (состав + инцидент «лживый коммит» + урок) после DET-3 [x] (222bc3d5)
  docs/audits/ADR-O-426_IMPACT.md:
    5) аппенд «## 9. Шаг 2 (D59) ... (исполнено)»
  docs/MUTATIONS.md:
    6) S354 после строки S353; МЕТА «Записей: 235 (» -> «Записей: 236 (S354-... добавлен; »

Запуск:  python reports/d59_doc_close.py [EPI-док-хеш]
  Без аргумента EPI-хеш ищется сам: git log -S S353 -- docs/MUTATIONS.md (гейт: ровно 1).
Откат (до коммита): git checkout -- docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md docs/MUTATIONS.md docs/audits/ADR-O-426_IMPACT.md
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7_EPI-updated.md"
MUT = ROOT / "docs" / "MUTATIONS.md"
IMPACT = ROOT / "docs" / "audits" / "ADR-O-426_IMPACT.md"
REL = ["docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md", "docs/MUTATIONS.md",
       "docs/audits/ADR-O-426_IMPACT.md"]

CODE, TESTS, LIAR, EPIKOD = "f51cc6ae", "5d0748ab", "311cd784", "5bd4592a"

TRACK_OLD = "Шаги 2–5 D59/D60/D70/D72"
TRACK_NEW = ("Шаг 2 D59 ✅ (детект-и-мигрировать/ADR-O-426, S354; детектор CURRENT/"
             "MIGRABLE/UNMIGRABLE, миграции v0→v1, .bak + побайтовая верификация, К3/К5; "
             "код f51cc6ae + тесты 5d0748ab, pytest 42/42) → Шаги 3–5 D60/D70/D72")

D59_CLOSED = ("закрыт (Шаг 2: ADR-O-426, S354 — детект-и-мигрировать; "
              "код f51cc6ae, тесты 5d0748ab, pytest 42/42) |")

S10_LINE = ("- ✅ **S354 / COV-D59 (Шаг 2 COV-1, ADR-O-426)** — save-версионирование сцен "
            "«детект-и-мигрировать»: детектор CURRENT / MIGRABLE (V0_SINGLE | V1_UNSTAMPED) / "
            "UNMIGRABLE (NOT_DICT, CORRUPT_JSON, NEWER_VERSION, UNKNOWN_VERSION, "
            "UNKNOWN_FORMAT, INVALID_V0, INVALID_SCENES, INCONSISTENT_V1); миграция v0 "
            "scene_state → v1 scenes + штамп; .bak из исходных байтов + побайтовая "
            "верификация, BACKUP_CONFLICT, tmp + round-trip, os.replace; К3: "
            "load_refusal_reason + campaign_load_refused (без лживого campaign_loaded); "
            "К5: save_scene_at штампует v1 и снимает scene_state; В7: "
            "CampaignLoadResponse.load_refusal_reason. **Тесты:** pytest 42 passed "
            "(снимки 0.54s и 0.49s). **Коммиты:** код f51cc6ae (v0.5.4.3.7), тесты "
            "5d0748ab (guard-аменд; полная история инцидента — §17.8). **Статус:** Шаг 2 "
            "закрыт; COV-GC-02 остаётся открытым до Шага 3/D60 (В8).")

S178_TMPL = ("- [x] **Шаг 2 COV-1 / COV-D59 [закрыт: реализуется→проверено]** ✅ "
             "save-версионирование «детект-и-мигрировать» (ADR-O-426; S354). Состав: "
             "детектор CURRENT / MIGRABLE (V0_SINGLE | V1_UNSTAMPED) / UNMIGRABLE "
             "(NOT_DICT | CORRUPT_JSON | NEWER_VERSION | UNKNOWN_VERSION | UNKNOWN_FORMAT | "
             "INVALID_V0 | INVALID_SCENES | INCONSISTENT_V1); SAVE_SCHEMA_VERSION=1, явный "
             "schema_version=0 ≠ v0 (v0 = отсутствие поля); миграция v0 scene_state → v1 "
             "scenes + штамп; .bak из исходных байтов + побайтовая верификация, "
             "BACKUP_CONFLICT = отказ; tmp + round-trip + os.replace — единственное "
             "касание живого файла; lifecycle К3: UNMIGRABLE → load_refusal_reason + "
             "campaign_load_refused (без лживого campaign_loaded), после успеха — статус "
             "migrated; писатель К5: save_scene_at штампует v1 и снимает scene_state; "
             "схемы В7: CampaignLoadResponse.load_refusal_reason. Тесты: pytest 42/42, "
             "два снимка (0.54s и 0.49s). Инцидент «лживый коммит» (разрешён, "
             "протоколируется): pathspec 311cd784 внёс только тесты (2 файла, +264/−1) под "
             "сообщением всей реализации; причина — full-save f51cc6ae (релиз v0.5.4.3.7) "
             "подмёл незакоммиченный фича-код D59 (~480 строк, 7 файлов) и чужой "
             "spatial_registry без атрибуции, untracked тест-файл в sweep не попал → "
             "разбивка; форензика четырьмя зондами (статус деревьев, состав релиза, дамп "
             "EPI-грязи, pytest) доказала весь код D59 в f51cc6ae; исправление — "
             "guard-аменд 5d0748ab (гейт «index пуст»), hook compile+arch GREEN, pytest "
             "42/42. Отклонение: amend исполнен до прочтения правила 4 живого реестра "
             "(amend при живых параллельных сессиях запрещён) — на релее Мастера, просится "
             "вердикт. Урок: full-save при незакоммиченном фича-коде = уезд кода в релиз "
             "без атрибуции (кандидат в правила реестра). EPI-контекст: код ME-1.4 "
             "5bd4592a, док-коммит EPI %s.")

IMPACT_LINES = [
    "## 9. Шаг 2 (D59): save-версионирование сцен — «детект-и-мигрировать» (исполнено)",
    "",
    "Статус: Шаг 2 закрыт — S354; COV-D59 → закрыт; COV-GC-01 GREEN наследуется от Шага 1; "
    "COV-GC-02 остаётся открытым до Шага 3/D60. Код: f51cc6ae (вошёл релизным sweep "
    "v0.5.4.3.7); тесты: 5d0748ab; pytest 42/42 (снимки 0.54s и 0.49s); док-закрытие: "
    "реестр MUTATIONS.md S354 + roadmap (трек COV, §10, §17.8).",
    "",
    "Исполнено:",
    "1. Детектор формата сейва: CURRENT / MIGRABLE (V0_SINGLE | V1_UNSTAMPED) / UNMIGRABLE "
    "(NOT_DICT | CORRUPT_JSON | NEWER_VERSION | UNKNOWN_VERSION | UNKNOWN_FORMAT | "
    "INVALID_V0 | INVALID_SCENES | INCONSISTENT_V1). SAVE_SCHEMA_VERSION=1; явный "
    "schema_version=0 не считается v0 (v0 = отсутствие поля).",
    "2. Миграция v0 → v1: scene_state → scenes + штамп schema_version. Резерв: .bak из "
    "исходных байтов + побайтовая верификация копии; BACKUP_CONFLICT — отказ, не "
    "перезапись. Атомарность: tmp + round-trip + os.replace — единственное касание живого "
    "файла.",
    "3. Lifecycle К3: UNMIGRABLE → load_refusal_reason + campaign_load_refused (без "
    "лживого campaign_loaded); после успеха — статус migrated.",
    "4. Писатель К5: save_scene_at штампует v1 и снимает scene_state — новые записи не "
    "рождают v0.",
    "5. Схемы В7: CampaignLoadResponse.load_refusal_reason.",
    "",
    "Инцидент доставки (разрешён): код вошёл релизным full-save f51cc6ae без атрибуции; "
    "pathspec 311cd784 внёс только тесты под сообщением всей реализации; исправлено "
    "guard-амендом 5d0748ab. Полная история и урок — roadmap §17.8 (S354).",
]

REG_CORE_TMPL = ("COV-D59 / Шаг 2 COV-1 (ADR-O-426): док-закрытие save-версионирования "
                 "«детект-и-мигрировать»: трек COV (Шаг 2 D59 ✅), COV-D59 закрыт, §10 + "
                 "§17.8 (инцидент «лживый коммит» разрешён, урок), IMPACT §9; код f51cc6ae "
                 "(v0.5.4.3.7), тесты 5d0748ab, pytest 42/42; EPI: код 5bd4592a, док %s")


def abort(msg):
    print("[ABORT] " + msg)
    sys.exit(1)


def git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def read_tx(p):
    if not p.exists():
        abort("нет файла: %s" % p)
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        tx = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        abort("%s: не utf-8 (%s)" % (p.name, e))
    return tx, bom, ("\r\n" if "\r\n" in tx else "\n")


def write_tx(p, tx, bom, eol):
    data = tx.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    p.write_bytes(data)


def phase0():
    for h, why, req in ((CODE, "код D59", True), (TESTS, "тесты D59", True),
                        (LIAR, "лживый 311cd784 (поглощён амендом; мог быть отпрюнен)", False),
                        (EPIKOD, "EPI-код ME-1.4", True)):
        if git("cat-file", "-e", h + "^{commit}").returncode != 0:
            if req:
                abort("коммит %s (%s) не найден — не тот репо/клон?" % (h, why))
            print("[WARN] коммит %s (%s) отсутствует в объектах — только текст в журнале" % (h, why))
    r = git("status", "--porcelain", "--", *REL)
    if r.returncode != 0 or r.stdout.strip():
        abort("рабочее дерево грязно по докам (параллельная сессия?):\n" + r.stdout)
    epi = sys.argv[1] if len(sys.argv) > 1 else ""
    if epi:
        if git("cat-file", "-e", epi + "^{commit}").returncode != 0:
            abort("аргумент-хеш %s не найден в репо" % epi)
    else:
        r = git("log", "-S", "S353", "--format=%h %s", "--", "docs/MUTATIONS.md")
        rows = [l for l in r.stdout.splitlines() if l.strip()]
        if len(rows) != 1:
            abort("авто-поиск EPI-док-коммита дал %d строк(и) — передай хеш аргументом:\n%s"
                  % (len(rows), r.stdout))
        epi = rows[0].split()[0]
        print("[OK] EPI-док-коммит (добавил S353): %s" % rows[0])
    return epi


def e1_track(tx, eol):
    n = tx.count(TRACK_OLD)
    if n != 1:
        cand = [l for l in tx.split(eol) if "D59" in l and "D72" in l]
        abort("якорь трека COV «%s»: %d вхожд.; строки D59+D72:\n%s"
              % (TRACK_OLD, n, "\n".join(l[:160] for l in cand[:6])))
    i = tx.find(TRACK_OLD)
    ls = tx.rfind("\n", 0, i) + 1
    le = tx.find("\n", i)
    line = tx[ls:le if le != -1 else len(tx)]
    if "MigrationRunner/ADR-O-426" not in line:
        abort("строка трека не содержит MigrationRunner/ADR-O-426 — не та:\n" + line[:300])
    return tx.replace(TRACK_OLD, TRACK_NEW, 1)


def e2_defect(tx, eol):
    rows = [l for l in tx.split(eol) if l.startswith("| COV-D59 |")]
    if len(rows) != 1:
        ids = sorted(set(re.findall(r"\| (COV-D\d+) \|", tx)))
        abort("COV-D59-строк: %d; ID в таблице дефектов: %s" % (len(rows), ", ".join(ids)))
    row = rows[0]
    if "закрыт" in row:
        abort("COV-D59 уже закрыт — повторное применение?\n" + row[:300])
    if not re.search(r"\| открыт \|\s*$", row):
        abort("COV-D59 не заканчивается «| открыт |»:\n" + row[:400])
    new_row = re.sub(r"\| открыт \|\s*$", D59_CLOSED, row)
    return tx.replace(row, new_row, 1)


def e3_s10(tx, eol):
    h = "### 10.1. Унаследованные хвосты журнала (живые владельцы)"
    if tx.count(h) != 1:
        abort("якорь §10.1: %d вхожд." % tx.count(h))
    i = tx.find(h)
    return tx[:i] + S10_LINE + eol + eol + tx[i:]


def e4_s178(tx, eol, epi):
    a = ("- [x] **DET-3 [закрыт: реализуется→проверено]** ✅ Crash-recovery Фазы 10 "
         "(код-коммит 222bc3d5")
    if tx.count(a) != 1:
        loose = [l for l in tx.split(eol) if "222bc3d5" in l]
        abort("якорь §17.8 DET-3[x] (222bc3d5): %d вхожд.; 222bc3d5-строки:\n%s"
              % (tx.count(a), "\n".join(l[:120] for l in loose[:4])))
    i = tx.find(a)
    j = tx.find("\n", i)
    ins = (j + 1) if j != -1 else len(tx)
    return tx[:ins] + (S178_TMPL % epi) + eol + tx[ins:]


def e5_impact(tx, eol):
    if "## 9." in tx or re.search(r"\bS354\b", tx):
        abort("IMPACT уже содержит §9/S354 — повторное применение?")
    if not tx.endswith("\n"):
        tx += eol
    return tx + eol + eol.join(IMPACT_LINES) + eol


def e6_mut(tx, eol, epi):
    if re.search(r"\bS354\b", tx):
        abort("реестр уже содержит S354 — повторное применение?")
    nums = [int(x) for x in re.findall(r"\bS(\d{3})\b", tx)]
    if not nums:
        abort("S-номера в MUTATIONS.md не найдены")
    smax = max(nums)
    if smax != 353:
        abort("живой max S = %d (ожидался 353) — реестр дрейфнул, проверь" % smax)
    m = re.search(r"Записей: (\d+) \(", tx)
    if not m:
        m2 = re.search(r"Записей: (\d+)", tx)
        abort("МЕТА «Записей: N (» не найдена; что есть: %s"
              % (m2.group(0) if m2 else "ничего"))
    cnt = int(m.group(1))
    if cnt != 235:
        abort("МЕТА «Записей: %d» (ожидалось 235) — дрейф" % cnt)
    s353 = [l for l in tx.split(eol) if re.search(r"\bS353\b", l)]
    if len(s353) != 1:
        cand = [l for l in tx.split(eol) if "S35" in l]
        abort("S353-строк: %d; S35*-строки:\n%s"
              % (len(s353), "\n".join(l[:160] for l in cand[:8])))
    row = s353[0]
    print("══ S353-строка (формат-эталон — сверить вставку в git diff):")
    print(row)
    core = REG_CORE_TMPL % epi
    if row.lstrip().startswith("|"):
        s354 = "| S354 | " + core + " | закрыт |"
    elif row.lstrip().startswith("- "):
        s354 = "- S354 — " + core
    else:
        s354 = "S354 — " + core
    i = tx.find(row)
    tx = tx[:i + len(row)] + eol + s354 + tx[i + len(row):]
    if len(re.findall(r"\bS354\b", tx)) != 1:
        abort("внутренняя ошибка: после вставки S354 не единственный")
    tx = tx.replace("Записей: 235 (", "Записей: 236 (S354-COV-D59-док-закрытие добавлен; ", 1)
    return tx


def main():
    epi = phase0()
    rt, rb, reol = read_tx(ROADMAP)
    mt, mb, meol = read_tx(MUT)
    it, ib, ieol = read_tx(IMPACT)

    if re.search(r"\bS354\b", rt) or "Шаг 2 D59 ✅" in rt:
        abort("roadmap уже содержит S354 / «Шаг 2 D59 ✅» — повторное применение?")
    if any("закрыт" in l for l in rt.split(reol) if l.startswith("| COV-D59 |")):
        abort("COV-D59 уже закрыт — повторное применение?")
    if "## 9." in it or re.search(r"\bS354\b", it):
        abort("IMPACT уже содержит §9/S354 — повторное применение?")

    rt = e1_track(rt, reol)
    rt = e2_defect(rt, reol)
    rt = e3_s10(rt, reol)
    rt = e4_s178(rt, reol, epi)
    it = e5_impact(it, ieol)
    mt = e6_mut(mt, meol, epi)

    write_tx(ROADMAP, rt, rb, reol)
    write_tx(MUT, mt, mb, meol)
    write_tx(IMPACT, it, ib, ieol)

    print("[OK] S354 записан: трек COV (Шаг 2 D59 ✅); COV-D59 закрыт; §10-строка; "
          "§17.8 (состав + инцидент + урок); IMPACT §9; реестр 235→236.")
    print("[OK] EPI-док-коммит в записях: %s" % epi)
    r = git("diff", "--stat", "--", *REL)
    print(r.stdout)
    print("Дальше: git diff -- docs/MUTATIONS.md (глазами, формат S354 против S353), "
          "затем pathspec-коммит — без amend, без push.")


if __name__ == "__main__":
    main()

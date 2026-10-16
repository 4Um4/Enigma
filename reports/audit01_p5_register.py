#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S353 / ТЗ АУДИТ-01 — Пакет 5: регистрация находок в docs (fail-before-write).

Правки (три файла, четыре точки; прецедент — reports/b1_zone_restore.py, S352):
  R1  атлас ADR : мини-ADR ADR-O-427 [INFRA] — после блока ADR-O-426
  R2  roadmap   : реестр §7.12 АУДИТ-01 — перед «## 8. MASTER TODO»
      (слот §7.11 занят реестром EPI-D от 2026-10-16, потому §7.12;
       ссылка в строке S353 патчится правкой R4 — строка ещё не в каноне)
  R3  roadmap   : строка журнала §10 — перед «> Архивные строки журнала»
  R4  MUTATIONS : S353 — «(мини-ADR)»→«(мини-ADR ADR-O-427)» и
      «находки → roadmap §7.11»→«находки → roadmap §7.12»

Режимы:
  --dry-run            (умолчание) только гейты и превью, диск не тронут
  --apply              все гейты GREEN -> запись трёх файлов
  --stamp-hash <sha>   после кода-коммита: «ADR-O-427; коммиты <sha>» в S353

Гейты — ВСЕ до первой записи (любой RED = abort, диск не тронут):
  G1 якоря уникальны (×1): «## 8. MASTER TODO»; «> Архивные строки журнала»;
     «`ADR-O-426»; «- **S353**»
  G2 слоты свободны (×0): «ADR-O-427» (атлас); «### 7.12.» (roadmap);
     IPT-D1/PATH-D1/STALE-D1/INFRA-D1/HYG-D1/GC-DIALOGUE-01/АУДИТ-01 (roadmap)
  G3 чужое не тронуто: «| EPI-D» = 14 до и после (реестр §7.11 read-only)
  G4 MUTATIONS: «Записей: 236» ×1; S353 содержит обе цели R4; после — обе замены
  G5 PATH_D1_FILES заполнен (файлы фикса PATH-D1 из git diff, шаг 0 ранбука)
  G6 EOL (CRLF/LF) и BOM сохранены (UTF-8, побайтово, кроме целевых вставок)

Запуск из корня репо: python reports/audit01_p5_register.py --dry-run
"""

import sys

ROADMAP = "docs/ENIGMA_ROADMAP_v4_7_EPI-updated.md"
ATLAS = "docs/ADR (Architecture Decision Records).md"
MUT = "docs/MUTATIONS.md"

# ── ЗАПОЛНИ (шаг 0 ранбука): только файлы фикса PATH-D1 из git diff, например:
# PATH_D1_FILES = "`backend/app/...py`, `backend/app/...py`"
PATH_D1_FILES = "`backend/app/services/spatial/spatial_registry.py`"

SEC712 = """### 7.12. АУДИТ-01 (реестр находок аудита доказательного слоя «Честный IPT», 2026-10-15/16; аудит на коде V.0.5.4.3.6, исполнение — S353)

> Основа — ТЗ АУДИТ-01 «Честный IPT и гигиена доказательного слоя» (S353, Пакеты 1–5); правило ТЗ: Y>0 skipped = непроверенные входы. Канон записи сессии — MUTATIONS S353 (гейты: ruff 0; сьют 2447/33/8/0; IPT 53/0/0 ×2; GC-11 — тёплая пара S316 при чистом окне тишины и mtime-стабильности). Вердикт-контракт ADR-O-399 проверен археологией (ACTIVE/CLOSED S270: A1==A2 межпроцессно; IMPACT-файл, drain_task_worker_outbox и SUPERBOX-вердикты на месте) — нарушений нет; roadmap-обязательств по O-399 нет (SSOT — атлас). Прод-фиксы PATH-D1/STALE-D1 — по санкции Мастера. Хвост S351 сохраняется: шапка «IPT 49/49»→53 — за Мастером (§R.7).

| ID | Находка | P | Действие | Статус |
|---|---|---|---|---|
| IPT-D1 | IPT не различал skipped: формат «53/53» при Y>0 скрывал непроверенные входы | P1 | InvariantResult.skipped + формат «X passed / Y skipped / 0 failed» + поимённый перечень; тройка CARDINALITY живая (§14.1: 1 тик=10.0с, N=3 — отклонение от N=2/N=5 по директиве Мастера «карта из игры»); стаб планировщика дополнен + откат | закрыто (S353) |
| INFRA-D1 | LLM-гейт не самодостаточен: мок/неявный skip маскируют готовность; GC-11 давал ложный PASS (направления trust инвертированы) | P1 | GC-11 самодостаточен: реальный LLM автостартом менеджера, INFRA-skip при честном отказе (мок не подставляется, ADR-O-425); направления trust выровнены | закрыто (S353; тёплая пара S316: 24.67с/22.52с, [DIAG-LLM] slow-path, автостарт/автостоп llama-server) |
| HYG-D1 | Доказательный слой рассинхронизирован: 54 файла вне reports/probes/, 10 _tmp (0 ссылок), 5 битых путей | P2 | 54→reports/probes/; 10 _tmp удалены; 5 путей патчены | закрыто (S353) |
| PATH-D1 | find_artifact и путь писателя расходились: артефакт ищется не там, куда пишет writer | P1 | единый SSOT-путь (мини-ADR ADR-O-427); санкция Мастера | закрыто (S353, ADR-O-427) |
| STALE-D1 | Карта артефактов/путей устарела после переносов П4 | P2 | пересборка карты; санкция Мастера | закрыто (S353) |
| GC-DIALOGUE-01 | Тёплая пара: intent seek_ally → seek_ally — ландшафт решений по intent не сдвинулся (сдвиг виден только в trust-дельте None→2.49); вопрос порога/ассерта ландшафта | P2 | релея в GC-трек: усилить ассерт intent-сдвига или зафиксировать доверительный порог; диагностика STEP1/STEP2 уже в тесте | открыт (владелец: GC-трек / Мастер) |

P0-сводка: собственного P0 нет (P1×3, P2×3 — целостность процесса доказательств, не ядра); открытый хвост один — GC-DIALOGUE-01 (релея); иных релеев в чужие треки нет."""

JOURNAL_ROW = ("| 2026-10-16 | Б: S353 ТЗ АУДИТ-01 (Пакеты 1–5: честный IPT; RED→xfail FR-11.2/CCH-4; "
               "GC-11 самодостаточен; гигиена probes; PATH-D1/STALE-D1 прод; реестр §7.12) | "
               "GC-11 тёплая пара (окно тишины; mtime-стабильность 21:26:55-56) + археология ADR-O-399 + ruff | "
               "GREEN: GC-11 2 passed ×2 (24.67с/22.52с; [DIAG-LLM] slow-path; trust player→maid_lusya None→0.5; "
               "STEP2 trust None→2.49, intent seek_ally→seek_ally); O-399 ACTIVE/CLOSED S270 (IMPACT+дренаж+SUPERBOX живы); "
               "ruff 0; сьют 2447/33/8/0 и IPT 53/0/0 ×2 — в сессии | — ; GC-DIALOGUE-01 — релея §7.12 |")

ADR427 = """ADR-O-427 [INFRA] **Artifact Path SSOT — find_artifact + путь писателя** (S353)
Суть: аудит АУДИТ-01 (находка PATH-D1, санкция Мастера) зафиксировал расхождение пути поиска и пути записи артефактов доказательного слоя: find_artifact искал не там, куда пишет writer; после гигиены П4 (54 файла → reports/probes/) такое расхождение теряет артефакты («записан — не найден»). Лечение: единый SSOT-путь — find_artifact и writer обязаны читать одну каноническую константу; запись и поиск не могут разойтись. Границы вердикт-контракта ADR-O-399 проверены археологией (ACTIVE/CLOSED S270) — не нарушены: точек дренажа/менеджеров/шин не добавлено.
❌ Taboo: хардкод пути в точке вызова; второй источник правды о расположении артефактов; «фикс» обходом всего дерева вместо SSOT; перенос файлов без обновления SSOT; молчаливый fallback на старый путь.
Status: ACTIVE (S353: PATH-D1 закрыт; гейты — MUTATIONS S353)
Files: {files}"""


def read_lines(path):
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig" if bom else "utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    return bom, eol, text.splitlines(keepends=True)


def write_lines(path, lines, bom):
    data = "".join(lines).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with open(path, "wb") as f:
        f.write(data)


def bare(line):
    return line.rstrip("\r\n")


def gate(ok, name):
    print(("  [GREEN] " if ok else "  [RED]   ") + name)
    return ok


def count(lines, pred):
    return sum(1 for ln in lines if pred(ln))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--stamp-hash":
        stamp_hash(sys.argv[2] if len(sys.argv) > 2 else "")
        return
    try:
        rb, reol, rlines = read_lines(ROADMAP)
        ab, aeol, alines = read_lines(ATLAS)
        mb, _meol, mlines = read_lines(MUT)
    except FileNotFoundError as e:
        print("ABORT: не найден %s — запусти из корня репо" % e.filename)
        sys.exit(1)

    print("== Гейты (все до первой записи) ==")
    ok = True
    ok &= gate(count(rlines, lambda ln: bare(ln).startswith("## 8. MASTER TODO")) == 1,
               "G1 roadmap: «## 8. MASTER TODO» ×1")
    ok &= gate(count(rlines, lambda ln: bare(ln).startswith("> Архивные строки журнала")) == 1,
               "G1 roadmap: «> Архивные строки журнала» ×1")
    ok &= gate(count(alines, lambda ln: bare(ln).startswith("ADR-O-426")) == 1,
               "G1 атлас: «ADR-O-426» ×1")
    ok &= gate(count(mlines, lambda ln: bare(ln).startswith("- **S353**")) == 1,
               "G1 MUTATIONS: «- **S353**» ×1")
    ok &= gate(count(alines, lambda ln: "ADR-O-427" in ln) == 0,
               "G2 атлас: «ADR-O-427» ×0 (номер свободен)")
    ok &= gate(count(rlines, lambda ln: bare(ln).startswith("### 7.12.")) == 0,
               "G2 roadmap: «### 7.12.» ×0 (слот свободен)")
    for pat in ("IPT-D1", "PATH-D1", "STALE-D1", "INFRA-D1", "HYG-D1",
                "GC-DIALOGUE-01", "АУДИТ-01"):
        ok &= gate(count(rlines, lambda ln, p=pat: p in ln) == 0,
                   "G2 roadmap: «%s» ×0 (дублей нет)" % pat)
    ok &= gate(count(rlines, lambda ln: bare(ln).startswith("| EPI-D")) == 14,
               "G3 roadmap: «| EPI-D» = 14 (реестр §7.11 read-only)")
    ok &= gate(count(mlines, lambda ln: "Записей: 236" in ln) == 1,
               "G4 MUTATIONS: «Записей: 236» ×1")
    s353 = next((ln for ln in mlines if bare(ln).startswith("- **S353**")), "")
    ok &= gate("(мини-ADR), STALE-D1" in s353 and "находки → roadmap §7.11" in s353,
               "G4 S353: обе цели R4 на месте")
    if mode == "--apply":
        ok &= gate(bool(PATH_D1_FILES.strip()), "G5 PATH_D1_FILES заполнен")
    else:
        print("  [WARN]  G5 PATH_D1_FILES пуст — заполни перед --apply (шаг 0 ранбука)")

    if not ok:
        print("\nABORT: RED-гейты; диск не тронут.")
        sys.exit(1)

    # ---- правки в памяти (диск ещё не тронут) ----
    # R2: реестр §7.12 перед «## 8. MASTER TODO»
    i8 = next(i for i, ln in enumerate(rlines) if bare(ln).startswith("## 8. MASTER TODO"))
    ins_sec = [s + reol for s in SEC712.split("\n")] + ["" + reol, "---" + reol, "" + reol]
    new_r = rlines[:i8] + ins_sec + rlines[i8:]
    # R3: строка §10 перед «> Архивные строки журнала»
    ij = next(i for i, ln in enumerate(new_r)
              if bare(ln).startswith("> Архивные строки журнала"))
    new_r = new_r[:ij] + [JOURNAL_ROW + reol] + new_r[ij:]

    # R1: мини-ADR ADR-O-427 после блока O-426
    i426 = next(i for i, ln in enumerate(alines) if bare(ln).startswith("ADR-O-426"))
    j = len(alines)
    for k in range(i426 + 1, len(alines)):
        b = bare(alines[k])
        if b.startswith("`ADR-O-") or b.startswith("#"):
            j = k
            break
    adr = [s.replace("{files}", PATH_D1_FILES.strip() or "<<PATH_D1_FILES — заполни>>") + aeol
           for s in ADR427.split("\n")]
    if j == len(alines):
        # O-426 — последний блок: аппенд в конец
        if alines and not alines[-1].endswith(("\n", "\r")):
            alines[-1] = alines[-1] + aeol
        lead = ["" + aeol] if bare(alines[-1]) else []
        new_a = alines + lead + adr
    else:
        ins_a = adr + ["" + aeol]
        if bare(alines[j - 1]):
            ins_a = ["" + aeol] + ins_a
        new_a = alines[:j] + ins_a + alines[j:]

    # R4: две замены в строке S353
    new_m = []
    for ln in mlines:
        if bare(ln).startswith("- **S353**"):
            ln = ln.replace("(мини-ADR), STALE-D1", "(мини-ADR ADR-O-427), STALE-D1")
            ln = ln.replace("находки → roadmap §7.11", "находки → roadmap §7.12")
        new_m.append(ln)
    s353n = next(ln for ln in new_m if bare(ln).startswith("- **S353**"))

    ok2 = True
    ok2 &= gate("(мини-ADR ADR-O-427), STALE-D1" in s353n
                and "находки → roadmap §7.12" in s353n,
                "G4' R4 применён к S353 (в памяти)")
    ok2 &= gate(count(new_r, lambda ln: bare(ln).startswith("| EPI-D")) == 14,
                "G3' после правок: «| EPI-D» = 14 (EPI-D не тронут)")

    print("\n== Превью ==")
    print("  roadmap  : +%d строк §7.12 перед «## 8. MASTER TODO»; +1 строка §10" % len(ins_sec))
    print("  атлас    : +%d строк ADR-O-427 (точка: %s)" %
          (len(adr), "EOF" if j == len(alines)
           else "перед «" + bare(alines[j])[:40] + "…»"))
    print("  MUTATIONS: 2 замены в S353 (мини-ADR ADR-O-427; §7.11→§7.12)")
    print("  §7.12:   " + SEC712.split("\n")[0][:96] + "…")

    if mode != "--apply":
        print("\nDRY-RUN: гейты %s; диск не тронут." % ("зелёные" if ok2 else "КРАСНЫЕ"))
        sys.exit(0 if ok2 else 1)
    if not ok2:
        print("\nABORT: пост-гейты RED; диск не тронут.")
        sys.exit(1)

    write_lines(ROADMAP, new_r, rb)
    write_lines(ATLAS, new_a, ab)
    write_lines(MUT, new_m, mb)
    print("\nAPPLY: записаны roadmap (+%d и +1), атлас (+%d), MUTATIONS (2 замены в S353)."
          % (len(ins_sec), len(adr)))


def stamp_hash(h):
    if not h:
        print("ABORT: usage --stamp-hash <short_sha>")
        sys.exit(1)
    mb, _eol, mlines = read_lines(MUT)
    out, n = [], 0
    for ln in mlines:
        if bare(ln).startswith("- **S353**") and "· ✅ · находки → roadmap §7.12" in ln:
            ln = ln.replace("· ✅ · находки → roadmap §7.12",
                          "· ✅ · ADR-O-427; коммиты " + h + " · находки → roadmap §7.12")
            n += 1
        out.append(ln)
    if n != 1:
        print("ABORT: целей штампа %d (ожидалась 1) — сперва выполни --apply" % n)
        sys.exit(1)
    write_lines(MUT, out, mb)
    print("OK: S353 — «ADR-O-427; коммиты %s»" % h)


if __name__ == "__main__":
    main()

from __future__ import annotations

# reports/b1_zone_restore.py
"""
Одноразовый доковый скрипт restore зоны Б roadmap (Anti-Race №3; приёмник Б-1).
Параллельный WIP (230518bc -> 65113fbd) перезаписал roadmap на до-Шаговой базе:
не сохранены чужие строки зоны Б — журнал §17.8 (COV-1 Шаг 1, DET-1), чекбоксы
DET-1..DET-3 и статусы Шага 1 (GC-01/D58/D100/COV-1/трек COV). Правки
det2_close.py не были применены (дефект якоря «гистерезис;тест» без пробела —
abort до записи), DET-3 закрывался без доковых правок — обе строки
восстанавливаются здесь впервые.
Источники (нулевая ручная транскрипция): константы close-скриптов (ast);
блоб 93a69179 (git show) — дословность закоммиченного; живой файл — заголовок
§17.8 и [ ]-строка DET-3. Гейты: OLD==1 live; NEW==0 live (идемпотентность);
NEW Шага 1/DET-1 ==1 в блобе; DET-2/DET-3-закрытия ==0 в блобе; зона А
(DLG/NL-8b/GC-58/§9.13/NL-D18/D19/W14) до и после; дельта строк +4.
ABORT до записи при любом несовпадении. НЕ перезапускать после коммита.
"""

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7.md"
BLOB_COMMIT = "93a69179"

HDR_PREFIX = "### 17.8. Детерминизм"
DET3_PREFIX = "- [ ] **DET-3 [реализуется] Crash-recovery тест**"

# DET-3: формулировка по прецеденту DET-2 (числа из коммит-сообщения 222bc3d5).
DET3_NEW = (
    "- [x] **DET-3 [закрыт: реализуется→проверено]** ✅ Crash-recovery Фазы 10 "
    "(код-коммит 222bc3d5; тест backend/tests/micro/test_det3_crash_recovery.py): "
    "карта границ атомарности по археологии — L1-флеш внутри Фазы 10 идемпотентен "
    "(INSERT OR IGNORE + UNIQUE), runtime — atomic_commit_all одной транзакцией, "
    "epistemic/conclusions — payload внутри сцен; cross-file атомарности нет "
    "BY CONSTRUCTION — инвариант «последнее допустимое зафиксированное состояние "
    "+ самовосстановление повтором тика; дублей нет (UNIQUE), частичных мутаций "
    "нет (транзакции)». Интеграционный тест 3/3 (живой kill процесса + spawn-воркер, "
    "os._exit без WAL-чисток): T1 до-Фазы-10-флеша / T2 ядро cross-file окна "
    "(L1 записан, runtime нет → рестарт + повтор тика: ноль дублей) / T3 чистая "
    "точка — полное совпадение. Воркер сам зовёт MigrationRunner.run_startup_migrations "
    "(стампинг tmp-БД — прототип будущего старт-гейта D70; идемпотентность T6 на "
    "живом пути). Процесс-уроки: select только по сокетам на Windows (WinError "
    "10038); fd-пайпы не наследуются spawn — kill-сигнал файлом-маркером; "
    "sqlite3.connect на каталоге = unable to open (RS-SPY-репродукция); воркер-пути "
    "= prod-структура (replay_sessions/replay.db). Полная карта границ — в "
    "сообщении коммита 222bc3d5."
)

J_DET3 = (
    "- ✅ **DET-3 (§17.8 / вердикт III.3)** — crash-recovery Фазы 10: карта границ "
    "атомарности (L1 идемпотентен INSERT OR IGNORE+UNIQUE; runtime — одна транзакция; "
    "epistemic/conclusions — payload внутри сцен; cross-file атомарности нет by "
    "construction — самовосстановление повтором тика, дублей/частичных мутаций нет); "
    "интеграционный тест 3/3 (живой kill + spawn: T1 до-Фазы-10 / T2 cross-file окно "
    "L1-записан-runtime-нет → рестарт без дублей / T3 чистая точка); воркер сам зовёт "
    "MigrationRunner — прототип старт-гейта D70; код 222bc3d5; полная карта границ — "
    "в сообщении коммита."
)

# Зона А (контент 230518bc/65113fbd) — обязана уцелеть; проверка до и после.
ZONE_A_SPOTS = (
    "### 3.6. DLG — Диалоговая вертикаль «ИГРОК=НПС» (v4.7-draft)",
    "NL-8b — Receptivity Contract",
    "GC-58 — «Связный ответ всегда»",
    "### 9.13. Vision suite",
    "NL-D18",
    "**W14** NL-8b",
)


def _abort(msg: str) -> None:
    print(f"[ABORT] {msg}")
    print("[ABORT] Стоп ДО записи: файл не изменён.")
    sys.exit(1)


def _load(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _save(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def _short(s: str) -> str:
    return s if len(s) < 240 else s[:240] + "…"


def _pair(label: str, old: str, new: str) -> None:
    print()
    print(f"══ {label} — БЫЛО ══")
    print(_short(old))
    print(f"══ {label} — СТАЛО ══")
    print(_short(new))


def _consts(script: str, names: tuple[str, ...]) -> dict[str, str]:
    """Строковые константы close-скрипта; источник = файл на диске (не память/паста)."""
    src = (ROOT / "reports" / script).read_bytes().decode("utf-8-sig")
    found: dict[str, str] = {}
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in names
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            found[node.targets[0].id] = node.value.value
    missing = [n for n in names if n not in found]
    if missing:
        _abort(f"{script}: константы не найдены: {missing}")
    return found


def _blob() -> str:
    r = subprocess.run(["git", "show", f"{BLOB_COMMIT}:docs/ENIGMA_ROADMAP_v4_7.md"],
                       capture_output=True, cwd=ROOT)
    if r.returncode != 0:
        _abort("git show " + BLOB_COMMIT + " не удался: "
               + r.stderr.decode(errors="replace")[:200])
    return r.stdout.decode("utf-8-sig")


def main() -> None:
    print("[Б-1 restore] Восстановление зоны Б roadmap после Anti-Race №3.")

    live, bom = _load(ROADMAP)
    if "закрыт (Шаг 1: ADR-O-426" in live:
        _abort("маркер закрытия D58 уже в файле — restore уже исполнен?")
    if "\r\n" in live:
        _abort("живой файл содержит CRLF — противоречит прецеденту cov1; покажи файл")

    cov1 = _consts("cov1_step1_close.py", (
        "GC01_OLD", "GC01_NEW", "D58_OLD_TAIL", "D58_NEW_TAIL",
        "D100_OLD_TAIL", "D100_NEW_TAIL", "COV1_STEP_OLD", "COV1_STEP_NEW",
        "COV_TRACK_OLD_TAIL", "COV_TRACK_NEW_TAIL", "JOURNAL_LINE"))
    det1 = _consts("det1_close.py", ("DET1_OLD", "DET1_NEW", "JOURNAL_LINE"))
    det2 = _consts("det2_close.py", ("DET2_OLD", "DET2_NEW", "JOURNAL_LINE"))
    j_cov1, j_det1, j_det2 = (cov1["JOURNAL_LINE"], det1["JOURNAL_LINE"],
                              det2["JOURNAL_LINE"])

    hdr = [ln for ln in live.split("\n") if ln.startswith(HDR_PREFIX)]
    if len(hdr) != 1:
        _abort(f"заголовок §17.8 по префиксу найден {len(hdr)} раз")
    marker = hdr[0]
    d3 = [ln for ln in live.split("\n") if ln.startswith(DET3_PREFIX)]
    if len(d3) != 1:
        _abort(f"DET-3 [ ]-строка по префиксу найдена {len(d3)} раз")
    det3_old = d3[0]

    blob = _blob()

    olds = {
        "§9.3f COV-GC-01": cov1["GC01_OLD"],
        "§7.10 COV-D58 (хвост)": cov1["D58_OLD_TAIL"],
        "§7.10 COV-D100 (хвост)": cov1["D100_OLD_TAIL"],
        "§17.5 COV-1 (ступень)": cov1["COV1_STEP_OLD"],
        "§0.1 трек COV (хвост)": cov1["COV_TRACK_OLD_TAIL"],
        "§17.8 DET-1": det1["DET1_OLD"],
        "§17.8 DET-2": det2["DET2_OLD"],
        "§17.8 DET-3": det3_old,
    }
    news = {
        "§9.3f COV-GC-01": cov1["GC01_NEW"],
        "§7.10 COV-D58 (хвост)": cov1["D58_NEW_TAIL"],
        "§7.10 COV-D100 (хвост)": cov1["D100_NEW_TAIL"],
        "§17.5 COV-1 (ступень)": cov1["COV1_STEP_NEW"],
        "§0.1 трек COV (хвост)": cov1["COV_TRACK_NEW_TAIL"],
        "§17.8 DET-1": det1["DET1_NEW"],
        "§17.8 DET-2": det2["DET2_NEW"],
        "§17.8 DET-3": DET3_NEW,
    }
    journal = [j_cov1, j_det1, j_det2, J_DET3]

    # Гейты A: живой файл.
    for label, s in olds.items():
        if live.count(s) != 1:
            _abort(f"якорь {label}: найден {live.count(s)} раз (ожидался 1)")
    for label, s in news.items():
        if live.count(s) != 0:
            _abort(f"идемпотентность {label}: NEW уже присутствует")
    for i, s in enumerate(journal, 1):
        if live.count(s) != 0:
            _abort(f"идемпотентность: журнал-строка #{i} уже присутствует")
    for spot in ZONE_A_SPOTS:
        if spot not in live:
            _abort("зона А до правок: маркер отсутствует: " + spot[:48] + "…")

    # Гейты B: блоб 93a69179 — дословность ранее закоммиченного.
    blob_one = {
        "GC01_NEW": cov1["GC01_NEW"], "D58_NEW_TAIL": cov1["D58_NEW_TAIL"],
        "D100_NEW_TAIL": cov1["D100_NEW_TAIL"],
        "COV1_STEP_NEW": cov1["COV1_STEP_NEW"],
        "COV_TRACK_NEW_TAIL": cov1["COV_TRACK_NEW_TAIL"],
        "журнал COV-1 Шаг 1": j_cov1, "DET1_NEW": det1["DET1_NEW"],
        "журнал DET-1": j_det1, "DET2_OLD": det2["DET2_OLD"],
        "DET3_OLD": det3_old, "заголовок §17.8": marker,
    }
    for label, s in blob_one.items():
        if blob.count(s) != 1:
            _abort(f"блоб {BLOB_COMMIT}: {label} найден {blob.count(s)} раз (ожидался 1)")
    if blob.count(j_det2) != 0:
        _abort("блоб: журнал-строка DET-2 уже есть — противоречит модели истории")
    if blob.count(DET3_NEW) != 0 or blob.count(J_DET3) != 0:
        _abort("блоб: DET-3-закрытие уже есть — противоречит модели истории")
    print(f"[OK] Блоб-гейты {BLOB_COMMIT}: {len(blob_one)} дословных якорей GREEN.")

    # Правки: 8 замен + журнал-блок ×4 после заголовка §17.8.
    nl_before = live.count("\n")
    for label in olds:
        _pair(label, olds[label], news[label])
        live = live.replace(olds[label], news[label], 1)
    _pair("§17.8 журнал (вставка ×4)", marker, marker + "\n" + "\n".join(journal))
    live = live.replace(marker, marker + "\n" + "\n".join(journal), 1)

    print()
    print("══ §17.8 DET-3 [x] — полный текст (авторская формулировка) ══")
    print(DET3_NEW)
    print("══ §17.8 журнал DET-3 — полный текст ══")
    print(J_DET3)

    # Пост-гейты.
    for label, s in news.items():
        if live.count(s) != 1:
            _abort(f"пост {label}: присутствует {live.count(s)} раз (ожидался 1)")
    for i, s in enumerate(journal, 1):
        if live.count(s) != 1:
            _abort(f"пост: журнал-строка #{i} присутствует {live.count(s)} раз")
    for spot in ZONE_A_SPOTS:
        if spot not in live:
            _abort("пост: зона А потеряла маркер: " + spot[:48] + "…")
    if live.count(marker) != 1:
        _abort("пост: заголовок §17.8 повреждён")
    nl_after = live.count("\n")
    if nl_after - nl_before != 4:
        _abort(f"пост: дельта строк {nl_after - nl_before} != 4")

    _save(ROADMAP, live, bom)
    print()
    print("[OK] Записано: 8 замен — GC-01 [x]; D58/D100 закрыты; COV-1 и трек COV (Шаг 1); DET-1/2/3 [x].")
    print("[OK] Записано: журнал §17.8 ×4: COV-1 Шаг 1 -> DET-1 -> DET-2 -> DET-3.")
    print("[OK] Далее отдельными шагами: IPT-хвост + validate_doc_refs -> pathspec-коммит -> S352 в MUTATIONS.")


if __name__ == "__main__":
    main()
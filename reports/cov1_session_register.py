from __future__ import annotations

# reports/cov1_session_register.py
"""
Одноразовый скрипт записи сессии в docs/MUTATIONS.md (протокол v5.0:
однострочник; тела сессий НЕ пишутся — решения в ADR/IMPACT, хроника
в git/roadmap-§10). Обновления:
  - реестр: строка - **S<N>** … после реестровой строки с МАКСИМАЛЬНЫМ
    номером (не хардкод: серия может записаться между чтением и записью);
  - МЕТА: счётчик динамический +1 по regex (инцидент: фиксированный якорь
    «Записей: 231» поймал ABORT — параллельная серия уже сдвинула МЕТА);
    Базлайн: IPT 52/52 -> 53/53 (легальная эволюция: S317->50, S319->51);
    уже 53/53 — пропуск без правки.
Гейт номера: S<N> = числовой max по живому файлу + git log --all + 1;
уже занят -> ABORT. Пары БЫЛО/СТАЛО печатаются.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUT = ROOT / "docs" / "MUTATIONS.md"


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


SESSION_LINE_TMPL = (
    "- **S{n}** COV-1 Шаг 1 (ветка Б; ТЗ-приёмник S343-S345): MigrationRunner (ADR-O-426) — "
    "per-file цепочки PRAGMA user_version над 3 файлами-семействами (enigma_memory HEAD=2: база 5 таблиц "
    "+ ленивые расширения L1 l1_chronicle_events/archive + L2.5 crystallized_beliefs — классификатор "
    "семейства 8 таблиц, дефект 5-таблицной модели пойман dry-run на копии, живой файл не тронут; "
    "enigma_runtime 1; replay 1 — путь settings.replay_store_path, Н-2 закрыт: БД существует 436 МБ — вход "
    "для D72) + bootstrap по маркерам (неоднозначно -> отказ без изменения файла) + бэкап online backup API "
    "с тройной верификацией + аудит _schema_migrations одной транзакцией с DDL/user_version + "
    "register_migrations (S1-контракт Ф9: А подключает event_memories поверх, раннер не редактируется) + "
    "даунгрейд-блок; перенос ad-hoc ALTER-гварда secret_id в миграцию 1->2 (последний снифинг-паттерн "
    "sqlite_store.py:186-197); стампинг живых БД по вердикту I.3 (8 условий: dry-run на копиях -> отчёт -> "
    "подтверждение -> apply; все три базы базлайн-штампом без DDL, данные не тронуты; 3 верифицированных "
    ".pre-migration.bak 10.8МБ/0.4МБ/457МБ; reports/cov1_stamp_report.{{json,md}}); обязательный "
    "lint_sqlite_registry (вердикт I.2: незарегистрированный стор = блокирующий RED, не warning; census 4 "
    "файла/8 сайтов) + INV-SQLITE-REGISTRY в IPT (52->53; сигнатура канона *_ctx) + pre-commit hook (до "
    "hooksPath-решения покыт IPT/CI); burial ExpectationStore (COV-D100, вердикт II.Г: DEL файла + "
    "могильные комментарии зоны Б + allowlist-хвосты lint_kernel_rng/lint_wall_clock + Устав §3 Фаза 0.5 "
    "и §12.5 по протоколу §9, журнал изменений создан; У-2 закрыт: стор был мёртв — 0 инстанцирований, "
    "memory.db не существовал); приёмка поймала 4 дефекта до живых данных (SyntaxError-гейт скрипта "
    "burial — py_compile теперь первый гейт блоков; пост-проверка данных раннера — семантика сохранности, "
    "не заморозки схемы, T1/T10/T11; sys.modules-importlib на Python 3.13 — зонд reports/…probe, "
    "удалён; T12 на живое 8-таблицное условие); roadmap v4_7: §17.8 DET-1..DET-7 (вердикт III/IV) + "
    "D100; GC-01 GREEN; sanity drift quick_debug на живых БД — сессия записана, 0 ошибок; полный сьют "
    "2435 passed / 1 RED = известный test_p2_provenance_origin_vs_seeded (А/CCH-4, канон Мастера); "
    "микротесты 23/23; IPT 53/0; открытые для Мастера: S1 полная публикация — после Шага 4/D70 либо "
    "решением Мастера; hooksPath а/б (третий инцидент подтверждён — pre-commit-линтеры не исполняются "
    "хуком коммита); шапка roadmap «IPT 49/49»->53 — за Мастером (§R.7) · ✅ · ADR-O-426; коммиты "
    "813407e9, 450931cd, d1a7a5de, 83e316b5, 150a8a32 · Базлайн: IPT 53/53"
)

# v2: МЕТА-якоря НЕ фиксируются — счётчик динамический (инцидент:
# «Записей: 231» найден 0 раз — серия записала «232» между чтением
# и записью; ABORT до записи спас файл).
META_RE = re.compile(r"Записей: (\d+) \((S\d+)-([^)]*)\)")
META_BASE_OLD = "Базлайн: IPT 52/52"
META_BASE_NEW = "Базлайн: IPT 53/53"


def main() -> None:
    print("[COV-1] Запись сессии в MUTATIONS.md")
    text, bom = _load(MUT)

    # Гейт 1: числовой max по живому файлу (учитывая §3-хвосты)
    nums = sorted({int(m) for m in re.findall(r"\bS(\d{3,})\b", text)})
    if not nums:
        _abort("в реестре не найдено S-номеров — покажи шапку реестра")
    candidate = nums[-1] + 1

    # Гейт 2: git-история (параллельные серии)
    proc = subprocess.run(
        ["git", "log", "--all", "--grep", f"S{candidate}"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if proc.returncode != 0:
        _abort(f"git log недоступен: {proc.stderr.strip()}")
    if f"S{candidate}" in text:
        _abort(f"S{candidate} уже в живом реестре — аномалия нумерации, покажи хвост реестра")
    if proc.stdout.strip():
        # претендент занят параллельной серией — поднять
        for bump in range(candidate + 1, candidate + 50):
            text2 = text
            p2 = subprocess.run(
                ["git", "log", "--all", "--grep", f"S{bump}"],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            already = f"S{bump}" in text2
            if not already and not p2.stdout.strip():
                candidate = bump
                break
        else:
            _abort("не удалось найти свободный номер в +50 — ручной разбор")

    n = candidate
    print(f"[OK] Гейт номера: S{n} (файловый max={nums[-1]}, git чист)")

    # v2: якорь вставки — реестровая строка '- **S<N>**' с МАКСИМАЛЬНЫМ
    # номером (не хардкод S348: серия записала S349/S350 между моим
    # чтением и записью; якорь обязан следовать за живым файлом).
    entry_re = re.compile(r"^- \*\*S(\d{3,})\*\*", re.M)
    entries = [(int(m.group(1)), m) for m in entry_re.finditer(text)]
    if not entries:
        _abort("реестровые строки '- **S<N>**' не найдены — покажи хвост реестра")
    entry_max, entry_match = max(entries, key=lambda e: e[0])
    anchor_line_idx = text[: entry_match.start()].count("\n")
    print(f"[OK] Якорь вставки: реестровая строка S{entry_max} (максимальный номер)")

    session_line = SESSION_LINE_TMPL.format(n=n)

    # БЫЛО/СТАЛО (вставка после строки S{entry_max})
    print()
    print(f"══ Реестр (вставка после S{entry_max}-строки) — СТАЛО ══")
    print(session_line[:240] + "…")

    lines = text.split("\n")
    lines.insert(anchor_line_idx + 1, session_line)
    text = "\n".join(lines)

    # v2: МЕТА — динамический счётчик (фиксированный якорь 231 уже поймал
    # ABORT: серия сдвинула МЕТА между чтением и записью). group(3) —
    # накопительная история «добавлен»-записей, сохраняется целиком.
    m_meta = META_RE.search(text)
    if not m_meta:
        _abort("МЕТА-строка 'Записей: N (…)' не найдена — покажи МЕТА-шапку")
    cur_count = int(m_meta.group(1))
    old_head = m_meta.group(0)
    new_head = f"Записей: {cur_count + 1} (S{n}-COV-1-Шаг1 добавлен; {m_meta.group(3)}"
    print("══ МЕТА — БЫЛО ══")
    print(old_head[:120] + "…")
    print("══ МЕТА — СТАЛО ══")
    print(new_head[:120] + "…")
    text = text.replace(old_head, new_head, 1)

    if text.count(META_BASE_OLD) == 1:
        print("══ Базлайн — БЫЛО ══")
        print(META_BASE_OLD)
        print("══ Базлайн — СТАЛО ══")
        print(META_BASE_NEW)
        text = text.replace(META_BASE_OLD, META_BASE_NEW, 1)
    elif "Базлайн: IPT 53/53" in text:
        print("[OK] Базлайн уже 53/53 (серия опередила) — пропуск без правки")
    else:
        _abort("Базлайн-якорь не найден ни в 52/52, ни в 53/53 — покажи МЕТА-шапку")

    _save(MUT, text, bom)
    new_count = cur_count + 1
    print()
    print(f"[OK] Сессия S{n} записана; МЕТА: {cur_count}->{new_count}; базлайн 53/53.")
    print()
    print('git add docs/MUTATIONS.md reports/cov1_session_register.py reports/cov1_c4_probe.py reports/cov1_step_a_output.txt reports/cov1_step_b_output.txt "backend/tests/sandbox/SUPERBOX/reports/дрейф_quick_debug.csv" "backend/tests/sandbox/SUPERBOX/reports/дрейф_quick_debug.md"')
    print(f'git commit -m "S{n}: COV-1 Шаг 1 (GC-01 GREEN / ADR-O-426) — запись сессии: MigrationRunner + реестр сторов + стампинг живых БД + lint_sqlite_registry/INV-SQLITE-REGISTRY + burial ExpectationStore; МЕТА {cur_count}->{new_count} (гейт номера: живой max учтён — параллельная серия S349/S350, коллизия исключена гейтом до записи); базлайн 52/52->53/53; АТРИБУЦИЯ: уборка мусора сессии, занесённого в git релизным коммитом 4f47d076 вне моего pathspec (просил не коммитить; урок: удалять до чужого релизного окна); дрейф-отчёты — артефакты моего sanity-прогона; ветка Б" -- docs/MUTATIONS.md reports/cov1_session_register.py reports/cov1_c4_probe.py reports/cov1_step_a_output.txt reports/cov1_step_b_output.txt "backend/tests/sandbox/SUPERBOX/reports/дрейф_quick_debug.csv" "backend/tests/sandbox/SUPERBOX/reports/дрейф_quick_debug.md"')


if __name__ == "__main__":
    main()
from __future__ import annotations

# reports/cov1_step1_close.py
"""
Одноразовый доковый скрипт закрытия Шага 1 COV-1 (DoD §17.7).
Правки (docs/ENIGMA_ROADMAP_v4_7.md):
  1) §9.3f: чекбокс COV-GC-01 -> [x] с доказательствами;
  2) §7.10: COV-D58 -> закрыт; COV-D100 -> закрыт (burial исполнен);
  3) §0.2 Ступень COV: строка COV-1 — прогресс Шага 1 (пакет не закрыт:
     D59/D60/D70/D72 — Шаги 2-5);
  4) §0.1 карта треков: строка COV — прогресс Шага 1;
  5) §10: строка журнала прогона.
MUTATIONS.md: сессия не пишется этим скриптом (номер = гейт max+1
живого реестра при записи; отдельный шаг).
Дисциплина: стражи — полные строки-якоря; ABORT до записи; пары
БЫЛО/СТАЛО; идемпотент-маркеры. После исполнения и коммита НЕ
перезапускать.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7.md"


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


def _pair(label: str, anchor: str, new_line: str) -> None:
    print()
    print(f"══ {label} — БЫЛО ══")
    print(anchor)
    print(f"══ {label} — СТАЛО ══")
    print(new_line)


GC01_OLD = "- [ ] **COV-GC-01 — Миграции прозрачны.** БД старой схемы поднимается migration runner'ом без потерь (round-trip на копии кампании); симуляция «schema+1» применяется идемпотентно и журналируется; отсутствие user_version у любого стора — красный тест (COV-D58)."
GC01_NEW = "- [x] **COV-GC-01 — Миграции прозрачны.** ✅ Шаг 1 COV-1 (ADR-O-426, коммиты 813407e9/450931cd/d1a7a5de/83e316b5): MigrationRunner — per-file цепочки PRAGMA user_version (enigma_memory HEAD=2 / enigma_runtime 1 / replay 1), bootstrap по маркерам (неоднозначно → отказ без изменения файла), бэкап online backup API + верификация, аудит _schema_migrations в одной транзакции с DDL/user_version; round-trip доказан T2+T12 (v1-легаси с данными: строки сохранены; семейство 8 таблиц: штамп без DDL) + сухой/живой стампинг живых БД по протоколу 8 условий (dry-run на копиях → отчёт → подтверждение → apply; все три базы v0→HEAD базлайн-штампом, данные не тронуты, 3 верифицированных .pre-migration.bak; reports/cov1_stamp_report.{json,md}); «schema+1» идемпотентно и журналируется — T11; отсутствие user_version/незарегистрированный стор — красный тест: lint_sqlite_registry + INV-SQLITE-REGISTRY в IPT (52→53) + pre-commit hook (вердикт Мастера I.2: блокирующий RED, не предупреждение); T1–T12 + 11 линтер-тестов 23/23; S1-контракт: register_migrations (ветвь А подключает event_memories поверх, раннер не редактируется — T10)."

D58_OLD_TAIL = "| P0 | COV-1 | migration runner (user_version + runner + тест); prerequisite NL-1/MEM-1; COV-GC-01 | открыт |"
D58_NEW_TAIL = "| P0 | COV-1 | migration runner (user_version + runner + тест); prerequisite NL-1/MEM-1; COV-GC-01 | закрыт (Шаг 1: ADR-O-426; коммиты 813407e9/450931cd/d1a7a5de/83e316b5; GC-01 GREEN; живые БД v0→HEAD; инвентарь уточнён: физически 3 файла-семейства — enigma_memory 8 таблиц, enigma_runtime state_kv, replay 6 таблиц; D58-формулировка «7+ сторов» = логический счёт; D59/D60/D70/D72 — Шаги 2–5) |"

D100_OLD_TAIL = "| исполняется (SHA burial-коммита — в §10-строке закрытия) |"
D100_NEW_TAIL = "| закрыт (burial исполнен: коммит 450931cd — DEL файла + могильные комментарии зоны Б + allowlist-хвосты линтеров + Устав §3 Фаза 0.5/§12.5 по протоколу §9, журнал изменений создан; references зоны А — за владельцем А; CAUSAL CONTRACT §8 — хвост COV-11) |"

COV1_STEP_OLD = "- [ ] **COV-1 — Персистентность, миграции и надёжность старта** (D58–D60, D70, D72): migration runner (user_version) для 7+ сторов; save-версии вместо «детект-и-удалить»; reset_campaign fail-loud; конфиг-гейт старта; replay-бюджет."
COV1_STEP_NEW = "- [ ] **COV-1 — Персистентность, миграции и надёжность старта** (D58–D60, D70, D72; поэтапно): ✅ Шаг 1 D58 — MigrationRunner + реестр + bootstrap + бэкап + стампинг живых БД + lint_sqlite_registry/INV-SQLITE-REGISTRY (ADR-O-426; GC-01 GREEN; коммиты 813407e9/450931cd/d1a7a5de/83e316b5; ожидание А: раннер+шаблон миграции готовы — S1 частично, полная публикация S1 после Шага 4/D70); Шаг 2 D59 save-версионирование; Шаг 3 D60 reset fail-loud; Шаг 4 D70 старт-гейт; Шаг 5 D72 replay-бюджет (вход: replay.db 436 МБ)."

COV_TRACK_OLD_TAIL = "| COV-1 персистентность/миграции (публикует S1) → COV-3…6 вердикты механик (экономика/сцена/комбат/движение) → COV-7 игрок/MVP-вертикаль → COV-8…11 фронтенд/релиз/контент/документация; протокол поддержания полноты — §17.7 (карта фактов §17.2, Gap Matrix §17.3). Раздел §17 | O-425 |"
COV_TRACK_NEW_TAIL = "| Шаг 1 D58 ✅ (MigrationRunner/ADR-O-426, GC-01 GREEN, живые БД версионируемы, раннер+шаблон готовы для А — S1 частично, полная после Шага 4) → Шаги 2–5 D59/D60/D70/D72 → COV-3…6 вердикты механик → COV-7 игрок/MVP → COV-8…11 фронтенд/релиз/контент/документация; протокол полноты §17.7. Раздел §17 | O-425, O-426 |"

JOURNAL_ANCHOR = "### 17.8. Детерминизм и целостность рантайма"
JOURNAL_LINE = "- ✅ **COV-1 Шаг 1 (D58, GC-01)** — ADR-O-426: MigrationRunner + bootstrap + бэкап + стампинг живых БД (memory v2 / runtime v1 / replay v1, базлайн-штампы, 3 бэкапа) + lint_sqlite_registry + INV-SQLITE-REGISTRY (IPT 53/0) + burial ExpectationStore (D100); микротесты 23/23; полный сьют 2435/1-известный-RED(А); коммиты 813407e9, 450931cd, d1a7a5de, 83e316b5."


def _sub_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        _abort(f"{label}: якорь найден {count} раз (ожидался 1)")
    _pair(label, old if len(old) < 240 else old[:240] + "…", new if len(new) < 240 else new[:240] + "…")
    return text.replace(old, new, 1)


def main() -> None:
    print("[COV-1 Шаг 1] Доковое закрытие (GC-01 + D58/D100 + прогресс COV-1 + §10)")
    if "закрыт (Шаг 1: ADR-O-426" in Path(ROADMAP).read_text(encoding="utf-8-sig"):
        _abort("маркер закрытия уже в файле — скрипт уже исполнен")
    text, bom = _load(ROADMAP)

    text = _sub_once(text, GC01_OLD, GC01_NEW, "§9.3f COV-GC-01")
    text = _sub_once(text, D58_OLD_TAIL, D58_NEW_TAIL, "§7.10 COV-D58")
    text = _sub_once(text, D100_OLD_TAIL, D100_NEW_TAIL, "§7.10 COV-D100")
    text = _sub_once(text, COV1_STEP_OLD, COV1_STEP_NEW, "§0.2 COV-1 (прогресс Шага 1)")
    text = _sub_once(text, COV_TRACK_OLD_TAIL, COV_TRACK_NEW_TAIL, "§0.1 трек COV")

    # §10-строка: журнал лежит в начале §17.8-секции (якорь вставлен коммитом A)
    anchor = JOURNAL_ANCHOR
    if text.count(anchor) != 1:
        _abort(f"§10-якорь найден {text.count(anchor)} раз — покажи секцию")
    marker = anchor + " (вердикт Мастера, эпоха COV-1; владелец Б)"
    if text.count(marker) != 1:
        _abort("§10-вставка: заголовок §17.8 неожиданной структуры — покажи строку заголовка")
    _pair("§10 строка журнала", marker, marker + "\n" + JOURNAL_LINE)
    text = text.replace(marker, marker + "\n" + JOURNAL_LINE, 1)

    _save(ROADMAP, text, bom)
    print()
    print("[OK] Записано: GC-01 [x], D58 закрыт, D100 закрыт, COV-1 прогресс, §10-строка.")
    print("[OK] Гейты: validate_doc_refs → pathspec-коммит (команды ниже).")
    print()
    print('git add docs/ENIGMA_ROADMAP_v4_7.md reports/cov1_step1_close.py')
    print('git commit -m "COV-1 Шаг 1 / закрытие (DoD §17.7): COV-GC-01 GREEN (чекбокс §9.3f), D58/D100 закрыты, прогресс Шага 1 в §0.1/§0.2, §10-строка журнала; доказательства: T1-T12+11 23/23, IPT 53/0, полный сьют 2435/1-известный(А), стампинг живых БД по 8 условиям; ветка Б" -- docs/ENIGMA_ROADMAP_v4_7.md reports/cov1_step1_close.py')


if __name__ == "__main__":
    main()
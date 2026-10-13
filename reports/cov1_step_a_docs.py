"""
Одноразовый доковый скрипт COV-1 / Шаг 1 / коммит A (доковый пакет).

Правки:
  1) docs/ADR (Architecture Decision Records).md — новая запись
     ADR-O-{max+1} [STANDARD] «Persistence Integrity» (вставка после
     Files-строки записи ADR-O-425).
  2) docs/audits/ADR-O-{max+1}_IMPACT.md — новый файл.
  3) docs/ENIGMA_ROADMAP_v4_7.md — новый §17.8 (DET-трек; вставка после
     пункта 6 «Иерархия» §17.7) + строка §7.10 COV-D100 (после COV-D99).

Дисциплина (РЕЖИМ §3.7): все тексты — литералы внутри скрипта; стражи —
полные строки-якоря и относительные проверки; ЛЮБОЙ провал стража = ABORT
всего скрипта ДО записи. Гейты номеров: ADR = max+1 по атласу + git log
--all (параллельные серии); D-строка = числовой max < 100. Идемпотент:
повторный запуск = ABORT. Печатает пары БЫЛО/СТАЛО (формат §4 РЕЖИМА).
После исполнения и коммита НЕ перезапускать (прецедент s337_registry_add).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_ATLAS = ROOT / "docs" / "ADR (Architecture Decision Records).md"
P_ROADMAP = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7.md"
P_AUDITS = ROOT / "docs" / "audits"


def _load(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if has_bom else "utf-8"), has_bom


def _save(path: Path, text: str, has_bom: bool) -> None:
    path.write_bytes((b"\xef\xbb\xbf" if has_bom else b"") + text.encode("utf-8"))


def _abort(reason: str) -> None:
    print(f"[ABORT] {reason}")
    print("[ABORT] Стоп ДО применения правок: ни один файл не записан.")
    sys.exit(1)


def _insert_after_unique(text: str, anchor_prefix: str, block: list[str], label: str) -> tuple[str, str]:
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if ln.rstrip("\r").startswith(anchor_prefix)]
    if len(hits) != 1:
        _abort(f"{label}: якорь '{anchor_prefix}' найден {len(hits)} раз (ожидался ровно 1)")
    idx = hits[0]
    crlf = lines[idx].endswith("\r")
    lines[idx + 1:idx + 1] = [(ln + "\r") if crlf else ln for ln in block]
    return "\n".join(lines), lines[idx].rstrip("\r")


def _insert_after_atlas_entry(text: str, hdr_prefix: str, block: list[str], label: str) -> tuple[str, str]:
    lines = text.split("\n")
    hdrs = [i for i, ln in enumerate(lines) if ln.rstrip("\r").startswith(hdr_prefix)]
    if len(hdrs) != 1:
        _abort(f"{label}: заголовок '{hdr_prefix}' найден {len(hdrs)} раз (ожидался ровно 1)")
    files_idx = None
    for j in range(hdrs[0] + 1, min(hdrs[0] + 80, len(lines))):
        if lines[j].rstrip("\r").startswith("Files"):
            files_idx = j
            break
    if files_idx is None:
        _abort(
            f"{label}: в пределах 80 строк после заголовка нет строки 'Files' — "
            "покажи запись ADR-O-425 целиком (неожиданная структура атласа)"
        )
    crlf = lines[files_idx].endswith("\r")
    lines[files_idx + 1:files_idx + 1] = [(ln + "\r") if crlf else ln for ln in block]
    return "\n".join(lines), lines[files_idx].rstrip("\r")


def _print_pair(label: str, anchor: str, block: list[str]) -> None:
    print()
    print(f"══════════ {label} — БЫЛО (строка-якорь) ══════════")
    print(anchor)
    print(f"══════════ {label} — СТАЛО (якорь + вставка) ══════════")
    print(anchor)
    for ln in block:
        print(ln)


def _adr_entry(adr_id: str) -> list[str]:
    return [
        "",
        adr_id + " [STANDARD] **Persistence Integrity: Migration Runner, Save Versioning, Startup Gate, Replay Budget** (эпоха COV-1; вердикты Мастера: эскиз v2 Ф1–Ф9, Step-1 packet GO, политика легаси-версий II.А–Г)",
        "Суть: единый контур целостности персистентности, поэтапно (Шаг 1 D58-ядро → Шаг 2 D59 → Шаг 3 D60 → Шаг 4 D70 → Шаг 5 D72; гейты COV-GC-01/02). (1) MigrationRunner (D58): per-file цепочки поверх PRAGMA user_version; MigrationSpec(store_id, from_version, to_version, owner, apply(conn)) — apply чист по соединению и не делает собственных COMMIT; применение = ОДНА транзакция (DDL + user_version + аудит-строка _schema_migrations); статический self-check реестра (непрерывность цепочки, без дыр/дуэлей/неоднозначных переходов) ДО любого касания БД; даунгрейд (version > HEAD) — блокирующий отказ, обходные флаги запрещены; единственный путь сторонних миграций — register_migrations (S1: владелец А подключает event_memories NL-1/MEM-1, раннер не редактируется). (2) Bootstrap v0: однократная классификация легаси-БД ТОЛЬКО по проверяемым маркерам (точное множество таблиц × состояние колонок; whitelist sqlite_* + _schema_migrations); неоднозначно → отказ без изменения файла; пустая БД → полная цепочка; после базлайн-штампа снифинг схемы запрещён. (3) Политика легаси-схем: каталог бесконечных адаптеров не строится; поддерживаются только состояния, необходимые для безопасного перевода на текущую целевую схему; ретроспективная поддержка — отдельное решение (~3 года, ориентир, не обязательство). (4) Бэкап/восстановление: SQLite online backup API → верификация копии (integrity_check + множество таблиц + row-counts) → атомарная замена .pre-migration.bak; единственная исправная копия не удаляется и не перезаписывается непроверенной; восстановление — воспроизводимый runbook (IMPACT §6); автоматического понижения нет. (5) Save-версионирование (D59, Шаг 2): schema_version в мете сейва; «детект-и-удалить» запрещён; конвертация только доказанная + верификация результата; исходный сейв не удаляется до успешной конвертации; невозможность → честный отказ + предложение новой игры. (6) Старт-гейт (D70, Шаг 4): единая блокирующая конъюнкция конфиг-схема → миграции → readiness; ленивый путь миграций запрещён. (7) Replay-бюджет (D72, Шаг 5): N-последних сессий + pinned-защита живых A/B (ADR-O-351); до подтверждения пути/активности ReplayStore ничего не удаляется. (8) ExpectationStore захоронен (COV-D100, вердикт II.Г): мёртвый стор (0 инстанцирований; wiring удалён DEEP-015; собственная SQLite = анти-паттерн ADR-O-381) — полное удаление отдельным ограниченным изменением; к MigrationRunner не подключается; будущая потребность → новый дизайн + регистрация в реестре ДО использования. (9) Машинное закрепление: lint_sqlite_registry — census поддерживаемых способов открытия SQLite; каждый стор RUNNER-OWNED / EXCLUDED(причина) / TEST-ONLY; новый незарегистрированный стор = блокирующая ошибка гейта (INV-SQLITE-REGISTRY в IPT + CI), не предупреждение; линтер имеет собственные тесты на позитивные/негативные случаи и не объявляет проверку полной при непокрытых способах создания соединений.",
        "❌ Taboo: снифинг схемы после базлайн-штампа; штамп HEAD по неизвестному/неоднозначному состоянию; миграция вне транзакции; user_version отдельной записью; COMMIT внутри apply; обходной флаг даунгрейда; молчаливое удаление/подмена сейва; удаление исходного сейва до верифицированной конвертации; перезапись единственного .bak непроверенной копией; ленивый путь миграций; правка раннера ради конкретного стора; новый SQLite-стор без статуса в реестре; воскрешение ExpectationStore без нового ADR + регистрации; ротация replay, съедающая pinned-сессию.",
        "Status: ACTIVE (поэтапно; Шаг 1 — GO вердиктом: раннер + реестр + bootstrap + бэкап + перенос secret_id-гварда в миграцию v1→v2 + обязательный линтер + контролируемый стампинг живых БД по протоколу 8 условий)",
        "Files: `backend/app/services/state/migration_runner.py`, `scripts/lint_sqlite_registry.py`, `backend/app/services/memory/sqlite_store.py`, `backend/tests/micro/test_migration_runner.py`, `backend/tests/micro/test_lint_sqlite_registry.py`, `backend/tests/IPT.py` (INV-SQLITE-REGISTRY), CI; Шаг 2+: `backend/app/services/state/save_format_detector.py`, `backend/app/services/game_loop/campaign_lifecycle.py`, `backend/app/core/schema_validator.py`, `backend/app/services/readiness.py`, `backend/app/services/replay/replay_store.py`. Детальный аудит: `docs/audits/" + adr_id + "_IMPACT.md`",
    ]


SEC_17_8 = [
    "",
    "### 17.8. Детерминизм и целостность рантайма (вердикт Мастера, эпоха COV-1; владелец Б)",
    "",
    "Основание — мастерский вердикт по COV-1: идеи четырёх инженерных школ разводятся на проверку корректности / дешёвые улучшения / будущие возможности. Статусы: реализуется / отложено (с триггером пересмотра) / исследование; упоминание в чате ≠ закрытие (закрытие = гейт/тест + строка §10). Порядок исполнения: Шаг 1 COV-1 → DET-1 → DET-2 → DET-3.",
    "",
    "- [ ] **DET-1 [реализуется] Аудит детерминизма AdaptiveTickLoader** — проверка корректности, не фича: найти все точки throttling/LOD-решений (`backend/app/services/adaptive_tick_loader.py:11`; wiring `tick_orchestrator.py:725-726`; первый подозреваемый — M-24-комментарий `tick_orchestrator.py:744` «восстанавливаем измерение времени… (LOD throttling)»); трассировка источников каждого входа: детерминированные (состояние мира + номер тика) vs wall-clock; воспроизводимый тест доказывает или опровергает расхождение replay при другой машине/нагрузке; при доказанном баге — решение переводится на детерминированные входы, wall-clock остаётся телеметрией (§15 Устава); если уже обеспечено порогами по состоянию сцены — зафиксировать доказательство тестом, исправное не переписывать.",
    "- [ ] **DET-2 [реализуется] Дешёвый детерминированный checksum** — первое действие = собственное измерение стоимости (число «2,4% тика» — из формулировки вердикта; грепом reports/ не локализовано, до измерения считать неподтверждённым); канонический контракт состояния (какие поля входят); стабильное представление без зависимости от порядка словарей и особенностей сериализации; бинарная канонизация/инкрементный хеш — только по измерениям на репрезентативной сцене; критерий принятия: доказанное равенство хешей эквивалентного состояния + обнаружение внесённых изменений + приемлемая стоимость; при подтверждении — частота проверки 1/100 → 1/1.",
    "- [ ] **DET-3 [реализуется] Crash-recovery тест** — сначала определить реальные границы атомарности Фазы 10 и допустимую точку восстановления; интеграционный тест: фиксация исходного состояния → искусственное завершение процесса в точке записи/фиксации тика → перезапуск восстановления → результат = последнее допустимое зафиксированное состояние; отсутствие частичных мутаций, двойного применения событий, призрачных состояний. Mutation recorder ≠ доказательство crash recovery без такого теста.",
    "- [ ] **DET-4 [отложено; триггер — MVP-вертикаль] Inputs-only replay** — воспроизведение мира из начального состояния, seeds и последовательности interventions без записи полного scene_state каждый тик; предусловия — подтверждённый детерминизм (выходы DET-1/DET-2) и формат входов; текущий recorder не удалять и не заменять; новый режим существует рядом с действующим до доказанной корректности.",
    "- [ ] **DET-5 [отложено; триггер — MVP-вертикаль] Контрфактические ветки / машина времени** — выбор тика + одно изменённое действие игрока → сравнение двух веток мира; до реализации проверить чистоту снапшотов (нет ссылок на живые сервисы и внешние мутабельные объекты); будущая функция причинного исследования мира, не задача COV-1.",
    "- [ ] **DET-6 [исследование] Фазовый I/O-контракт с AST-линтом** — декларативное описание полей ctx, которые каждая фаза имеет право читать/изменять; аудит текущей архитектуры → небольшой прототип → тесты; не вводить общий контракт одним большим коммитом.",
    "- [ ] **DET-7 [исследование; предусловия — профилирование + сравнительный A/B с последовательным исполнением] Детерминизм-сохраняющий параллелизм Фазы 5** — редюсер над замороженным снимком; результат не зависит от порядка завершения задач; нет скрытых общих мутаций; сериализация/передача не съедают выигрыш.",
    "",
]

D100_ROW = (
    '| COV-D100 | Мёртвый стор ExpectationStore: 0 инстанцирований (wiring-греп backend), wiring удалён сознательно '
    '(DEEP-015: tick_orchestrator:2177-2179, state_applicator:789, idle_services:54), memory.db не существует нигде в дереве, '
    'собственная SQLite = анти-паттерн (conclusion_store:9, ADR-O-381); default db_path="memory.db" CWD-относительный '
    '(класс урока S314) — риска записи нет; хвосты: allowlist-строки lint_kernel_rng.py:25 / lint_wall_clock.py:32; '
    'строка реестра адаптеров Устав §12.5 (:485); PE Decay-упоминание Устав §3 Фаза 0.5 (:201; аналог в CAUSAL CONTRACT §8 — '
    'хвост документационной гигиены COV-11); уточняет фактологию D58 (npc_expectations выбывает; физически 3 .db-файла: '
    'enigma_memory / enigma_runtime / replay) | P2 | COV-1 | вердикт Мастера II.Г: полное удаление отдельным ограниченным '
    'изменением (файл + могильные комментарии зоны Б + allowlist-хвосты двух линтеров + обе строки Устава по протоколу '
    '§9 Устава); к MigrationRunner не подключается; будущая потребность → новый дизайн + регистрация в реестре до '
    'использования; ссылки зоны А (state_applicator:789, npc_tick_pipeline:459-462, формулировка conclusion_store:9) — '
    'владелец А | исполняется (SHA burial-коммита — в §10-строке закрытия) |'
)


def _impact_text(adr_id: str) -> str:
    return """ADR-O-NUM [STANDARD] **IMPACT**

> Детальный аудит одного ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`.
> Эпоха: COV-1, Шаг 1 (ядро D58; гейт COV-GC-01). Основания-вердикты Мастера: эскиз v2 (Ф1–Ф9); Step-1 packet GO; линтер реестра обязателен; стампинг живых БД в Шаге 1 (протокол 8 условий); политика легаси-версий II.А–Г; детерминизм-приоритеты III/IV (закреплены roadmap §17.8, DET-1…DET-7).

## 1. Changed Domains

- Персистентность: версии схем трёх SQLite-файлов — `PRAGMA user_version` per-file; аудит-таблица `_schema_migrations` в каждом файле.
- Контуры одного ADR исполняются поэтапно: D59 сейвы (Шаг 2), D60 reset (Шаг 3), D70 старт-гейт (Шаг 4), D72 replay-бюджет (Шаг 5).
- Behavioral-neutral по построению: миграции меняют схему и мету, не значения; тик-латентность не затронута.

## 2. Фактический инвентарь сторов (read-only археология сессии)

| Файл | Логические сторы | HEAD | Цепочка |
|---|---|---|---|
| saves/enigma_memory.db | SqliteMemoryStore (entries, state_collections, memory_crystals, experience_traces, event_memories); l1_chronicle и crystallized_belief_store — через generic store.execute/query поверх того же файла | 2 | v1 = 5 таблиц; v2 = event_memories.secret_id + индекс (перенос последнего ad-hoc ALTER, sqlite_store.py:190-194) |
| saves/enigma_runtime.db | SqlitePersistenceAdapter (state_kv; Фаза 10 atomic_commit_all; load_scene_at — ADR-O-352); EpistemicStore/conclusions/relationship_state едут payload'ом внутри state_kv (отдельных БД нет) | 1 | v1 = state_kv |
| replay.db (путь — config; резолвер) | ReplayStore (sessions, tick_snapshots, interventions, llm_calls, causal_probes, scene_changes; WAL) | 1 | v1 = 6 таблиц |
| memory.db / npc_expectations | — | — | EXCLUDED: ExpectationStore захоронен (COV-D100, вердикт II.Г); реанимация = новый дизайн + регистрация ДО использования |

Примечание к «пустая БД → полная цепочка»: DDL миграции v1 дублирует CREATE стора (идемпотентный CREATE IF NOT EXISTS в `__init__` остаётся); паритет схем зафиксирован тестом T1 — замок против дрейфа двух копий DDL.

## 3. Downstream Consumers

- Ветвь А / гейт S1: миграция `event_memories` (NL-1/MEM-1) подключается через `register_migrations` — раннер не редактируется. Иллюстративный каркас (НЕ утверждение схемы NL-1):

```python
from app.services.state.migration_runner import MigrationSpec, register_migrations


def _event_memories_v2_to_v3(conn) -> None:
    # Только DDL/DML. Без COMMIT: транзакцию ведёт раннер (II.2).
    conn.execute("ALTER TABLE event_memories ADD COLUMN example_nl1_column TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_memories_example"
        " ON event_memories(campaign_id, npc_id)"
    )


register_migrations(
    MigrationSpec(
        store_id="enigma_memory",
        from_version=2,
        to_version=3,
        owner="NL-1/A",
        description="event_memories: хронология памяти (NL-1)",
        apply=_event_memories_v2_to_v3,
    )
)
```

- replay A/B (ADR-O-351): pinned-защита живых сессий (Шаг 5).
- save/load (ADR-O-352) и релизный контур COV-9: будущие обновления едут через миграции, не через «детект-и-удалить».
- Соседние инварианты: ADR-FOUNDATION-FREEZE (atomic_commit_all — единственный runtime-путь записи; раннер — старт-контур, не runtime); Rule 28 (миграции L1-таблиц — только additive DDL).

## 4. Runtime Impact

- Старт: однократные транзакции миграций при первом запуске после апгрейда; далее no-op (чтение user_version).
- Тик: 0 (раннер вне тика; единая точка исполнения — конфиг-гейт, Шаг 4/Ф4).
- Диск: ~11 МБ на файл (`.pre-migration.bak`) + строки `_schema_migrations`.

## 5. Sandbox Tests

- `backend/tests/micro/test_migration_runner.py` — T1–T11: fresh-цепочка + паритет схем; v1→v2 с сохранением строк; штамп-без-DDL; неоднозначное состояние → отказ без изменений; даунгрейд → блок; повторный прогон = no-op; исключение в apply → полный откат; дыры/дуэли реестра → блок до касания БД; бэкап + верификация + старый .bak не затирается; register_migrations сторонним владельцем; «schema+1» применяется однократно и журналируется.
- `backend/tests/micro/test_lint_sqlite_registry.py` — позитив/негатив: незарегистрированный стор = RED; EXCLUDED(причина) = GREEN; TEST-ONLY = GREEN; непокрытый способ соединения = RED полноты.
- Стампинг живых БД: `reports/cov1_stamp_report.json` + `.md` — результат по каждому файлу (протокол §7).

## 6. Rollback (runbook, воспроизводимо — вердикт II.В)

1. Код: git-revert (раннер не выполняется без явного вызова).
2. Данные: (а) остановить бэкенд; (б) сохранить проблемный файл с суффиксом `.failed`; (в) вернуть проверенный `<db>.pre-migration.bak`; (г) повтор обновления — только после устранения причины; (д) автоматического понижения версий нет (Ф2).
3. Единственная исправная копия не удаляется и не перезаписывается непроверенной: замена `.bak` — только после верификации новой копии (integrity_check + множество таблиц + row-counts).

## 7. Протокол стампинга живых БД (вердикт I.3 — 8 условий, дословно)

1. Бэкенд остановлен; соблюдено окно тишины.
2. На копиях реальных баз выполнен dry-run. Представлен отчёт по классификации, предполагаемым изменениям и результатам проверок.
3. Все неоднозначные состояния разрешены. Неизвестная схема не получает HEAD автоматически.
4. Резервные копии созданы через SQLite online backup API, проверены на целостность и сохранность данных.
5. Стампинг выполняется только для баз, которые однозначно соответствуют ожидаемому состоянию.
6. После операции проверены user_version, схема, содержимое и возможность открыть базы.
7. Создан `reports/cov1_stamp_report.json` и соответствующий Markdown-отчёт с результатом по каждому файлу.
8. При любом неожиданном расхождении операция останавливается; никаких догадок о правильной версии и молчаливого продолжения.

Ожидаемый исход: `enigma_memory.db` → v2 (штамп-без-DDL, v2-легаси); `enigma_runtime.db` → v1 (штамп-без-DDL); `replay.db` отсутствует → skip без создания.

## 8. Bootstrap-таблица решений (Шаг 1; пользовательские таблицы = все, кроме sqlite_* и _schema_migrations)

| Файл | Состояние | Маркеры | Решение |
|---|---|---|---|
| enigma_memory.db | пустая | таблиц нет | полная цепочка v1→v2 |
| enigma_memory.db | v1-легаси | ровно 5 таблиц; event_memories без secret_id | миграция v1→v2 (ALTER + индекс) → штамп 2 |
| enigma_memory.db | v2-легаси | те же 5; secret_id есть; idx_event_memories_secret есть | штамп 2 без DDL |
| enigma_memory.db | иное | частичный набор / чужие таблицы | отказ; файл не изменяется |
| enigma_runtime.db | пустая | таблиц нет | цепочка v1 |
| enigma_runtime.db | ровно state_kv | одна таблица state_kv | штамп 1 без DDL |
| enigma_runtime.db | иное | прочее | отказ; файл не изменяется |
| replay.db | отсутствует | — | skip; файл НЕ создаётся |
| replay.db | ровно 6 канонических таблиц | sessions, tick_snapshots, interventions, llm_calls, causal_probes, scene_changes | штамп 1 без DDL |
| replay.db | иное | прочее | отказ; файл не изменяется |
""".replace("ADR-O-NUM", adr_id)


def main() -> None:
    print("[COV-1 / коммит A] Доковый скрипт: атлас + IMPACT + roadmap (§17.8 + COV-D100)")
    if not P_ATLAS.exists():
        _abort(f"нет файла: {P_ATLAS}")
    if not P_ROADMAP.exists():
        _abort(f"нет файла: {P_ROADMAP}")
    if not P_AUDITS.is_dir():
        _abort(f"нет каталога: {P_AUDITS}")

    atlas, atlas_bom = _load(P_ATLAS)
    roadmap, roadmap_bom = _load(P_ROADMAP)

    # ── Идемпотент-стражи (повторный запуск = ABORT) ──
    if "Persistence Integrity: Migration Runner" in atlas:
        _abort("атлас: запись Persistence Integrity уже есть — скрипт уже исполнен")
    if "### 17.8." in roadmap:
        _abort("roadmap: §17.8 уже есть — скрипт уже исполнен")
    if "COV-D100" in roadmap:
        _abort("roadmap: COV-D100 уже есть — скрипт уже исполнен или номер занят")

    # ── Гейт номера ADR: атлас max+1 ──
    nums = sorted({int(m) for m in re.findall(r"ADR-O-(\d+)", atlas)})
    if not nums:
        _abort("атлас: не найдено ни одного ADR-O-номера")
    adr_id = f"ADR-O-{nums[-1] + 1}"
    if adr_id in atlas:
        _abort(f"атлас: {adr_id} уже существует — аномалия нумерации, покажи хвост атласа")

    # ── Гейт номера ADR: git-история (параллельные серии) ──
    proc = subprocess.run(
        ["git", "log", "--all", "--oneline", "--grep", adr_id],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    if proc.returncode != 0:
        _abort(f"git log недоступен: {proc.stderr.strip()}")
    if proc.stdout.strip():
        _abort(f"{adr_id} уже фигурирует в истории коммитов — номер занят параллельной серией (гейт номеров)")

    # ── Гейт D-нумерации: числовой max < 100 ──
    dnums = sorted({int(m) for m in re.findall(r"COV-D(\d+)", roadmap)})
    if dnums and dnums[-1] >= 100:
        _abort(f"roadmap: числовой max COV-D = {dnums[-1]} (>= 100) — D100 занят, переназначь номер строки")

    print(f"[OK] Гейт номера ADR: {adr_id} (атлас max = {nums[-1]}, git-история чиста)")
    print(f"[OK] Гейт D-нумерации: числовой max COV-D = {dnums[-1] if dnums else 'нет'} → D100 свободен")

    # ── Правки (все проверки пройдены; тексты строятся до записи) ──
    entry = _adr_entry(adr_id)
    atlas_new, atlas_anchor = _insert_after_atlas_entry(
        atlas, "ADR-O-425 [STANDARD]", entry, "атлас/вставка ADR"
    )
    roadmap_new, hier_anchor = _insert_after_unique(
        roadmap, "6. **Иерархия.**", SEC_17_8, "roadmap/§17.8"
    )
    roadmap_new2, d99_anchor = _insert_after_unique(
        roadmap_new, "| COV-D99 |", [D100_ROW], "roadmap/COV-D100"
    )
    impact_path = P_AUDITS / f"{adr_id}_IMPACT.md"
    if impact_path.exists():
        _abort(f"IMPACT уже существует: {impact_path} — скрипт уже исполнен")
    impact = _impact_text(adr_id)

    # ── Печать пар БЫЛО/СТАЛО (формат §4 РЕЖИМА) ──
    _print_pair("Атлас: вставка новой записи после ADR-O-425", atlas_anchor, entry)
    _print_pair("Roadmap: §17.8 после пункта 6 §17.7", hier_anchor, SEC_17_8)
    _print_pair("Roadmap: COV-D100 после COV-D99", d99_anchor, [D100_ROW])
    print()
    print(f"══════════ НОВЫЙ ФАЙЛ: docs/audits/{adr_id}_IMPACT.md ══════════")
    print("(БЫЛО: файл отсутствовал)")
    print(f"(СТАЛО: {len(impact.splitlines())} строк; полный текст — открыть в VS Code для ревью ДО коммита)")

    # ── Запись ──
    _save(P_ATLAS, atlas_new, atlas_bom)
    _save(P_ROADMAP, roadmap_new2, roadmap_bom)
    impact_path.write_bytes(impact.encode("utf-8"))

    print()
    print(f"[OK] Записано: атлас ({adr_id}), roadmap (§17.8 + COV-D100), docs/audits/{adr_id}_IMPACT.md")
    print("[OK] Гейты коммита A: validate_doc_refs → compileall frontend → pathspec-коммит:")
    print(f'git add "docs/ADR (Architecture Decision Records).md" "docs/audits/{adr_id}_IMPACT.md" docs/ENIGMA_ROADMAP_v4_7.md reports/cov1_step_a_docs.py')
    print(f'git commit -m "COV-1 Шаг 1 / коммит A (доковый): {adr_id} [STANDARD] Persistence Integrity (атлас + IMPACT; вердикты Ф1-Ф9 + II.А-Г) + roadmap: §17.8 DET-трек DET-1..DET-7 (вердикт III/IV) + §7.10 COV-D100 захоронение ExpectationStore (II.Г); номера — гейтами max+1; ветка Б" -- "docs/ADR (Architecture Decision Records).md" "docs/audits/{adr_id}_IMPACT.md" docs/ENIGMA_ROADMAP_v4_7.md reports/cov1_step_a_docs.py')


if __name__ == "__main__":
    main()
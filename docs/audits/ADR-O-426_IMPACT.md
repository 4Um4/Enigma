ADR-O-426 [STANDARD] **IMPACT**

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

## 9. Шаг 2 (D59): save-версионирование сцен — «детект-и-мигрировать» (исполнено)

Статус: Шаг 2 закрыт — S354; COV-D59 → закрыт; COV-GC-01 GREEN наследуется от Шага 1; COV-GC-02 остаётся открытым до Шага 3/D60. Код: f51cc6ae (вошёл релизным sweep v0.5.4.3.7); тесты: 5d0748ab; pytest 42/42 (снимки 0.54s и 0.49s); док-закрытие: реестр MUTATIONS.md S354 + roadmap (трек COV, §10, §17.8).

Исполнено:
1. Детектор формата сейва: CURRENT / MIGRABLE (V0_SINGLE | V1_UNSTAMPED) / UNMIGRABLE (NOT_DICT | CORRUPT_JSON | NEWER_VERSION | UNKNOWN_VERSION | UNKNOWN_FORMAT | INVALID_V0 | INVALID_SCENES | INCONSISTENT_V1). SAVE_SCHEMA_VERSION=1; явный schema_version=0 не считается v0 (v0 = отсутствие поля).
2. Миграция v0 → v1: scene_state → scenes + штамп schema_version. Резерв: .bak из исходных байтов + побайтовая верификация копии; BACKUP_CONFLICT — отказ, не перезапись. Атомарность: tmp + round-trip + os.replace — единственное касание живого файла.
3. Lifecycle К3: UNMIGRABLE → load_refusal_reason + campaign_load_refused (без лживого campaign_loaded); после успеха — статус migrated.
4. Писатель К5: save_scene_at штампует v1 и снимает scene_state — новые записи не рождают v0.
5. Схемы В7: CampaignLoadResponse.load_refusal_reason.

Инцидент доставки (разрешён): код вошёл релизным full-save f51cc6ae без атрибуции; pathspec 311cd784 внёс только тесты под сообщением всей реализации; исправлено guard-амендом 5d0748ab. Хвост док-закрытия (6d01f6a2 — скрипт без применения, применяющий коммит) — roadmap §17.8 (S354).

## 10. Шаг 3 (D60): fail-loud сброс кампании — «довести или честно остановиться» (исполнено)

Статус: Шаг 3 закрыт — S356; COV-D60 → закрыт; COV-GC-02 закрыт полностью (три критерия: конверсия/честный отказ и поле-версии — Шаг 2/S354; fail-loud reset — Шаг 3/S356). Код: d67e9eda (campaign_lifecycle.py + routes.py, +85/−12; hook WARNING «ADR IMPACT AUDIT REQUIRED» — ожидаемо: campaign_lifecycle.py в Files-списке ADR-O-426, закрывается этим §10); тесты: 0633ed0c (+370, backend/tests/micro/test_d60_reset_fail_loud.py); pytest 14/14 D60 + 44/44 совместно с D59 (1.55s); IPT 53/0/0; док-закрытие: реестр MUTATIONS.md S356 + roadmap (трек COV, §7.10, §9.3f, §17.8, §10) + ЗАВЕЩАНИЕ письмо №6 + атлас Status O-426.

Исполнено:
1. Класс CampaignResetError(RuntimeError): поля campaign_id/step/detail + машиночитаемое сообщение (прецедент В7 — CampaignLoadResponse.load_refusal_reason у D59). Отдельный класс, не SimulationIntegrityError: перехват в маршруте узкий, чужие ошибки летят сырыми.
2. 15 сайтов immediate-interrupt (шаги 1–12 + P-MVP-1; step-ids: sqlite_persistence, json_files, relationships, crystallized_beliefs, player_session, life_engine_npc, scene_reinit, current_location_seed, body_topology, atomic_commit, memory_manager, temporal_engine, avatar_session, npc_runtime_caches, mvp_controller_init): log остаётся, затем raise … from e. Единственное удаление патча — continue в json_files: тихий пропуск осиротевшего JSON был корневым классом бага (JSON-fallback PersistencePort мог прочитать осиротевший файл).
3. Фикс биндинга _mem_reset: Optional[dict] = None до try шага 9 + гвард if _mem_reset is not None вокруг 12-sqlite. Латентный NameError (пре-патч :330-333 vs :360) устранён; регрессия запинена тестом (type is CampaignResetError, step='memory_manager').
4. П1-18 passthrough: except CampaignResetError: raise перед generic-обработчиком шага 6 — уже классифицированный отказ current_location_seed не переупаковывается в scene_reinit; верхнеуровневое step-поле не лжёт.
5. Маршрут (Патч №2): new_game — импорт CampaignResetError (между combat_service и game_loop_accessor) + catch → HTTPException(status_code=500, detail={"error": "campaign_reset_failed", "campaign_id", "step", "detail"}) from exc — честный перевод доменного отказа (500, не 503/412). Happy path не тронут (тот же return внутри try); фасад GameLoop.new_game (:678) без try/except — свободный пролёт CampaignResetError до маршрута доказан.

Тесты (backend/tests/micro/test_d60_reset_fail_loud.py, 14): TestHappyPath 3 — порядок 13 операций владельцев (пин контракта O-403), files_removed состав + board_state.json удаляется/characters.json выживает, гвард _mem_reset None; TestImmediateInterrupt 6 — немедленность sqlite_persistence (rec==[]), json_files (monkeypatch Path.unlink, файл не тронут), atomic_commit прерван до memory/mvp, NameError-регрессия memory_manager, scene_reinit, passthrough current_location_seed; TestMachineReadable 3 — поля/точное str-сообщение, __bases__==(RuntimeError,), все 15 step-id в inspect.getsource(reset_campaign); TestRouteTranslation 2 — 500 + точный dict-detail + __cause__ instanceof, happy path насквозь.

Вне скоупа (косметика, релей Мастеру): мислейбл «Atomic commit:» в логе шага 2; дубль нумерации шагов 7/12; _current_campaign_id выставляется до reset (домен GameLoop); узел CampaignLifecycle отсутствует в YAML-топологии; дубли constraints в ARCHITECTURE_FLOW_GENERATED; комментарий пути сессий (файл saves/<cid>.json, обещано saves/<cid>/session.json); _load_sessions_from_disk читает все .json в saves/.

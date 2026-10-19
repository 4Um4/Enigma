# ADR-O-420 IMPACT — CCH-5: Export Projections (дополнение)

> **Связанный ADR:** ADR-O-420 (Character Chronicle — Authoring Compiler, S331)
> **Этап:** CCH-5 — экспорт-проекции канон-хроник
> **Сессия:** S<номер_в_MUTATIONS> (присваивается при записи)
> **Ветвь:** А «Субъект»

## Суть

CCH-5 завершает контур экспорт-проекций канон-хроник в форматы старых систем:
- `origin_events`-совместимый JSON (для `_convert_origin_events` round-trip)
- `village_relations.json`-формат (шкала 0..1, загрузчик ×100)
- `truth_state_*.json`-формат (Secret + TruthRelation)

Проекции — **артефакты аудита**, НЕ источник истины для рантайма. Канон остаётся единственным SSOT. `npc_loader.py` и `chronicle_seeder.py` НЕ изменены.

## Changed Domains

- `services/chronicle/` — новый модуль `chronicle_projections.py`
- `api/routes_chronicle.py` — 2 новых endpoint
- `tests/micro/` — новый тест-файл

## Downstream Consumers

- **Рантайм: НЕТ** (проекции не читаются `npc_loader` / `chronicle_seeder` / `tick_orchestrator`)
- **API:** `POST /chronicle/{campaign_id}/export-projections`, `GET /chronicle/projections/current`
- **Тесты:** `test_cch5_projections.py` (22 теста)
- **Аудит:** человек (автор мира) — для проверки round-trip канон ↔ legacy-форматы

## Runtime Impact

- **RAM:** 0 (вне тик-контура)
- **VRAM:** 0
- **Latency:** 0 (endpoint вызывается вручную автором)

## Sandbox Tests

- `backend/tests/micro/test_cch5_projections.py` — 22 теста:
  - `TestLegacyNoDrift` (T-CCH-09): NPC без хроники → legacy-путь нетронут
  - `TestProjectionRoundTrip` (T-CCH-01): семантическая сохранность полей
  - `TestTruthRelationDirection`: направление `source=E, target=C, DEPENDS_ON`
  - `TestEmptyInitialHolders`: `initial_holders=[]` допустим, проходит валидатор
  - `TestBlockedReferences`: повреждённые ссылки → BLOCKED
  - `TestPublishAtomicity`: A3 — при ошибке старый `current.json` действующий

## Rollback

1. Удалить `backend/app/services/chronicle/chronicle_projections.py`
2. Удалить 2 endpoint из `backend/app/api/routes_chronicle.py`
3. Удалить `backend/tests/micro/test_cch5_projections.py`
4. Удалить `config/npc/chronicles/_projections/` (если создавался)
5. Рантайм не зависит от проекций — отката не требует

## Новые правила CCH-5 (НЕ существующие гарантии схемы)

1. **EXPLICIT:** секретность — только `payload["is_secret"] is True` на `kind=EVENT`. Не выводим из важности/травматичности/текста/категории/causes/KNOWLEDGE_LINK.
2. **K1:** `initial_holders` — только resolved knowers из `KNOWLEDGE_LINK`. `[]` допустим, НЕ доказательство, что никто не знает. Диагностика `no_resolved_knowers` в manifest.
3. **C2:** структурно повреждённые `origin_ref` → блокировка публикации. Корректные, но непредставимые связи (CauseKind≠EVENT, target не секрет) → пропуск с диагностикой.
4. **A3:** атомарная публикация через поколение (`gen_<ts>_<hash>/`) + `current.json`. Одно `os.rename` каталога, не три `os.replace`. При ошибке старый `current.json` действующий.
5. **EMPTY:** нет секретных EVENT → `truth_state_status: EMPTY`, файл не создаётся, `manifest.files.truth_state: null`.
6. **Шкала village_relations-проекции:** файловая 0..1 (`SEED_TRUST_POSITIVE/100 = 0.3`, `SEED_TRUST_NEGATIVE/100 = -0.4`). Загрузчик `npc_loader:251` умножает на 100.
7. **Направление TruthRelation:** `source=E` (зависящий), `target=C` (основание), `DEPENDS_ON`. Согласовано с существующей семантикой `truth_state.py:36` (`DEPENDS_ON = "A зависит от B"`, `source=A, target=B`).

## Существующие гарантии схемы (НЕ тронуты CCH-5)

- `ChronicleEntry` frozen, `EntryKind` закрытый enum (SECRET НЕ введён)
- `CauseRef.__post_init__` — UNKNOWN без origin_ref; остальные требуют origin_ref
- `KnowledgeLink.validate_against` — learned ≥ historical
- `TruthStateLoader.validate` — participants по known_npcs, importance [0,1], dangling/self-loop/strength
- `npc_loader._enrich_with_social_relations` — шкала 0..1 → ×100

## Запреты (соблюдены)

- `npc_loader.py` — НЕ изменён
- `chronicle_seeder.py` — НЕ изменён
- Авторские JSON (`individuals/*.json`, `village_relations.json`, `truth_state_*.json`) — НЕ изменены
- `EntryKind.SECRET` — НЕ введён
- Рантайм НЕ читает проекции
- Существующие каноны НЕ размечены автоматически (нет `is_secret`-инъекций)
- Фиктивные ID НЕ создаются
- Неизвестное НЕ подменяется утверждением об отсутствии факта

## Открытые долги (вне CCH-5)

1. **`chronicle_seeder.build_seed_knowledge` создаёт `is_secret=True` для ВСЕХ `KNOWLEDGE_LINK`** — расхождение с EXPLICIT. Домен EventMemory (память NPC) ≠ домен TruthState (карта правды). Решение — отдельное (не CCH-5).
2. **`maid_lusya.json` отсутствует в каноне** — эталон CCH-1 не канонизирован. CCH-5 для текущих канонов даёт `truth_state_status: EMPTY`.
3. **`object_id=null` во всех EVENT существующих канонов** — `participants=[subject]`. Не баг CCH-5.
4. **F1-урок в редакторе персонажей** — отдельная UX-задача (не CCH-5).
5. **CCH-6** — калибровка порога `needs_confirmation` на корпусе 3-5 биографий; самоочистка TZ_CCH-01.

## Гейты

- ruff: ✅ All checks passed (3 файла)
- pytest CCH-5: ✅ 22/22 passed (0.34s)
- IPT: ✅ 53/53 passed, 0 CRITICAL
- lint_frontend_isolation: ✅ Нарушений не найдено
- compileall: ✅ Все 3 файла скомпилированы

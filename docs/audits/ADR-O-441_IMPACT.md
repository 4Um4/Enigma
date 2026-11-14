# ADR-O-441 Impact Audit

> Детальный аудит ОДНОГО ADR. Атлас: `docs/ADR (Architecture Decision Records).md`.
> Связанные: ADR-128 (COLD-1 SQLite runtime truth), ADR-O-440 (WARA §12.2), ADR-O-309 (WorldProjectionBuffer, AUDIT #10 OFF), S1-FIX (INV-COMMIT-CARDINALITY).
> Коммит: `67a13349` — fix(persistence): restore NPC runtime commit path (R1-R6)

## Дефект и эмпирическое доказательство

Разорванная цепь:

- `commit_phase.py:168,200` и `campaign_lifecycle.py:398` вызывают `SSM.commit(npc_dicts=...)`
- `SSM.commit:1348` кладёт пейлоад в `_last_committed_npcs_src` — консюмер OFF (AUDIT #10)
- `SSM.commit:1350` возвращает 2, персистентности нет
- `unlock_tick:293-296` вызывает `atomic_commit_all(all_scenes=...)`; `npc_states=None` → ветка адаптера 328-329 мертва
- `life_engine:1017` читает `load_npc_runtime` → `_select(runtime:{id})` — ключ, который никто не пишет

Дисковое доказательство (read-only инспекция живой БД): `saves/enigma_runtime.db` 409 600 bytes (2026-11-08 23:55) + WAL 4 206 552. Таблица `state_kv` содержала ровно два ключа: `scene:Open_road:tavern` (36444) и `scene:tavern_silver_wolf:tavern` (16568). Ключа `runtime:` нет; `npc_runtime.json` в saves/ нет.

Две независимые линии сошлись: цензус кода по всему backend (ни один production-вызывающий не передаёт NPC-пейлоад) и состояние диска.

Виновник регрессии: S1-FIX (INV-COMMIT-CARDINALITY) перенёс запись из Phase 10 в unlock_tick, не перенеся NPC-пейлоад. Фоссили до-рефакторного поведения — докстринг `SSM:1285` («Делегирует в PersistencePort.atomic_commit()») и комментарий `life_engine:1012`; оба утверждали запись, которой код не делал.

Почему зелёный baseline не поймал: `INV-SAVE-LOAD-INTEGRITY` проверяет round-trip сцены (`IPT:1687` load_scene_at). NPC runtime round-trip ни одним инвариантом не требовался — пробел покрытия, не ложнозелёный тест.

## Changed Domains

- **SSM __init__** — tick-scoped поле `_tick_npc_runtime: list[dict] | None` рядом с `_tick_scenes`.
- **SSM commit()** — `copy.deepcopy(npc_dicts)` при непустом пейлоаде. `_last_committed_npcs_src` не тронут (иная семантика: state_t-1).
- **SSM unlock_tick()** — `npc_states=self._tick_npc_runtime`; результат в `_commit_ok`; `logger.error` с campaign_id при False. Сигнатура остаётся `-> None`.
- **SSM unlock_tick() finally** — сброс снимка рядом с `_tick_aborted = False`, обе ветки (persist и abort).
- **IPT** — `inv_npc_runtime_roundtrip` + регистрация в INVARIANTS.

Не изменены: SqlitePersistenceAdapter, JsonPersistenceAdapter, PersistencePort, NPCState.to_persistence_dict, npc_loader, LifeEngine, TickOrchestrator.

## Downstream Consumers

- **LifeEngine._load_npcs:1015-1017** — read-back ADR-128 (injuries, blood_loss, affective_load после TTL/LRU eviction) становится работающим.
- **npc_loader.load_npcs_merged:398-421** — ветка runtime-overlay вместо тихого отката к static.
- **commit_phase / campaign_lifecycle** — вызывающие не изменены; их пейлоад теперь доезжает.
- **WorldProjectionBuffer** — консюмер остаётся OFF, поведение не изменилось.

## Runtime Impact

- **RAM**: +1 deepcopy списка NPC на commit() (раз в тик на локацию). Симметрично существующему `copy.deepcopy(scene_state)` на SSM:1334. Владение all_npcs_raw не передаётся — копия обязательна.
- **Latency**: +1 сериализация NPC-списка в транзакцию. Измерений не проводилось — UNVERIFIED.
- **Persistence**: ключ `runtime:{campaign}` в state_kv. Транзакция уже покрывала сцены+NPC+events (sqlite:326-332) — границы не менялись.
- **Обратная совместимость**: аддитивно, схема не меняется, миграция не требуется.
## Legacy Policy

| Состояние | Поведение |
| --- | --- |
| Новый сейв после патча | полный NPC runtime round-trip |
| Старый сейв: scene: без runtime: | существующий fallback npc_loader:405-409 (static + warning). Диагностика с перечнем утраченных полей — DEFERRED |
| NPC в сцене, runtime отсутствует | из npc_positions доступны position, local_position, activity, name, location_id (новая схема сцены). Остальное честно отсутствует |
| BODY_STATE_HEALTHY при отсутствии runtime | контракт рождения NPC сохранён (npc_loader:465-470). **Это не восстановление здоровья — фактическое состояние неизвестно.** Компромисс совместимости; отдельная политика legacy — будущая задача |
| Runtime повреждён | 405-409 перехватывает Exception → static. **Отсутствие runtime (legacy) и повреждение (ошибка целостности) — разные состояния**; сейчас сливаются в один переход. Разделение — DEFERRED |
| Ошибка SQLite-коммита | R4: logger.error с campaign_id. Проброс наверх не вводился — контракт -> None сохранён |

## Sandbox Tests

`backend/tests/micro/test_npc_runtime_persistence.py` (4 теста):

- **T1** adapter-level persistence round-trip: мутация NPC → commit() → мутация того же dict ПОСЛЕ commit → unlock_tick() → adapter.close() → новый адаптер → load_npc_runtime. Сверены body_state.blood_loss=0.35, injuries=[cut_left_arm], psyche.stress=47.5, drives.hunger=0.62, location_id, intent=TRADE, narrative_cache. Двухступенчатая проверка: сначала сцена сохранена (tick-путь отработал), затем runtime — отличает дефект от ошибки подготовки.
- **T2** atomic_commit_all → False → ERROR с campaign_id, не теряется бесследно.
- **T3** aborted tick → ни сцен, ни NPC; _tick_npc_runtime is None после границы (нет протечки).
- **T6** multi-location: две сцены сохранены, npc_a в runtime ровно один.

**Терминология точно:** adapter-level persistence round-trip (прежний адаптер закрыт, его RAM уничтожена, новый читает с диска). **Не** full process restart — полноценный перезапуск процесса игры остаётся отдельным E2E-контролем, NOT VERIFIED.

Красное до патча: T1/T2/T6 — 3 failed, 1 passed, сообщение DEFECT при сохранённых сценах.

**IPT:** без патча 54 passed / 1 failed (1 CRITICAL) — INV-NPC-RUNTIME-ROUNDTRIP: load_npc_runtime пуст. С патчем 55 / 0 / 0. Красное состояние инварианта наблюдалось контролируемым откатом SSM с гарантированным возвратом.

**Регресс:** test_det3_crash_recovery, test_new_8_scene_manager, test_persistence_port — 16 passed.

## DEFERRED

- **T4** — диагностика legacy-сейва: явный WARNING с перечнем невосстановимых полей вместо тихого using static only. Требует правки npc_loader.py — вне разрешённых границ патча.
- **T5** — разделение «runtime отсутствует» (legacy fallback) и «runtime повреждён» (ошибка целостности). Сейчас оба идут через npc_loader:405-409 в один переход к static.

Оба не выполнялись. Статус честно «отложено», не «выполнено».

## Дефект маркера миграции (ЗАКРЫТ)

**CONFIRMED по коду, не исправлен в этом патче.**

- `migrate_legacy:324-369` — transform пишет в scene_state[relationship_state][directed] (RAM)
- `unlock_tick:307` — atomic_commit_all → False, rollback → v2 НЕ на диске
- `unlock_tick:311-313` — _confirm_v2_migration вызывается безусловно
- `confirm_migration:388` — пишет .migrated
- следующий запуск: `migrate_legacy:318-319` видит маркер → return skipped=True → legacy-пары больше не импортируются, а в v2 на диске их нет

Докстринг relationship_state_store:303-306 обещает идемпотентность «даже без маркера», но аргумент о чистоте transform работает только если transform запустится; при наличии маркера строка 318-319 делает early return до чтения. Предпосылка 370-375 «ИСТИНА — v2 на диске» верна лишь при успешном коммите.

- **Что теряется:** legacy-пары NPC→NPC (trust, fear, debt, attraction) из npc_relationships.json.
- **Окно:** кампании mid-cutover (legacy есть, .migrated нет) И отказ коммита. Уже мигрированные вне риска.
- **Обратимость:** данные на диске целы (.migrated — отдельный файл); автоматически не восстановятся, ручное удаление маркера возвращает миграцию.
- **Предложенный фикс (одна строка, требует отдельного GO):** `if _commit_ok: self._confirm_v2_migration(campaign_id)`. Флаг доступен от R4.


### Статус закрытия

Дефект **ЗАКРЫТ**. Фикс применён и закоммичен.

- **Фикс:** `_confirm_v2_migration` обёрнут в `if _commit_ok` (scene_state_manager.py:313-315). Флаг `_commit_ok` появился в R4 (коммит 67a13349).
- **Коммит:** `01047197` (релиз V.0.5.4.6.5). Фикс вошёл в релизный коммит вместе со всем рабочим деревом; отдельным атомарным коммитом не стал — отклонение от плана, принятое Мастером (Вариант 1).
- **Тесты:** `backend/tests/micro/test_migration_marker_guard.py` — T-M1 RED→GREEN (маркер не создаётся при `atomic_commit_all → False`); T-M2 GREEN (создаётся при успехе); T-M3 GREEN (идемпотентность). Регрессия: 10 passed, 1 xfailed; IPT 55/0/0.
- **Отклонение:** коммит не атомарный (релиз включил чужие правки). История для этого фикса нечитаемая. Принято, не исправляется.
- **Смежный дефект (вне скоупа):** `confirm_migration` (relationship_state_store.py:384-388) создаёт маркер даже без legacy-файла. Зафиксирован как T-M4 xfail. Отдельная задача.

## Rollback

Полный revert в 3 файлах (коммит `67a13349`):

1. scene_state_manager.py — удалить _tick_npc_runtime (init), deepcopy-блок в commit(), npc_states= и _commit_ok-блок в unlock_tick(), сброс в finally.
2. IPT.py — удалить inv_npc_runtime_roundtrip и регистрацию.
3. tests/micro/test_npc_runtime_persistence.py — удалить файл.

**Совместимость с сейвами:** ключ runtime:{campaign}, записанный новым кодом, остаётся читаемым старым загрузчиком (life_engine:1017 → load_npc_runtime, формат идентичен — raw npc_dicts). Состояние NPC после отката загружается лучше, чем до патча; регрессии состояния нет. Схема БД не менялась, миграций не вводилось.

Тег до патча: `pre-persist-recovery`.

# Отчёт сравнения: V.0.5.2.5_Почти_почти_4 vs V.0.5.2.6_Почти_почти_5

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | 37 |
| **Строк добавлено** | 869 |
| **Строк удалено** | 380 |
| **Новых файлов** | 6 |
| **Удалённых файлов** | 2 |
| **Переименований/переносов** | 3 |
| **Новых function defs (вкл. методы, gross)** | 9 |
| **Новых function defs (net, без переопределения сигнатуры)** | 8 |
| **Базовый коммит (V.0.5.2.5)** | `a65718c` |

## Какие функции реально добавлены

Новые (net) функции/методы в рабочем коде:

1. `TickOrchestrator.set_state_applicator`
2. `TickOrchestrator.set_reputation_engine`
3. `TickOrchestrator.add_idle_handler`
4. `TickOrchestrator._phase_0_5_idle_services`
5. `TickOrchestrator._build_npc_snapshots`
6. `TickOrchestrator._aggregate_deltas`
7. `ServiceFactory.get_state_applicator`
8. `SceneStateManager._enrich_spatial_data`

Отдельно: `GameLoop.idle_tick()` не новая сущность, а смена boundary-контракта (возврат dict вместо DTO на границе фронта).

## Что сделано по сути (а не по объёму строк)

### 1. Фаза 0.5 переведена в непрерывный режим времени
**Ключевые файлы:**
- `backend/app/services/tick_orchestrator.py`
- `backend/app/services/game_loop/__init__.py`
- `backend/app/services/game_loop/service_factories.py`

**Суть:**
- Time-driven handlers (social/reputation decay) исполняются не только в idle, но и в player finalize.
- Добавлен `delta_buffer` с агрегацией дельт перед единым persistence-шагом.
- Введён DI-контур для `StateApplicator`/`ReputationEngine`/idle-handlers.

**Ценность:**
- Закрыт класс эксплойтов «игрок ходит — время мира не идёт».
- Поведение мира становится более каузально устойчивым между тиками разных типов.

### 2. Пространственная модель стала жёстче и чище
**Ключевые файлы:**
- `backend/app/services/spatial/movement_engine.py`
- `backend/app/services/spatial/graph_compiler.py`
- `backend/app/services/spatial/spatial_service.py`
- `backend/app/services/scene_state_manager.py`

**Суть:**
- Удалены legacy fallback-механики `LocationGraph` в `MovementEngine`.
- `compile_graph()` возвращает `connections` явно, убран глобальный скрытый store.
- Сцена при загрузке обогащается `spatial_walls/spatial_obstacles` из editor JSON.

**Ценность:**
- Меньше скрытого состояния и менее хрупкая навигация NPC.
- Логика перемещения ближе к единому source of truth карты.

### 3. Граница frontend/backend очищена
**Ключевые файлы:**
- `backend/app/services/game_loop/__init__.py`
- `frontend/game_loop_bridge.py`
- `frontend/game_screen.py`

**Суть:**
- DTO->dict конверсия idle-результата перенесена внутрь backend (`GameLoop.idle_tick`).
- Bridge больше не зависит от `app.domain.*`.
- Удалён фронтовый обходной enrich spatial на старте экрана (обогащение перенесено в `SceneStateManager`).

**Ценность:**
- Снижение межслойной связности и риска «тихих» контрактных рассинхронов.

### 4. Нормализация семантики интенсивности действия
**Ключевые файлы:**
- `backend/app/domain/constants.py`
- `backend/app/services/action/dm_router.py`
- `backend/app/services/game_loop/phase_1_input.py`

**Суть:**
- Единая карта `ACTION_INTENSITY` вынесена в domain constants.
- Одинаковая шкала теперь используется в классификации player-событий и downstream-пайплайне.

**Ценность:**
- Снижение drift-ошибок между слоями обработки одного и того же события.

### 5. Тестовый контур переформатирован под новую архитектуру
**Ключевые файлы:**
- `backend/tests/test_spatial_runtime_r4.py`
- `backend/tests/test_location_graph_r4.py` (удалён)
- `backend/tests/test_provider_manager.py`
- `backend/tests/test_event_memory.py`

**Суть:**
- Убраны/очищены устаревшие тесты legacy-контуров.
- Часть ранее `skip`-тестов по spatial-runtime активирована.
- Тесты, завязанные на новый контракт `StateDeltas`, приведены к требованию `npc_id`.

**Ценность:**
- Меньше ложнопозитивного «зелёного» CI на неактуальных инвариантах.

## Сколько реально сделано за день

Если оценивать инженерный вклад не строками, а «закрытыми классами системных рисков», за день выполнено:

1. **1 крупный архитектурный сдвиг:** непрерывное time-driven обновление мира в обоих путях тика.
2. **1 критичная стабилизация spatial-контура:** переход от смешанного legacy/fallback режима к каноническому сервису.
3. **1 boundary-рефакторинг высокого ROI:** чистая сериализация idle-контракта на backend-границе.
4. **1 унификация доменной семантики:** централизованный `ACTION_INTENSITY`.
5. **1 пакет инфраструктурной чистки документации:** перенос регламентных документов в `docs/Tasks/`.

Это не «написано много текста», а серия изменений, которые уменьшают энтропию ядра симуляции и повышают предсказуемость изменений в следующих версиях.

## Риски и вторичные эффекты

1. В `Phase 8` ещё сохраняется ручная мутация части social-deltas в `_apply_phase8_result`, то есть миграция в полностью единый `apply_batch()` не завершена.
2. Жёсткая зависимость `MovementEngine` от `SpatialService` повышает требования к корректной DI-инициализации на старте сцены.
3. Удаление legacy-тестов снижает шум, но временно сужает ретроспективное покрытие старых путей.
4. Большой блок doc-изменений в одном коммите повышает когнитивную стоимость code review.

---

*Источник: `git diff --cached` относительно `V.0.5.2.5_Почти_почти_4` (commit `a65718c`), включая `--shortstat`, `--name-status --find-renames`, `--numstat`, и анализ добавленных function defs по python-диффу.*

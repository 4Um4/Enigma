# Отчёт сравнения: V.0.5.2.4_Почти_почти_3 vs V.0.5.2.5_Почти_почти_4

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | 29 |
| **Строк добавлено** | 1228 |
| **Строк удалено** | 1679 |
| **Новых файлов** | 5 |
| **Удалённых файлов** | 1 |
| **Новых function defs (вкл. методы)** | 13 |
| **Новых top-level классов/протоколов** | 4 |
| **Базовый коммит (V.0.5.2.4)** | `953c1ad` |

## Что реально добавлено (по функционалу, а не по строкам)

### 1. Формализована idle-фаза 0.5 как отдельный time-driven контур
**Файлы:**
- `backend/app/models/idle_tick.py`
- `backend/app/services/social/social_decay_handler.py`
- `backend/app/services/social/reputation_decay_handler.py`

**Суть:**
- Введён протокол `IdleTickHandler` и снапшот-контракт `NPCStateSnapshot`.
- Добавлены два независимых drift-механизма: социальный (`trust -> base`) и репутационный (`reputation -> base_reputation`).
- Дрейфы считаются как чистые функции и возвращают `StateDeltas` вместо прямых мутаций runtime-структур.

**Ценность:**
- Это переход от «эпизодических правок состояния» к регулярной физике социального мира, когда NPC и фракции меняются даже без действий игрока.

### 2. Усилен единый язык мутаций (`StateDeltas`) и точка применения (`StateApplicator`)
**Файлы:**
- `backend/app/models/state_delta.py`
- `backend/app/services/npc/state_applicator.py`
- `backend/app/services/social/reputation_engine.py`

**Суть:**
- `StateDeltas` получил маршрутизацию по типу цели: `intent_target`, `social_target`, `faction_id`, `npc_id`.
- Добавлены семантические ограничения (изоляция `reputation_delta` от `trust/fear` домена).
- `StateApplicator` получил `apply_batch()` для пакетного применения дельт (фракции + NPC) через единый мутатор.
- `ReputationEngine` разделён на `compute_decay()` (чистый расчёт) и `apply_deltas()` (единственная мутация).

**Ценность:**
- Архитектура стала ближе к event-sourcing модели: вычисление и применение разделены, что повышает проверяемость и предсказуемость.

### 3. Социальная пропагация переведена с прямых мутаций на дельта-поток
**Файлы:**
- `backend/app/services/social/propagation.py`
- `backend/app/services/events/social_subscriber.py`
- `backend/app/services/events/perception_subscriber.py`
- `backend/app/services/game_loop/phase_1_input.py`

**Суть:**
- `propagate_social_rumors()` теперь возвращает `(tick, List[StateDeltas])`.
- `SocialSubscriber` перестал мутировать `all_npcs_raw` напрямую и отдает дельты в оркестратор.
- Источник интенсивности события стандартизирован через `EventDTO.payload.intensity`.
- `PerceptionSubscriber` начал учитывать все накопленные события за drain-цикл, а не только последнее.

**Ценность:**
- Подсистема стала причинно полнее: меньше потерь сигнала, меньше скрытых side-effect мутаций, выше наблюдаемость фазы 8.

### 4. SpatialService перешёл из «слоя рядом» в «рабочий слой навигации»
**Файлы:**
- `backend/app/services/spatial/spatial_service.py`
- `backend/app/services/spatial/movement_engine.py`
- `backend/app/services/npc/life_engine.py`
- `backend/app/services/npc/npc_tick_pipeline.py`
- `backend/app/services/game_loop/npc_orchestration.py`
- `backend/app/services/scene_state_manager.py`

**Суть:**
- Добавлена фабрика `SpatialService.build_for_location(...)` с компиляцией графа и оверлея под текущую сцену.
- `MovementEngine` и `LifeEngine` получили DI для SpatialService и маршрутную логику через него.
- Реактивное движение NPC (`approach/flee`) теперь умеет работать через SpatialService (с fallback на legacy-граф).
- Пространственные подписи в `scene_state_manager` резолвятся динамически через SpatialService.

**Ценность:**
- Пространственный интеллект NPC начал влиять на реальные игровые решения внутри тика, а не быть только подготовительным модулем.

### 5. Консолидация источника spatial-данных и чистка legacy
**Файлы:**
- `backend/data/campaigns/Open_road/locations/tavern.json` (удалён)
- `backend/data/locations/location_templates.json` (упрощён)
- `backend/app/services/spatial/location_graph.py`
- `backend/tests/test_location_graph_r4.py`
- `frontend/game_loop_bridge.py`

**Суть:**
- Удалён большой дублирующий `tavern.json` из backend campaign data.
- В `location_graph.py` удалён встроенный fallback-граф, акцент смещён на editor JSON как источник истины.
- Временный `skip` для R4-тестов location_graph до завершения migration gap.
- Удалены устаревшие bridge-методы в frontend bridge.

**Ценность:**
- Меньше дублирования и расхождения данных между frontend/backend, меньше риска silent-divergence графов.

## Сколько новых функций добавлено за день

Подсчёт по AST-диффу (по сравнению с `953c1ad`):

1. **13 новых function defs** (включая методы классов).
2. **4 новых top-level класса/протокола** (`NPCStateSnapshot`, `IdleTickHandler`, `ReputationDecayHandler`, `SocialDecayHandler`).
3. Ключевые новые точки расширения: `StateApplicator.apply_batch`, `ReputationEngine.compute_decay`, `SpatialService.build_for_location`, `LifeEngine._make_random_events` (в class scope), `MovementEngine.set_spatial_service`.

## Что было сделано за день по фактической ценности

1. Добавлен **новый контур симуляции времени** (phase 0.5), который влияет на динамику мира без участия игрока.
2. Завершён **критичный шаг к детерминизму мутаций**: social/reputation изменения переведены в поток `StateDeltas`.
3. Пространственная подсистема стала **операционной частью NPC-поведения**, а не изолированной заготовкой.
4. Снижено дублирование источников spatial-данных и удалён legacy-шум в bridge-слое.

Это прирост не в «объёме текста», а в глубине симуляционной причинности и в устойчивости архитектуры.

## Риски и вторичные эффекты

1. В коде есть признаки merge-артефактов (дублирующиеся определения в отдельных файлах), что повышает риск скрытого перекрытия логики.
2. Часть coverage временно потеряна (`test_location_graph_r4.py` в `skip`) до завершения миграции.
3. Удаление backend-`tavern.json` усиливает зависимость от editor JSON-пути; при сбое загрузки SpatialService деградирует в fallback-режим.
4. В Phase 8 остаётся промежуточный мост с ручным применением некоторых дельт, пока не завершён полный перенос в `StateApplicator`.

---

*Источник: staged diff ветки `V.0.5.2.5_Почти_почти_4` относительно базового коммита `953c1ad`, `git diff --cached --shortstat/--numstat/--name-status`, AST-анализ новых function defs.*

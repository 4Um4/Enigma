Вот переработанный файл `MUTATIONS.md`. 
**Что было сделано:**
1. **Дедупликация и консолидация:** Исходный файл содержал множество разрозненных блоков с одинаковыми номерами сессий (например, четыре блока `SESS_09` и три `SESS_14`). Все изменения объединены в единые хронологические записи.
2. **Хронология:** Даты выстроены в строгую логическую последовательность от старта проекта (07.04.2026) до текущего дня (10.05.2026). Устранены анахронизмы (вроде 27.05.26 в прошлом).
3. **LLM-friendly формат:** Внедрена строгая структура: `### [SESS_XX] Дата: Название спринта`, список измененных файлов, суть изменений маркированная через `Контракт/Баг/Рефакторинг`. 
4. **Читаемость:** Исправлены рваные переносы, добавлены пробелы, выделены ключевые сущности (DTO, домены, имена файлов) для мгновенного парсинга контекста ИИ-ассистентом.

---

# MUTATIONS.md — История изменений проекта ENIGMA

## Сессия 01: Реформа Idle Tick и делегирование оркестратору
**Дата:** 07.04.2026  
**Изменения:**
- `GameLoop.idle_tick()`: Новый метод, делегирует выполнение в `TickOrchestrator.execute()` (idle mode). Импортирован `TickResultDTO`.
- `GameLoopBridge.idle_tick()`: Новый метод, конвертация `WorldSnapshotDTO→dict` через `asdict()`. Удалены deprecated методы `get_life_engine()` и `get_npc_runtime_path()`.
- `DirectGateway.idle_tick()`: Переписан с ~50 строк ручной работы с `LifeEngine` на 5 строк делегирования в `bridge.idle_tick()`.
- `routes.py idle_tick()`: Переписан с ~30 строк извлечения `scene_state` на 5 строк через `game_loop.idle_tick()`. Устранён баг создания `TickOrchestrator` без `memory_manager` и `event_bus`.

## Сессия 02: Миграция на WorldSnapshot
**Дата:** 08.04.2026  
**Изменения:**
- `game_screen.py`: `npc_positions` теперь читается из `world_snapshot` (канонический источник, Фаза 9) с fallback. Добавлена синхронизация `player_position`, `time_of_day`, `weather`.
- **Багфикс:** Изменен `setdefault("npc_id")` → `setdefault("npc_positions")`.

## Сессия 03: Интенсивность событий и мультисобытийность Perception
**Дата:** 09.04.2026  
**Изменения:**
- `phase_1_input.py`: Добавлен `_INTENSITY_MAP`, `publish_classified_player_event()` теперь включает `intensity` в `EventDTO.payload`.
- `propagation.py`: В `propagate_social_rumors()` добавлен параметр `events`. Канонический путь: `intensity/event_type/actor_id` из `EventDTO.payload`. Заменены `_evt.*` на локальные переменные.
- `social_subscriber.py`: `handle()` передаёт `events` в `propagate_social_rumors()`.
- `perception_subscriber.py`: `handle()` обрабатывает ВСЕ накопленные события через цикл вместо `events[-1]`. Применён `set.update()`.

## Сессия 04: SpatialService v1.2 и централизация пространственных данных
**Дата:** 10.04.2026  
**Изменения:**
- **Интеграция SpatialService v1.2:** `NpcTickServices` добавлено поле `spatial_service`. `LifeEngine` добавлен DI через `set_spatial_service`, хардкод "bar_area" заменен на `svc.resolve_node(NodeRole.BAR)`.
- `movement_engine.py`: Добавлен DI, `LocationGraph.find_path` заменен на `svc.find_path`.
- `scene_state_manager.py`: `_position_map` удален, заменен на `svc.get_node_label`. Добавлен метод `_enrich_spatial_data()` (загрузка `spatial_walls/obstacles`). В сборку `npc_positions` добавлено поле `"name"`.
- `graph_compiler.py`: Удалена глобальная переменная `_connections_data` и функция `get_connections()`. `compile_graph` теперь возвращает кортеж `(graph, connections, alias_map)`.
- **Очистка frontend:** В `game_screen.py` удалены вызовы `_gateway._bridge.*` (нарушение Устава §1.1). Создана локальная функция `_build_perceived_scene()`.
- **Очистка legacy:** Из `movement_engine.py` удален кэш `_graphs`, методы `_get_graph`, `invalidate_cache`, денормализация ID (`denormalize_id`). Удалены _BUILTIN_NODES.

## Сессия 05: Delta Buffer как единый канал мутации
**Дата:** 12.04.2026  
**Изменения:**
- `propagation.py`: Баг `break` заменен на `max()` (агрегация intensity). Удалена мутация `shared_context.social_propagation`.
- `Phase8Result`: Добавлены поля `socially_affected_npc_ids` и `events_processed`.
- `social_subscriber.py`: Извлекает affected IDs из deltas.
- `domain/constants.py`: Создан единый источник `ACTION_INTENSITY`. Удалены дубликаты `_INTENSITY_MAP` и `_BASE_INTENSITY`.
- `GameLoop.idle_tick()`: Конвертация DTO→dict перенесена из `game_loop_bridge.py`. Bridge больше не импортирует `app.domain.*` (Устав §1.1).
- `TickOrchestrator.finalize_and_commit()`: Удалён (deprecated).

## Сессия 06: Time-driven vs Event-driven (Фаза 0.5)
**Дата:** 27.04.2026  
**Изменения:**
- `StateDeltas`: Расширена полями `intent_target`, `social_target`, `faction_id`, `reputation_delta`. Добавлена `__post_init__` валидация (# LOCKED v1).
- Создан `app/models/idle_tick.py` (`NPCStateSnapshot`, `IdleTickHandler`).
- Создан `app/services/social/social_decay_handler.py` (`SocialDecayHandler` с closing drift).
- Изменён `app/services/social/reputation_engine.py` (`compute_decay()` чистая функция, `apply_deltas()` принимает `StateDeltas`).
- Создан `app/services/social/reputation_decay_handler.py` (`ReputationDecayHandler`).
- `state_applicator.py`: Добавлен `_apply_faction_delta`, `apply_batch`, `_apply_delta_to_raw`.
- `tick_orchestrator.py`: Добавлен `delta_buffer`, `_phase_0_5_idle_services`, `_build_npc_snapshots`, `_aggregate_deltas`. Добавлен guard `if not events` и flush `delta_buffer` в Фазе 10.

## Сессия 07: Реставрация тестового покрытия (ADR-001/003)
**Дата:** 01.05.2026  
**Изменения:**
- Во все тестовые фабрики добавлено обязательное поле `npc_id` (нарушение контракта `StateDeltas`).
- Удалены мертвые файлы и классы: `test_location_graph_r4.py`, `TestMemoryBreathes`, `KnowledgeIngestTests`, `PdfDropImporterTests`.
- Устранены Fragile Tests: I/O фикстура `real_scene_state` заменена на `_make_rich_scene()`.
- Обновлены ассерты под русскую вербализацию. Сняты skip-маркеры с `test_spatial_runtime_r4.py`. Тестовый набор: 424 PASSED.

## Сессия 08: Социальный маппинг и обогащение NPC
**Дата:** 03.05.2026  
**Изменения:**
- `_build_npc_snapshots()`: Починен критический разрыв данных. Маппинг `social_stats` → `relationship_cache["player"]`, `loyalty_true` → `base_values["player"]`.
- `npc_loader.py`: Создана `_enrich_with_social_relations()` — обогащает NPC dict связями из `village_relations.json` (конвертация ×100). Критический фикс: shallow copy + гарантированное добавление player entry.
- `tick_orchestrator.py`: Починен баг: `ctx.all_npcs_raw` не заполнялся в idle-пути. Добавлена синхронизация `ctx.all_npcs_raw = ctx.npc_states`.

## Сессия 09: ReactionSubscriber и очистка мутаций
**Дата:** 04.05.2026  
**Изменения:**
- Создан `ReactionSubscriber` (Phase8Handler). Прямые эмоциональные реакции (stress/fear/trust) без decision-цикла. Порядок: `perception → reaction → social`.
- `_apply_phase8_result()`: Прямая мутация `all_npcs_raw` заменена на маршрутизацию через `delta_buffer → apply_batch()`. Добавлен flush буфера.

## Сессия 10: Narrative Beat System и починка Pipeline движения
**Дата:** 07.05.2026  
**Изменения:**
- **Cinematic Layer:** Создан `NarrativeBeat`, `DeliveryType`, `RecognitionLevel`. Создан `NarrativeRenderer` (пузыри Persona 5 стиля). Текст игрока — справа. Запрет Ctrl+V.
- **Движение:** Восстановлен контракт возврата в `check_random_events()` (кортеж). Страж мутации `position` смягчён (debug log). Запрещено использовать `MovementIntent` для микро-перемещений (требуется `LocalSteeringIntent`).
- **Микро/Макро:** Миграция позиций в `archetypes/*.json` с микро-зон на макро-зоны.

## Сессия 11: StateDeltas v2 и Спикеры
**Дата:** 08.05.2026  
**Изменения:**
- **StateDeltas v2:** Создан `app/models/delta_payloads.py` (frozen dataclasses). `StateDeltas` расширена `DeltaDomain`, `target`, `payload`. ReactionSubscriber разделен на 2 дельты (EMOTION + SOCIAL). `_aggregate_deltas` группирует по `(npc_id, domain, target)`.
- **Speaker Extraction:** `dm_response` разбивается на строки, спикер извлекается через `known_names`. Создан `system_log` (Log Layer). Починка фильтра эха (флаг `is_short_input`).
- **UI:** Реализован Bubble Lifetime (5 сек жизнь, 2 сек фейд). Визуальная экспрессия для SHOUT/WHISPER.

## Сессия 12: Physiology Domain и Impact Engine
**Дата:** 09.05.2026  
**Изменения:**
- **Домен PHYSIOLOGY:** `DeltaDomain.COMBAT` удален. Создан `InjuryDTO` (`target_zone`), `PhysiologyPayload` (hp, pain, blood_loss, shock_impulse). В `NPCState` добавлено `body_state`.
- **Impact Propagation Engine:** Pure Function. Контактная модель вместо RPG Hit Roll. Возвращает ТОЛЬКО Physiology-дельты (No Domain Leakage).
- **Time Control System:** Добавлена переменная `_time_scale` (1-50). Бэкенд продвигает `game_time_seconds`. Добавлен `format_world_date`.

## Сессия 13: DRSL, CombatSubscriber и Decay
**Дата:** 09.05.2026  
**Изменения:**
- **DRSL (Domain Reduction Semantics Layer):** Добавлен `ReductionPolicy` и `DELTA_POLICY_REGISTRY`. `PHYSICS_COMPOSITE` обходит merge.
- **CombatSubscriber:** Мост `EventDTO → ImpactEngine`. Порядок Фазы 8 обновлен.
- **PhysiologyDecayHandler:** Leaky Integrator для Фазы 0.5. `S_t = S_{t-1} * exp(-lambda * dt)`.
- **Embodied Traversal:** `_MoveState` разделен на Навигацию, Кинетику, Эмбодимент (`facing_angle`, `facing_mode`).

## Сессия 14: Починка крашей и Визуализация
**Дата:** 09.05.2026  
**Изменения:**
- **Багфиксы:** Починен возврат `str` вместо `Path` в `_get_npc_runtime_path`. Починен `NameError: DELTA_POLICY_REGISTRY`. Защита micro-position (`from_node_id == target_node_id`).
- **NPC Position Delivery:** `DirectGameGateway` теперь передаёт `world_snapshot` и `npc_positions` на фронтенд (has_ws=True).
- **Визуал:** Ротация стрелки игрока через поворот полигона. Календарь в HUD.

## Сессия 15: Архитектурная чистка и CFRM
**Дата:** 10.05.2026  
**Изменения:**
- **Очистка:** Удалены `cached_position`, `position_valid`, `_cached_distance_to()` из `npc_state.py`. Удалена `patch_scene_state`.
- **CFRM (Causal Field Reduction Model):** Принят ADR-0016. Глобальный объект World удалён. Введены `ClusterGraph`, `EventBuffer`, `MembraneField`. NPC хранит `PerceptualKernel`.

## Сессия 16: Layered Reduction и Body Profile
**Дата:** 10.05.2026  
**Изменения:**
- **Layered Reduction (ADR-0016):** Фаза 8 переписана на многоступенчатую редукцию: `Perception → Combat → Reaction → Social`. Combat материализует дельты в `physical_deltas_materialized`.
- **Каскад Shock → Emotion:** ReactionSubscriber извлекает `shock_impulse`. Цель получает шок от боли, свидетель — эмпатический ужас. `shock > 0.5` генерирует `emotion_tag="panic"`.
- **Миграция конфигов (ADR-0017):** Во всех `archetypes/*.json` удалена секция `combat_stats`. `abilities` перенесены в `body_profile`, добавлены `max_hp` и `base_ac`.
- **Визуал (Lerp):** Сглаживание поворота стрелки игрока (10 рад/сек). Индикатор внимания NPC (желтая линия). Рендер `spatial_obstacles`. Увеличено время жизни пузырей (10 сек + 3 сек фейд). Отключено перемещение кликом мыши.
- **E2E тесты:** Создан `test_combat_pipeline_e2e.py`. Итого: 459 passed, 0 failed.

## Сессия 17: Реализация CFRM Layer 1 и Legacy Bridge
**Дата:** 10.05.2026  
**Изменения:**
- **`backend/app/models/cfrm.py` (Новый):** Создан доменный слой Causal Field Reduction Model. Введены: `ClusterID`, `ClusterDef` (1 макро-узел = 1 кластер, `boundary_cells`), `ClusterGraph` (пространственная декомпозиция), `CausalAxis` (PHYSICAL, COGNITIVE, SOCIAL), `EventBuffer` (временный causal input stream с `drain()`), `ClusterOccupancy` (Spatial Index для O(1) поиска NPC в кластерах), `classify_event()` (Legacy Bridge маппит `EventType` на 3 оси CFRM). **[Контракт]**
- **`backend/app/services/spatial/spatial_service.py`:** Добавлен импорт CFRM-моделей. Внедрён метод `build_cluster_graph()`, строящий `ClusterGraph` из текущих узлов макро-графа и связей. **[Рефакторинг]**
- **`backend/app/services/events/event_bus.py`:** Внедрены методы `attach_cfrm_buffer()` и `detach_cfrm_buffer()` для перехвата фактов реальности. В `publish()` добавлен автоматический вызов `classify_event()` и `event_buffer.add()` при привязанном буфере. **[Контракт]**
- **`backend/app/services/tick_orchestrator.py`:** В `_TickContext` добавлены поля `event_buffer` и `cluster_occupancy`. В `execute()` внедрена привязка буфера к шине с блоком `try...finally` для гарантии отключения. Добавлен метод `_rebuild_cluster_occupancy()`, восстанавливающий пространственный индекс из `scene_state['npc_positions']` на старте тика. **[Контракт]**
- **`tests/test_cfrm_models.py` (Новый):** Создан набор из 13 юнит-тестов (ClusterGraph, EventBuffer, classify_event, ClusterOccupancy). 14 тестов (включая дымовой оркестратор) проходят успешно. **[Тестирование]**

## Сессия 18: UI Фиксы и Player as Hybrid Consciousness Entity (ADR-030)
**Дата:** 11.05.2026  
**Изменения:**
- `frontend/game_menu.py`: Починка залипания подсветки кнопок (state drift). Переход от интегратора `hovered = hovered or new_state` к frame-deterministic `hovered = f(mouse, keyboard)`.
- `frontend/map_editor/editor_core.py`: Починка выхода из редактора. `Esc` теперь прерывает цикл `while self._running` (вместо снятия выделения) и возвращает в главное меню. Добавлена кнопка "В главное меню" в выпадающее меню File.
- `frontend/character_select.py`: Рефакторинг Создания Персонажа. Удалены D&D-поля (race, class_name). Добавлен Вектор Начальных Условий: Архетип (задает body_profile) и Темперамент (задает psyche/willpower). Навигация по выбору стрелками.
- `backend/app/services/game_loop/__init__.py`: Инъекция Аватара Игрока. В `_load_npcs_with_runtime()` добавлено внедрение `npc_id="player"` в `all_npcs_raw` на основе активной сессии и данных CharacterService.
- `backend/app/models/schemas.py`: В `CharacterSheet` добавлены поля Вектора: `archetype`, `temperament`, `body_profile`, `psyche`.
- **Архитектура:** Принят ADR-030 (Player as Hybrid Consciousness Entity & WillpowerGate). Обновлены DTO Registry (WillResponseDTO, Avatar Creation Vector).

## Сессия 19: WillpowerGate — Cumulative Strain Model (ADR-031)
**Дата:** 11.05.2026  
**Изменения:**
- **Архитектура (ADR-031):** Подавление бинарной модели `action × temperament`. Введен `IntentPressureResolver` — промежуточный слой, транслирующий семантику действия в `IntentPressureProfile` (вектор давления на психику: violence, humiliation, self_risk, moral_violation, identity_deviation и др.).
- **WillpowerGate:** Переписан на Cumulative Strain Model. Вычисляет сопротивление формулой: `resistance = pressure.identity_deviation * psyche.identity_rigidity + ...`. Willpower — инерция, а не порог.
- **WillState:** Введена шкала деградации воли (COMPLY, RELUCTANT, DISTRESSED, PANICKED, DISSOCIATING, BROKEN, CONDITIONED) вместо бинарных ACCEPTED/RESISTED.
- **WillResponseDTO:** Обновлен для работы с WillState и IntentPressureProfile. Counter-Offer стал обязательным механизмом выживания аватара, а не фичей.
- **Топология:** Обновлен ARCHITECTURE_FLOW. Внедрен `IntentPressureResolver` между `Player Input` и `WillpowerGate`.
- **Запрет:** Использование матриц поведения как онтологии системы запрещено (допускается только как debug fallback).

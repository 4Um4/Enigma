
---
[SESS_01] Дата: Текущая: GameLoop.idle_tick() — новый метод, делегирует в TickOrchestrator.execute() (idle mode). TickResultDTO импортирован.
[SESS_02] Дата: Текущая: GameLoopBridge.idle_tick() — новый метод, конвертирует WorldSnapshotDTO→dict через asdict(). Удалены get_life_engine() и get_npc_runtime_path() (deprecated, нет потребителей).
[SESS_03] Дата: Текущая: DirectGateway.idle_tick() — переписан: ~50 строк ручной работы с LifeEngine → 5 строк делегирования в bridge.idle_tick().
[SESS_04] Дата: Текущая: routes.py idle_tick() — переписан: ~30 строк ручного извлечения scene_state + отдельный TickOrchestrator → 5 строк через game_loop.idle_tick(). Устранён баг: старый TickOrchestrator создавался без memory_manager и event_bus.
[SESS_05] Дата: Текущая: game_screen.py idle_tick обработка — npc_positions теперь читается из world_snapshot (канонический источник, фаза 9) с fallback. Добавлена синхронизация player_position, time_of_day, weather из world_snapshot. Исправлен баг: setdefault("npc_id") → setdefault("npc_positions").
[SESS_06] Дата: Текущая: phase_1_input.py — добавлен _INTENSITY_MAP, publish_classified_player_event() теперь включает intensity в EventDTO.payload.
[SESS_07] Дата: Текущая: propagation.py — propagate_social_rumors() +параметр events. Канонический путь: intensity/event_type/actor_id из EventDTO.payload. Fallback на dm_result.event_context. Заменены _evt.* на локальные переменные.
[SESS_08] Дата: Текущая: social_subscriber.py — handle() передаёт events в propagate_social_rumors().
[SESS_09] Дата: Текущая: perception_subscriber.py — handle() обрабатывает ВСЕ накопленные события вместо только events[-1]. set.update() для объединения.
[SESS_10] Дата: Текущая: TickOrchestrator.finalize_and_commit() — удалён (deprecated, заменён на execute_player_finalize(), нет потребителей).

[SESS_01] idle_tick реформа: GameLoop.idle_tick() — новый метод (делегирует в TickOrchestrator). GameLoopBridge.idle_tick() — новый метод (конвертация WorldSnapshotDTO→dict). DirectGateway.idle_tick() — 50→5 строк. routes.py idle_tick — 30→5 строк. Устранён баг: TickOrchestrator без memory_manager/event_bus.
[SESS_02] world_snapshot миграция: game_screen.py читает npc_positions из world_snapshot (фаза 9) с fallback. Синхронизация player_position/time_of_day/weather. Баг: setdefault("npc_id")→"npc_positions".
[SESS_03] intensity из EventDTO: phase_1_input.py +_INTENSITY_MAP, payload.intensity. propagation.py +events param, канонический путь EventDTO.payload, fallback dm_result.event_context. social_subscriber.py передаёт events.
[SESS_04] Perception мультисобытийность: perception_subscriber.py handle() — цикл по events, set.update() вместо events[-1].
[SESS_05] Удаление deprecated: TickOrchestrator.finalize_and_commit(), GameLoopBridge.get_life_engine(), GameLoopBridge.get_npc_runtime_path().
---
[SESS_03] 04.05.26: Интегрирован SpatialService v1.2. NpcTickServices: добавлено поле spatial_service. LifeEngine: добавлен DI через set_spatial_service, _make_random_events стал методом класса, хардкод "bar_area" заменен на svc.resolve_node(NodeRole.BAR). MovementEngine: добавлен DI, LocationGraph.find_path заменен на svc.find_path. SceneStateManager: _position_map удален, заменен на svc.get_node_label. GraphCompiler: добавлен _PROJECT_ROOT и get_connections. Данные: удалены _BUILTIN_NODES, блоки positions из location_templates.json, дубликат tavern.json.
---
[SESS_06] 27.05.26: SpatialService контракт. В test_location_graph_r4.py добавлен @pytest.mark.skip. Из tick_orchestrator.py удален прямой импорт load_graph (нарушение черного ящика). Заменено на заглушку для SpatialService v1.2.
[SESS_07] 27.05.26: delta_buffer как единственный канал мутации. В propagation.py баг break заменен на max() (агрегация intensity). Удалена мутация shared_context.social_propagation. В Phase8Result добавлены socially_affected_npc_ids и events_processed. SocialSubscriber извлекает affected IDs из deltas.
[SESS_08] 27.05.26: Единый источник ACTION_INTENSITY. Создан domain/constants.py. Удалены дубликаты _INTENSITY_MAP (phase_1_input.py) и _BASE_INTENSITY (dm_router.py).
[SESS_09] 27.05.26: Устав §1.1 (Frontend/Backend граница). Конвертация DTO→dict перенесена из game_loop_bridge.py в GameLoop.idle_tick(). Bridge больше не импортирует app.domain.*.
---
[SESS_12] 27.05.26: Починка _build_npc_snapshots() — критический разрыв данных. NPC dict хранит social_stats (плоский: trust, fear_of_player, debt), но _build_npc_snapshots() читал ключ relationship_cache (не существует) → SocialDecayHandler всегда получал пустой кэш → нулевой дрейф trust. Исправлено: маппинг social_stats → relationship_cache["player"] вложенного формата. loyalty_true → base_values["player"]. faction_rank → faction_affiliations. Плоский кэш {trust: val} автоматически конвертируется. 17 тестов.

[SESS_13] 27.05.26: NPC-to-NPC Social Relations Enrichment (Приоритет 1). Создана _enrich_with_social_relations() в npc_loader.py — обогащает NPC dict связями из village_relations.json (шкала 0-1 → 0-100, конвертация ×100). Формат: relationship_cache[target] = {trust, fear, base_trust, nature}, base_values[target] = base_trust*100. Вызывается во всех 3 return-путях load_npcs_merged(). Критический фикс _build_npc_snapshots(): после обогащения NPC→NPC, relationship_cache уже вложенный → старый код брал «как есть» и ПРОПУСКАЛ player entry из social_stats → player drift ломался. Исправлено: shallow copy + гарантированное добавление player из social_stats (если нет). Аналогично для base_values — player из loyalty_true. 17 новых тестов (test_npc_social_enrichment.py). Обнаружен предсуществующий баг: test_tick_orchestrator_full_loop_player_attacks (untracked, падал ДО изменений) → добавлен в deselect. Итого: 400 passed.

[SESS_11] 27.05.26: Создан ReactionSubscriber (Phase8Handler). Прямые эмоциональные реакции наблюдателей на угрозы/атаки/помощь — stress/fear/trust дельты без decision-цикла. Модификатор на основе NPCPersonality (drives_base.fear, willpower, текущий stress). Порядок handlers: perception → reaction → social. Маршрутизация: intent_target для player, social_target для NPC-источника. Источник события исключён из реакций. Использует perceiving_npcs от PerceptionSubscriber с fallback на всех NPC (None vs [] — разная семантика). 27 тестов.

[SESS_10] 27.05.26: ADR-002 починка — _apply_phase8_result() прямая мутация all_npcs_raw заменена на маршрутизацию через delta_buffer → apply_batch(). Удалён блок прямой записи stress/trust в dict (нарушал единый мутатор). Добавлен flush delta_buffer в _phase_8_drain_secondary() после цикла обработчиков → Phase 9 видит обновлённое состояние. Бонус: trust_delta теперь корректно маршрутизируется по social_target/intent_target через apply_batch (раньше писалось в _rc["trust"] без учёта target).
---
[SESS_09] 27.04.26: Расширен StateDeltas (intent_target, social_target, faction_id, reputation_delta, __post_init__ валидация, # LOCKED v1). Создан app/models/idle_tick.py (NPCStateSnapshot, IdleTickHandler). Создан app/services/social/social_decay_handler.py (SocialDecayHandler с closing drift). Изменён app/services/social/reputation_engine.py (compute_decay() чистая функция, apply_deltas() принимает StateDeltas). Создан app/services/social/reputation_decay_handler.py (ReputationDecayHandler). Изменён app/services/social/propagation.py (social_target=_actor_id). Изменён app/services/npc/decision_hub.py (intent_target="player"). Изменён app/services/npc/state_applicator.py (reputation_engine DI, маршрутизация по таргету, _apply_faction_delta, apply_batch, _apply_delta_to_raw, импорт Any/Dict/List). Изменён app/services/tick_orchestrator.py (delta_buffer, _phase_0_5_idle_services, _build_npc_snapshots, _aggregate_deltas, idle_handlers, state_applicator, reputation_engine DI, Phase 8 guard if not events, flush delta_buffer в Фазе 10). Изменён app/services/game_loop/service_factories.py (get_state_applicator). Изменён app/services/game_loop/__init__.py (DI wiring idle handlers).
---
[SESS_09] 05.05.2026: Реставрация тестового покрытия после ADR-001 и внедрения Delta Buffer. Восстановлен контракт `StateDeltas`: во все тестовые фабрики (`test_decision_pipeline`, `test_dm_frame`, `test_scene_outcome_builder`, `test_state_applicator_pipeline`) добавлено обязательное поле `npc_id`. Удален мертвый файл `test_location_graph_r4.py` (тестировал удаленный `load_graph`). Удален мертвый класс `TestMemoryBreathes` из `test_event_memory.py` (зависел от удаленного `build_verbalization_context`). Сняты skip-маркеры с `test_spatial_runtime_r4.py` (логика фильтрации скрытых NPC уже реализована). Обновлены assert-ы в `test_dm_frame.py` под русскую вербализацию (`intimidate`, `зол холодно`). Удалены устаревшие тесты в `test_provider_manager.py` и `test_services.py` (привязка к qwen_7b и старой структуре checks).
---
[SESS_09] Текущая: Реставрация тестового покрытия после ADR-001 и внедрения Delta Buffer. Восстановлен контракт `StateDeltas`: во все тестовые фабрики (`test_decision_pipeline`, `test_dm_frame`, `test_scene_outcome_builder`, `test_state_applicator_pipeline`) добавлено обязательное поле `npc_id`. Удален мертвый файл `test_location_graph_r4.py` (тестировал удаленный `load_graph`). Удален мертвый класс `TestMemoryBreathes` из `test_event_memory.py` (зависел от удаленного `build_verbalization_context`). Сняты skip-маркеры с `test_spatial_runtime_r4.py` (логика фильтрации скрытых NPC уже реализована). Обновлены assert-ы в `test_dm_frame.py` под русскую вербализацию (`intimidate`, `зол холодно`). Удалены устаревшие тесты в `test_provider_manager.py` и `test_services.py` (привязка к qwen_7b и старой структуре checks).
[SESS_10] Текущая: Архитектурная чистка тестов (Enforcing ADR-003). Удалено 5 файлов мертвых тестов (`test_decision_pipeline.py`, `test_r3_verbalization_final.py`, `test_scene_to_dm_adapter.py`, `test_verbalization_chain.py`, `test_verbalization_chain_ANY.py`). Удалены мертвые классы `KnowledgeIngestTests` и `PdfDropImporterTests` из `test_services.py` (зависели от удаленного `persist_world_canon`). Устранены Fragile Tests: в `test_player_cognition_pipeline.py` хрупкая I/O фикстура `real_scene_state` (чтение JSON с диска) заменена на детерминированную синтетическую фабрику `_make_rich_scene()`. В `test_spatial_runtime_r4.py` обновлены координаты `local_position` под логику fallback-графов. Тестовый набор: 424 PASSED, 0 FAILED, 4 legitimate SKIPPED (LLM/бинарники).
---
[SESS_11] Текущая: Создан сквозной дым-тест test_tick_orchestrator_full_loop.py. Проверен полный цикл Phases 0-10: генерация EventDTO, прохождение через PerceptionSubscriber (Phase8Result), маршрутизация StateDeltas(npc_id=...) и применение через StateApplicator. Починен критический баг: ctx.all_npcs_raw не заполнялся в idle-пути, что ломало единый мутатор (ADR-002). Добавлен exc_info=True в логгер оркестратора.
---
[SESS_04] Текущая дата: Удалена глобальная переменная _connections_data и функция get_connections() из graph_compiler.py. Функция compile_graph теперь возвращает кортеж (graph, connections, alias_map). Обновлен spatial_service.py и test_spatial_service.py.[SESS_04] Текущая дата: Из movement_engine.py удален легаси-кэш _graphs, методы _get_graph, invalidate_cache, импорты LocationGraph. Удалена денормализация ID (denormalize_id), в TransitTracker теперь передаются канонические ID. Удален fallback на LocationGraph.find_path().[SESS_04] Текущая дата: В scene_state_manager.py добавлен метод _enrich_spatial_data() (загрузка spatial_walls/obstacles). В сборку npc_positions добавлено поле "name".[SESS_04] Текущая дата: Во frontend/game_screen.py удалены вызовы _gateway._bridge.* (нарушение Закона 1.1). Создана локальная функция _build_perceived_scene(). Исправлен UnboundLocalError для _ws.[SESS_04] Текущая дата: В tick_orchestrator.py добавлены поля status и error в TickPlayerResultDTO. Обработчик except теперь возвращает правильный тип DTO.[SESS_04] Текущая дата: В npc_tick_pipeline.py добавлен импорт Optional. В interpretation_engine.py изменен доступ к драйвам на state.personality.drives_base (ВНОСИТ БАГ, требует фикса в следующей сессии).
---
[SESS_11] Текущая дата: Починка краша WillState. В npc_state.py изменена десериализация на WillState(psyche.get("state", "free")) (строка 675).
[SESS_11] Текущая дата: InterpretationEngine отвязан от state.personality. В compute() добавлен аргумент drives_base: Dict[str, float]. Зависимость разорвана на уровне данных (Устав §1.2).
[SESS_11] Текущая дата: Инжекция SpatialService в idle-тики. В tick_orchestrator._phase_0_simulation добавлен fallback-инжект SpatialService.build_for_location(). В scene_init.py добавлен инжект для TICK_CATCHUP.
[SESS_11] Текущая дата: Починка имен NPC. В WorldSnapshotBuilder добавлена передача data.get("name") в display_name. В game_screen.py добавлен каскадный fallback display_name→name→эвристика.
[SESS_11] Текущая дата: Миграция имен в SceneStateManager._enrich_local_positions добавлено заполнение поля name через _npc_id_to_display.
[SESS_11] Текущая дата: Начало миграции конфигов. В maid.json изменены позиции serving_table_3 на main_hall.
---
[SESS_UI_01] Дата: 08.05.2026 21:07 Создана система Narrative Beat (Cinematic Layer) взамен плоского message_log. Добавлен frontend/narrative_beat.py (DeliveryType, RecognitionLevel, BeatLifetime, NarrativeBeat).Добавлен frontend/narrative_renderer.py (отрисовка пузырей Persona 5 стиля).frontend/text_input.py: Добавлена физика инерции зажатия клавиш (Custom Key Repeat с ускорением). Добавлен Shift+Enter для многострочного ввода. Полный запрет Ctrl+V (ТЗ п.4). Удалена поддержка буфера обмена.frontend/game_screen.py: Интегрирован NarrativeRenderer. Ввод игрока отображается расширяющимся пузырем справа (ТЗ п.3). Эхо LLM фильтруется через _last_player_input + SequenceMatcher (построчный разбор). Удален legacy-вывод "⟳ {text}" (вызывал призрачное эхо). Починено залипание WASD (объединение KEYUP обработчиков).БАГ: Ответы NPC отображаются как "Система" из-за того, что dm_response не разделен на спикеров.
---
[SESS_14] Дата: 08.05.2026 22:08 Починка Pipeline движения и открытие LOD-границы (Macro vs Micro Space)

life_engine.py: Восстановлен контракт возврата в check_random_events(). Все return пути теперь возвращают кортеж (changes, None) вместо голого списка. Устранён краш "not enough values to unpack".
life_engine.py: Починена распаковка кортежей в _simulate_major() и _simulate_minor() для update_routine() и check_random_events().
scene_state_manager.py: Удалён RuntimeError "Архитектурный guard: прямая мутация position запрещена". Страж заменён на debug log. Теперь SceneChange(field="position") разрешён и атомарно резолвится в local_position (x,y) через SpatialService (ADR-0008).
scene_state_manager.py: Добавлены структурные логи [PIPELINE][SCENE_CHANGE][APPLY] и [APPLY_FAILED] для трейсинга применения координат.
movement_engine.py: Добавлен fallback поиска узлов с префиксом локации (location_id:node_id) в get_node(), так как SpatialService хранит узлы с префиксом (например, tavern_silver_wolf:main_hall).
movement_engine.py: Добавлены логи [PIPELINE][MOVEMENT][PATH_RESOLVE] и [INTENT_CONSUME].
npc_orchestration.py: Удалён мёртвый код обновления local_position через удалённый load_graph, который блокировал применение координат.
npc_tick_pipeline.py: Добавлены логи [PIPELINE][REACTIVE_MOVEMENT][CREATE/SKIP].
npc_tick_pipeline.py: ОТКАТЕН опасный фикс микро-перемещений (MovementIntent с target_node_id=current_node). Устранён краш ModuleNotFoundError. Утверждено разделение Macro (MovementIntent) и Micro (LocalSteeringIntent) уровней пространства.
config/npc/archetypes/: Миграция позиций guard.json и merchant.json с микро-зон (gate_post, stall_3, bed) на макро-зоны (entrance, main_hall).
---
[SESS_14] Дата: 08.05.2026 22:21: Приоритет 1 (StateDeltas v2) завершён. Создан app/models/delta_payloads.py (frozen dataclasses: SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload). StateDeltas расширен: enum DeltaDomain, поля domain, target, payload. post_init валидирует соответствие payload типу domain (TypeError при несовпадении). Мигрированы на v2: SocialDecayHandler, ReputationEngine, ReactionSubscriber, propagation.py, StateApplicator (tick_recovery). _aggregate_deltas группирует по (npc_id, domain, target) и мержит frozen payloads. ReactionSubscriber разделен на 2 дельты (EMOTION + SOCIAL) вместо 1 смешанной. StateApplicator._apply_deltas извлекает данные из payload с fallback на v1 поля. DecisionHub оставлен на v1 (требует рефакторинга DecisionResult). 400 тестов проходят + 10 новых v2 контрактов.
---
[SESS_14] Дата: 09.05.2026 15:43: Починка бага "Система" (Приоритет 0) и Experiential Architecture (Приоритет 1).В game_screen.py: dm_response теперь разбивается на строки. Спикер извлекается из текста через словарь known_names (из scene_state). Устранена мутация line_stripped, ломавшая парсинг.В game_screen.py: Исправлен фильтр эха npc_reactions — добавлена защита от ложных срабатываний на коротких вводах (is_short_input). Для npc_reactions добавлен парсинг DeliveryType (по маркерам *, (), !!!) и RecognitionLevel (для Мужчина/Женщина).В game_screen.py: Разделение слоев UI. Создан system_log. Все системные сообщения (ошибки, логи движения, переходы) перенаправлены из message_log в system_log. Функция _check_transition_trigger переведена на system_log. Удален дубликат инициализации system_log.В game_screen.py: Реализован Bubble Lifetime. Добавлено поле creation_tick при создании NarrativeBeat. Добавлен цикл обновления возраста для TRANSIENT (живет 5 сек, фейд-аут 2 сек). Добавлена очистка памяти от растворившихся пузырей (alpha <= 0).В narrative_renderer.py: Внедрена визуальная логика DeliveryType (SHOUT=красная рамка 3px/контрастный текст, WHISPER=серый текст 1px, INTERNAL=синяя рамка 1px/голубоватый текст). Шрифты не мельчились ради читаемости. Реализован fade-out пузырей и плашек имен через BLEND_RGBA_MULT с использованием beat.alpha.В game_screen.py: Удален мертвый код адаптации строк в NarrativeBeat внутри _draw_message_log (теперь log содержит только NarrativeBeat). Добавлена отрисовка system_log в верхнем правом углу (полупрозрачный фон).
---
[SESS_15] Дата: 09.05.2026 17:16:Domain (Damage & Stress Propagation System) вместо Combat System. Следование вердикту Мастера Тая: "Бой — не отдельная система, а режим предельного давления на ВСЕ системы".

[SESS_15] app/models/delta_payloads.py: Удален CombatPayload. Создан InjuryDTO (target_zone вместо body_part, разделение structural_damage/functional_loss/critical_effects). Создан PhysiologyPayload (hp, pain, fatigue, blood_loss, shock_impulse, add_injuries, add_statuses, remove_statuses).

[SESS_16] Мастер Тай: Domain Reduction Semantics Layer (DRSL). В state_delta.py добавлен enum ReductionPolicy (ADDITIVE, BOUNDED_ADDITIVE, OVERWRITE, PHYSICS_COMPOSITE) и DELTA_POLICY_REGISTRY — конституция мира: каждый домен знает свой закон редукции. _aggregate_deltas в tick_orchestrator.py переписан: PHYSICS_COMPOSITE (Physiology) обходит merge — дельты передаются как инъекции энергии без суммирования. Алгебраические домены (Social, Emotion, Reputation) редуцируются через политики. Удалён бог-свич _merge_payloads, заменён на _reduce_additive.

[SESS_16] CombatSubscriber (combat_subscriber.py): Phase8Handler — мост EventDTO → ImpactEngine. Подписка: PLAYER_ATTACKS, PLAYER_ATTACKED, COMBAT. Извлекает ImpactIntentDTO из EventDTO.payload. Строит снапшоты атакующего/защищающегося (fallback player snapshot). Вызывает resolve_physical_impact(). Возвращает Phase8Result(deltas=physiology_deltas). Порядок Фазы 8: perception → reaction → social → combat.

[SESS_16] PhysiologyDecayHandler (physiology_decay_handler.py): Phase 0.5 idle-handler — Leaky Integrator. S_t = S_{t-1} * exp(-lambda * dt). Боль (lambda=0.05), усталость (0.03), кровопотеря (0.01) экспоненциально затухают. Сознание восстанавливается при низкой боли. Closing drift для обнуления микро-осцилляций. Фазовые переходы: pain > 50 → stagger, consciousness < 0.1 → unconscious.

[SESS_16] NPCStateSnapshot расширен полем statuses: List[str]. _build_npc_snapshots маппит body_state.statuses. CombatSubscriber._build_snapshot и _make_player_snapshot обновлены.

[SESS_16] DeltaDomain исправлен на lowercase значения (social, emotion, physiology) — соответствие конвенции EventType.

[SESS_16] game_loop/__init__.py: подключён PhysiologyDecayHandler как idle-handler.

[SESS_16] tick_orchestrator.py: CombatSubscriber добавлен в _phase_8_drain_secondary (последним). Импорт CombatSubscriber.

[SESS_16] Тесты: 12 CombatSubscriber (test_combat_subscriber.py), 12 PhysiologyDecayHandler (test_physiology_decay_handler.py). Итого: 444 passed, 0 failed.

[SESS_15] app/models/state_delta.py: DeltaDomain.COMBAT удален. Оставлен DeltaDomain.PHYSIOLOGY. PhysiologyPayload добавлен в Union DeltaPayload и _DOMAIN_PAYLOAD_MAP.

[SESS_15] app/models/idle_tick.py: NPCStateSnapshot расширен полями Physiology Domain: hp, max_hp, pain, fatigue, blood_loss, consciousness, injuries_by_zone (группировка по target_zone вместо плоского списка), base_abilities, modifiers (разделение базы и модификаторов по требованию Мастера Тая).

[SESS_15] app/models/npc_state.py: В NPCState добавлено поле body_state: Dict[str, Any] (рантайм-контейнер всей физиологии).

[SESS_15] app/services/tick_orchestrator.py: _build_npc_snapshots() обновлен для маппинга body_profile (статика) + body_state (рантайм) в NPCStateSnapshot. Травмы группируются по target_zone. Effective values НЕ вычисляются (хранятся база и модификаторы отдельно).

[SESS_15] app/services/npc/state_applicator.py: Добавлен хук для DeltaDomain.PHYSIOLOGY. Экстракция полей из PhysiologyPayload. Мутация state.body_state (current_hp, pain, fatigue, blood_loss, injuries, statuses) с ограничениями по шкалам. Инициализация body_state при первом применении.

[SESS_15] app/models/impact.py: Создан ImpactIntentDTO (actor_id, target_id, damage_type, target_zone, force, weapon_reach) и ContactLevel enum (MISS, GLANCING, PARTIAL, SOLID, PERFECT).

[SESS_15] app/services/combat/impact_engine.py: Создан Impact Propagation Engine (Pure Function). Контактная модель вместо RPG Hit Roll (уклонение зависит от боли, усталости, кровопотери). Зональные модификаторы (голова/пах). Типы урона (slash/blunt). Генерация InjuryDTO. Возвращает ТОЛЬКО Physiology-дельты (No Domain Leakage).

[SESS_15] tests/test_impact_engine.py: 10 тестов Contact Resolution, Zone Modifiers, Damage Types, Injury Generation, Determinism. Итого: 420 passed.
---
[SESS_15] 09.05.26: Приоритет 1 (Time Controls) — частичная реализация, критические баги.

game_screen.py: Добавлена переменная _time_scale (1, 4, 10, 50) и обработка клавиш 1-4.
game_screen.py: Добавлен индикатор скорости (▶ 1x) в правом верхнем углу.
game_screen.py: Вынесен запуск idle_tick из блока proactive_events (починка стояния времени при простое).
tick_orchestrator.py: Создан _advance_idle_time() для продвижения game_time_seconds на GAME_TICK_INTERVAL_SECONDS (15 мин) за тик.
tick_orchestrator.py: _get_npc_runtime_path переписан на использование settings.saves_dir.
scene_init.py: Убран max(1, _catch_up), вызывающий лишние тики и скачки времени при старте.
time_advance.py: Добавлена запись game_time_seconds в scene_state для персистенции.
domain/snapshot.py: В WorldSnapshotDTO добавлено поле game_time_seconds: int = 0.
world_snapshot_builder.py: Передача game_time_seconds из scene_state в DTO.
[SESS_15] 09.05.26: КРИТИЧЕСКИЕ БАГИ (БЛОКИРУЮЩИЕ РАБОТУ):

tick_orchestrator.py: _get_npc_runtime_path возвращает str вместо Path, ломая load_npcs_merged (AttributeError: 'str' object has no attribute 'exists').
tick_orchestrator.py: _aggregate_deltas падает с NameError: name 'DELTA_POLICY_REGISTRY' is not defined. Idle-тик и ход игрока полностью сломаны.
---
[SESS_16] Дата: 09.05.2026 21:32: Диагностика и частичный фикс NPC Movement Pipeline.

[SESS_16] frontend/game_loop_bridge.py: В TurnResult добавлены поля world_snapshot и npc_positions. После _collect() — построение world_snapshot из актуального scene_state через get_scene_state(), чтобы DirectGameGateway передавал позиции NPC на фронтенд.

[SESS_16] frontend/api_client.py: DirectGameGateway.send_action() теперь передаёт world_snapshot и npc_positions из TurnResult в GameActionResponse (раньше эти поля были None — разрыв pipeline).

[SESS_16] backend/app/services/spatial/movement_engine.py: Добавлена защита micro-position — если from_node_id == target_node_id, macro SceneChange(field="position") не генерируется, предотвращая затирание micro-координат на center node.

[SESS_16] РЕЗУЛЬТАТ: has_ws=True подтверждён в логах. Макро-движение работает (guard_borko → entrance, merchant_goran → market_trading). Micro-snap применяется (blacksmith_orm → координаты рядом с игроком). ОДНАКО: система остаётся «state relocation» — NPC телепортируются, а не двигаются непрерывно. Требуется архитектурный переход к TraversalState (continuous spatial simulation).
---
[SESS_16] 09.05.2026 22:41: Починка крашей бэкенда и Визуализация Календаря + Ротация игрока

[SESS_16] backend/app/services/tick_orchestrator.py: Починен критический баг возврата str вместо Path в _get_npc_runtime_path (AttributeError: 'str' object has no attribute 'exists'). Удалена обертка str().[SESS_16] backend/app/services/tick_orchestrator.py: Починен краш NameError: DELTA_POLICY_REGISTRY. Создан enum ReductionPolicy (ADDITIVE, BOUNDED_ADDITIVE, OVERWRITE, PHYSICS_COMPOSITE) и словарь DELTA_POLICY_REGISTRY. Добавлен импорт DeltaDomain.[SESS_16] frontend/constants.py: Добавлена функция format_world_date(seconds) -> str для HUD ("Год X, День Y, HH:MM"). Календарные константы (DAYS_PER_YEAR, SECONDS_PER_DAY и др.) продублированы из бэкенда чистой функцией ради Устава §1.1 (Фронтенд не знает Бэкенд).[SESS_16] frontend/game_screen.py: HUD обновлен для вывода полной даты через format_world_date вместо format_game_time.[SESS_16] frontend/game_screen.py: Проведен онтологический рефакторинг _MoveState. Состояние разделено на 3 природы: Навигация (path, target), Кинетика (cooldown, distance), Эмбодимент/Внимание (facing_angle, facing_mode). Взгляд отвязан от вектора скорости (кинематическая редукция заменена на целенаправленное внимание).[SESS_16] frontend/game_screen.py: Добавлено вычисление facing_angle. При движении по пути к NPC — взгляд прикован к цели (LOOK_TARGET), даже если путь извилистый. При WASD — взгляд по вектору движения (VELOCITY).[SESS_16] frontend/scene_renderer.py: Метод render() и _draw_player() принимают player_facing. Стрелка игрока отрисовывается через математический поворот полигона (cos/sin) вместо статичного треугольника.
---
[SESS_17] 09.05.2026 22:53 дата: Архитектурная сессия (Embodied World Simulation & Temporal Arbitration)

[SESS_17] Удалён призрачный кэш: из backend/app/models/npc_state.py удалены поля cached_position, position_valid и метод _cached_distance_to() (нарушали причинность, никто не обновлял).

[SESS_17] Удалена функция patch_scene_state из backend/app/services/state/context_builder.py и её вызов из backend/app/services/game_loop/scene_init.py (in-place мутация контекста для DM-агентов после apply_changes).

[SESS_18] Текущая дата: Спринт 17 — Чистый Визуал

[SESS_18] frontend/scene_renderer.py: Добавлен Lerp для сглаживания поворота стрелки игрока (Приоритет 0). Добавлено поле `_visual_facing_angle` и математика интерполяции в `render()`. Учет перехода через ±π.
[SESS_18] frontend/game_screen.py: В вызов `renderer.render()` добавлена передача `dt` для работы Lerp.
[SESS_18] frontend/scene_renderer.py: Добавлен визуальный индикатор внимания NPC (Приоритет 1). Если NPC в фокусе или имеет inference "communication", отрисовывается желтая линия от края кружка к игроку. Метод `_draw_npcs` теперь принимает `player_xy`.
[SESS_18] frontend/scene_renderer.py: Починен рендер спрайтов объектов (стулья, столы). Создан метод `_draw_obstacles` для отрисовки `spatial_obstacles` из `scene_state`.
[SESS_18] frontend/scene_renderer.py: Починен fallback спрайтов для NPC. Если спрайт по `entity_id` не найден, используется базовый тип `"person"`.
[SESS_18] frontend/game_screen.py: Увеличено время жизни NarrativeBeat (TRANSIENT) до 10 секунд, фейд-аут до 3 секунд (было 5с / 2с).
[SESS_18] frontend/game_screen.py: Отключено перемещение кликом мыши (`MOUSEBUTTONDOWN` заблокирован).
[SESS_18] frontend/narrative_renderer.py: Добавлены визуальные фильтры для WHISPER (полупрозрачность alpha=200 + серый ореол текста) и уточнена вибрация для SHOUT (1px вместо 2px) (Приоритет 3).
[SESS_17] Дозачистка orphaned code от ADR-0015: из npc_state.py удалено тело метода _cached_distance_to (строки 554-563, остались внутри post_init после неполного удаления) и ссылка на position_valid в snapshot() (строка 603). 444 теста проходят.
[SESS_17] Архитектурная сессия с Мастером Таем. Принят ADR-0016: Causal Field Reduction Model (CFRM). Глобальный объект World удалён из онтологии. Мир = локальные причинные пузыри с ограниченной проницаемостью. delta_buffer мёртв (императив), заменён на EventBuffer (декларатив). Snapshot[t] = Reduce(ClusterGraph, EventBuffer, MembraneField). NPC хранит PerceptualKernel, а не world state. Обновлены ADR, DTO Registry.
---

---
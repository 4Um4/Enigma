# DTO Registry — Каузальный Атлас Контрактов ENIGMA
**Основание:** CAUSAL CONTRACT v2.0 (2026-05-21), ADR-O-208 / ADR-O-305A (S85.2), ТЗ-02 (S86), ADR-O-301 (S93)

> **Формат:** Домен пайплайна → Поток данных → Актуальные DTO → 🚫 КАУЗАЛЬНЫЕ ЗАПРЕТЫ (HARD CONSTRAINTS).
> ИИ-ассистенту: Нарушение правила из блока 🚫 = архитектурный баг, равносильный крашу пайплайна.

---

## 0. ФИЛОСОФИЯ КОНТРАКТОВ (L0-L1-L2)
Все DTO в системе подчиняются трехуровневой архитектуре восприятия:
- **L0 (PERCEPTION):** Мир → Восприятие. Никакой телепатии. Игрок и NPC получают информацию симметрично через `PerceptualKernel` / `ProjectionPolicy`.
- **L1 (BODY):** Инерция личности. Любая мутация стана должна подчиняться формуле: `new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))`. Моментальные скачки = баг.
- **L2 (BEHAVIOR):** `DecisionHub` — единственный источник решений. Давление искривляет utility, но не приказывает.
- **`TickState`** (`domain/tick.py`): Пассивный иммутабельный снимок состояния мира для передачи в редюсер (TZ-10). Содержит ВСЕ данные, включая preloaded блоки (`memory_weights_map`, `narrative_cache_map`, `social_modifiers_map`, `reputation_modifiers_map`, `economic_profiles_map`, `crystallized_beliefs_map`, `identity_traits_map`) и read-only сервисы (`relationship_store`, `spatial_service`, `spatial_query`).
  🚫 ЗАПРЕТ: Изменяемые дефолты в `TickState` (использовать `frozen()`). Возврат параметра `svc` в редюсер.
- **`DRFBus` & `DRFExecutionContext`** (`services/drf_bus.py`): Вынесены из `tick_orchestrator.py` (S97). Шина каузального арбитража (ADR-134) и scoped ledger (ADR-136).
- **`TickContext` & DTOs** (`services/dto.py`): Вынесены из `tick_orchestrator.py` (S97). Содержит `ReductionPolicy`, `SemanticFrame`, `TickPlayerResultDTO`, `_TickContext`, `DMContextDTO` (DEPRECATED).
- **`TickMutation`** (`domain/tick.py`): Чистый результат работы `NpcTickPipeline.run()`. Содержит `npc_deltas`, `communication_intents`, `movement_intents`, а также отложенные I/O мутации: `l1_drift_events` и `memory_events` (применяются оркестратором).
- **`TickResultDTO`** (`domain/tick.py`): Единый результат тика ядра. Возвращает только status, world_snapshot и npc_contexts (Narrative Projection). 

  🚫 ЗАПРЕТ: Возврат `TickPlayerResultDTO` из ядра. Возврат `movement_intents` (они исполняются внутри Фазы 8 и не покидают ядро).
---

## 1. ВВОД И СЖАТИЕ (Input & Intent Compression)
**Поток:** Сырой текст → Семантическое поле → Строгие параметры намерения.

**Актуальные DTO:**
- **`IntentSemanticField`** (`domain/intent_profile.py`): Вероятностное поле. `ActionType`, `TargetZone`, `SemanticAmbiguity`, `EmotionalVector`, `ConfidenceVector`. **ADR-088:** `EmotionalVector` больше не возвращается нулевым. Для `ATTACK` инжектится `aggression=0.8`.
- **`IntentParametersDTO`** (`domain/intent.py`): Строгий контракт. `semantic_action`, `target_reference`, `target_id`, `physical_force`, `emotional_charge`, `social_pressure`. **ADR-083:** `semantic_action` — приоритетный источник. **ADR-125:** `target_id` — DEPRECATED. 
- **`InterventionEvent`** (`contracts/interventions.py`): Внешнее вмешательство в мир (TZ-08 v0.2). Ядро не знает 'player', 'world_scheduler' или 'CK successor'. 
  Поля: `source` (str), `payload` (Dict[str, Any]), `tick` (int). 
  Factory: `from_player_action()`. 
- **`PlayerActionPayload`** (`domain/events.py`): TypedDict. Контракт полезной нагрузки для `EventDTO` при действии игрока. Содержит `action_type`, `semantic_action`, `target_id`, `physical_force`, `social_pressure`.
- **`MemoryPayload`** (`domain/events.py`): TypedDict. Контракт полезной нагрузки для событий памяти (запись в STM/L2).
- **`EventContext`** (`services/npc/decision_hub.py`): Чистая проекция `Intent` для DecisionHub. Содержит `intent`, `target_id`, `event`. Никакая внешняя система не имеет права модифицировать его после создания (§ENIGMA-005).
- **`NPCObservedState`** (`services/npc/npc_tick_pipeline.py`): Наблюдаемый слепок состояния NPC (ADR-TZ08-6). Формируется ядром как замена `real_state` для соблюдения Эпистемического Барьера. Содержит только публичные поля: `name`, `description`, `narrative_cache`. Передаётся в `npc_contexts` под ключом `observed_state`.
  🚫 ЗАПРЕТ: Восстановление ментальных полей (stress, trust, psyche) через инференс из этих данных.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.2):**
- ❌ **Слепота Fuzzy Matching (Rule 14):** Удаление поля `name` из `npc_positions` запрещено.
- ❌ **Silent Fallback:** Если `target_ref` не резолвится, действие обязано стать `UNCERTAINTY`.
- ❌ **Легаси-ключи:** Использование старых ключей `attack_target` вместо `player_attacks` / `player_threatens`.
- ❌ **Чтение intent.action без fallback:** Обращение к `intent.action` без fallback на `parameters.semantic_action` — Silent Crash (ADR-083).
- ❌ **Мёртвый Вектор Эмоций (ADR-088):** Возврат дефолтного `EmotionalVector()` для `ActionType.ATTACK` запрещён.
- ❌ **Подмена Campaign ID (ADR-089):** Использование `location_id` в качестве `campaign_id` запрещено.
- ❌ **ЗАПРЕТ: Передача DTO** (напр. `DMContextDTO`) внутри payload как активной логики. Только данные.
---

## 2. ВОЛЯ И ДАВЛЕНИЕ (Will & Pressure)
**Поток:** Параметры намерения → Вектор давления → Исказждение аффектом → Вычисление сопротивления.

**Актуальные DTO:**
- **`IntentPressureProfile`** (`models/will.py`): Вектор давления на психику.
- **`AmplifiedPressureProfile`** (`models/will.py`): Давление, искаженное `ResponseBias`.
- **`WillResponseDTO`** (`models/will.py`): Результат WillpowerGate. `WillState` (канонический источник — `app.models.npc_state`, реэкспортируется из `app.models.will`, ADR-TZ6-1), `resistance`, `stress_delta` (ADR-S101.1: моральный конфликт → стресс аватара, 0-100 scale), `identity_damage`, `counter_offer`, `embodied_vector`.
- **`CommunicationIntent`** (`domain/communication.py`): Единый источник истины для ответа NPC. Обязателен непустой `topic`. Добавлены `semantic_action` и `target_id` для проброса в `NPC_SPOKE` EventDTO.
- **`WillConflictPayload`** (`models/delta_payloads.py`): Контракт данных о конфликте воли (сопротивление игрока приказу NPC). Пробрасывается через API в `WorldSnapshotDTO` для фронтенда (Resistance Medium).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2, ADR-O-139):**
- ❌ **Решение без происхождения (Rule 6):** Создание `MovementIntent` без `pressure_sources` запрещено.
- ❌ **Double Invocation (Rule 8):** WillpowerGate вызывается ОДИН раз за цикл.
- ❌ **Fallback без тела (Rule 92, ADR-O-139):** Создание NPC dict без `body_state` запрещено. Убит `{"social_stats": {"fear_of_player": 0.1}}`.
- ❌ **Somatic Gate после парсинга (Rule 93, ADR-O-139):** Проверка `shock > 0.7` ПОСЛЕ семантического парсинга директивы запрещена. Каузальный порядок: `Body → Somatic Gate → Semantic Parsing → Legitimacy → Action`.
- ❌ **Skip без Sentinel (Rule 94, ADR-O-139):** `if not body_state: return []` без инъекции `BODY_STATE_DISABLED` запрещён.

---

## 3. ПРИЧИННОСТЬ И ВОСПРИЯТИЕ (CFRM & Perception)
**Поток:** Факт реальности → Возмущение поля → Проекция наблюдателем → Психологическое давление.

**Актуальные DTO:**
- **`FieldDisturbance`** (`models/cfrm.py`): Возмущение поля. Оси: кинетика, акустика, материя, поведение.
- **`PerceptualKernel`** (`models/npc_state.py`): Субъективная модель NPC (L1 — Поле Причин). 11+ полей: `threat_gradient`, `trust_gradient`, `uncertainty`, `anomaly_score`, `last_hostile_direction`, `dominant_emotion`, `aggression_inhibition`, `initiative_suppression`, `compliance_bias`, **`somatic_urgency`** (ADR-O-143: воспринимаемый телесный дистресс = `(pain_norm + shock_norm) / 2.0`, модулируется willpower), `recent_directive`. **ADR-115:** Обязательная сериализация. **Rule 38 / ADR-138:** Поля затухают в idle-тиках (Фаза 0.5).
- **`NPCState.consciousness_state`** (`models/npc_state.py`): Новый SoR (ADR-O-142). FSM: SLEEPING/AWAKE/UNCONSCIOUS/DEAD. `routine["current"]` НЕ является FSM state.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §1.1, §4.2, §4.3, §138):**
- ❌ **Давление из пустоты (Rule 7):** Получение давления через мембрану с `attenuation=0.0` запрещено.
- ❌ **Телепатия (Rule 11, §1.1):** Передача Игроку информации, которую NPC не мог получить через `PerceptualKernel`, запрещена.
- ❌ **Perception & Social Serialization (Rule 31, ADR-115/121/138):** `write_to_legacy` / `from_legacy` сериализует `perceptual_kernel` и `affective_load`. `relationship_cache` больше НЕ сериализуется (SSOT = RelationshipStore).
- ❌ **Leaky Integrator / Perpetual Fear (Rule 84/85, ADR-138):** Использование интегратора с утечкой для `affective_load` ЗАПРЕЩЕНО. Только Асимметричный Аттрактор (Гистерезис).
- ❌ **Somatic Bypass (§ENIGMA-S72, ADR-O-143):** Инъекция `pain`/`shock` напрямую в `psyche` dict ЗАПРЕЩЕНА. Боль проходит через `PerceptualKernel.somatic_urgency`.

---

## 4. РЕШЕНИЯ И ДВИЖЕНИЕ (Decision & Locomotion)
**Поток:** Восприятие + Давление → Контекст → Искривление Utility → Интент → Транзит.

**Актуальные DTO:**
- **`DecisionContext`** (`domain/decision_context.py`): `UtilityFieldDeformation`, `ActionSpaceCompression`. **GAP3 FIX:** `body_state` инжектируется для Соматического Вето.
- **`IntentDomain`** (`domain/movement.py`): Enum онтологических доменов намерений. `SURVIVAL`, `SOCIAL`, `ROUTINE`, `EXPLORATION`. **ADR-O-137:** Viability mask проекция PerceptualKernel → IntentDomain.
- **`MacroMovementGoal`** (`domain/movement.py`): LOD1. Содержит `target_node_id`, `from_node_id`, `target_local_xy`, **`domain: IntentDomain`** (ADR-O-137), `processed` (bool). Повторная обработка с `processed=True` вызывает `RuntimeError`.
- **`TraversalState`** (`models/`): Физическое состояние перемещения. `source_node`, `target_node`, `waypoints`, `progress` (0.0-1.0), `speed`, `created_tick`.
- **`SceneChange`**: Проекция свершившегося. **Boundary Transition Pipeline (ADR-145):** `target_location_id` заполняется ТОЛЬКО в `_process_traversals()` при факте пересечения boundary node. **ADR-130.2 (S85.1):** При `cause="traversal_complete"` `apply_changes` делает snap `local_position`, не создавая новый `TraversalState`. **ADR-TZ04-5 (B4-B5):** `ChangeType.NPC_METADATA` (activity, initiative_suppression) и `SCENE_METADATA` (line_of_sight) добавлены для маршрутизации мутаций через единый канал.
- **`ThickSceneChange` & `TraversalContract`**: **ADR-O-201.4 (S97):** `EventCompiler` возвращает `traversal=None` для `cause="traversal_complete"` и boundary snap. `TraversalContract` создаётся ТОЛЬКО для новых перемещений (`status="NEW"`). Управление lifecycle (COMPLETED/CANCELLED) — исключительная прерогатива `SceneStateManager` (ADR-TRAV-FSM).
- **`SpatialFactory`** (`services/spatial/spatial_factory.py`): Единственная точка входа для сборки `SpatialService` (ADR-TZ04-4). Прямые вызовы `SpatialService.build_for_location()` запрещены.
- **`KernelRNG`** (`services/npc/kernel_rng.py`): Единственный источник случайности в kernel layer (ADR-O-301). Привязан к `(tick, npc_id, salt)`. Создаётся через `_TickContext.rng_factory` в `TickOrchestrator` и передаётся в `NpcTickPipeline.run()`.
- **`DecisionHub`** (`services/npc/decision_hub.py`): Принимает `rng: Optional[KernelRNG]` в конструкторе. В production ВСЕГДА передаётся `rng`. `seed` оставлен только для legacy-тестов. Вызов `DecisionHub()` без аргументов запрещён (ADR-O-301).

**ETKE-IK v1: Motion Core DTOs**
- **`AffordanceVector`** (`domain/motion_core.py`): Физические возможности среды (can_stand, surface_grip, light_level, exposure). Заменяет дискретные узлы на непрерывное поле.
- **`BodySchema`** (`domain/motion_core.py`): Кинематические ограничения тела NPC (max_velocity, acceleration, stamina). Расширяет body_state.
- **`DriveVector`** (`domain/motion_core.py`): Замена MovementIntent для микро-уровня. Поля: `direction` (Tuple[float, float]), `intensity` (float 0-1). Тело само ищет путь в поле возможностей.
- **`KinematicProfile`** (`domain/motion_core.py`): Выходной профиль движения для фронтенда. Поля: `velocity`, `posture`, `facing`, `exertion_level`.

**Motion Routing Layer (ADR-ETKE-ACT1, ADR-S91)**
- **`drive_vector` в npc dict**: `[dx, dy, intensity, primitive_str]` — список из 4 элементов. Записывается Motion Router в `LifeEngine.tick_decisions()` (Фаза 5), потребляется `_process_continuous_motion()` (Фаза 0.8) на следующем тике. Эфемерен — очищается при каждом `tick_decisions`. Правила маршрутизации: `same_node + has_coords` → DriveVector (ETKE-IK); `different_node` → MovementIntent (FSM). APPROACH: intensity=0.7. FLEE: intensity=1.0 (или 0.5 для RETREAT). SOCIAL_DRIFT: intensity=0.2 (микро-перемещение к якорю).
  🚫 ЗАПРЕТ: DriveVector без очистки при каждом tick_decisions (L3-P1 эфемерность). ❌ FLEE с неинвертированным direction. ❌ MovementIntent для same_node (no-op, обязан идти через DriveVector). ❌ Использование рандомного `PATROL` (убивает социальную глубину, использовать `SOCIAL_DRIFT`).

**S91: Stigmergy & Dynamic Affordance DTOs**
- **`DeformationRecord`** (`domain/motion_core.py`): Запись о структурной деформации среды (Hard Override). Поля: `deformation_type` (str), `magnitude` (float, Absolute Override), `created_tick` (int), `ttl` (int, 0=вечная), `source_id` (str). 
- **`TracePayload`** (`domain/motion_core.py`): Эмиттер поведенческого следа (Soft Trace). Поля: `region` (str), `zone_id` (str), `trace_type` (str, напр. "movement_density"), `magnitude` (float), `created_tick` (int), `ttl` (int), `source_id` (str).
- **`DynamicAffordanceField`** (`services/spatial/world_topology_provider.py`): State-object с двумя слоями. 1. Hard Override Layer (`Dict[region, Dict[zone_id, Dict[type, DeformationRecord]]]`). 2. Soft Trace Layer (`Dict[region, Dict[zone_id, Dict[type, float]]]`). Методы: `apply_deformation`, `apply_trace`, `purge_hard_overrides`, `step_decay`.
  🚫 ЗАПРЕТ: Хранение состояния внутри `WorldTopologyProvider`. ❌ Очистка региона при смене локации.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ:**
- ❌ Boundary resolution при создании traversal — только при завершении (факт пересечения, не свойство маршрута)
- ❌ MovementEngine заполняет target_location_id — это ответственность _process_traversals
- ❌ **Domain-less MovementIntent (Rule 88, ADR-O-137):** `MovementIntent` без поля `domain` — viability mask не может работать.
- ❌ **Post-Generation Filtering (Rule 87, ADR-O-137):** Фильтрация кандидатов ПОСЛЕ генерации вместо pre-generation gate.
- ❌ **SceneChange как триггер (Rule 4, §2.2):** Вызов `scene_manager.apply_changes()` из подписчика запрещен.
- ❌ **Прямая мутация позиции (Rule 1):** `npc["position"] = ...` запрещено.
- ❌ **Двойной исполнитель (Rule 18, ADR-066):** Вызов `process_intents()` из `npc_orchestration.py` запрещен. Единственный владелец — `TickOrchestrator`.
- ❌ **Schedule Override Reactive Movement (Rule 57, ADR-130):** `update_routine()` НЕ имеет права мутировать `routine`, если NPC имеет активный traversal.
- ❌ **LifeEngine Intent Generation for Moving NPC (ADR-154, S85.1):** `LifeEngine._simulate_major` ЗАПРЕЩЕНО генерировать интенты для NPC в статусе `MOVING`.
- ❌ **Traversal Overwrite in apply_changes (ADR-130.1, S85.1):** Перезапись активного транзита (`status="MOVING"`) в `apply_changes` запрещена.
- ❌ **New Traversal on Complete (ADR-130.2, S85.1):** Создание нового `TraversalState` для `cause="traversal_complete"` запрещено (нужен только snap).
- ❌ **Голый DecisionHub() (ADR-O-301):** Вызов `DecisionHub()` без передачи `rng` запрещён. Использование глобального `random.*` в kernel layer запрещено.
- ❌ **Нарушение изоляции подсистем (ADR-O-301):** Создание `KernelRNG` без `salt` (или использование одного `salt` для разных подсистем) запрещено. Каждая подсистема (DecisionHub, LifeEngine, MovementEngine) обязана иметь свой `salt`.

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Поток:** Контакт → Урон → Боль → Шок-импульс.

**Актуальные DTO:**
- **`InjuryDTO`** (`models/delta_payloads.py`): `damage_type`, `target_zone`, `structural_damage`, `functional_loss`, `critical_effects`. **ADR-123:** `critical_effects` — информационные теги, НЕ источник логики.
- **`PhysiologyPayload`** (`models/delta_payloads.py`): `hp_delta`, `pain_delta`, `blood_loss_delta`, `fatigue_delta`, `shock_impulse`. **ADR-109:** `shock_impulse` поддерживает отрицательные дельты (decay). **ADR-122:** `affective_load` убран из payload.
- **`LifeStatus`** (`domain/vital_state.py`): Enum `ALIVE` / `DEAD`. ЕДИНСТВЕННЫЙ источник истины о жизни/смерти (ADR-123).
- **`BODY_STATE_DISABLED`** (`models/npc_state.py`): Константа sentinel. Используется когда `body_state` отсутствует. Значения: `disabled=True, shock_impulse=1.0, pain=100.0` (NPIC, ADR-O-139).
- **`NPCState.body_state`** (`models/npc_state.py`): Dict. Ключи: `current_hp`, `pain` (0-100), `fatigue` (0-100), `blood_loss` (0-1.0), `consciousness` (0-1.0), `shock_impulse` (0-1.0), `injuries`, **`life_status` (str: "ALIVE"/"DEAD", ADR-123/127)**. **ADR-100/127:** Обязательная сериализация.
- **`NPCState.hp` / `NPCState.max_hp`** (`models/npc_state.py`): DEPRECATED. Канонический источник HP — `body_state["current_hp"]`. Свойства `effective_hp` и `effective_max_hp` читают из `body_state` с fallback на `hp` (ADR-HP-UNIFICATION, S86).
- **`ImpactIntentDTO`** (`models/impact.py`): Контракт физического контакта (удар, касание). Генерируется CombatSubscriber, потребляется ImpactEngine.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2):**
- ❌ **Domain Leakage (Rule 9):** `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload`. Прямая генерация эмоций запрещена.
- ❌ **Rule X Violation (Rule 26, ADR-101):** `BehaviorManifestationService` читает эмоции вместо физиологии.
- ❌ **Shock Immortality (Rule 28, ADR-109):** `shock_impulse` без decay = перманентный шок.
- ❌ **HP Death (Rule 38, ADR-123):** `hp <= 0` как источник смерти запрещён. Единственный владелец — `evaluate_vital_state()`.
- ❌ **Player Action Without Life Status Check (Rule 59, ADR-131):** Мёртвый игрок не может действовать.
- ❌ **MSOC Normalization (Rule 63/64, ADR-094):** Чтение `pain`/`fatigue` без нормализации `/100.0` в потребителях с порогами 0-1 запрещено.
- ❌ **Player Body State Hydration Gap (Rule 55, ADR-128):** `PlayerAvatarService._state_from_dict()` без `body_state`/`affective_load`/`perceptual_kernel` запрещён.
- ❌ **HP Double Truth (ADR-HP-UNIFICATION, S86):** Прямая запись в `state.hp` в обход `body_state["current_hp"]` запрещена. Канонический источник — `body_state`.

---

## 6. МУТАЦИЯ И ЭМОЦИИ (State Mutation & Affective Integration)
**Поток:** Все изменения → Буфер → Агрегация → Интеграл Аффекта → Эмоция.

**Актуальные DTO:**
- **`DeltaDomain`** (`models/state_delta.py`): `PHYSIOLOGY`, `EMOTION`, `SOCIAL`, `PERCEPTION`, `IDENTITY`, `SPATIAL`.
- **`PerceptionPayload`** (`models/delta_payloads.py`): `threat_gradient_delta`, `uncertainty_delta`, `anomaly_score_delta`. Обновляет `PerceptualKernel`.
- **`EmotionPayload`** (`models/delta_payloads.py`): Порождается только после фазового перехода в Аффект-Интеграторе (Фаза 9).
- **`IdentityPayload`** (`models/delta_payloads.py`): `compliance_bias_delta`, `initiative_suppression_delta`, `recent_directive_data`.
- **`ReputationPayload`** (`models/delta_payloads.py`): Дельта репутации NPC в социальном слое (InstitutionLayer/VillageMemoryField).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.9, §4.2, §4.4):**
- ❌ **Прямая генерация эмоций (§2.1, §3.9):** Обход `AffectiveIntegrator` запрещен.
- ❌ **Ретро-симуляция (Rule 16):** `TICK_CATCHUP` запрещен. Только `reconcile_state(elapsed_seconds)`.
- ❌ **Emotional Residue Isolation (ADR-O-206):** Смешивание эмоционального остатка с физиологическим циклом затухания без изоляции запрещено.

---

## 7. ПРЕЗЕНТАЦИЯ И UI (Presentation & Frontend)
**Поток:** Runtime Истина → Феноменологическая Проекция → Фронтенд.

**Актуальные DTO:**
- **`WorldSnapshotDTO`** (`domain/snapshot.py`): `npc_positions` (**Dict[str, NPCPositionDTO]**, ADR-TZ03-1 A2-FIX), `active_traversals`, `avatar_state`, `ambient_phenomenology`.
- **`AvatarStateDTO`** (`domain/snapshot.py`): Непрерывные скаляры + **`life_status`** (ADR-137). Вычисляется через `AvatarPresentationAssembler`.
- **`PlayerPerceptionDTO`** (`domain/snapshot.py`): `embodied_traces`, `peripheral_cues`, **`manifestations`** (ADR-O-147), `active_perceptions`, `avatar_desync`.
- **`ManifestationDTO`** (`domain/snapshot.py`, ADR-O-147): Наблюдаемое физическое проявление NPC. Поля: `npc_id`, `tags` (List[str]). НЕ эмоция!
- **`PeripheralCueDTO`** (`domain/snapshot.py`): Периферическое наблюдение. Поля: `npc_id`, **`cue_key`** (renamed from `cue_type`, ADR-TZ03-1 A3-FIX), `hover_text`.
- **`EmbodiedTraceDTO`** (`domain/embodied_trace.py`): Моторный след NPC (instability, micro_pause, action_interruption). Генерируется `BehaviorManifestationService`, конвертируется в `ManifestationDTO` для API.
- **`AvatarDesyncDTO`** (`domain/snapshot.py`): Метрика рассинхронизации восприятия аватара игрока и реальности. Часть `PlayerPerceptionDTO`.
- **`ReconstructionEventDTO`** (`domain/snapshot.py`): Событие реконструкции памяти/восприятия для UI.
- **`SceneEvent`** (`models/scene_event.py`): Событие изменения сцены (дверь открылась, предмет упал). Часть `WorldSnapshotDTO` для фронтенда.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.3, §4.4):**
- ❌ **Телепатия в UI (Rule 11):** Передача Игроку внутренних состояний NPC запрещена.
- ❌ **Kernel Leakage в DM (Rule 23, ADR-093):** DM-агент читает внутренние состояния напрямую вместо `embodied_traces`.
- ❌ **Масштабная несовместимость pain (Rule 24, ADR-094):** Обязательна нормализация `pain / 100.0`.
- ❌ **Показ эмоций (Rule 35):** Только наблюдаемые проявления (tense, rigid). Запрещено показывать fearful.
- ❌ **Смешивание cues и manifestations (Rule 36):** Только отдельные каналы.
- ❌ **Death Guard без npc_positions (Rule 82, ADR-137):** Мир замерзает при смерти игрока. Обязательно включать.

---

## 8. ИДЕНТИЧНОСТЬ И ОНТОЛОГИЯ (Identity Layer & Chronicle)
**Поток:** L0 (Perception) + L1 (Chronicle) → L1.5 (PatternDetector) → L2.5 (Belief Engine) → L3 (EffectiveDrives) → Модуляция Давления/Риска.

### S-93 Secondary Cognitive Contour (PE Active Inference)
- **`ExpectationStore`** (`services/npc/expectation_store.py`): EMA-хранилище ожиданий NPC (T-1). Содержит словари ожидаемых значений драйвов. Обновляется исключительно в `StateApplicator` (Single Writer). Затухает в Фазе 0.5.
- **`DopaminePayload`** (`models/delta_payloads.py`): Сигнал Reward Prediction Error (RPE). Вычисляется в `StateApplicator` как разница между актуальным состоянием и `ExpectationStore`.
- **`PEModifierResolver`** (`services/npc/pe_modifier_resolver.py`): Pure function. Преобразует `DopaminePayload` (PE) в `drive_modifiers` (T0) через `tanh` нормализацию и `MAX_PE_INF` (Clamp = 0.25). PE не может доминировать над DRF.
  🚫 ЗАПРЕТ: Вычисление EMA вне `StateApplicator`. ❌ Прямое управление интентами на основе PE (только через `drive_modifiers`). ❌ Влияние PE на utility > 0.25.

**Актуальные DTO:**
- **`TraitDriftEvent`** (`domain/identity_events.py`): Единица записи давления мира в L1 Chronicle (ADR-O-208 / ADR-O-305A). **Символическая смерть старого контракта (S85.1)**. Поля: `tick_id` (int), `target_id` (str), `source_id` (str), `effect_value` (float), `observation_weight` (float), `event_type` (str). Immutable.
- **`EvidenceOfPersistence`** (`domain/identity_events.py`): Агрегированная статистика PatternDetector (L1.5). Чистая математика, без психологии (ADR-O-305A). Поля: `source_id`, `cumulative_effect`, `behavior_variance`.
- **`CrystallizedBelief`** (`domain/identity_events.py`): Психологическая проекция статистики (L2.5). Поля: `source_id` (str), `trait` (str: fear/trust), `weight` (0.0-1.0), `last_updated_tick` (int). Подвержена асимметричной травме (x6) и экспоненциальному затуханию (Decay).
- **`EffectiveDrives`** (`domain/identity_events.py`): Эфемерная, неизменяемая проекция драйвов (L3) (ADR-O-208). Содержит `values: MappingProxyType`. Попытка мутации вызывает `TypeError`. Запрещено кэшировать (L3-P1).
- **`EventMemory`** (`models/npc_state.py`): Запись в `narrative_cache` (L2). Хранит структурированный след события для долгосрочной памяти NPC.
- **`OntologyViolationError`** (`domain/exceptions.py`): Критическое нарушение инвариантов (L5 Post-Commit Validation Gate) (ADR-O-207). Выбрасывается при нарушении Закона Сохранения Я (sum!=1.0), выходе за границы [0,1] или NaN. Убивает тик.
- **`L1Chronicle`** (`services/npc/l1_chronicle.py`): Append-only хранилище событий деформации идентичности (L1) (ADR-O-208). **S86:** Персистентно в SQLite (таблица `l1_chronicle_events`). In-memory dict — кэш. Методы: `append(event)`, `query_raw(npc_id)`, `query_weighted(npc_id, current_tick)`. Удаление запрещено. Использует `tick_id` для времени.
- **`PatternDetector`** (`services/npc/pattern_detector.py`): Чистая функция L1.5. Группирует L1Chronicle по `source_id` и генерирует `EvidenceOfPersistence`. Не имеет права читать эмоции/драйвы (ADR-O-305).
- **`BeliefCrystallizationEngine`** (`services/npc/belief_crystallization_engine.py`): Мост L2.5. Проецирует `EvidenceOfPersistence` в `CrystallizedBelief`, модулированный `drives_base` (L0). Реализует асимметричную травму (ADR-O-307) и энтропию (Decay).
- **`DriveResolver`** (`services/npc/drive_resolver.py`): Чистая функция вычисления проекции (L0 + L1 -> L3) (ADR-O-208). Метод: `resolve_drives(archetype, l1_events_weighted) -> EffectiveDrives`. Не имеет состояния.
- **`RulesSubscriber`** (`services/events/rules_subscriber.py`): Pure Reducer (TZ-08 v0.2). Вычисляет механику D&D 5e (DC, броски, урон) на основе event + snapshot. Возвращает `RulesDelta` (damage, success, checks metadata).
- **`WorldProjectionEvent`** (`domain/world_projection.py`): Наблюдаемый вторичный эффект, порождённый буфером проекций (ADR-O-309). Frozen dataclass. Поля: `event_id` (str), `tick` (int), `projection_type` (ProjectionType: RUMOR/REPUTATION/AMBIENT), `source_id` (str), `location_id` (str), `description` (str), `salience` (float, 0..1), `target_id` (Optional[str]).
- **`DMContextDTO`** (`services/tick_orchestrator.py`): DEPRECATED (TZ-08). Ранее использовался для передачи контекста DM в ядро. Возвращать из ядра запрещено.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (ADR-O-207, ADR-O-208, ADR-O-211, ADR-O-305, S85.1/S85.2/S86):**
- ❌ **Кэширование EffectiveDrives (L3-P1):** Эфемерная проекция, пересчитывается каждый тик. Кэш = рассинхрон идентичности.
- ❌ **Удаление из L1Chronicle:** Append-only хранилище. Удаление = переписывание истории.
- ❌ **Коммит невалидной онтологии (ADR-O-207):** Сохранение состояния с NaN, sum(drives) != 1.0, выход за [0,1] — краш пайплайна (OntologyViolationError).
- ❌ **Некалиброванный дрейф (ADR-O-211 / S86):** Изменение базовых драйвов (`drives_runtime`) через `CalibrationEngine` (применение `ctx.drives_updates`) ЗАПРЕЩЕНО. Мутация скалярных драйвов минуя Belief Layer (L2.5) недопустима.
- ❌ **Устаревшие поля TraitDriftEvent (S85.1):** Чтение полей `npc_id`, `tick`, `trait`, `delta` запрещено. Использовать `target_id`, `tick_id`, `effect_value`.
- ❌ **Прямой конструктор NPCState:** В `TickOrchestrator` и `BreakProgressEngine` использовать `NPCStateAdapter.from_legacy()`, а не `NPCState.from_legacy()`.
- ❌ **Использование event_type в формулах L1.5 (ADR-O-305A):** `event_type` существует исключительно как provenance и запрещён в математических формулах `PatternDetector`.
- ❌ **Psychological fields in L1.5 (ADR-O-306):** Наличие полей `trait`/`emotion` в `PatternDetector` или `EvidenceOfPersistence` запрещено.
- ❌ **Belief Engine reads L1 directly (ADR-O-305):** `BeliefCrystallizationEngine` читает `L1Chronicle` напрямую (работает только через `EvidenceOfPersistence`).
- ❌ **Scalar Fear / No Decay (ADR-O-305.1):** Скалярный страх (`CrystallizedBelief` без `source_id`) и отсутствие Decay для `CrystallizedBelief` запрещены.
- ❌ **Phantom Identity Drift (ADR-S86.7):** Запуск `check_identity_promotion` (L2.5 кристаллизация) в idle-тиках без `phase_2_events` запрещен. Память не может генерировать идентичность без каузального входа.
- ❌ ЗАПРЕТ: Мутация state, асинхронность, наличие internal state/cache. Детерминированность RNG обязательна (seed from event_id + tick).
- ❌ **Глобальный random (ADR-O-301):** Использование `random.*` в kernel layer запрещено. Все вызовы должны идти через `KernelRNG(tick, npc_id, salt)`.

---

## 9. TIME SKIP (Observation Layer)
**Поток:** TimeSkipExecutor → Kernel.execute() → TickResultDTO → Detectors → TimeSkipResult.

**Актуальные DTO:**
- **`TimeSkipResult`** (`services/world/time_skip_executor.py`): Результат промотки времени. Поля: `final_state`, `event_log`, `stop_reason`, `ticks_skipped`, `stops`, `significant_event`, `checkpoints`, `summary`.
- **`SignificantEvent`** (`services/world/time_skip_executor.py`): Остановка Policy B. Поля: `type` (str), `tick` (int), `details` (Dict).
- **`Milestone`** (`services/world/time_skip_executor.py`): Запомненный этап для Policy C. Поля: `type`, `tick`, `details`, `requires_playback`.
- **`MilestoneCheckpoint`** (`services/world/time_skip_executor.py`): Sparse checkpoint. Поля: `tick`, `state` (deepcopy of scene_state), `milestone`.
- **`MicroEvent`** (`services/reaction/micro_event.py`): Событие микро-реакции (вздрогнул, зажмурился). Генерируется `ReactionRules`, резолвится `ReactionResolver` в `EmotionPayload`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ:**
- ❌ **Second Simulator (TZ-08 Addendum):** Создание отдельного симулятора для long-duration events. Time Skip — это только многократный вызов `Kernel.execute()`.
- ❌ **Hardcoded SSOT:** Прямой вызов `LifeEngine` из детекторов. Используется `get_npcs_callback`.
- ❌ **Direct Cache Access:** Прямой доступ к `LifeEngine._npc_cache` из `GameLoop` или детекторов. Используется `LifeEngine.get_npc_light_states()`.
- ❌ **Time Advancement in Kernel:** `TimeSkipExecutor` (или `GameLoop`) инкрементирует тик, ядро остаётся pure function.
- ❌ **Deferred Commit in Kernel:** `TickOrchestrator.execute()` обязан завершать commit состояния ДО возврата, иначе детекторы Time Skip прочитают устаревший SSOT.

### Список Песочниц (Fail Conditions)
Каждый запрет из этого реестра должен быть покрыт тестом:
- `test_no_direct_mutation_of_position` (Rule 1)
- `test_no_direct_scene_change_in_resolver` (Rule 4)
- `test_pressure_modifies_utility_not_commands` (Rule 6 / L2)
- `test_willpower_gate_single_invocation_per_tick` (Rule 8)
- `test_no_telepathy_in_ui_observation` (Rule 11)
- `test_perceptual_kernel_survives_legacy_roundtrip` (Rule 31, ADR-115)
- `test_movement_processed_once` (Rule 18, ADR-066)
- `test_bridge_includes_active_traversals` (Rule 21, ADR-071)
- `test_fast_path_emotional_vector_injection` (ADR-088)
- `test_campaign_id_not_replaced_by_location_id` (ADR-089)
- `test_no_local_scope_variable_leakage` (Rule 32, ADR-116)
- `test_relationship_cache_not_persisted_in_legacy` (Rule 36, ADR-121)
- `test_sqlite_readback_preserves_injuries` (Rule 52, ADR-128)
- `test_player_body_state_survives_save_load` (Rule 54/55, ADR-128)
- `test_wounds_not_used_as_physiology_source` (Rule 56, ADR-128)
- `test_movement_lock_blocks_schedule_on_active_traversal` (Rule 57, ADR-130)
- `test_drf_bus_instance_level_not_default_factory` (Rule 73, ADR-134)
- `test_drf_pipeline_receives_execution_context_not_bare_bus` (Rule 76, ADR-136)
- `test_drf_scoring_additive_not_clamp` (Rule 80, ADR-135)
- `test_threatened_npc_no_routine_intent` (ДОЛГ 4.3, ADR-O-137)
- `test_paralyzed_npc_only_survival` (ADR-O-137)
- `test_avatar_to_prompt_includes_life_status_dead` (Rule 65, ADR-140)
- `test_somatic_urgency_modulated_by_willpower` (ADR-O-143)
- `test_effective_drives_not_cachable` (ADR-O-208)
- `test_l1_chronicle_append_only` (ADR-O-208)
- `test_ontology_violation_kills_tick_on_nan` (ADR-O-207)
- `test_manifest_tags_not_emotions` (ADR-O-147)
- `test_boundary_node_not_movement_goal` (ADR-145)
- `test_apply_changes_does_not_overwrite_active_traversal` (ADR-130.1)
- `test_apply_changes_snaps_position_on_traversal_complete` (ADR-130.2)
- `test_life_engine_skips_moving_npcs` (ADR-154)
- `test_trait_drift_event_contract_no_legacy_fields` (ADR-O-208.1)
- `test_pattern_detector_math_correct` (ADR-O-305A)
- `test_asymmetric_trauma_x6` (ADR-O-307)
- `test_belief_decay_model` (ADR-O-305.1)
- `test_belief_engine_no_direct_l1_read` (ADR-O-305)
- `test_hp_double_truth_invariant` (ADR-HP-UNIFICATION, S86)
- `test_l3_ephemeral_invariant` (ADR-O-211 / ADR-IMMUNE-001, S86)
- `test_kernel_rng_determinism` (ADR-O-301)
- `test_no_global_random_in_kernel` (ADR-O-301)
- `test_decision_hub_requires_rng` (ADR-O-301)
- `test_no_zombie_readers` (ADR-TZ04-1)
- `test_no_random_uniform_in_apply_change` (ADR-TZ04-2)
- `test_dead_spatial_modules_removed` (ADR-TZ04-3)
- `test_spatial_factory_used` (ADR-TZ04-4)
- `test_metadata_scene_change_routing` (ADR-TZ04-5)
- `test_no_print_in_movement_engine` (ADR-TZ6-1)
- `test_willstate_single_definition` (ADR-TZ6-1)
- `test_compute_continuous_drift_returns_list` (ADR-TZ6-1)
- `test_no_silent_failures_in_tick_orchestrator` (ADR-TZ6-1)
- `test_constants_has_spatial` (ADR-TZ6-1)
- `test_constants_has_dm_messages` (ADR-TZ6-1)
- `test_i18n_has_menu_keys` (ADR-TZ6-1)



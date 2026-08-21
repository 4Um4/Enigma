# DTO Registry — Каузальный Атлас Контрактов ENIGMA

> **Статус:** ACTIVE | **Сессия:** S201 | **Версия:** 8.0 (Unified & Expanded)
> **Основание:** CAUSAL CONTRACT v2.0, ADR-O-208/305A, ADR-O-354/355/357/358 (Epistemic Core)
> 
> **Формат для LLM:** `📦 DTO` → `🔗 Поток` → `📁 Файл` → `🚫 КАУЗАЛЬНЫЕ ЗАПРЕТЫ`.
> **Path Alias:** `svc/`=backend/app/services/ | `dom/`=backend/app/domain/ | `mod/`=backend/app/models/

---

## 0. 🧭 ENIGMA ONTOLOGY (Context Anchor for LLM)

Все DTO в системе подчиняются **пятиуровневой архитектуре восприятия**. Любой LLM-агент должен понимать эту иерархию, чтобы не создавать каузальных разрывов:

| Уровень | Суть | Примеры DTO |
|---------|------|-------------|
| **L0** Perception | Мир → Восприятие. Нет телепатии. | `PerceptualKernel`, `FieldDisturbance` |
| **L1** Chronicle | Append-only SQLite факты | `TraitDriftEvent`, `EvidenceOfPersistence` |
| **L2** Identity | Кристаллизованные убеждения (линзы) | `CrystallizedBelief`, `EpistemicRecord` |
| **L3** Drives | Эфемерные драйвы (1 тик) | `EffectiveDrives`, `DriveVector` |
| **L4** Behavior | Решение → `DecisionHub` | `CommunicationIntent`, `MovementIntent` |

**Философия контрактов:**
- **L0 (PERCEPTION):** Симметричная подача информации игроку и NPC через `PerceptualKernel`.
- **L1 (BODY):** Формула инерции: `new = old * rigidity + delta * (1 - rigidity)`. Скачки = баг.
- **L2 (BEHAVIOR):** `DecisionHub` — единственный источник решений. Давление искривляет utility, но не приказывает.
- **L3 (EPISTEMIC):** Убеждения = линзы (модификаторы весов), не факты. `confidence ≠ truth`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Глобальные):**
- ❌ Изменяемые дефолты в иммутабельных DTO (используй `@dataclass(frozen=True)`).
- ❌ Возврат сервисных объектов (svc) в редюсер.
- ❌ Прямая мутация `state.hp`, `npc["position"]`, `scene_state["npc_positions"]`.
- ❌ Чтение `psyche`/`stress`/`trust` в DM-слое и фронтенде (Epistemic Boundary).
- ❌ `random.*` / `time.time()` / `datetime.now()` в kernel layer.
- ❌ `except: pass` без логирования (L4 Silent Failure).

---

## 1. 🔗 ВВОД И СЖАТИЕ (Input & Intent Compression)

**Поток:** Сырой текст → `IntentSemanticField` → `IntentParametersDTO` → `InterventionEvent`

### 📦 `IntentSemanticField`
- 📁 `dom/intent_profile.py`
- **Вероятностное поле.** `actor_reference`, `ActionType`, `TargetZone`, `SemanticAmbiguity`, `EmotionalVector`, `ConfidenceVector`.
- **ADR-088:** `EmotionalVector` больше не нулевой. Для `ATTACK` → `aggression=0.8`.
- **ADR-O-314:** Добавлено `actor_reference`.

### 📦 `IntentParametersDTO`
- 📁 `dom/intent.py`
- **Строгий контракт.** `semantic_action`, `actor_id`, `target_reference`, `target_id`, `physical_force`, `emotional_charge`, `social_pressure`.
- **ADR-083:** `semantic_action` приоритетный. **ADR-125:** `target_id` DEPRECATED.

### 📦 `InterventionEvent`
- 📁 `svc/contracts/interventions.py`
- **Внешнее вмешательство.** `source` (str), `payload` (Dict), `tick` (int). Factory: `from_player_action()`.
- Ядро не знает 'player', 'dm_ctx' или 'world_scheduler'.

### 📦 `PlayerActionPayload` / `MemoryPayload`
- 📁 `dom/events.py` (TypedDict)
- **Player:** `action_type`, `semantic_action`, `target_id`, `physical_force`, `social_pressure`.
- **Memory:** Контракт записи в STM/L2.

### 📦 `NPCObservedState`
- 📁 `svc/npc/npc_tick_pipeline.py`
- **Наблюдаемый слепок** (ADR-TZ08-6). Содержит ТОЛЬКО публичные поля: `name`, `description`, `narrative_cache`.
- 🚫 **ЗАПРЕТ:** Восстановление ментальных полей через инференс.

### 📦 `IntentCompressor`
- 📁 `svc/game_loop/input/intent_compressor.py`
- **Async-компрессор.** `compress()` → `IntentSemanticField`. Slow-Path (LLM) / Fast-Path.
- 🚫 **ЗАПРЕТ:** LLM внутри `phase_1_input.py`; `IntentCompressor(llm_client=None)`.

### 📦 `EventContext`
- 📁 `svc/npc/decision_hub.py`
- **Чистая проекция Intent** для DecisionHub. `intent`, `target_id`, `event`. Immutable после создания (§ENIGMA-005).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 1):**
- ❌ Удаление `name` из `npc_positions` (Rule 14, Fuzzy Matching).
- ❌ Silent Fallback: `target_ref` не резолвится → `UNCERTAINTY`.
- ❌ Чтение `intent.action` без fallback на `parameters.semantic_action`.
- ❌ Дефолтный `EmotionalVector()` для `ATTACK`.
- ❌ `location_id` вместо `campaign_id`.

---

## 2. 🔗 ВОЛЯ И ДАВЛЕНИЕ (Will & Pressure)

**Поток:** `IntentParametersDTO` → `IntentPressureProfile` → `AmplifiedPressureProfile` → `WillResponseDTO`

### 📦 `IntentPressureProfile` / `AmplifiedPressureProfile`
- 📁 `mod/will.py`
- Вектор давления и его искажение через `ResponseBias`.

### 📦 `WillResponseDTO`
- 📁 `mod/will.py`
- **Результат WillpowerGate.** `WillState`, `resistance`, `stress_delta` (0-100, ADR-S101.1), `identity_damage`, `counter_offer`, `embodied_vector`.
- **ADR-TZ6-1:** `WillState` канонически в `mod/npc_state.py`.

### 📦 `CommunicationIntent`
- 📁 `dom/communication.py`
- **SSOT ответа NPC.** Обязателен `topic`. Добавлены `semantic_action`, `target_id` для проброса в `NPC_SPOKE`.

### 📦 `WillConflictPayload`
- 📁 `mod/delta_payloads.py`
- Конфликт воли (сопротивление игрока). Пробрасывается в `WorldSnapshotDTO`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 2):**
- ❌ `MovementIntent` без `pressure_sources` (Rule 6).
- ❌ `WillpowerGate` > 1 раза за цикл (Rule 8).
- ❌ NPC dict без `body_state` (Rule 92, ADR-O-139).
- ❌ Somatic Gate ПОСЛЕ семантического парсинга. Порядок: `Body → Somatic → Semantic → Legitimacy → Action`.
- ❌ `if not body_state: return []` без `BODY_STATE_DISABLED`.

---

## 3. 🔗 ПРИЧИННОСТЬ И ВОСПРИЯТИЕ (CFRM & Perception)

**Поток:** Факт → `FieldDisturbance` → `PerceptualKernel` → Психологическое давление

### 📦 `FieldDisturbance`
- 📁 `mod/cfrm.py`
- Возмущение поля. Оси: кинетика, акустика, материя, поведение.

### 📦 `PerceptualKernel`
- 📁 `mod/npc_state.py`
- **Субъективная модель (L1).** 11+ полей: `threat_gradient`, `trust_gradient`, `uncertainty`, `anomaly_score`, `last_hostile_direction`, `dominant_emotion`, `aggression_inhibition`, `initiative_suppression`, `compliance_bias`, **`somatic_urgency`** (ADR-O-143), `recent_directive`.
- **ADR-115:** Обязательная сериализация. **Rule 38:** Затухание в idle.

### 📦 `PerceivedNarrativeDTO` (S158)
- 📁 `dom/presentation.py`
- **Эпистемический канал реплик.** Поля: `speaker_id`, `text`, `auditory_clarity` (0-1), `delivery_type` (whisper/shout/normal), `perception_certainty`.
- 🚫 **ЗАПРЕТ:** Поле `INTERNAL` в `delivery_type`; Прямой доступ к тексту при `auditory_clarity < 0.3`.

### 📦 `PerceivedManifestationDTO` (S158)
- 📁 `dom/presentation.py`
- **Канал наблюдаемых проявлений.** Поля: `npc_id`, `manifestation_tags`, `visual_certainty`.

### 📦 `AuditoryDistortionPolicy` (S159)
- 📁 `svc/perception/auditory_distortion_policy.py`
- **Честный фильтр восприятия.** Определяет искажение текста на основе `auditory_clarity` и `distance`.
- 🚫 **ЗАПРЕТ:** Мутация входного текста; Использование `scene_state` вместо `PerceptionContext`.

### 📦 `AvatarPerceptionProfile` (S159)
- 📁 `dom/presentation.py`
- Изоляция психики аватара от восприятия.

### 📦 `NPCState.consciousness_state`
- 📁 `mod/npc_state.py`
- FSM: `SLEEPING`/`AWAKE`/`UNCONSCIOUS`/`DEAD` (ADR-O-142).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 3):**
- ❌ Давление через мембрану с `attenuation=0.0` (Rule 7).
- ❌ Телепатия Игроку (Rule 11).
- ❌ `write_to_legacy` без `perceptual_kernel` и `affective_load`.
- ❌ `Leaky Integrator` для `affective_load` — только гистерезис.
- ❌ Инъекция `pain`/`shock` напрямую в `psyche` (Somatic Bypass).

---

## 4. 🔗 РЕШЕНИЯ И ДВИЖЕНИЕ (Decision & Locomotion)

**Поток:** `PerceptualKernel` + `DecisionContext` → `DecisionHub` → `MovementIntent` / `TraversalState`

### 📦 `DecisionContext`
- 📁 `dom/decision_context.py`
- **Контекст решения.** `UtilityFieldDeformation`, `ActionSpaceCompression`, `body_state` (Somatic Veto), **`epistemic_context: Optional[EpistemicContext]`** (S188). Frozen.

### 📦 `IntentDomain`
- 📁 `dom/movement.py`
- Enum: `SURVIVAL`, `SOCIAL`, `ROUTINE`, `EXPLORATION`. (ADR-O-137)

### 📦 `MacroMovementGoal`
- 📁 `dom/movement.py`
- LOD1. `actor_id`, `target_node_id`, `from_node_id`, `target_local_xy`, **`domain: IntentDomain`**, `processed` (bool).
- 🚫 **ЗАПРЕТ:** Повторная обработка с `processed=True` → `RuntimeError`.

### 📦 `TraversalState` / `TraversalContract`
- 📁 `mod/` / `mod/thick_scene_change.py`
- **Физическое состояние:** `source_node`, `target_node`, `waypoints`, `progress` (0-1), `speed`, `created_tick`.
- **ADR-O-201.4:** `TraversalContract(status="NEW"|"COMPLETED")` в `ThickSceneChange`. Lifecycle = прерогатива `SceneStateManager`.

### 📦 `SceneChange` / `ThickSceneChange`
- 📁 `svc/scene_change.py` / `mod/thick_scene_change.py`
- **`SceneChange`:** Thin legacy. **`ThickSceneChange`:** Полный физический контракт с `SpatialResolution`, `MotionPlan`, `BoundaryResolution`, `TraversalContract`.
- 🚫 **ЗАПРЕТ:** `target_location_id` вне `_process_traversals()`.

### 📦 `SpatialFactory` / `KernelRNG`
- 📁 `svc/spatial/spatial_factory.py` / `svc/npc/kernel_rng.py`
- **SSOT сборки графа** (ADR-TZ04-4). **SSOT случайности** (ADR-O-301): `(tick, npc_id, salt)`.
- 🚫 **ЗАПРЕТ:** Прямой `SpatialService.build_for_location()`; `DecisionHub()` без `rng`.

### 📦 Motion Core DTOs (ETKE-IK v1)
- 📁 `dom/motion_core.py`
- **`AffordanceVector`:** Физические возможности среды.
- **`BodySchema`:** Кинематические ограничения.
- **`DriveVector`:** Микро-движение. `direction: Tuple[float,float]`, `intensity: float` (0-1).
- **`KinematicProfile`:** Выход для FE. `velocity`, `posture`, `facing`, `exertion_level`.
- **`drive_vector` в npc dict:** `[dx, dy, intensity, primitive_str]`. Очищается каждый `tick_decisions`.
- 🚫 **ЗАПРЕТ:** DriveVector без очистки; FLEE с неинвертированным direction; MovementIntent для same_node.

### 📦 Stigmergy & Dynamic Affordance (S91)
- 📁 `dom/motion_core.py` / `svc/spatial/world_topology_provider.py`
- **`DeformationRecord`:** Hard Override (`type`, `magnitude`, `ttl`, `source_id`).
- **`TracePayload`:** Soft Trace (`region`, `zone_id`, `trace_type`).
- **`DynamicAffordanceField`:** State-object с Hard + Soft слоями.

### 📦 Motion Semantic Classification (S127, ADR-O-328)
- 📁 `dom/traversal_schema.py`
- **`MovementPlanStatus`:** `MICRO_MOVEMENT` (<0.1) / `MACRO_TRAVERSAL` / `ACCEPTED`.
- **`MovementPlanResult`:** `MICRO_MOVEMENT` не требует `proposal`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 4):**
- ❌ Boundary resolution при создании traversal.
- ❌ MovementEngine заполняет `target_location_id`.
- ❌ `MovementIntent` без `domain` (Rule 88).
- ❌ `scene_manager.apply_changes()` из подписчика (Rule 4).
- ❌ Прямая мутация `npc["position"]` (Rule 1).
- ❌ `LifeEngine._simulate_major` для NPC в `MOVING` (ADR-154).
- ❌ Перезапись `status="MOVING"` в `apply_changes` (ADR-130.1).
- ❌ Создание `TraversalState` на `traversal_complete` (ADR-130.2).
- ❌ `TraversalProposal` для `MICRO_MOVEMENT` (ADR-O-328).

---

## 5. 🔗 ФИЗИОЛОГИЯ, БОЙ И СОН (Physiology, Combat & Sleep)

**Поток:** Контакт → `ImpactIntentDTO` → `PhysiologyPayload` → `body_state` → `LifeStatus` / `CouplingProfile`

### 📦 `InjuryDTO`
- 📁 `mod/delta_payloads.py`
- `damage_type`, `target_zone`, `structural_damage`, `functional_loss`, `critical_effects` (ADR-123: только инфо-теги).

### 📦 `PhysiologyPayload`
- 📁 `mod/delta_payloads.py`
- `hp_delta`, `pain_delta`, `blood_loss_delta`, `fatigue_delta`, `shock_impulse`.
- **ADR-109:** `shock_impulse` поддерживает отрицательные дельты.
- **ADR-122:** `affective_load` убран.

### 📦 `LifeStatus`
- 📁 `dom/vital_state.py`
- Enum `ALIVE` / `DEAD`. **ЕДИНСТВЕННЫЙ** источник (ADR-123).

### 📦 `BODY_STATE_DISABLED`
- 📁 `mod/npc_state.py`
- Sentinel: `disabled=True, shock_impulse=1.0, pain=100.0` (NPIC).

### 📦 `NPCState.body_state`
- 📁 `mod/npc_state.py`
- Dict: `current_hp` (SSOT), `pain` (0-100), `fatigue`, `blood_loss`, `consciousness`, `shock_impulse`, `injuries`, `life_status`, **`coupling_profile`** (S189).

### 📦 `attack_roll` / `ImpactEngine`
- 📁 `svc/combat/combat_math.py` / `svc/combat/impact_engine.py`
- **D&D 5e контракт (ADR-164).** Возвращает `ContactLevel`: `MISS`, `GLANCING`, `PARTIAL`, `SOLID`, `PERFECT`.
- 🚫 **ЗАПРЕТ:** Вычисление попадания вне `combat_math.py`.

### 📦 `CouplingProfile` (S189, ADR-O-356)
- 📁 `dom/body.py`
- **Режим телесной связанности.** Поля: `external_vision_mult`, `external_hearing_mult`, `motor_output_mult`, `memory_activation_mult`, `imagination_mult`, `coupling_mode` (Enum).
- Вычисляется каждый тик из `sleep_pressure` + `arousal` через `CouplingResolver`.
- 🚫 **ЗАПРЕТ:** Скриптовые флаги `is_sleeping`.

### 📦 `DreamSignal` (S189)
- 📁 `dom/events.py`
- **Сигнал сна.** Генерируется `DreamGenerationService` из `PerceptualKernel`. `EventType` = `DREAM` / `NIGHTMARE`.
- При пробуждении конвертируется в `affective_load` + `threat_gradient` (DreamResidue).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 5):**
- ❌ `CombatSubscriber` пишет `EmotionPayload` (Rule 9).
- ❌ `shock_impulse` без decay (Rule 28).
- ❌ `hp <= 0` как смерть (Rule 38).
- ❌ Мёртвый игрок действует (Rule 59).
- ❌ Чтение `pain`/`fatigue` без `/100.0` (Rule 63/64).
- ❌ Прямая запись в `state.hp` (ADR-HP-UNIFICATION).

---

## 6. 🔗 МУТАЦИЯ И ЭМОЦИИ (State Mutation & Affective)

**Поток:** Payloads → `DeltaBuffer` → `AffectiveIntegrator` → `EmotionPayload`

### 📦 `DeltaDomain`
- 📁 `mod/state_delta.py`
- Enum: `PHYSIOLOGY`, `EMOTION`, `SOCIAL`, `PERCEPTION`, `IDENTITY`, `SPATIAL`.

### 📦 Payload DTOs
- 📁 `mod/delta_payloads.py`
- **`PerceptionPayload`:** `threat_gradient_delta`, `uncertainty_delta`, `anomaly_score_delta`.
- **`EmotionPayload`:** Порождается ТОЛЬКО после фазового перехода (Фаза 9).
- **`IdentityPayload`:** `compliance_bias_delta`, `initiative_suppression_delta`.
- **`ReputationPayload`:** Дельта репутации (VillageMemoryField).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 6):**
- ❌ Обход `AffectiveIntegrator` (§2.1, §3.9).
- ❌ `TICK_CATCHUP` (Rule 16).
- ❌ Смешивание эмоционального остатка с физиологией (ADR-O-206).

---

## 7. 🔗 ЭПИСТЕМИЧЕСКИЙ СЛОЙ (Epistemic Core — S188-S201) ⭐ НОВОЕ

**Поток:** `COMMUNICATION_CLAIM` → `ClaimEvent` → `EpistemicRecord` → `EpistemicContext` → `epistemic_modifiers` → `DecisionHub`

### 📦 `Proposition`
- 📁 `dom/epistemology.py`
- **Семантическое ядро утверждения.** Enum-структура: `STOLE`, `HELPED`, `ATTACKED`, `BETRAYED`, `PRAISED`, `WARNED`.
- 🚫 **ЗАПРЕТ:** Proposition как World Truth.

### 📦 `ClaimEvent`
- 📁 `dom/epistemology.py`
- **Событие утверждения.** Поля: `speaker_id`, `listener_id`, `proposition`, `target_id` (о ком), `confidence`, `tick`.
- Преобразуется из `EventDTO` через `ClaimEventSubscriber`.

### 📦 `EpistemicRecord`
- 📁 `dom/epistemology.py`
- **Субъективное убеждение в EpistemicStore.** Поля: `proposition`, `confidence` (0-1), `source_id`, `last_updated_tick`, `provenance` (chain of claims).
- 🚫 **ЗАПРЕТ:** `confidence` как `truth_probability`; Отрицательный `confidence` (защита `max(0.0)`).

### 📦 `EpistemicContext`
- 📁 `dom/epistemology.py`
- **Изолированный контекст для DecisionHub.** Поля: `perceived_claims`, `perceived_beliefs`, `max_confidence`. Формула `to_modifiers()` использует `max_confidence * 0.992`.
- 🚫 **ЗАПРЕТ:** Хранение World Truth; `perceived_*` поля заменяются на факты.

### 📦 `EpistemicStore`
- 📁 `svc/npc/epistemic_store.py`
- **Per-agent хранилище убеждений.** Методы: `record_claim`, `get_beliefs`, `to_dict` / `from_dict` (round-trip, S193).
- 🚫 **ЗАПРЕТ:** Глобальный store (только per-agent); DELETE операции.

### 📦 `BeliefModifierResolver` / `BeliefRevisionEngine`
- 📁 `svc/npc/belief_revision_engine.py`
- **Pure function ревизии.** Принимает `ClaimEvent` → обновляет `EpistemicRecord`.
- **Trust-Based Reliability (S199):** При `trust < -30` → обратный эффект (confidence падает).
- 🚫 **ЗАПРЕТ:** `max(0.0)` guard только для update (S201 fix: применять и для create).

### 📦 `COMMUNICATION_CLAIM`
- 📁 `svc/events/event_types.py`
- **EventType для передачи Proposition** через `EventBus`. Не содержит текста.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Epistemic Core):**
- ❌ `ClaimEvent` мутирует World State (ADR-O-354).
- ❌ `EpistemicRecord` хранит факты — только субъективность.
- ❌ Proposition мутирует `RelationshipStore` напрямую.
- ❌ `DecisionHub` читает `EpistemicStore` (только `Dict[str, float]`).
- ❌ L1 Chronicle хранит субъективные убеждения.
- ❌ Модификаторы с побочными эффектами / не коммутативные (ADR-O-355).
- ❌ Мутация входного `scores` в `apply_modifiers`.
- ❌ SUPERBOX инъецирует Belief/Relationship напрямую.

---

## 8. 🔗 ИДЕНТИЧНОСТЬ И ОНТОЛОГИЯ (Identity Layer & Chronicle)

**Поток:** L0 + L1 → L1.5 (PatternDetector) → L2.5 (Belief Engine) → L3 (EffectiveDrives)

### 📦 `TraitDriftEvent`
- 📁 `dom/identity_events.py`
- **Запись давления в L1 Chronicle** (ADR-O-208). Поля: `tick_id`, `target_id`, `source_id`, `effect_value`, `observation_weight`, `event_type`. Immutable.

### 📦 `EvidenceOfPersistence`
- 📁 `dom/identity_events.py`
- **Агрегированная статистика (L1.5).** `source_id`, `cumulative_effect`, `behavior_variance`. Чистая математика, без психологии.

### 📦 `CrystallizedBelief`
- 📁 `dom/identity_events.py`
- **Психологическая проекция (L2.5).** `source_id`, `trait`, `weight` (0-1), `last_updated_tick`.
- **ADR-O-306/307:** Асимметричная травма (x6) для опровержений.

### 📦 `LifeProject` / `IdentityPressureVector`
- 📁 `svc/npc/life_project_resolver.py`
- **FSM идентичности (L2.7).** Управляется Identity Pressure Vector.
- 🚫 **ЗАПРЕТ:** Мгновенная смена; Бусты в `LOST`/`SEARCHING`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 8):**
- ❌ Удаление из `L1Chronicle` (Rule 28, append-only).
- ❌ Кэширование L3 (ADR-O-208, эфемерность).
- ❌ Фоллбэк на L0 в `InterpretationEngine`.
- ❌ Скалярный `identity_crisis` вместо Pressure Vector.

---

## 9. 🔗 ПРЕЗЕНТАЦИЯ И UI (Presentation & Frontend)

**Поток:** Runtime → `WorldSnapshotDTO` → 3-Channel DTOs → Фронтенд

### 📦 `WorldSnapshotDTO`
- 📁 `dom/snapshot.py`
- `npc_positions` (Dict[str, NPCPositionDTO]), `active_traversals`, `avatar_state`, `ambient_phenomenology`, `player_body_topology`, **`perceived_narratives`** (S158), `visual_dto`, `audible_dto`.

### 📦 3-Channel Presentation (S147, ADR-O-331)
- 📁 `dom/presentation.py`
- **`VisualDTO`:** `Tuple[NPCVisualState, ...]`.
- **`AudibleDTO`:** `Tuple[VoiceAudio, ...]`, `Tuple[BreathingAudio, ...]`.
- **`NarrativeDTO`:** Текстовая проекция.
- 🚫 **ЗАПРЕТ:** Зависимость каналов друг от друга (Visual First).

### 📦 `BodyTopology` / `Item` / `BodySlot` (S147)
- 📁 `dom/body.py`
- **D&D 5e Encumbrance.** `BodyTopology`: слоты (hands, belt, pockets, backpack, worn, hidden) + contents.
- **`Item`:** `item_id`, `name`, `weight`, `bulk`, `value`, `item_type`, `properties`.
- **`BodySlot`:** `slot_id`, `slot_type`, `body_part`, `capacity`, `max_bulk`, `concealment`.

### 📦 `AvatarStateDTO` / `PlayerPerceptionDTO`
- 📁 `dom/snapshot.py`
- **Avatar:** Непрерывные скаляры + `life_status`.
- **Perception:** `embodied_traces`, `peripheral_cues`, `manifestations`, `active_perceptions`, `avatar_desync`.

### 📦 `ManifestationDTO` / `EmbodiedTraceDTO`
- 📁 `dom/snapshot.py` / `dom/embodied_trace.py`
- **Наблюдаемое проявление NPC.** `npc_id`, `tags` (List[str]). НЕ эмоция!
- Моторный след: `instability`, `micro_pause`, `action_interruption`.

### 📦 `NPCVisualState`
- 📁 `dom/presentation.py`
- `npc_id`, `display_name`, `name_certainty`, `pose_overlay`, `gaze_arrow`, `blur_intensity`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 9):**
- ❌ Телепатия в UI (Rule 11).
- ❌ DM читает внутренние состояния напрямую (Rule 23).
- ❌ Показ эмоций (Rule 35) — только проявления (tense, rigid).
- ❌ Смешивание cues и manifestations (Rule 36).

---

## 10. 🔗 СОЦИАЛЬНЫЙ СЛОЙ И END-SCREEN (Social & Fate) ⭐ НОВОЕ

**Поток:** `NPC_SPOKE` → `SocialSubscriber` → `RelationshipStore` → `FateTracker` → `EndScreenData`

### 📦 `CausalEmissionPacket` / `CausalPressureVector` (ADR-O-209/210)
- 📁 `dom/causal_state_vector.py`
- **CFL излучение.** `npc_id`, `position`, `pressure_vector` (5D: fear, control, significance, desire, volatility), `decay_radius`, `signature_hash`.
- 🚫 **ЗАПРЕТ:** Прямая интерференция метрик агентов; CFL как персистентное состояние.

### 📦 `FateTracker` / `FateOutcome` (S198)
- 📁 `svc/social/mvp_tavern_controller.py`
- **Отслеживание судеб NPC.** `FateOutcome`: `ALIVE`, `DEATH`, `ESCAPE`, `BROKEN` (5 тиков CRITICAL подряд, S199).
- Поля: `stability` (связано со `stress`), `threat` (связано с `threat_gradient`).

### 📦 `EndScreenData` / `EndScreenDataBuilder` (S198)
- 📁 `mod/end_screen.py`
- **Финальный нарратив.** Поля: `verdict_text`, `fate_texts` (List[str]), `relationship_texts`, `stats`.
- Генерируется `EndScreenNarrator` из production-данных (без ручных инъекций).

### 📦 `SocialDelta` / `RelationshipUpdate`
- 📁 `svc/social/relationship_store.py`
- **SSOT отношений (0-100).** Детерминированные триггеры (S199): gossip (-2.0), accuse (+1.0 fear), praise (+1.5 trust).
- 🚫 **ЗАПРЕТ:** `relationship_cache` в `NPCState`; Ручные инъекции.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 10):**
- ❌ Ручные инъекции отношений в End-Screen.
- ❌ Игнорирование `trust < -30` в reliability.
- ❌ `FateTracker` без `_critical_ticks` счётчика.

---

## 11. 🔗 ТИК-ОРКЕСТРАЦИЯ И МУТАЦИИ (Tick Orchestration)

### 📦 `TickState`
- 📁 `dom/tick.py`
- **Иммутабельный снимок.** Preloaded блоки: `memory_weights_map`, `narrative_cache_map`, `social_modifiers_map`, `reputation_modifiers_map`, `economic_profiles_map`, `crystallized_beliefs_map`, `identity_traits_map`.
- Read-only сервисы: `relationship_store`, `spatial_service`, `spatial_query`.

### 📦 `TickMutation`
- 📁 `dom/tick.py`
- **Чистый результат Pipeline.** `npc_deltas`, `communication_intents`, `movement_intents`, `l1_drift_events`, `memory_events`, **`scores_trace_map`** (S190, telemetry).

### 📦 `TickResultDTO` / `GameActionResponse`
- 📁 `dom/tick.py` / `svc/game_loop/__init__.py`
- **Ядро:** `status`, `world_snapshot`, `npc_contexts`, `final_scene_state`.
- **GameLoop:** `dm_response`, `world_snapshot`, `will_conflict_data`. Возвращается как `dict` (ADR-161).

### 📦 `DRFBus` / `DRFExecutionContext` / `TickContext`
- 📁 `svc/drf_bus.py` / `svc/dto.py`
- Шина каузального арбитража (ADR-134) + scoped ledger (ADR-136).
- **`_TickContext`:** `@dataclass` (критично, S84), содержит `hub_event`, `rng_factory`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Секция 11):**
- ❌ `TickPlayerResultDTO` из ядра.
- ❌ `movement_intents` покидают ядро.
- ❌ `_TickContext` без `@dataclass` (idle pipeline dies).

---

## 12. 🔗 СПЕЦИФИКАЦИИ СОБЫТИЙ (Event Types Registry)

**📁 `svc/events/event_types.py`**

| EventType | Источник | Payload |
|-----------|----------|---------|
| `NPC_SPOKE` | DialogueMaterializer | `speaker_id`, `intent_type`, `proposition` |
| `NPC_MOVED` | MovementEngine | `from_node`, `to_node`, `distance` |
| `PROXIMITY` | SpatialQuery | `distance`, `other_id` |
| `COMBAT_HIT` | ImpactEngine | `damage`, `contact_level` |
| `COMMUNICATION_CLAIM` | ClaimEventSubscriber | `Proposition` (нормализованная) |
| `DREAM` / `NIGHTMARE` | DreamGenerationService | `DreamSignal` |
| `OFFER_JOB` / `REQUEST_SERVICE` / `SPREAD_RUMOR` | IntentEventAdapter | Коммуникативные интенты |
| `CALL_FOR_HELP` / `CHANGE_ROLE` / `WARN` | IntentEventAdapter | Социальные интенты |
| `TRADE` / `REPORT` | IntentEventAdapter | Экономические/инфо-интенты |

🚫 **ЗАПРЕТЫ:**
- ❌ Использование сырых строк вместо `EventType` enum.
- ❌ Новые `CommunicationIntent` без регистрации в `IntentEventAdapter._INTENT_EVENT_MAP`.
- ❌ `unknown` / `npc_spoke` fallback для известных интентов (ADR-O-349).

---

## 🧪 СПИСОК ПЕСОЧНИЦ (Fail Conditions)

Каждый запрет из этого реестра должен быть покрыт тестом. Ключевые инварианты:

### Foundation & Runtime
- `test_no_direct_mutation_of_position` (Rule 1)
- `test_no_direct_scene_change_in_resolver` (Rule 4)
- `test_pressure_modifies_utility_not_commands` (Rule 6 / L2)
- `test_willpower_gate_single_invocation_per_tick` (Rule 8)
- `test_l1_chronicle_append_only` (Rule 28, ADR-O-208)
- `test_l3_ephemeral_invariant` (ADR-O-211 / IMMUNE-001)
- `test_kernel_rng_determinism` (ADR-O-301)
- `test_no_global_random_in_kernel` (ADR-O-301)
- `test_decision_hub_requires_rng` (ADR-O-301)
- `test_ontology_violation_kills_tick_on_nan` (ADR-O-207)

### Perception & Epistemic
- `test_no_telepathy_in_ui_observation` (Rule 11)
- `test_perceptual_kernel_survives_legacy_roundtrip` (Rule 31, ADR-115)
- `test_telepathy_epistemic_barrier` (S158)
- `test_epistemic_modifier_attribution` (S190, SUPERBOX-005)
- `test_epistemic_isolation` (S191, SUPERBOX-006)
- `test_epistemic_observation_divergence` (S192, SUPERBOX-007)
- `test_epistemic_membrane_hardening` (S192.1, SUPERBOX-008)
- `test_epistemic_persistence` (S193, SUPERBOX-009)
- `test_epistemic_decision_divergence` (S194, SUPERBOX-010)
- `test_epistemic_action_causation` (S195, SUPERBOX-011)
- `test_epistemic_world_event` (S196, SUPERBOX-012)
- `test_epistemic_second_order` (S198, SUPERBOX-013)
- `test_epistemic_player_belief` (S201, SUPERBOX-014)
- `test_epistemic_runtime_closure` (S201, SUPERBOX-015)

### Body & Physiology
- `test_somatic_urgency_modulated_by_willpower` (ADR-O-143)
- `test_manifest_tags_not_emotions` (ADR-O-147)
- `test_player_body_state_survives_save_load` (Rule 54/55, ADR-128)
- `test_hp_double_truth_invariant` (ADR-HP-UNIFICATION, S86)
- `test_effective_drives_not_cachable` (ADR-O-208)

### Spatial & Traversal
- `test_movement_processed_once` (Rule 18, ADR-066)
- `test_bridge_includes_active_traversals` (Rule 21, ADR-071)
- `test_boundary_node_not_movement_goal` (ADR-145)
- `test_apply_changes_does_not_overwrite_active_traversal` (ADR-130.1)
- `test_apply_changes_snaps_position_on_traversal_complete` (ADR-130.2)
- `test_life_engine_skips_moving_npcs` (ADR-154)
- `test_spatial_factory_used` (ADR-TZ04-4)

### Identity & Beliefs
- `test_trait_drift_event_contract_no_legacy_fields` (ADR-O-208.1)
- `test_pattern_detector_math_correct` (ADR-O-305A)
- `test_asymmetric_trauma_x6` (ADR-O-307)
- `test_belief_decay_model` (ADR-O-305.1)
- `test_belief_engine_no_direct_l1_read` (ADR-O-305)

### Infrastructure
- `test_drf_bus_instance_level_not_default_factory` (Rule 73, ADR-134)
- `test_drf_pipeline_receives_execution_context_not_bare_bus` (Rule 76, ADR-136)
- `test_drf_scoring_additive_not_clamp` (Rule 80, ADR-135)
- `test_no_zombie_readers` (ADR-TZ04-1)
- `test_no_random_uniform_in_apply_change` (ADR-TZ04-2)
- `test_metadata_scene_change_routing` (ADR-TZ04-5)
- `test_no_print_in_movement_engine` (ADR-TZ6-1)
- `test_willstate_single_definition` (ADR-TZ6-1)
- `test_no_silent_failures_in_tick_orchestrator` (ADR-TZ6-1)

---

*Версия: 8.0 (Unified & Expanded)*
*Сессия: S201 | Epistemic Core (S188-S201) полностью интегрирован*
*Файлов DTO: 80+ | Инвариантов в IPT: 39/39*
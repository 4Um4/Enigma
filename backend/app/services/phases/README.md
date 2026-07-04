# Директория `phases/` — Контракты Фаз Тик Оркестратора

Эта директория содержит модули, инкапсулирующие бизнес-логику фаз симуляции (Тик Оркестратора). 
Оркестратор (`tick_orchestrator.py`) выступает в роли тонкого диспетчера, делегируя выполнение тяжёлой логики этим модулям.

**Главное правило:** Импорты внутри модулей должны быть отложенными (lazy imports), чтобы избежать циклических зависимостей.

---

## Список Модулей и Контракты

### 1. `simulation.py` (Фаза 0: Симуляция жизни)
- **Назначение:** Вызов `LifeEngine.tick()`, обработка пространственных изменений (инъекция `SceneChange`).
- **Вход:** `_TickContext` (содержит `all_npcs_raw`, `scene_state`, `spatial_service`).
- **Выход:** Мутация `ctx.all_npcs_raw` (генерация интентов, дельт), заполнение `ctx.delta_buffer`.
- **Инварианты:** 
  - Запрет на прямую мутацию позиций (ADR-051).
  - Мёртвые NPC исключаются до Фазы 1 (ADR-S93.1).
  - NPC в статусе `MOVING` не генерируют новые интенты (ADR-154).

### 2. `idle_services.py` (Фаза 0.5: Затухание в простое)
- **Назначение:** Time-decay для `PerceptualKernel`, `DynamicAffordanceField` (purge/decay), `ExpectationStore` (PE Decay), `AffectiveDecayHandler`.
- **Вход:** `_TickContext`, экземпляры сервисов затухания.
- **Выход:** Мутация `ctx.delta_buffer` (отрицательные дельты для衰减).
- **Инварианты:**
  - `affective_load` использует асимметричный аттрактор (гистерезис), не интегратор с утечкой (ADR-138).
  - `shock_impulse` обязательно затухает (ADR-109).

### 3. `input.py` (Фаза 1: Ввод и Воля)
- **Назначение:** Обработка `InterventionEvent`, маршрутизация, `WillpowerGate` (Cumulative Strain Model), Affective Resonance.
- **Вход:** `_TickContext` (с `interventions`).
- **Выход:** `IntentPressureProfile`, `AmplifiedPressureProfile`, `WillResponseDTO`, заполнение `ctx.delta_buffer` (например, `stress_delta`).
- **Инварианты:**
  - `WillpowerGate` вызывается строго 1 раз за цикл (Rule 8).
  - `semantic_action` читается с fallback (ADR-083).
  - Somatic Gate: проверка `shock > 0.7` ДО семантического парсинга (ADR-O-139).

### 4. `decision.py` (Фаза 5: Принятие решений)
- **Назначение:** Предзагрузка данных (`TickState`), вызов Pure Reducer (`NpcTickPipeline.run()`), применение `TickMutation`.
- **Вход:** `_TickContext`, `TickState` (immutable snapshot).
- **Выход:** `TickMutation` (deltas, intents, pending_io), мутация `ctx.all_npcs_raw`.
- **Инварианты:**
  - `DecisionHub` работает на консолидированном восприятии прошлого тика (T-1).
  - Viability Pre-Generation Gate: ROUTINE исключается до генерации интентов при угрозе (ADR-O-137).
  - `L2.5 Beliefs` инжектируются как `drive_modifiers` (ADR-O-305).

### 5. `post_decision.py` (Фазы 6, 7: Адаптация интентов и Windup)
- **Назначение:** `IntentEventAdapter` (`CommunicationIntent` → `EventDTO`), `WindupWriteGate` (перехват ATTACK для создания `ActionWindup`).
- **Вход:** `ctx.communication_intents`, `ctx.windup_registry`.
- **Выход:** Публикация `EventDTO` на `EventBus`, создание/обновление `ActionWindup`.
- **Инварианты:**
  - `IntentEventAdapter` — единственная точка превращения решения в событие (Устав §3.3).
  - Публикация EventDTO атак с windup происходит только в Фазе 7 (ADR-O-310).

### 6. `reduction.py` (Фаза 8: Многоступенчатая редукция)
- **Назначение:** Layered Reduction (Physical → Materialization → Cognitive → Social). Обработка `EventDTO` подписчиками (`CombatSubscriber`, `ReactionSubscriber`).
- **Вход:** `ctx.delta_buffer`, события с `EventBus`.
- **Выход:** Дельты физиологии, восприятия, эмоций (через `DeltaBuffer`).
- **Инварианты:**
  - `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload` (Rule 9).
  - Прямая генерация эмоций из боевых событий запрещена (только через Perception).

### 7. `integration.py` (Фаза 9: Интеграция и Снапшот)
- **Назначение:** CFRM P2 (`LocalCausalSolver`), L2.5 Belief Crystallization, сборка `WorldSnapshotDTO` + `AvatarStateDTO`.
- **Вход:** `_TickContext`, финальное состояние NPC.
- **Выход:** `ctx.perception_snapshot`, обновление `CrystallizedBeliefStore`.
- **Инварианты:**
  - `MemoryManager.check_identity_promotion` работает только при наличии `phase_2_events` (ADR-S86.7).
  - Эпистемический барьер: DM-агент не читает внутренние состояния NPC (ADR-TZ08-4).

### 8. `affective.py` (Фаза 9.1: Аффективный пайплайн)
- **Назначение:** Вычисление интеграла аффекта (`AffectiveIntegrator`), фазовый переход эмоций (`EmotionTransition`).
- **Вход:** `ctx.all_npcs_raw` (поля `perceptual_kernel`, `affective_load`).
- **Выход:** `EmotionPayload` в `ctx.delta_buffer`.
- **Инварианты:**
  - Эмоции не генерируются из одного события. Они рождаются из интеграла угрозы по времени (ADR-049).
  - `Anti-DOUBLE TRUTH bootstrap` при `emotion != NEUTRAL` но `affective_load < threshold` (ADR-117).

### 9. `motion.py` (ETKE-IK: Непрерывное движение)
- **Назначение:** Обработка `DriveVector` (микро-перемещения). `CollisionAvoidance`, `SteeringResolver`, `MotionIntegrator`.
- **Вход:** `ctx.all_npcs_raw` (поле `drive_vector`), `WorldTopologyProvider`.
- **Выход:** Обновление `local_position` и `velocity` в `ctx.all_npcs_raw`.
- **Инварианты:**
  - `DriveVector` эфемерен: очищается при каждом `tick_decisions` (L3-P1).
  - FLEE через `DriveVector` использует инвертированный `direction` (ADR-ETKE-ACT1).
  - `SOCIAL_DRIFT` используется вместо рандомного `PATROL` (ADR-S91).

### 10. `traversal.py` (Macro-traversals и Shadow Observer)
- **Назначение:** Обработка `MovementIntent` (макро-перемещения). `EventCompiler`, `ProjectionEngine`, `EquivalenceValidator` (Dual Rail).
- **Вход:** `ctx.movement_intents`, `ctx.scene_state`.
- **Выход:** `ThickSceneChange`, мутация `active_traversals` в `scene_state`.
- **Инварианты:**
  - `apply_changes` не может перезаписать активный транзит (`status="MOVING"`) (ADR-130.1).
  - `EventCompiler` не создаёт `TraversalContract` со статусом `COMPLETED` (ADR-O-201.4).
  - `EquivalenceValidator` отключен для кросс-локационных переходов (ADR-O-201.2).

### 11. `validation.py` (Валидация дрейфа)
- **Назначение:** Dual Rail Drift Validation. Сравнение применения физики через Legacy (`scene_manager.apply_changes`) и Shadow (`EventCompiler`).
- **Вход:** `snapshot`, `thick_changes`, `scene_state`.
- **Выход:** Логирование дрейфа (DRIFT A-E), вызов `OntologyViolationError` при критических разрывах.
- **Инварианты:**
  - Shadow Observer только наблюдает и логирует, не вмешиваясь в каузальный поток (Устав §11.2).
  - Проверка `sum(drives)==1.0`, bounds, NaN (ADR-O-207).

# ADR-O-142 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs\Tasks\ADR (Architecture Decision Records).md`

## Суть
Двухуровневая модель сознания NPC. Consciousness FSM (SLEEPING/AWAKE/UNCONSCIOUS/DEAD) + Behavior Layer (routine/activity_overrides/schedule).
Arousal Gate = единственный мутатор FSM, стоит ДО schedule resolution в LifeEngine.
State Resolution Binding = Phase 7.5 в TickOrchestrator — синхронизирует FSM + behavior → scene_state.activity.
Оживлён мёртвый pipeline activity_overrides → scene_state_manager.update_npc_position().

## Changed Domains
- Consciousness (FSM — новый слой)
- Will/Decision (wake_pressure агрегатор)
- Physiology (pain → wake, shock → unconscious)
- Perception (perception_filter корректно работает с заполненным activity)
- Spatial/Scene (activity в scene_state обновляется рантайм)
- Frontend (визуализация состояния NPC)

## Downstream Consumers
- perception_filter._npc_is_conscious() — читает activity из scene_state
- reaction_priority._is_incapacitated() — читает state/status/conditions
- scene_renderer — визуализация сна/работы/движения
- game_screen — tooltip, иконки сна
- dm_agent — контракт на описание спящих NPC
- TickOrchestrator — применяет activity_overrides к scene_state (Phase 7.5)
- LifeEngine._simulate_major — Arousal Gate ДО schedule resolution

## Изменённые файлы (8)

### 1. backend/app/models/npc_state.py
- Новое поле: `consciousness_state: str = "AWAKE"` (SoR для FSM)
- `can_awaken: bool` → DEPRECATED, заменён на wake_pressure
- `write_to_legacy` / `from_legacy` — сериализация consciousness_state

### 2. backend/app/services/npc/life_engine.py
- `_simulate_major`: Arousal Gate ДО schedule resolution
- `_compute_wake_pressure(npc)` — агрегатор (threat + pain + directive + acoustic)
- `_compute_sleep_resistance(npc)` — инерция сна (fatigue + base + depth)
- При SLEEPING→AWAKE: `routine["current"] = "awake"`, activity_override генерируется
- При *→UNCONSCIOUS: `consciousness_state = "UNCONSCIOUS"`

### 3. backend/app/services/tick_orchestrator.py
- Phase 7.5: STATE RESOLUTION BINDING перед apply_changes
- Применение activity_overrides к scene_state через scene_state_manager.update_npc_position()
- Idle-путь: routine["current"] → activity binding аналогично

### 4. backend/app/services/scene_state_manager.py
- update_npc_position() — оживлён (был мёртвый метод)
- _enrich_local_positions — обогащение activity из all_npcs_raw при наличии

### 5. backend/app/services/npc/npc_tick_contracts.py
- _INTENT_TO_ACTIVITY: добавлены "WAKE" → "awake", "SLEEP" → "sleeping"

### 6. backend/app/services/npc/npc_tick_pipeline.py
- При APPROACH/FLEE после Arousal Gate: activity_overrides[npc_id] = "awake"
- Передача consciousness_state в VerbalizationContext

### 7. backend/app/services/npc/perception_filter.py
- _npc_is_conscious() теперь читает consciousness_state, не только activity

### 8. backend/app/services/npc/reaction_priority.py
- _is_incapacitated() проверяет consciousness_state

## Runtime Impact
- +0.1ms tick (wake_pressure computation per NPC)
- +0.05ms tick (activity binding в Phase 7.5)
- +0 bytes RAM/NPC (wake_pressure вычисляется, не хранится)

## Rollback
1. Удалить вызов _compute_wake_pressure из LifeEngine
2. Удалить Phase 7.5 из TickOrchestrator
3. activity_overrides возвращаются в мёртвое состояние (статус-кво до S78)
4. consciousness_state поле остаётся (default "AWAKE" = статус-кво)

## Sandbox Tests
- test_wake_pressure_overcomes_sleep
- test_no_wake_without_cause
- test_activity_overrides_applied_to_scene_state
- test_perception_filter_respects_awake_activity
- test_sleeping_npc_wakes_on_pain
- test_sleeping_npc_wakes_on_directive
- test_unconscious_cannot_be_woken_by_directive
- test_consciousness_state_survives_legacy_roundtrip
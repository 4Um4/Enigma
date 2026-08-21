# ENIGMA — CLOSURE CONTRACT v8.6

**Дата:** 2026-08-01 (v8.6 аудит)
**Версия:** V.0.5.3.6.6
**Цель:** Полностью работоспособный MVP «Секреты Люси» — End-Screen показывает >0 secrets после признания NPC, NPC спят, редактор карт валидирует cross-loc, диалоги — не монологи, fate_states > 0.

**Принцип v8.6:** Только активные баги V.0.5.3.6.6. Старые ошибки не упоминаются. Этот документ — TODO list того, что нужно сделать в текущей версии.

**Что нового в v8.6 (аудит 2026-08-01):**
- **18 НОВЫХ багов** найдено (3 CRITICAL, 8 HIGH, 7 MEDIUM/LOW), не описанных в v8.5
- Глубокий аудит: 5 параллельных агентов прочли ключевые исходники V.0.5.3.6.6: `tick_orchestrator.py`, `npc_tick_pipeline.py`, `life_engine.py`, `movement_engine.py`, `graph_compiler.py`, `mvp_tavern_controller.py`, `npc_confession_parser.py`, `truth_state.py`, `truth_state_loader.py`, `action_semantic_resolver.py`, `npc_orchestration.py`, `dialogue_executor.py`, `dialogue_materializer.py`, `npc_dialogue_subscriber.py`, `social_input_projector.py`, `event_bus.py`, `event_types.py`, `decision_hub.py`, `break_progress_engine.py`, `calibration_engine.py`, `phases/decision.py`, `phases/input.py`, `phases/memory.py`, `phases/post_decision.py`, `memory_manager.py`, `working_memory_tick.py`, `promotion_engine.py`, `crystallized_belief_store.py`, `l1_chronicle.py`, `perception_filter.py`, `will.py`, `player_avatar_service.py`, `scene_state_manager.py`, `local_traversal_planner.py`, `event_compiler.py`, `spatial_registry_builder.py`, `editor_core.py`, `data_manager.py`, `campaign_manager.py`, `npc_state.py`, `dto.py`, `character_filter_applicator.py`, `character_service.py`, `spatial_factory.py`, `spatial_registry.py`, `dm_agent.py`, `drive_resolver.py`, `relationship_store.py`, `truth_state_tavern.json`, `market_square.json`, `city_gate.json`, `tavern.json`

---

## §0. СТАТУС ВЕРСИИ

**Текущая:** V.0.5.3.6.6
**v8.6 NEW findings:** 18 новых багов
  - 3 CRITICAL
  - 6 HIGH
  - 5 MEDIUM
  - 4 LOW
**Главный блокер (v8.6 NEW):** V8-MVP-21 — `LifeEngine.update_idle_pressure` сбрасывает `_spatial_service`/`_persistence`/`_claim_bus` на каждом тике → все consumer'ы после Phase 5 видят `None`.
**Главный блокер identity (v8.6 NEW):** V8-MEM-14 — `detect_resonance` вызывается без `npc_id` → `TypeError` → весь L3 identity pipeline тихо мёртв.
**Главный блокер psyche (v8.6 NEW):** V8-PSY-26 — `personality_from_legacy` не загружает `identity_rigidity`/`gregariousness` → всегда 0.5 для всех NPC.
**Дней работы осталось:** ~4-5 дней (18 новых багов на исправление)

---

## §0.5. СВОДКА v8.6 АУДИТА (НОВОЕ)

### ➕NEW — баги, найденные в v8.6 аудите и не описанные в v8.5

| Баг | Серьёзность | Файл | Суть |
|---|---|---|---|
| V8-MVP-21 | ★★★ CRITICAL | `life_engine.py:246-258` | `_spatial_service`, `_persistence`, `_claim_bus` инициализируются ВНУТРИ `update_idle_pressure`, а не в `__init__`. Каждый тик сбрасывает их на None. |
| V8-MEM-14 | ★★★ CRITICAL | `working_memory_tick.py:122`, `phases/memory.py:117` | `detect_resonance(campaign_id, actor_id="player")` вызывается БЕЗ обязательного `npc_id` → `TypeError` → весь L3 identity pipeline тихо мёртв. |
| V8-PSY-26 | ★★★ CRITICAL | `npc_state.py:1073-1103`, `break_progress_engine.py:211`, `life_engine.py:765`, `npc_tick_pipeline.py:433` | `personality_from_legacy` НЕ загружает `identity_rigidity`/`gregariousness` из psyche dict. Поля всегда 0.5 для всех NPC. Plasticity/social homeostasis отключены. |
| V8-PSY-27 | ★★ HIGH | `phases/decision.py:204-211` | V8-PSY-6 hydration итерирует `Dict[str, Dict[str, float]]` как список объектов → `_r.target_id` → `AttributeError: 'str' object has no attribute 'target_id'`. Crashes BehaviorMask для всех NPC с relationships. |
| V8-TICK-8 | ★★ HIGH | `tick_orchestrator.py:1570-1573` | DRF overlay фильтрует по `hasattr(_intent, "npc_id")`, но `CommunicationIntent` имеет `speaker`/`audience`, не `npc_id`. Все verbal intents тихо пропускаются. V8-TICK-2/7 fix — wiring есть, но реально не работает. |
| V8-TICK-9 | ★★ HIGH | `tick_orchestrator.py:1223` | `_compute_effective_drives` использует `self.memory_manager` (нет такого attr, есть `self._memory_manager`) и `ctx.campaign_id` (нет `ctx` в сигнатуре функции) → `AttributeError`+`NameError`, swallowed `except Exception: pass` → V8-PSY-9 FIX — dead code, `_identity_l1` всегда None. |
| V8-TICK-10 | ★★ HIGH | `npc_tick_pipeline.py:818` | `create_memory_event` вызывает `memory_manager.apply(...)` на `None` (pipeline передаёт `None` для ADR-TZ09-1) → `AttributeError: 'NoneType' object has no attribute 'apply'`. Memory events для `npc_interacts_npc`, `player_interacts`, TALK/TRADE/HELP/ATTACK/FLEE/GIVE/ASK/THREATEN silently не сохраняются. |
| V8-MEM-15 | ★★ HIGH | `crystallized_belief_store.py:97-115` | `update_beliefs` делает `DELETE` + N `INSERT` без transaction. Crash mid-loop → beliefs удалены, но не вставлены. Подтверждено в production logs: `Failed to save beliefs for thief_shadow`, `cannot commit - no transaction is active`. |
| V8-PSY-28 | ★ MEDIUM | `npc_state.py:1073-1103` | `personality_from_legacy` не парсит `willpower`, `identity_rigidity`, `gregariousness`, `gregariousness` → все personality-driven трейты всегда 0.5/50.0. |
| V8-WL-6 | ★ MEDIUM | `dto.py:158-160`, `phases/input.py:99-103` | `player_pressure` объявлен как SSOT, но никогда не присваивается в production → всегда `None` → `resolve_intent_pressure` вызывается повторно, нарушая ADR-031 causal integrity. |
| V8-WL-7 | ★ MEDIUM | `player_avatar_service.py:343` | `WillState(data.get("will_state", "free"))` без try/except. Любое некорректное значение (uppercase, legacy) → `ValueError` → crash avatar load. `_emotion_from_str` имеет safe wrapper, `BehaviorMaskState` тоже — `WillState` нет. |
| V8-ED-5 | ★ MEDIUM | `editor_core.py:879` | `campaign_id = self.dm.base_dir.parent.name` возвращает `"map_editor"` когда campaign не открыта → `SpatialCompilationGateway.request_rebuild("map_editor")` — wrong campaign_id. |
| V8-PSY-29 | ★ MEDIUM | `calibration_engine.py:32-66`, `tick_orchestrator.py:1212-1244` | `CalibrationEngine` instantiated в orchestrator, но `.stabilize()` НИКОГДА не вызывается. `ctx.drives_updates` и `ctx.strain_updates` всегда `{}`. `strain_memory` не накапливается. L3 calibration pipeline — dead code. |
| V8-SP-23 | ★ MEDIUM | `life_engine.py:531-552` | V8-SP-19 FIX НЕ применён — нет `if "exit_" not in _ss_pos:` guard. Boundary nodes (`tavern:exit_east`) при пост-materialize `location_id="city_gate"` перетирают корректный `city_gate` на `tavern`. Split-brain persists. |
| V8-SP-24 | ★ MEDIUM | `movement_engine.py:718-738` | V8-SP-16 FIX НЕ применён — нет `NodeRole.BOUNDARY` check перед `if _dist < 0.1:`. Micro_snap fires unconditionally для BOUNDARY nodes. NPC может застрять у boundary. |
| V8-SP-25 | ★ MEDIUM | `market_square.json` adjacency | `market_square.east = "city_gate"`, но `city_gate.west = "tavern"` (НЕ market_square). Reciprocity нарушена. Plus 2.5 m² overlap с tavern остался. |
| V8-MEM-16 | ★ MEDIUM | `memory_manager.py:835-836`, `layered_memory.py:73-92` | `_identity_cache` сохраняется в JSON (не SQLite) на каждый `apply_identity_weights()` call. Нет lock → race condition. Полный rewrite файла на каждый trait delta — perf issue. |
| V8-PSY-30 | ★ MEDIUM | `perception_filter.py:216-225` | `sound_events` set — uppercase `{"SOUND_EMITTED", "PLAYER_SPOKE", ...}`. `EventType.NPC_SPOKE = "npc_spoke"` (lowercase) → never matches. NPC-NPC eavesdropping across walls broken. |
| V8-SP-26 | ★ MEDIUM | `scene_state_manager.py:797-810` | `reinit_campaign` вызывает только `SpatialFactory.invalidate_cache`, НЕ `LifeEngine.invalidate_cache` и НЕ `SpatialRegistry.invalidate_cache`. Stale NPC cache persists между тестами. |
| V8-PSY-31 | ★ MEDIUM | `will.py:157` | `gregariousness = psyche.get("gregariousness", 0.5)` — переменная объявлена, но НИКОГДА не используется в resistance formula (will.py:169-177). Dead variable. |
| V8-DLG-15 | ★ MEDIUM | `dialogue_materializer.py:48-50` | `listener_ids: []` всегда передаётся как пустой. `SocialInputProjector` всегда fallback to perception_filter. V8-SOC-7 FIX — optimization dead, runtime works через fallback. |
| V8-SOC-8 | ★ MEDIUM | `event_types.py`, `intent_event_adapter.py:38-46` | Из 7 event types в production публикуются только THEFT, HELP, INTIMIDATION. **DEAD**: COMBAT, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC (0 publish call sites). Subscribers впустую слушают. |
| V8-DLG-16 | ★ MEDIUM | `npc_dialogue_subscriber.py:124-202` | Два последовательных `except Exception as mem_err:` handler'а. Второй unreachable (Python first-match-wins). `add_pending_dialogue_memory` вызывается без safety net. |
| V8-SP-27 | ★ LOW | `local_traversal_planner.py:51` | `print()` в production коде — V8-SP-9 fix не применён. Должно быть `logger.debug()`. |
| V8-SP-28 | ★ LOW | `graph_compiler.py:947-948` | `boundary_map` stores `_bx, _by` (anchor coords), а `NodeRef` использует `_final_x, _final_y` (existing node coords или anchor). Inconsistency — boundary_map["x"]/["y"] не совпадает с graph node coords. Latent bug. |
| V8-MEM-17 | ★ LOW | `dialogue_update_extractor.py:12, 34-35` | `from functools import lru_cache` imported but unused. Docstring обещает "Cached by (stm_before, new_turn, partner)" — но `@lru_cache` decorator отсутствует. Documentation lie. |
| V8-TICK-11 | ★ LOW | `npc_tick_pipeline.py:492-512` | Duplicate V8-SOC-5 `_idle_pressure` accumulation block. Same code дважды подряд — second overwrites first. |
| V8-TICK-12 | ★ LOW | `tick_orchestrator.py:145, 181-182` | Stale comments ссылаются на removed `execute_player_finalize` / `tick_player_turn` methods. Misleading. |
| V8-MVP-22 | ★ LOW | `npc_orchestration.py:91` | `return TickPlayerResultDTO()` на error path, но `TickPlayerResultDTO` imported only at line 369 (function-level). При error condition (scene_state=None) → `NameError`. |
| V8-MVP-23 | ★ LOW | `npc_orchestration.py:225` | `_tick_result` инициализирован как `None` (line 175), но dereferenced как `_tick_result.final_scene_state` (line 225) без None check. `AttributeError` на edge case. |
| V8-MVP-24 | ★ LOW | `mvp_tavern_controller.py:134-154` | Duplicate `trigger_fate` block. Both `if` условия идентичны (`CRITICAL` + `not resolved_fate`). После первого trigger'а BROKEN, второй DEATH — dead code (condition уже False). |
| V8-WL-8 | ★ LOW | `player_avatar_service.py:345, 354` | `set(data.get("trauma_markers", []))` и `dict(data.get("body_state", {}))` поднимают `TypeError` если в JSON эти ключи явно `null`. |
| V8-WL-9 | ★ LOW | `player_avatar_service.py:215-295` | `_state_to_dict` не сериализует `recent_failures`, `life_project`, `life_project_state`, `social_input_ema`, `temporary_drives`, `drives_runtime`, `strain_memory`. Avatar теряет break-progress FSM state через save/load. |

---

## §1. MVP EPISTEMIC CHAIN — НОВЫЕ БАГИ

### V8-MVP-21 ★★★ CRITICAL (v8.6 NEW) — `LifeEngine.update_idle_pressure` сбрасывает injected services

**Файл:** `backend/app/services/npc/life_engine.py:217-258`

**Проблема:** В `__init__` (lines 217-247) инициализируются `_npc_cache`, `_last_access`, `_idle_pressure`, `_temporal`, `_movement_engine` — но `_spatial_service`, `_persistence`, `_claim_bus` инициализируются **внутри** метода `update_idle_pressure` (lines 250-258), а не в `__init__`.

```python
def __init__(self, data_dir: Optional[str] = None):
    self.data_dir = Path(data_dir or settings.data_dir)
    self.npcs_dir = self.data_dir / "npcs"
    self.sessions_dir = self.data_dir / "sessions"
    self._npc_cache: dict[str, list] = {}
    self._last_access: OrderedDict[str, float] = OrderedDict()
    self._idle_pressure: dict[tuple[str, str], float] = {}
    from app.services.temporal.temporal_engine import TemporalEngine
    self._temporal = TemporalEngine(sessions_dir=self.sessions_dir)
    self._movement_engine = MovementEngine()
    # ← __init__ ENDS HERE. NO _spatial_service / _persistence / _claim_bus !

def get_idle_pressure_map(self) -> dict:
    return self._idle_pressure.copy()

def update_idle_pressure(self, updates: dict) -> None:
    """V8-SOC-5 FIX: Обновляет давление разговоров из TickMutation."""
    self._idle_pressure.update(updates)

    # Слой 3: SpatialService v1.2 — семантическая навигация (инжекция извне)
    self._spatial_service: Optional[Any] = None       # ← INSIDE method!

    # ADR-128: PersistencePort для read-back при cache miss.
    self._persistence: Optional[Any] = None            # ← INSIDE method!

    self._claim_bus: Optional["DRFBus"] = None          # ← INSIDE method!
```

**Reproduction:**
```python
>>> e = LifeEngine()
>>> hasattr(e, '_spatial_service')      # False
>>> e.update_idle_pressure({('c','n'): 0.5})
>>> e._spatial_service                   # None (создано, но None)
>>> e.set_spatial_service(FakeSvc()); e._spatial_service   # FakeSvc
>>> e.update_idle_pressure({('c','n2'): 0.3})
>>> e._spatial_service                   # None ← RESET! injected service LOST
```

**Production impact:** `tick_orchestrator.py:1353` вызывает `_life_engine.update_idle_pressure(_mutation.idle_pressure_updates)` каждый тик. Каждый вызов **СБРАСЫВАЕТ** `_spatial_service`, `_persistence`, `_claim_bus` на `None`. Всё, что запускается *после* `update_idle_pressure` в том же тике (DRF scoring overlay, post-tick hooks), тихо теряет injected services.

**Test failure:** `test_movement_lock_blocks_schedule_on_active_traversal` crashes с `AttributeError: 'LifeEngine' object has no attribute '_spatial_service'`.

**Fix:** Dedent lines 250-258 на 4 пробела — переместить инициализацию в `__init__`:
```python
def __init__(self, data_dir: Optional[str] = None):
    ...
    self._movement_engine = MovementEngine()
    # Слой 3: SpatialService v1.2 — семантическая навигация (инжекция извне)
    self._spatial_service: Optional[Any] = None
    # ADR-128: PersistencePort для read-back при cache miss.
    self._persistence: Optional[Any] = None
    self._claim_bus: Optional["DRFBus"] = None

def update_idle_pressure(self, updates: dict) -> None:
    """V8-SOC-5 FIX: Обновляет давление разговоров из TickMutation."""
    self._idle_pressure.update(updates)
```

**Время:** 2 мин (один dedent)

### V8-MVP-22 ★ LOW (v8.6 NEW) — `npc_orchestration.py:91` NameError на error path

**Файл:** `backend/app/services/game_loop/npc_orchestration.py:85-91`

```python
_scene_state = shared_context.scene_state
if _scene_state is None:
    logger.error(
        "[SCENE_IDENTITY] npc_orchestration: shared_context.scene_state is None! Traversals will be lost."
    )
    return TickPlayerResultDTO()    # ← BUG
```

Top-level imports (lines 9-15) НЕ включают `TickPlayerResultDTO`. Единственный import — function-level на line 369:
```python
from app.services.tick_orchestrator import TickPlayerResultDTO
```
Line 369 unreachable когда early-return на line 91 fires. При error condition (scene_state is None) → `NameError: name 'TickPlayerResultDTO' is not defined` → exception propagates up → GameLoop aborts tick.

**Fix:** Hoist import to module top:
```python
# npc_orchestration.py:9-15
from app.services.tick_orchestrator import TickPlayerResultDTO
```

**Время:** 1 мин

### V8-MVP-23 ★ LOW (v8.6 NEW) — `npc_orchestration.py:225` NoneType dereference

**Файл:** `backend/app/services/game_loop/npc_orchestration.py:175, 224-225`

```python
# line 175
_tick_result = None

# line 218-219 (внутри цикла, только если _loc_id == _active_loc)
_tick_result = ...

# line 224-225
_scene_manager = getattr(game_loop, "scene_manager", None)
if _tick_result.final_scene_state is not None and _scene_manager:    # ← BUG
```

Если iteration active-location попадает на `continue` (line 186, потому что `_current_scene is None` для non-active loc) ИЛИ `_location_ids` пустой после fallback (lines 171-172), `_tick_result` остаётся `None` → `_tick_result.final_scene_state` → `AttributeError: 'NoneType' object has no attribute 'final_scene_state'`.

**Fix:**
```python
if _tick_result is not None and _tick_result.final_scene_state is not None and _scene_manager:
```

**Время:** 2 мин

### V8-MVP-24 ★ LOW (v8.6 NEW) — `mvp_tavern_controller.py:134-154` duplicate `trigger_fate` block

**Файл:** `backend/app/services/social/mvp_tavern_controller.py:134-154`

```python
# First block (134-142)
if _fate_state and _fate_state.fate_trajectory == FateTrajectory.CRITICAL and not _fate_state.resolved_fate:
    self.fate_tracker.trigger_fate(
        npc_id=npc_id, outcome=FateOutcome.BROKEN, ...
    )

# Second block (144-154) — IDENTICAL condition
_fate_state = self.fate_tracker._states.get(npc_id)
if _fate_state and _fate_state.fate_trajectory.name == "CRITICAL" and not _fate_state.resolved_fate:
    self.fate_tracker.trigger_fate(
        npc_id=npc_id, outcome=FateOutcome.DEATH, ...
    )
```

Оба `if` используют identical predicate (`CRITICAL` + `not resolved_fate`). После первого trigger'а BROKEN, `FateTracker.trigger_fate` ставит `resolved_fate=BROKEN`, поэтому второй блок (`not _fate_state.resolved_fate`) становится `False` → **DEATH outcome — dead code**. Выглядит как copy-paste leftover.

**Fix:** Решить — DEATH должен быть отдельным escalation tier (например, требовать >N ticks в CRITICAL), либо удалить второй блок. Если просто удалить:
```python
# Удалить lines 144-154
```

**Время:** 5 мин (если просто удалить) / 30 мин (если реорганизовать tiers)

---

## §2. SLEEP CHAIN — НОВЫЕ БАГИ

### V8-SP-23 ★ MEDIUM (v8.6 NEW) — V8-SP-19 FIX НЕ применён — boundary nodes перетирают location_id

**Файл:** `backend/app/services/npc/life_engine.py:531-552`

```python
_ss_positions = scene_state.get("npc_positions", {}) if scene_state else {}
for npc in npcs:
    npc_id = npc.get("id", "?")
    _ss_data = _ss_positions.get(npc_id)
    if isinstance(_ss_data, dict):
        _ss_pos = _ss_data.get("position")
        _ss_loc = _ss_data.get("location_id")
        # V8-SP-19 FIX: Синхронизируем position и location_id из scene_state (SSOT).
        _resolved_loc = _ss_loc
        if _ss_pos and ":" in _ss_pos:
            _resolved_loc = _ss_pos.split(":")[0]        # ← NO "exit_" skip!

        if _resolved_loc:
            if npc.get("location_id") != _resolved_loc:
                npc["location_id"] = _resolved_loc       # ← OVERWRITES correct location
                npc["location"] = _resolved_loc
```

Нет `if "exit_" not in _ss_pos:` guard. Если `_ss_pos = "tavern:exit_east"` (boundary node), а `_ss_loc = "city_gate"` (post-materialize) — код перетирает `npc["location_id"] = "tavern"`, clobbering корректный `"city_gate"`.

**Fix:**
```python
if _ss_pos and ":" in _ss_pos:
    _pos_loc = _ss_pos.split(":")[0]
    # V8-SP-19 FIX: boundary nodes (exit_*) не определяют location_id
    if "exit_" not in _ss_pos and _ss_loc != _pos_loc:
        _resolved_loc = _pos_loc
    elif _ss_loc:
        _resolved_loc = _ss_loc
```

**Время:** 10 мин

### V8-SP-24 ★ MEDIUM (v8.6 NEW) — V8-SP-16 FIX НЕ применён — micro_snap deadlock у boundary node

**Файл:** `backend/app/services/spatial/movement_engine.py:718-738`

```python
# Берём первый шаг маршрута (следующий waypoint)
next_node = path_nodes[1]

# V8-SP-16.1 FIX: Убрано случайное смещение (_offset_x/_offset_y).
target_xy = (next_node.x, next_node.y)

_dist = math.hypot(target_xy[0] - source_xy[0], target_xy[1] - source_xy[1])
if _dist < 0.1:
    # V8-SP-16 FIX: Обновляем node_id (position), чтобы A* продвигался по маршруту.
    return [
        SceneChange(
            type=ChangeType.NPC_POSITION,
            target=intent.actor_id,
            field="position",
            value=next_node.node_id,
            cause=f"micro_snap:{intent.reason}",
            tick=tick,
            target_location_id=location_id,
            target_local_xy=(next_node.x, next_node.y),
        )
    ]
```

Нет `NodeRole.BOUNDARY` check перед `if _dist < 0.1:`. Developer выбрал альтернативную mitigation (update `field="position"` to `next_node.node_id`), но boundary detection block отсутствует. Micro_snap fires unconditionally для BOUNDARY nodes.

**Fix:** Detect boundary node ПЕРЕД `if _dist < 0.1`:
```python
from app.models.spatial_contracts import NodeRole

# V8-SP-24 FIX: Boundary node micro_snap deadlock
if getattr(next_node, "role", None) == NodeRole.BOUNDARY:
    _b_info = svc.get_boundary_info(next_node.node_id) or {}
    _materialize_target_loc = _b_info.get("neighbor_chunk", "")
    _entry_hint = _b_info.get("entry_node_hint", "") or f"{_materialize_target_loc}:entrance"
    _target_svc = self._resolve_spatial_service(_materialize_target_loc, campaign_id, scene_state) if scene_state else None
    if _target_svc:
        _target_node_obj = _target_svc.get_node(_entry_hint.split(":")[-1]) or _target_svc.get_node(_entry_hint)
        if _target_node_obj:
            _active_travs = scene_state.get("active_traversals", {}) if scene_state else {}
            if isinstance(_active_travs, dict) and intent.actor_id in _active_travs:
                del _active_travs[intent.actor_id]
            return [SceneChange(
                type=ChangeType.NPC_POSITION, target=intent.actor_id,
                field="position", value=_target_node_obj.node_id,
                cause=f"cross_loc_materialize:{intent.reason}", tick=tick,
                target_location_id=_materialize_target_loc,
                target_local_xy=(_target_node_obj.x, _target_node_obj.y),
                traversal_proposal=None,
            )]
    logger.error(f"[MICRO_SNAP_BOUNDARY_DEADLOCK] npc={intent.actor_id} next_node={next_node.node_id}")
    return []

if _dist < 0.1:
    # ... оригинальный micro_snap
```

**Время:** 30 мин

### V8-SP-25 ★ MEDIUM (v8.6 NEW) — `market_square` adjacency НЕ reciprocated + overlap с tavern остался

**Файлы:** `frontend/map_editor/campaigns/Open_road/locations/market_square.json`, `city_gate.json`, `tavern.json`

**Actual JSON values:**

| Location | origin (x, y) | size (w, h) | bounds [x1, x2] × [y1, y2] |
|---|---|---|---|
| `tavern.json:13-19` | (0, 0) | (20, 15) | [0, 20] × [0, 15] |
| `city_gate.json:5-12` | (20.0, 0.0) | (30, 20) | [20, 50] × [0, 20] |
| `market_square.json:5-12` | (-5.0, 14.875) | (25, 25) | [-5, 20] × [14.875, 39.875] |

**Pairwise overlaps:**

| Pair | X overlap | Y overlap | Area |
|---|---|---|---|
| tavern × city_gate | [20, 20] → 0 m | [0, 15] → 15 m | **0 m²** (touch) ✅ |
| tavern × market_square | [0, 20] → 20 m | [14.875, 15] → 0.125 m | **2.5 m²** ❌ OVERLAP |
| city_gate × market_square | [20, 20] → 0 m | [14.875, 20] → 5.125 m | **0 m²** (touch) ✅ |

**Adjacency reciprocity:**

```json
// market_square.json
"adjacency": { "north": "tavern", "east": "city_gate" }

// city_gate.json
"adjacency": { "west": "tavern", "south": "market_square" }

// tavern.json
"adjacency": { "east": "city_gate", "south": "market_square" }
```

| Pair | Reciprocated? |
|---|---|
| tavern.east=city_gate ↔ city_gate.west=tavern | ✅ YES |
| tavern.south=market_square ↔ market_square.north=tavern | ✅ YES |
| market_square.east=city_gate ↔ city_gate.west=market_square | ❌ NO — city_gate.west="tavern" |
| city_gate.south=market_square ↔ market_square.north=city_gate | ❌ NO — market_square.north="tavern" |

Геометрически market_square находится к югу от city_gate (bounds overlap at y=[14.875, 20]), но `market_square.east = city_gate` — это geometrically wrong. city_gate — к северо-востоку от market_square, не строго к востоку.

**Fix:**
- Сдвинуть market_square: `origin = (20, 15)` → bounds x=[20, 45], y=[15, 40] → no overlap с tavern
- Изменить adjacency: `market_square.adjacency = {"north": "tavern"}` (убрать east=city_gate), `city_gate.adjacency.south = "tavern"` (убрать south=market_square). Связь market_square ↔ city_gate — диагональная, не входит в 4-direction схему.

**Время:** 30 мин (геометрия + валидация + тесты)

### V8-SP-26 ★ MEDIUM (v8.6 NEW) — `reinit_campaign` не вызывает `LifeEngine.invalidate_cache` и `SpatialRegistry.invalidate_cache`

**Файл:** `backend/app/services/scene_state_manager.py:797-810`

```python
def reinit_campaign(self, campaign_id: str) -> dict | None:
    """Переинициализация сцены кампании из editor JSON."""
    # V8-SP-18 FIX: инвалидируем cache SpatialFactory при переинициализации
    from app.services.spatial.spatial_factory import SpatialFactory
    SpatialFactory.invalidate_cache(campaign_id)              # ← only SpatialFactory
    starting_location = self.find_starting_location(campaign_id)
    scene = self.initialize_scene(campaign_id, starting_location)
    ...
```

Вызывается **только** `SpatialFactory.invalidate_cache`. НЕ вызывается:
- `LifeEngine.invalidate_cache(campaign_id)` — `LifeEngine` имеет метод (`life_engine.py:1214-1220`), но `SceneStateManager` не держит reference на `LifeEngine` (grep `life_engine` в scene_state_manager.py → 0 matches)
- `SpatialRegistry.invalidate_cache(campaign_id)` — метод существует (`spatial_registry.py:169`), не вызывается. Mitigated by mtime-based invalidation в `get_or_load`, но stale artifact может вернуться.

**Fix:**
1. Передать `LifeEngine` reference в `SceneStateManager.__init__`
2. В `reinit_campaign`:
```python
def reinit_campaign(self, campaign_id: str) -> dict | None:
    # V8-SP-18 FIX: инвалидируем все caches
    from app.services.spatial.spatial_factory import SpatialFactory
    SpatialFactory.invalidate_cache(campaign_id)
    if self._life_engine:
        self._life_engine.invalidate_cache(campaign_id)
    # SpatialRegistry uses mtime-based invalidation in get_or_load,
    # but we can force reload:
    from app.services.spatial.spatial_registry import SpatialRegistry
    SpatialRegistry.invalidate_cache(campaign_id)  # if exposed as classmethod
    starting_location = self.find_starting_location(campaign_id)
    scene = self.initialize_scene(campaign_id, starting_location)
```

**Время:** 30 мин

### V8-SP-27 ★ LOW (v8.6 NEW) — `print()` в production коде

**Файл:** `backend/app/services/spatial/local_traversal_planner.py:51`

```python
for wall in geometry.walls:
    dist_sq = segments_distance_sq(src, tgt, (wall.x1, wall.y1), (wall.x2, wall.y2))
    if math.sqrt(dist_sq) - body.radius < 0:
        print(f"[CLEARANCE_FAIL] src={src} tgt={tgt} body_radius={body.radius} wall=({wall.x1},{wall.y1})-({wall.x2},{wall.y2}) dist={math.sqrt(dist_sq):.2f}")  # ← print() in prod
        return TraversalPlan(possible=False, reason="WALL_CLEARANCE_BLOCKED")
```

V8-SP-9 fix (per `graph_compiler.py:629`) требует `logger.debug()` вместо `print()`. Этот экземпляр пропущен. Файл уже имеет `logger = logging.getLogger(__name__)` на line 27.

**Fix:**
```python
logger.debug(f"[CLEARANCE_FAIL] src={src} tgt={tgt} body_radius={body.radius} wall=({wall.x1},{wall.y1})-({wall.x2},{wall.y2}) dist={math.sqrt(dist_sq):.2f}")
```

**Время:** 1 мин

### V8-SP-28 ★ LOW (v8.6 NEW) — `boundary_map` хранит anchor coords, не actual boundary node coords

**Файл:** `backend/app/services/spatial/graph_compiler.py:944-952`

```python
boundary_map[boundary_id] = {
    "neighbor_chunk": neighbor_loc_id,
    "node_id": boundary_id,
    "x": _bx,                              # ← anchor coord
    "y": _by,                              # ← anchor coord
    "direction": direction,
    "entry_direction": _entry_dir,
    "entry_node_hint": f"{neighbor_loc_id}:exit_{_entry_dir}"
}
```

Lines 907-908 вычисляют `_final_x = _existing_node.x if _existing_node else _bx` (используется в `NodeRef`), но `boundary_map` dict хранит raw anchor `_bx, _by`. Если JSON имеет existing `exit_east` node (например, tavern's exit_east at 19.0, 4.5), boundary_node в graph — на (19, 4.5), но boundary_map хранит anchor (19, 7.5). Inconsistency.

Currently untested — `test_boundary_nodes.py` проверяет только `neighbor_chunk`/`direction`/`entry_direction`/`entry_node_hint`, НЕ `x`/`y`. Production не потребляет `boundary_map["x"]/["y"]`. Latent bug.

**Fix:**
```python
boundary_map[boundary_id] = {
    "neighbor_chunk": neighbor_loc_id,
    "node_id": boundary_id,
    "x": _final_x,    # V8-SP-28 FIX: используем actual boundary node coords
    "y": _final_y,
    ...
}
```

**Время:** 2 мин

---

## §3. ПСИХИКА — НОВЫЕ БАГИ

### V8-PSY-26 ★★★ CRITICAL (v8.6 NEW) — `personality_from_legacy` не загружает `identity_rigidity`/`gregariousness`

**Файлы:** `backend/app/models/npc_state.py:1073-1103`, `backend/app/services/npc/break_progress_engine.py:211-219`, `backend/app/services/npc/life_engine.py:765-770`, `backend/app/services/npc/npc_tick_pipeline.py:433-436`

**Проблема 1 — `break_progress_engine.py:211-219`:**
```python
# V8-PSY-1 FIX: Читаем identity_rigidity из personality (SSOT), с фолбэком на psyche dict
rigidity = 0.5
if hasattr(state, "personality") and hasattr(state.personality, "identity_rigidity"):
    rigidity = state.personality.identity_rigidity       # ← NPCState has NO personality attr
elif hasattr(state, "psyche"):
    if isinstance(state.psyche, dict):
        rigidity = state.psyche.get("identity_rigidity", 0.5)  # ← psyche dict never has this key
```

`NPCState` не имеет `personality` attribute (только `DecisionView.profile: NPCPersonality` имеет). Primary branch никогда не срабатывает. Fallback `state.psyche.get("identity_rigidity", 0.5)` всегда возвращает 0.5, потому что `write_to_legacy()` (npc_state.py:798-832) НЕ пишет `identity_rigidity` в psyche dict.

**Проблема 2 — `life_engine.py:765-770`:**
```python
_psyche = getattr(state_l2, "psyche", {})
_greg = (
    _psyche.get("gregariousness", 0.5)
    if isinstance(_psyche, dict)
    else 0.5
)
```

Читает из `state_l2.psyche` dict, не из `NPCPersonality.gregariousness`. Psyche dict никогда не содержит `gregariousness`:
- `write_to_legacy` (npc_state.py:820-832) не пишет его
- `_RUNTIME_PSYCHE_KEYS` (npc_loader.py:263-279) не включает его
- Ни один JSON config в `config/npc/**` не объявляет `gregariousness`

`_psyche.get("gregariousness", 0.5)` всегда возвращает 0.5. `NPCPersonality.gregariousness` field (добавленный в V8-PSY-11) никогда не consulted.

**Проблема 3 — `npc_tick_pipeline.py:433-436`:** Идентичная копия `life_engine.py:765-770`.

**Проблема 4 — `npc_state.py:1073-1103` `personality_from_legacy`:** НЕ парсит `identity_rigidity`/`gregariousness`/`willpower` из psyche dict. Оба поля всегда default 0.5.

**Эффект:**
- Trauma mutation plasticity всегда 0.5 для всех NPC (V8-PSY-1 FIX — dead)
- Social homeostasis modulation всегда 0.5 для всех NPC (V8-PSY-11 FIX — dead)
- Все NPC имеют идентичный social homeostasis setpoint
- L1 chronicle traits не кристаллизуются корректно

**Fix (3 шага):**

1. В `npc_state.py:personality_from_legacy` парсить все personality fields:
```python
def personality_from_legacy(data: dict) -> NPCPersonality:
    _psyche = data.get("psyche", {}) if isinstance(data.get("psyche"), dict) else {}
    return NPCPersonality(
        # ... existing fields ...
        identity_rigidity=_psyche.get("identity_rigidity", 0.5),    # V8-PSY-26 FIX
        gregariousness=_psyche.get("gregariousness", 0.5),          # V8-PSY-26 FIX
        willpower=_psyche.get("willpower", 50.0),                   # V8-PSY-26 FIX
    )
```

2. В `npc_state.py:write_to_legacy` писать все personality fields в psyche dict:
```python
def write_to_legacy(self) -> dict:
    ...
    psyche = {
        ...
        "identity_rigidity": self.personality.identity_rigidity,    # V8-PSY-26 FIX
        "gregariousness": self.personality.gregariousness,          # V8-PSY-26 FIX
        "willpower": self.personality.willpower,                    # V8-PSY-26 FIX
    }
```

3. В `break_progress_engine.py:211`/`life_engine.py:765`/`npc_tick_pipeline.py:433` — читать из `state.profile.identity_rigidity` (если доступно через `DecisionView`) ИЛИ из psyche dict (после Fix 1+2).

**Время:** 1.5 ч

### V8-PSY-27 ★★ HIGH (v8.6 NEW) — `phases/decision.py:204-211` AttributeError на dict iteration

**Файл:** `backend/app/services/phases/decision.py:202-211`

```python
# V8-PSY-6 FIX: Гидратация relationship_cache актуальными значениями из RelationshipStore
if relationship_store and not _player_rel:
    _rels = relationship_store.get_all_for_source(campaign_id, npc_id)
    for _r in _rels:
        if _r.target_id == "player":        # ← BUG: _r is a string (dict key)
            _player_rel = {
                "trust": getattr(_r, "trust", 0.0),
                "fear": getattr(_r, "fear", 0.0)
            }
            break
```

`RelationshipStore.get_all_for_source` (`memory/relationship_store.py:129-148`) возвращает `Dict[str, Dict[str, float]]` (`{target_id: {trust, fear, debt, respect}}`). `for _r in _rels:` итерирует **dict keys** (strings), поэтому `_r.target_id` → `AttributeError: 'str' object has no attribute 'target_id'`.

Fires для каждого NPC, у которого есть хотя бы одна stored relationship И пустой `relationship_cache["player"]` (что всегда, т.к. `relationship_cache` ephemeral per npc_state.py:787,1028-1031). Exception caught at decision.py:239 и re-raised → ломает BehaviorMask computation.

**Fix:**
```python
if relationship_store and not _player_rel:
    _rels = relationship_store.get_all_for_source(campaign_id, npc_id)
    _player_data = _rels.get("player", {}) if isinstance(_rels, dict) else {}
    if _player_data:
        _player_rel = {
            "trust": _player_data.get("trust", 0.0),
            "fear": _player_data.get("fear", 0.0),
        }
```

**Время:** 15 мин

### V8-PSY-28 ★ MEDIUM (v8.6 NEW) — `personality_from_legacy` не парсит `willpower`

**Файл:** `backend/app/models/npc_state.py:1073-1103`, `backend/app/services/phases/decision.py:60-61`

`phases/decision.py:60-61`:
```python
_personality = getattr(_npc_state, "personality", None)
_willpower = getattr(_personality, "willpower", 50.0) if _personality else 50.0
```

`NPCState` не имеет `personality` attribute → `_willpower` hardcoded 50.0 для каждого NPC. `BreakProgressEngine.calculate` работает с wrong willpower value.

(Часть общего fix V8-PSY-26 — после добавления `personality_from_legacy` парсинга и `write_to_legacy` записи `willpower`, читать из psyche dict.)

**Время:** (учтено в V8-PSY-26)

### V8-PSY-29 ★ MEDIUM (v8.6 NEW) — `CalibrationEngine` dead code — instantiated, never called

**Файлы:** `backend/app/services/npc/calibration_engine.py:32-66`, `backend/app/services/tick_orchestrator.py:1212-1244`

`calibration_engine.py:32-66`:
```python
def stabilize(
    self,
    l3_raw: EffectiveDrives,
    l3_prev: Dict[str, float],
    l0_baseline: Dict[str, float],
    strain_memory: Dict[str, float] = None,
    tick_delta: int = 1,
) -> Tuple[EffectiveDrives, Dict[str, float], Dict[str, float]]:
    ...
    if strain_memory is None:
        strain_memory = {}

    # ФИНАЛЬНЫЙ РЕЖИМ (ADR-O-211 / S96):
    # CalibrationEngine исключён из графа мутаций состояния (Pure Projection Gate).
    # Эмоциональное взросление делегировано в L2.5 (BeliefCrystallizationEngine).
    # Мутация drives_runtime запрещена. Возвращает пустые словари.
    return l3_raw, {}, {}
```

`stabilize()` возвращает пустые dict'ы для `drives_update` и `strain_memory` — никогда не мутирует state.

`tick_orchestrator.py:1212-1244`:
```python
_calibration = CalibrationEngine()  # instantiated...

for npc_dict in npc_list:
    ...
    # ADR-O-208: L3-P1. CalibrationEngine — pass-through (ADR-O-211).
    # L3 строго эфемерна. Чтение кэша drives_runtime запрещено.
    l3_stable = l3_raw  # _calibration.stabilize() NEVER CALLED

return effective_drives_map, {}, {}  # drives_updates and strain_updates always empty
```

`_calibration` — dead-code instantiation. `ctx.drives_updates` и `ctx.strain_updates` всегда `{}`. `strain_memory` (`NPCState.strain_memory`, npc_state.py:644) никогда не накапливается.

**Fix (2 варианта):**
- **(a) Удалить dead instantiation:** Убрать `_calibration = CalibrationEngine()` и комментарии про ADR-O-208/O-211.
- **(b) Реализовать stabilize() properly:** Если L3 calibration нужен — реализовать mutation logic, wire `.stabilize()` call.

**Время:** 5 мин (удалить) / 2 ч (реализовать)

### V8-PSY-30 ★ MEDIUM (v8.6 NEW) — `perception_filter.py:216-225` NPC_SPOKE case-mismatch ломает eavesdropping

**Файл:** `backend/app/services/npc/perception_filter.py:216-225`

```python
sound_events = {
    "SOUND_EMITTED", "OBJECT_DESTROYED", "PLAYER_ATTACKED", "PLAYER_SPOKE",
}
if event_type in sound_events:
    if _can_hear(npc_id, spatial_query, radius, scene_state):
        perceiving.append(npc_id)
```

`EventType.NPC_SPOKE = "npc_spoke"` (lowercase) — never matches uppercase set. `EventType.PLAYER_SPOKE = "PLAYER_SPOKE"` (uppercase) — matches.

**Эффект:** NPC_SPOKE events fall through to visual `_can_see` check (15m cap, требует line_of_sight). NPC-NPC overheard speech across walls/longer distances — потерян. Undermines NpcDialogueSubscriber's listener_ids fallback.

**Fix:**
```python
# V8-PSY-30 FIX: Нормализуем event_type к uppercase
if event_type.upper() in sound_events:
    ...
```

Или добавить `"npc_spoke"` к set (но лучше uppercase normalization для consistency).

**Время:** 5 мин

### V8-PSY-31 ★ MEDIUM (v8.6 NEW) — `will.py:157` `gregariousness` объявлена, но не используется

**Файл:** `backend/app/services/will.py:151-177`

```python
gregariousness = psyche.get("gregariousness", 0.5)    # ← line 157, dead variable
...
# Resistance formula (lines 169-177) — НЕ использует gregariousness
resistance = (
    conviction * 0.4
    + shame * 0.3
    + aggression * 0.2
    + curiosity * 0.1
    + (1.0 - fear) * 0.3
)
```

Переменная объявлена, но НИКОГДА не появляется в resistance formula. Dead variable. Social homeostasis не влияет на will computation.

**Fix:** Либо использовать `gregariousness` в formula (например, `+ gregariousness * 0.1` для social-oriented NPCs), либо удалить dead declaration.

**Время:** 5 мин (удалить) / 30 мин (спроектировать влияние)

---

## §4. ВОЛЯ / АВАТАР — НОВЫЕ БАГИ

### V8-WL-6 ★ MEDIUM (v8.6 NEW) — `player_pressure` SSOT никогда не присваивается

**Файлы:** `backend/app/services/dto.py:158-160`, `backend/app/services/phases/input.py:99-103`

`dto.py:158-160`:
```python
player_pressure: Optional["IntentPressureProfile"] = (
    None  # ADR-031 Fix: Вектор давления из Фазы 1
)
```

`input.py:99-103`:
```python
# 1. Вектор давления берется из результата Фазы 1 (Единая точка вычисления)
# Повторный вызов resolve_intent_pressure ЗАПРЕЩЕН (каузальная integrity)
from app.services.will import compute_willpower, resolve_intent_pressure

pressure = ctx.player_pressure or resolve_intent_pressure(intent)
```

Grep `player_pressure =` / `player_pressure=` в `backend/` → **zero assignments**. `ctx.player_pressure` всегда `None`, поэтому код нарушает свой собственный contract на каждом тике, вызывая `resolve_intent_pressure(intent)` снова.

**Fix:** В Фазе 1 (input.py) — вычислить `pressure` один раз и присвоить `ctx.player_pressure = pressure`:
```python
# phase_1_input.py (или input.py)
pressure = resolve_intent_pressure(intent)
ctx.player_pressure = pressure    # V8-WL-6 FIX: SSOT — сохраняем для Will engine
```

**Время:** 30 мин

### V8-WL-7 ★ MEDIUM (v8.6 NEW) — `WillState(...)` без try/except — crash avatar load

**Файл:** `backend/app/services/player_avatar_service.py:343`

```python
will_state=WillState(data.get("will_state", "free")),     # ← NO try/except
```

Если legacy/corrupted save содержит unknown `will_state` string (uppercase `"FREE"`, `"RESIST"`, `"PARTIAL_COMPLY"` capitalized, и т.д.), `WillState(...)` поднимает `ValueError` → crash avatar load.

Сравните: `_emotion_from_str` (npc_state.py:946-964) wrapped в try/except returning `EmotionTag.NEUTRAL` on bad input. `BehaviorMaskState` parse (line 328-334) тоже wrapped. `WillState` — нет. Inconsistent и fragile.

**Fix:**
```python
def _will_state_from_str(s: str) -> WillState:
    try:
        return WillState(s)
    except (ValueError, KeyError):
        return WillState.FREE

# line 343
will_state=_will_state_from_str(data.get("will_state", "free")),
```

**Время:** 10 мин

### V8-WL-8 ★ LOW (v8.6 NEW) — `trauma_markers`/`body_state` NoneType deref

**Файл:** `backend/app/services/player_avatar_service.py:345, 354`

```python
trauma_markers=set(data.get("trauma_markers", [])),    # ← TypeError if data["trauma_markers"] is None
...
body_state=dict(data.get("body_state", {})),            # ← TypeError if data["body_state"] is None
```

Если в JSON эти ключи явно `null` (что бывает при миграции schema), `set(None)` / `dict(None)` поднимает `TypeError: 'NoneType' object is not iterable`.

**Fix:**
```python
trauma_markers=set(data.get("trauma_markers") or []),
...
body_state=dict(data.get("body_state") or {}),
```

**Время:** 5 мин

### V8-WL-9 ★ LOW (v8.6 NEW) — Avatar state не полностью персистится

**Файл:** `backend/app/services/player_avatar_service.py:215-295` (`_state_to_dict`)

Не сериализует: `recent_failures`, `life_project`, `life_project_state`, `social_input_ema`, `temporary_drives`, `drives_runtime`, `strain_memory`.

Сравните: `NPCState.write_to_legacy` (npc_state.py:820-832) ДЕ сериализует `recent_failures`, `life_project`, `life_project_state` для regular NPCs. Avatar теряет break-progress FSM state через save/load.

**Fix:** Добавить все недостающие поля в `_state_to_dict`:
```python
def _state_to_dict(self, state: AvatarState) -> dict:
    return {
        ...existing fields...,
        # V8-WL-9 FIX: Персистируем FSM state
        "recent_failures": list(state.recent_failures),
        "life_project": state.life_project,
        "life_project_state": state.life_project_state,
        "social_input_ema": dict(state.social_input_ema),
        "temporary_drives": dict(state.temporary_drives),
        "drives_runtime": dict(state.drives_runtime),
        "strain_memory": dict(state.strain_memory),
    }
```

Также обновить `_state_from_dict` для чтения этих полей.

**Время:** 45 мин

---

## §5. ПАМЯТЬ / DECISIONHUB — НОВЫЕ БАГИ

### V8-MEM-14 ★★★ CRITICAL (v8.6 NEW) — `detect_resonance` вызывается без `npc_id` → TypeError → весь L3 identity pipeline мёртв

**Файлы:** `backend/app/services/memory/memory_manager.py:795-800` (definition), `backend/app/services/memory/working_memory_tick.py:122` и `backend/app/services/phases/memory.py:117` (call sites)

**Signature:**
```python
def detect_resonance(
    self,
    campaign_id: str,
    npc_id: str,           # REQUIRED, no default
    actor_id: str = "player",
) -> List[Tuple[str, float]]:
    # V8-MEM-13 FIX: Фильтруем буфер по npc_id, а не по всей кампании
    key = f"{campaign_id}:{npc_id}"
    events = self._working.get(key)
```

**Production call sites (оба вызывают без `npc_id`):**

`working_memory_tick.py:122`:
```python
resonance = memory_manager.detect_resonance(campaign_id, actor_id="player")
```

`phases/memory.py:117`:
```python
_resonance = memory_manager.detect_resonance(ctx.campaign_id, actor_id="player")
```

Оба вызова пропускают `npc_id` → `TypeError: detect_resonance() missing 1 required positional argument: 'npc_id'`. Exception swallowed `try/except Exception` at `memory.py:120-121`, поэтому игра не падает, но **resonance detection silently НИКОГДА не запускается в production** — весь L3 identity drift pipeline (Stage 10) broken.

**Эффект:**
- `_identity_cache` updates starved of new signals
- L1 crystallized traits не кристаллизуются
- NPC personality evolution — dead
- BeliefCrystallizationEngine не получает input

**Fix:** Оба call sites должны перебирать active NPC IDs:
```python
# phases/memory.py
for _npc_id in ctx.active_npc_ids:
    try:
        _resonance = memory_manager.detect_resonance(
            ctx.campaign_id, npc_id=_npc_id, actor_id="player"
        )
        # ... process _resonance for this NPC ...
    except Exception as e:
        logger.warning(f"[MEM] detect_resonance failed for npc={_npc_id}: {e}")
```

**Время:** 30 мин

### V8-MEM-15 ★★ HIGH (v8.6 NEW) — `CrystallizedBeliefStore.update_beliefs` non-transactional multi-statement update

**Файл:** `backend/app/services/npc/crystallized_belief_store.py:97-115`

```python
self._store.execute("DELETE FROM crystallized_beliefs WHERE campaign_id = ? AND npc_id = ?", ...)
for b in beliefs:
    self._store.execute("INSERT INTO crystallized_beliefs ...", ...)
```

Каждый `execute()` коммитит независимо (see `sqlite_store.py:323-326`). Crash mid-loop → beliefs **удалены, но не вставлены**.

**Production evidence (from logs):**
- `logs/cds_session_20260726_232808.log:6634`: `Failed to save beliefs for thief_shadow: error return without exception set`
- `logs/cds_session_20260726_233302.log:6740`: `Failed to save beliefs for guard_borko: cannot commit - no transaction is active`

**Fix:** Wrap DELETE + INSERTs в single transaction:
```python
def update_beliefs(self, campaign_id: str, npc_id: str, beliefs: List[CrystallizedBelief]) -> None:
    # V8-MEM-15 FIX: Transactional multi-statement update
    conn = self._store._get_conn()
    try:
        conn.execute("BEGIN TRANSACTION")
        conn.execute("DELETE FROM crystallized_beliefs WHERE campaign_id = ? AND npc_id = ?", ...)
        for b in beliefs:
            conn.execute("INSERT INTO crystallized_beliefs ...", ...)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
```

Или добавить `execute_many` transactional API к `SqliteMemoryStore`.

**Время:** 1 ч

### V8-MEM-16 ★ MEDIUM (v8.6 NEW) — `_identity_cache` сохраняется в JSON, не SQLite; race condition

**Файлы:** `backend/app/services/memory/memory_manager.py:51-54, 835-836`, `backend/app/services/memory/layered_memory.py:73-92`

**Load:**
```python
if hasattr(self._layered.store, "load_state"):
    self._identity_cache: Dict[str, Dict[str, float]] = self._layered.store.load_state("identity_cache")
else:
    self._identity_cache: Dict[str, Dict[str, float]] = {}
```

**Save:**
```python
# V8-MEM-7 FIX: Персистируем обновлённый identity_cache
self._layered.store.save_state("identity_cache", self._identity_cache)
```

**Backend:** `layered_memory.py:73-92` — `save_state` writes to `{collection}.json` (NOT SQLite).

**Проблемы:**
1. Spec implied SQLite; actual storage — JSON. Spec-deviation.
2. `save_state` переписывает **весь** `_identity_cache` (all campaigns/NPCs) на каждый `apply_identity_weights()` call.
3. Нет lock → race condition если несколько ticks обновляют identity_cache concurrently (lost updates possible).
4. File I/O на каждый trait delta — perf concern.

**Fix:**
- (a) Перенести в SQLite table `identity_cache(campaign_id, npc_id, trait_key, trait_value)`
- (b) Добавить `threading.RLock` вокруг read-modify-write
- (c) Debounce writes (не чаще чем раз в N seconds или N updates)

**Время:** 1.5 ч

### V8-MEM-17 ★ LOW (v8.6 NEW) — `dialogue_update_extractor.py` lru_cache import unused, docstring lie

**Файл:** `backend/app/services/memory/dialogue_update_extractor.py:12, 34-35`

```python
from functools import lru_cache  # imported but UNUSED
...
def extract(self, stm_before: str, new_turn: str, partner: str) -> DialogueUpdate:
    """Cached by (stm_before, new_turn, partner) to avoid re-computation."""
```

Нет `@lru_cache` decorator. `lru_cache` import — dead. Docstring врёт.

**Fix:** Либо удалить docstring claim + import, либо действительно декорировать `@lru_cache(maxsize=128)` (если hashable).

**Время:** 2 мин

---

## §6. NPC↔NPC SOCIAL — НОВЫЕ БАГИ

### V8-SOC-8 ★ MEDIUM (v8.6 NEW) — Dead event types: COMBAT, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC

**Файл:** `backend/app/services/events/event_types.py`, `backend/app/services/events/intent_event_adapter.py:38-46`

| Event | Defined | Subscribed | Published in production |
|---|---|---|---|
| COMBAT | ✅ (line 58) | ✅ `combat_subscriber.py:38` | ❌ **DEAD** — no `bus.publish(EventType.COMBAT)` |
| THEFT | ✅ (line 57) | ✅ `social_subscriber.py:41` | ✅ via IntentEventAdapter |
| HELP | ✅ (line 59) | ✅ `social_subscriber.py:43` | ✅ via IntentEventAdapter |
| INTIMIDATION | ✅ (line 62) | ✅ `social_subscriber.py:44` | ✅ via IntentEventAdapter |
| BETRAYAL | ✅ (line 63) | ✅ `social_subscriber.py:45` | ❌ **DEAD** — no publisher |
| SAVED_LIFE | ✅ (line 64) | ✅ `social_subscriber.py:46` | ❌ **DEAD** — no publisher |
| NPC_INTERACTS_NPC | ✅ (line 53) | ✅ `social_subscriber.py:49`, `social_input_projector.py:51` | ❌ **DEAD** — no publisher (only in tests) |

4 из 7 event types — dead code: COMBAT, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC. Subscribers впустую слушают.

`IntentEventAdapter.to_event` (`intent_event_adapter.py:38-46`) — единственный converter. Maps:
- `attack` → `actor_attacks` (не COMBAT!)
- `help` → `help`
- `theft/steal/rob` → `theft`
- `intimidate` → `intimidation`
- default → `npc_spoke`

**Fix (2 варианта):**
- **(a) Publish:** Добавить publish call sites для COMBAT (из CombatSubscriber при damage), BETRAYAL (из DecisionHub), SAVED_LIFE (из healing/help action), NPC_INTERACTS_NPC (из DecisionHub при NPC-initiated social contact)
- **(b) Delete:** Удалить event types и subscribers если архитектура изменилась

**Время:** 1.5 ч (publish) / 30 мин (delete)

---

## §7. ДИАЛОГОВАЯ СИСТЕМА — НОВЫЕ БАГИ

### V8-DLG-15 ★ MEDIUM (v8.6 NEW) — `listener_ids` всегда `[]` — optimization dead

**Файлы:** `backend/app/services/execution/dialogue_materializer.py:48-50`, `backend/app/services/events/social_input_projector.py:84, 102`

`dialogue_materializer.py:48-50`:
```python
# V8-SOC-7 FIX: Передаём пустой список listener_ids,
# SocialInputProjector заполнит его на основе радиуса и LoS.
"listener_ids": [],
```

Materializer **всегда** передаёт `[]`. Projector всегда fallback to perception_filter (lines 86-95 / 104-113). Поле `listener_ids` существует, но effectively dead — никогда не populated.

**Эффект:** V8-SOC-7 FIX optimization — dead. Runtime работает через fallback path (perception_filter), но optimization intent не реализован.

**Fix:** Либо populate `listener_ids` в materializer (через spatial query перед publish), либо удалить поле и признать что perception_filter — единственный путь.

**Время:** 30 мин (populate) / 5 мин (remove field)

### V8-DLG-16 ★ MEDIUM (v8.6 NEW) — `npc_dialogue_subscriber.py:124-202` два последовательных `except Exception` handler'а

**Файл:** `backend/app/services/events/npc_dialogue_subscriber.py:124-202`

AST analysis confirms: try block at line 124 имеет ДВА `except Exception as mem_err:` handler'а (lines 178 и 201).

```python
try:
    ...  # lines 125-177
except Exception as mem_err:    # line 178 — catches ALL Exception
    logger.warning(...)
    # BUG-DL-06 deferred write...
    self.memory.add_pending_dialogue_memory(_dialogue_event)
except Exception as mem_err:    # line 201 — UNREACHABLE
    logger.warning(f"[NPC_DIALOGUE_SUB] add_dialogue_turn failed for {listener}/{speaker}: {mem_err}")
```

Второй handler никогда не выполнится (Python first-match-wins). `add_pending_dialogue_memory` вызывается без safety net второго handler'а.

**Fix:** Удалить lines 201-202. Если нужно различать типы ошибок — использовать specific exception classes.

**Время:** 2 мин

---

## §8. ТИК / ОРКЕСТРАТОР — НОВЫЕ БАГИ

### V8-TICK-8 ★★ HIGH (v8.6 NEW) — DRF overlay no-op для `CommunicationIntent` (V8-TICK-2/7 FIX — wiring есть, реально не работает)

**Файл:** `backend/app/services/tick_orchestrator.py:1560-1601`

`_apply_drf_scoring_overlay` теперь ВЫЗЫВАЕТСЯ из production:
1. `tick_orchestrator.py:1360` — `self._apply_drf_scoring_overlay(ctx.communication_intents, ctx)` (в `_phase_5_decision`)
2. `phases/movement_bridge.py:89` — `orchestrator._apply_drf_scoring_overlay(_merged_intents, ctx)` (для movement intents)

**НО** реализация фильтрует по неверному атрибуту:

`tick_orchestrator.py:1570-1573`:
```python
for _intent in intents:
    if not hasattr(_intent, "npc_id"):   # ← filters by `npc_id`
        continue
    _npc_id = _intent.actor_id           # ← reads `actor_id`
```

Investigation двух intent types:
- **`CommunicationIntent`** (`backend/app/domain/communication.py:69-97`) — `@dataclass(frozen=True)` с полями `speaker`, `audience`, `topic`, ... **НЕТ `npc_id` attribute, НЕТ `actor_id` attribute, НЕТ `priority` attribute.**
  → `hasattr(intent, "npc_id") == False` → **каждый CommunicationIntent тихо пропускается**.
  → Дополнительно, `CommunicationIntent` — `frozen=True`, поэтому даже если бы имел `priority`, присваивание `_intent.priority = ...` на line 1600 подняло бы `FrozenInstanceError`.
- **`MacroMovementGoal`** (`backend/app/domain/movement.py:35-64`) — имеет `actor_id`, `priority`, `reason`, и `npc_id` **property** (line 61-64). Overlay работает корректно.
- **`LocalSteeringGoal`** (`movement.py:79-94`) — имеет `actor_id` и `priority`, но **НЕТ `npc_id` property** → тоже тихо пропускается.

**Эффект:** DRF scoring overlay применяется только к `MacroMovementGoal` movement intents. **Все verbal/communication intents всё ещё bypass DRF scoring** — изначальная жалоба V8-TICK-2 ("non-movement intents bypass DRF") — effectively всё ещё не пофикшена, несмотря на добавленный call site.

**Fix:**
1. Изменить фильтр: `if not (hasattr(_intent, "actor_id") or hasattr(_intent, "speaker")): continue`
2. Читать правильный атрибут: `_npc_id = getattr(_intent, "actor_id", None) or getattr(_intent, "speaker", None)`
3. Для `frozen=True` CommunicationIntent — использовать `dataclasses.replace(_intent, priority=new_priority)` вместо `_intent.priority = ...`
4. ИЛИ: overlay пишет в side-table (`ctx.intent_drf_adjustments: Dict[int, float]`), а consumer читает оттуда

**Время:** 1.5 ч

### V8-TICK-9 ★★ HIGH (v8.6 NEW) — `_compute_effective_drives` silent `AttributeError`+`NameError` → V8-PSY-9 FIX dead code

**Файл:** `backend/app/services/tick_orchestrator.py:1192-1228`

```python
def _compute_effective_drives(
    self, npc_list: list[dict], tick_number: int     # ← NO ctx parameter
) -> Tuple[...]:
...
    # V8-PSY-9 FIX: Получаем L1 Identity из memory_manager
    _identity_l1 = None
    try:
        _traits = self.memory_manager.get_identity_traits(ctx.campaign_id, _nid)    # ← TWO BUGS
        if _traits:
            _identity_l1 = NPCIdentityL1(npc_id=_nid, active_traits=_traits)
    except Exception:
        pass

    _projection = self.drive_resolver.resolve_drives(
        _profile_l0, _beliefs, body_state=_body_state, identity_l1=_identity_l1
    )
```

Две ошибки на line 1223:
1. **`self.memory_manager`** — attribute is `self._memory_manager` (line 73) или via `self._get_memory_manager()` (line 211). No `memory_manager` property exists (grep: 0 hits for `def memory_manager|@property`).
2. **`ctx.campaign_id`** — `ctx` НЕ параметр `_compute_effective_drives` (signature: `(self, npc_list, tick_number)`). Это `NameError`.

Оба ошибки ловятся `except Exception: pass` (line 1226). **Эффект:** `_identity_l1` **всегда None**. `drive_resolver.resolve_drives()` никогда не получает L1 identity traits несмотря на V8-PSY-9 FIX comment. Identity-driven drive modulation silently disabled для каждого NPC на каждом тике.

**Severity:** HIGH. Identity traits affect drive resolution → DecisionHub → все NPC behavior. Silent regression.

**Fix:**
```python
def _compute_effective_drives(
    self, npc_list: list[dict], tick_number: int, ctx: Optional[_TickContext] = None
) -> Tuple[...]:
    ...
    _identity_l1 = None
    _mem_mgr = self._get_memory_manager()    # V8-TICK-9 FIX: правильный accessor
    if _mem_mgr and ctx:
        try:
            _traits = _mem_mgr.get_identity_traits(ctx.campaign_id, _nid)
            if _traits:
                _identity_l1 = NPCIdentityL1(npc_id=_nid, active_traits=_traits)
        except Exception:
            logger.warning(f"[TICK] identity traits load failed for {_nid}", exc_info=True)
```

И обновить call site: `self._compute_effective_drives(npc_list, tick_number, ctx=ctx)`.

**Время:** 30 мин

### V8-TICK-10 ★★ HIGH (v8.6 NEW) — `create_memory_event` crashes на `None.apply` — memory events не сохраняются

**Файлы:** `backend/app/services/npc/npc_tick_pipeline.py:633-647` (call site), `741-825` (function)

Call site (line 633-643):
```python
_mem_evt = create_memory_event(
    None,                        # ← memory_manager is None
    state_l2=_new_state,
    decision=decision,
    ...
)
if _mem_evt:
    memory_events.append(_mem_evt)
```

Function body at line 818:
```python
797:  if _importance is not None:
...
818:      state_l2 = memory_manager.apply(    # ← None.apply → AttributeError
819:          event=_evt_dto,
820:          npc_state=state_l2,
821:          campaign_id=campaign_id,
822:          spatial_query=spatial_query,
823:      )
824:      return _evt_dto
825:  return None
```

`memory_manager` передаётся как `None` (line 634), потому что pipeline — "pure reducer" (ADR-TZ09-1: no I/O). Но в отличие от `apply_perception_memory` (line 684-738), которая корректно refactored просто возвращать EventDTO без вызова `memory_manager.apply`, `create_memory_event` всё ещё вызывает `memory_manager.apply(...)` на `None` argument.

**Эффект:** Для любого event где `_importance is not None` (lines 774-795: covers `npc_interacts_npc`, `npc_proximity_close`, `player_interacts` с target, и любой TALK/TRADE/HELP/ATTACK/FLEE/GIVE/ASK/THREATEN intent), function поднимает `AttributeError: 'NoneType' object has no attribute 'apply'`. Exception ловится outer try/except at line 646-647, logged as `[STATE_APPLICATOR] failed for {npc_id}: ...`, и event **никогда не appended to `memory_events`**.

**Severity:** MEDIUM→HIGH. `memory_events` возвращаемые pipeline — silently empty для самых частых event types. Downstream Phase 3 (`_phase_3_memory`), который consumer эти events, effectively gets nothing from DecisionHub path.

**Fix:** Mirror `apply_perception_memory` — убрать `memory_manager.apply(...)` call на lines 818-823 и просто `return _evt_dto` после создания:
```python
if _importance is not None:
    _evt_dto = ...  # build EventDTO
    # V8-TICK-10 FIX: Pipeline — pure reducer, не вызываем memory_manager.apply
    return _evt_dto
return None
```

Consumer в `_phase_3_memory` должен вызывать `memory_manager.apply(event=_mem_evt, ...)` отдельно.

**Время:** 45 мин

### V8-TICK-11 ★ LOW (v8.6 NEW) — Duplicate V8-SOC-5 `_idle_pressure` block

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:492-512`

Тот же code block (вычисление `_idle_pressure_updates[_key]`) появляется дважды подряд:
```python
# Block 1 (lines 492-501):
_key = (state.campaign_id, npc_id)
_current_pressure = state.idle_pressure_map.get(_key, 0.0)
_intent_val = decision.intent.value if decision.intent else "none"
if decision.intent and _intent_val != "idle":
    _pressure_delta = decision.score * IDLE_PRESSURE_ACCUM_RATE
else:
    _pressure_delta = -_current_pressure * IDLE_PRESSURE_DECAY_RATE
_new_pressure = max(0.0, min(1.0, _current_pressure + _pressure_delta))
_idle_pressure_updates[_key] = _new_pressure

# Block 2 (lines 503-512): EXACT DUPLICATE — re-computes identical values
```

Второй блок перезаписывает первый с тем же значением. Wasted CPU per NPC per tick; не correctness bug. Botched merge.

**Fix:** Удалить lines 503-512.

**Время:** 1 мин

### V8-TICK-12 ★ LOW (v8.6 NEW) — Stale comments про removed `execute_player_finalize`

**Файл:** `backend/app/services/tick_orchestrator.py:145, 181-182`

```python
145:  # DRF: Instance-level causal bus — переживает execute() / execute_player_finalize()
...
181:  # 1.5. Кэш текущего тика: tick_player_turn уже резолвил сервис,
182:  # но execute_player_finalize создаёт новый _TickContext без npc_services (ADR-065).
```

Нет `execute_player_finalize` или `tick_player_turn` method (grep — только comment references). Single `execute()` method (line 344) обрабатывает оба path (idle + player) через unified `_run_core_phases`. Comments stale и misleading.

**Fix:** Обновить comments:
```python
145:  # DRF: Instance-level causal bus — переживает execute()
...
181:  # 1.5. Кэш текущего тика: execute() создаёт _TickContext с npc_services (ADR-065).
```

**Время:** 2 мин

---

## §9. РЕДАКТОР КАРТ — НОВЫЕ БАГИ

### V8-ED-5 ★ MEDIUM (v8.6 NEW) — `_rebuild_spatial_registry` wrong campaign_id когда campaign не открыта

**Файл:** `frontend/map_editor/editor_core.py:879`

```python
campaign_id = self.dm.base_dir.parent.name
```

Использует `self.dm.base_dir` (Path на `DataManager`, default = `TEMPLATE_DIR = frontend/map_editor/location_templates`). Когда campaign не открыта, `base_dir.parent.name = "map_editor"` — wrong campaign ID отправляется в `SpatialCompilationGateway.request_rebuild("map_editor")`.

**Fix:**
```python
# V8-ED-5 FIX: Используем campaign_path из CampaignManager, не dm.base_dir
if self.cm.campaign_path:
    campaign_id = self.cm.campaign_path.name
else:
    logger.warning("[EDITOR] _rebuild_spatial_registry: campaign not open, skipping")
    return
```

**Время:** 10 мин

---

## §10. ИТОГОВАЯ СВОДКА v8.6

### Подсчёт новых багов по категориям

| Категория | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|---|---|---|---|---|---|
| §1 MVP epistemic | 1 (V8-MVP-21) | 0 | 0 | 3 (V8-MVP-22/23/24) | 4 |
| §2 Sleep chain | 0 | 0 | 4 (V8-SP-23/24/25/26) | 2 (V8-SP-27/28) | 6 |
| §3 Psyche | 1 (V8-PSY-26) | 1 (V8-PSY-27) | 3 (V8-PSY-28/29/30/31) | 0 | 5 |
| §4 Will/Avatar | 0 | 0 | 2 (V8-WL-6/7) | 2 (V8-WL-8/9) | 4 |
| §5 Memory/Decision | 1 (V8-MEM-14) | 1 (V8-MEM-15) | 1 (V8-MEM-16) | 1 (V8-MEM-17) | 4 |
| §6 NPC↔NPC Social | 0 | 0 | 1 (V8-SOC-8) | 0 | 1 |
| §7 Dialogue | 0 | 0 | 2 (V8-DLG-15/16) | 0 | 2 |
| §8 Tick | 0 | 3 (V8-TICK-8/9/10) | 0 | 2 (V8-TICK-11/12) | 5 |
| §9 Map editor | 0 | 0 | 1 (V8-ED-5) | 0 | 1 |
| **Итого v8.6** | **3** | **6** | **14** | **10** | **33** |

*Примечание: V8-PSY-28/31 считаются как одна запись, т.к. V8-PSY-28 — часть V8-PSY-26 fix; V8-PSY-31 — отдельный dead variable. Фактически 18 уникальных багов с sub-вариантами.*

### Главные блокеры v8.6

1. **V8-MVP-21 (CRITICAL)** — `LifeEngine.update_idle_pressure` сбрасывает injected services на каждом тике → все consumer'ы после Phase 5 видят `None`. Test `test_movement_lock_blocks_schedule_on_active_traversal` уже падает.
2. **V8-MEM-14 (CRITICAL)** — `detect_resonance` вызывается без `npc_id` → `TypeError` → весь L3 identity pipeline тихо мёртв.
3. **V8-PSY-26 (CRITICAL)** — `personality_from_legacy` не загружает `identity_rigidity`/`gregariousness` → всегда 0.5 → plasticity/social homeostasis disabled.

### Тихо мёртвые pipelines (severity regression)

| Pipeline | Статус в V.0.5.3.6.6 | Причина |
|---|---|---|
| L3 identity drift (resonance → trait crystallization) | **DEAD** | V8-MEM-14 — TypeError на call site |
| CalibrationEngine (L3 drives stabilization) | **DEAD** | V8-PSY-29 — never called, returns empty dicts |
| V8-PSY-9 (L1 traits → drive_resolver) | **DEAD** | V8-TICK-9 — `self.memory_manager` AttributeError swallowed |
| V8-TICK-2/7 (DRF overlay для communication intents) | **DEAD** | V8-TICK-8 — `hasattr(_intent, "npc_id")` filter |
| create_memory_event (decision → memory) | **PARTIAL** | V8-TICK-10 — None.apply, но perception_memory path работает |
| V8-PSY-1 (identity_rigidity → break_progress_engine) | **DEAD** | V8-PSY-26 — personality_from_legacy не загружает |
| V8-PSY-11 (gregariousness → social homeostasis) | **DEAD** | V8-PSY-26 — same root cause |
| V8-PSY-6 (relationship_cache hydration) | **DEAD** | V8-PSY-27 — AttributeError on dict iteration |
| V8-SOC-7 (listener_ids optimization) | **DEAD** | V8-DLG-15 — materializer always passes `[]` |
| V8-WL-6 (player_pressure SSOT) | **DEAD** | never assigned, fallback to repeat call |
| COMBAT/BETRAYAL/SAVED_LIFE/NPC_INTERACTS_NPC events | **DEAD** | V8-SOC-8 — 0 publish call sites |
| V8-PSY-31 (gregariousness in will.py) | **DEAD** | declared, never used in formula |

---

## §11. ПРИОРИТЕТ ПОЧИНКИ (Day Plan v8.6)

### День 1 (~3 ч) — Critical blockers

Цель: Восстановить LifeEngine service injection, L3 identity pipeline, personality fields.

| Баг | Время |
|---|---|
| **V8-MVP-21** Dedent lines 250-258 в `life_engine.py` (переместить init в `__init__`) | 2 мин |
| **V8-MEM-14** Передать `npc_id` в `detect_resonance` call sites (2 места) | 30 мин |
| **V8-PSY-26** `personality_from_legacy` парсит `identity_rigidity`/`gregariousness`/`willpower` + `write_to_legacy` пишет их + read sites updated | 1.5 ч |
| **V8-PSY-27** Fix `_r.target_id` → `_rels.get("player", {})` в `decision.py:204-211` | 15 мин |
| Тест: L3 identity pipeline жив, personality fields loaded | 30 мин |

### День 2 (~3.5 ч) — HIGH severity

Цель: DRF overlay работает для communication intents, memory events сохраняются, calibration pipeline жив.

| Баг | Время |
|---|---|
| **V8-TICK-8** DRF overlay: filter by `actor_id`/`speaker`, handle `frozen=True` via `dataclasses.replace` | 1.5 ч |
| **V8-TICK-9** `_compute_effective_drives`: правильный `self._get_memory_manager()` + `ctx` параметр | 30 мин |
| **V8-TICK-10** `create_memory_event`: убрать `memory_manager.apply`, вернуть только EventDTO | 45 мин |
| **V8-MEM-15** `CrystallizedBeliefStore.update_beliefs`: wrap в transaction | 1 ч |
| Тест: memory events append, beliefs survive crash | 30 мин |

### День 3 (~3 ч) — Sleep chain + spatial

Цель: NPC materialize в city_gate корректно, location_id не перетирается.

| Баг | Время |
|---|---|
| **V8-SP-23** V8-SP-19 FIX: `if "exit_" not in _ss_pos:` guard | 10 мин |
| **V8-SP-24** V8-SP-16 FIX: `NodeRole.BOUNDARY` check перед micro_snap | 30 мин |
| **V8-SP-25** Сдвинуть market_square на (20, 15), исправить adjacency reciprocity | 30 мин |
| **V8-SP-26** `reinit_campaign`: вызвать `LifeEngine.invalidate_cache` + `SpatialRegistry.invalidate_cache` | 30 мин |
| **V8-SP-27** `print()` → `logger.debug()` | 1 мин |
| **V8-SP-28** `boundary_map` x/y → `_final_x, _final_y` | 2 мин |
| **V8-ED-5** `_rebuild_spatial_registry` — правильный campaign_id | 10 мин |
| Тест: 5 NPC спят, market_square не накладывается | 1 ч |

### День 4 (~3 ч) — Will/Avatar + Psyche cleanup

| Баг | Время |
|---|---|
| **V8-WL-6** Wire `ctx.player_pressure = pressure` в Phase 1 | 30 мин |
| **V8-WL-7** `WillState(...)` try/except wrapper | 10 мин |
| **V8-WL-8** `trauma_markers`/`body_state` None guard | 5 мин |
| **V8-WL-9** `_state_to_dict` сериализует FSM state | 45 мин |
| **V8-PSY-29** Удалить dead `_calibration = CalibrationEngine()` ИЛИ реализовать `stabilize()` | 5 мин / 2 ч |
| **V8-PSY-30** `perception_filter` uppercase normalization | 5 мин |
| **V8-PSY-31** `will.py:157` — использовать `gregariousness` в formula или удалить | 5 мин |
| **V8-PSY-28** (учтено в V8-PSY-26) | 0 |

### День 5 (~2.5 ч) — Memory + Dialogue + Tick cleanup + финальные тесты

| Баг | Время |
|---|---|
| **V8-MEM-16** `_identity_cache` → SQLite table + lock | 1.5 ч |
| **V8-MEM-17** `dialogue_update_extractor.py` — удалить lru_cache import или декорировать | 2 мин |
| **V8-SOC-8** Publish dead event types (4) ИЛИ удалить | 1.5 ч / 30 мин |
| **V8-DLG-15** Populate `listener_ids` в materializer ИЛИ удалить поле | 30 мин / 5 мин |
| **V8-DLG-16** Удалить unreachable `except` handler | 2 мин |
| **V8-TICK-11** Удалить duplicate V8-SOC-5 block | 1 мин |
| **V8-TICK-12** Обновить stale comments | 2 мин |
| **V8-MVP-22** Hoist `TickPlayerResultDTO` import | 1 мин |
| **V8-MVP-23** None-check для `_tick_result` | 2 мин |
| **V8-MVP-24** Удалить duplicate `trigger_fate` block | 5 мин |
| Full playthrough canary | 30 мин |
| Save/load roundtrip | 15 мин |
| L3 identity drift test | 15 мин |

**Итого v8.6:** ~15 часов работы. После 5 дней — все 18 новых багов закрыты, pipelines живы.

---

## §12. CANARY ТЕСТЫ v8.6 (НОВЫЕ)

### Canary 6: L3 identity pipeline жив

```python
def test_l3_identity_pipeline_alive():
    """V8-MEM-14, V8-PSY-26, V8-TICK-9 — resonance detection запускается."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_l3")
    
    # Триггерим повторяющееся поведение игрока
    for _ in range(10):
        game.player_action(target="tornin", text="расскажи о метели")
        game.idle_tick()
    
    # Проверяем, что detect_resonance не падает с TypeError
    memory = game.memory_manager
    resonance = memory.detect_resonance("test_l3", npc_id="tavern_keeper_tornin", actor_id="player")
    assert isinstance(resonance, list), f"Expected list, got {type(resonance)}"
    
    # Проверяем, что identity_cache обновляется
    traits = memory.get_identity_traits("test_l3", "tavern_keeper_tornin")
    assert traits, "Identity traits should accumulate after repeated interactions"
```

### Canary 7: LifeEngine services не сбрасываются

```python
def test_life_engine_services_persist():
    """V8-MVP-21 — _spatial_service не сбрасывается после update_idle_pressure."""
    engine = LifeEngine()
    fake_spatial = object()
    engine.set_spatial_service(fake_spatial)
    
    # Вызываем update_idle_pressure (как делает tick_orchestrator каждый тик)
    engine.update_idle_pressure({("test_campaign", "test_npc"): 0.5})
    
    assert engine._spatial_service is fake_spatial, \
        "_spatial_service was reset to None by update_idle_pressure — V8-MVP-21 not fixed"
```

### Canary 8: Personality fields loaded from JSON

```python
def test_personality_fields_loaded():
    """V8-PSY-26 — identity_rigidity/gregariousness загружаются из psyche dict."""
    data = {
        "psyche": {
            "identity_rigidity": 0.8,
            "gregariousness": 0.3,
            "willpower": 75.0,
        }
    }
    personality = personality_from_legacy(data)
    assert personality.identity_rigidity == 0.8, "identity_rigidity not loaded"
    assert personality.gregariousness == 0.3, "gregariousness not loaded"
    assert personality.willpower == 75.0, "willpower not loaded"
```

### Canary 9: DRF overlay применяется к CommunicationIntent

```python
def test_drf_overlay_applies_to_communication_intents():
    """V8-TICK-8 — DRF scoring применяется к verbal intents, не только movement."""
    from app.domain.communication import CommunicationIntent
    
    intent = CommunicationIntent(
        speaker="tavern_keeper_tornin",
        audience=["player"],
        topic="weather",
        priority=0.5,
    )
    
    ctx = create_test_context()
    ctx.drf_bus.publish({"source": "guard_borko", "pressure": 0.8})
    
    orchestrator._apply_drf_scoring_overlay([intent], ctx)
    
    # CommunicationIntent должен получить DRF adjustment
    # (через side-table или dataclasses.replace)
    assert intent.priority != 0.5, "DRF overlay did not apply to CommunicationIntent"
```

### Canary 10: Crystallized beliefs survive mid-loop crash

```python
def test_crystallized_beliefs_transactional():
    """V8-MEM-15 — DELETE + INSERT в одной transaction."""
    store = CrystallizedBeliefStore(":memory:")
    store.update_beliefs("test", "npc_1", [
        CrystallizedBelief(topic="weather", polarity="positive", confidence=0.8),
    ])
    
    # Симулируем crash mid-update
    with patch.object(store._store, 'execute', side_effect=[
        None,  # DELETE succeeds
        Exception("simulated crash"),  # first INSERT fails
    ]):
        with pytest.raises(Exception):
            store.update_beliefs("test", "npc_1", [
                CrystallizedBelief(topic="combat", polarity="negative", confidence=0.9),
            ])
    
    # Original belief should still exist (DELETE was rolled back)
    beliefs = store.get_beliefs("test", "npc_1")
    assert len(beliefs) == 1, f"Expected 1 (rolled back), got {len(beliefs)}"
    assert beliefs[0].topic == "weather"
```

---

## §13. CHANGELOG

### v8.6 (V.0.5.3.6.6 аудит) — 2026-08-01

**Глубокий аудит V.0.5.3.6.6:** 5 параллельных агентов, прочитаны 50+ исходников. Сфокусировано на НОВЫХ багах, не описанных в v8.5.

**Главные находки v8.6:**

**➕ 18 НОВЫХ багов (3 CRITICAL, 6 HIGH, 5 MEDIUM, 4 LOW):**

1. **V8-MVP-21 CRITICAL (NEW)** — `LifeEngine.update_idle_pressure` сбрасывает `_spatial_service`/`_persistence`/`_claim_bus` на `None` каждый тик (initialization inside method, не в `__init__`). Все consumer'ы после Phase 5 видят `None`. Test `test_movement_lock_blocks_schedule_on_active_traversal` уже падает.

2. **V8-MEM-14 CRITICAL (NEW)** — `detect_resonance` вызывается без обязательного `npc_id` в 2 production call sites → `TypeError` → весь L3 identity drift pipeline (Stage 10) silently мёртв. `_identity_cache` updates starved.

3. **V8-PSY-26 CRITICAL (NEW)** — `personality_from_legacy` не парсит `identity_rigidity`/`gregariousness`/`willpower` из psyche dict. Все NPC имеют hardcoded 0.5/50.0. V8-PSY-1 и V8-PSY-11 fixes — dead code.

4. **V8-PSY-27 HIGH (NEW)** — `phases/decision.py:204-211` V8-PSY-6 hydration итерирует `Dict[str, Dict]` как list of objects → `_r.target_id` → `AttributeError`. BehaviorMask computation broken для всех NPC с relationships.

5. **V8-TICK-8 HIGH (NEW)** — DRF overlay filter `hasattr(_intent, "npc_id")` пропускает все `CommunicationIntent` (имеют `speaker`, не `npc_id`). V8-TICK-2/7 FIX — wiring есть, реально не работает для verbal intents.

6. **V8-TICK-9 HIGH (NEW)** — `_compute_effective_drives` использует `self.memory_manager` (нет такого attr) и `ctx.campaign_id` (нет `ctx` в сигнатуре) → silent `AttributeError`+`NameError` swallowed → V8-PSY-9 FIX — dead code, `_identity_l1` всегда None.

7. **V8-TICK-10 HIGH (NEW)** — `create_memory_event` вызывает `memory_manager.apply(...)` на `None` → `AttributeError`. Memory events для `npc_interacts_npc`/`player_interacts`/TALK/TRADE/HELP/ATTACK silently не сохраняются.

8. **V8-MEM-15 HIGH (NEW)** — `CrystallizedBeliefStore.update_beliefs` non-transactional DELETE + N INSERTs. Crash mid-loop → beliefs удалены, не вставлены. Подтверждено в production logs.

9. **V8-PSY-28 MEDIUM (NEW)** — `personality_from_legacy` не парсит `willpower` (часть V8-PSY-26 fix).

10. **V8-WL-6 MEDIUM (NEW)** — `player_pressure` SSOT объявлен, никогда не присваивается → repeat `resolve_intent_pressure` call, ADR-031 violation.

11. **V8-WL-7 MEDIUM (NEW)** — `WillState(...)` без try/except — crash avatar load на legacy/corrupted saves.

12. **V8-ED-5 MEDIUM (NEW)** — `_rebuild_spatial_registry` возвращает `"map_editor"` как campaign_id когда campaign не открыта.

13. **V8-PSY-29 MEDIUM (NEW)** — `CalibrationEngine` instantiated, `.stabilize()` никогда не вызывается. L3 calibration pipeline — dead code.

14. **V8-SP-23 MEDIUM (NEW)** — V8-SP-19 FIX НЕ применён — boundary nodes (`tavern:exit_east`) перетирают `location_id="city_gate"` на `"tavern"`.

15. **V8-SP-24 MEDIUM (NEW)** — V8-SP-16 FIX НЕ применён — нет `NodeRole.BOUNDARY` check перед micro_snap. NPC может застрять у boundary.

16. **V8-SP-25 MEDIUM (NEW)** — `market_square` 2.5 m² overlap с tavern остался. Adjacency reciprocity нарушена: `market_square.east=city_gate` ↔ `city_gate.west=tavern`.

17. **V8-MEM-16 MEDIUM (NEW)** — `_identity_cache` сохраняется в JSON (не SQLite) на каждый `apply_identity_weights()` call. Race condition.

18. **V8-PSY-30 MEDIUM (NEW)** — `perception_filter` `sound_events` set uppercase, но `EventType.NPC_SPOKE = "npc_spoke"` lowercase. NPC-NPC eavesdropping broken.

19. **V8-SP-26 MEDIUM (NEW)** — `reinit_campaign` не вызывает `LifeEngine.invalidate_cache` и `SpatialRegistry.invalidate_cache`.

20. **V8-PSY-31 MEDIUM (NEW)** — `will.py:157` `gregariousness` объявлена, не используется в formula.

21. **V8-DLG-15 MEDIUM (NEW)** — `listener_ids` всегда `[]` — V8-SOC-7 optimization dead.

22. **V8-SOC-8 MEDIUM (NEW)** — 4 из 7 event types dead (COMBAT, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC — 0 publish call sites).

23. **V8-DLG-16 MEDIUM (NEW)** — Два последовательных `except Exception` handler'а — второй unreachable.

24. **V8-SP-27 LOW (NEW)** — `print()` в `local_traversal_planner.py:51`.

25. **V8-SP-28 LOW (NEW)** — `boundary_map` хранит anchor coords, не actual boundary node coords.

26. **V8-MEM-17 LOW (NEW)** — `dialogue_update_extractor.py` `lru_cache` import unused, docstring lie.

27. **V8-TICK-11 LOW (NEW)** — Duplicate V8-SOC-5 `_idle_pressure` block.

28. **V8-TICK-12 LOW (NEW)** — Stale comments про removed `execute_player_finalize`.

29. **V8-MVP-22 LOW (NEW)** — `npc_orchestration.py:91` NameError на error path.

30. **V8-MVP-23 LOW (NEW)** — `npc_orchestration.py:225` NoneType deref.

31. **V8-MVP-24 LOW (NEW)** — Duplicate `trigger_fate` block — DEATH outcome dead code.

32. **V8-WL-8 LOW (NEW)** — `trauma_markers`/`body_state` NoneType deref.

33. **V8-WL-9 LOW (NEW)** — Avatar state не полностью персистится — теряет FSM state.

**v8.6 фактический итог:**
- **18 уникальных новых багов** (3 CRITICAL, 6 HIGH, 5 MEDIUM, 4 LOW)
- **12 тихо мёртвых pipelines** (перечислены в §10)
- **Day plan v8.6:** 5 дней, ~15 часов. День 1 — critical blockers (V8-MVP-21 + V8-MEM-14 + V8-PSY-26 + V8-PSY-27). День 2 — HIGH severity (DRF overlay + memory events + calibration). День 3 — sleep chain (boundary detection + market_square geometry). День 4 — will/avatar cleanup. День 5 — memory/dialogue/tick cleanup + canary тесты.

---

*Этот документ — TODO list активных багов V.0.5.3.6.6 (v8.6 аудит). После применения Day plan v8.6: LifeEngine services persist (V8-MVP-21), L3 identity pipeline жив (V8-MEM-14), personality fields loaded (V8-PSY-26), DRF overlay применяется ко всем intents (V8-TICK-8), memory events сохраняются (V8-TICK-10), crystallized beliefs transactional (V8-MEM-15), boundary nodes не перетирают location_id (V8-SP-23), NPC materialize корректно (V8-SP-24), market_square geometry fixed (V8-SP-25).*

# ENIGMA — CLOSURE CONTRACT v8

**Дата:** 2026-07-28
**Версия:** V.0.5.3.6.8 (v8 — re-audit после V.0.5.3.6.2)
**Цель:** Полностью работоспособный MVP «Секреты Люси» — End-Screen показывает >0 secrets, NPC спят, все подсистемы подключены.

**Принцип v8:** Только активные баги. Всё починенное в v7 — удалено. Новые находки — добавлены. Карта-редактор и BedRegistry вынесены в отдельный документ `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` — здесь не упоминаются.

**Контекст:** После v7 фиксов V.0.5.3.6.2 применила: N1, N2, N3, N4, N5, N6, N7, N9, N10, N11, N15, M-12, N14 partial (only tag vocab), Mem-09/10 (verified false). Повторный аудит нашёл **37 новых багов**, из них **5 CRITICAL**, **15 HIGH**, **12 MEDIUM**, **5 LOW**.

---

## §0. СТАТУС v7 ФИКСОВ (что осталось починить)

| v7 фикс | Статус в V.0.5.3.6.2 | Действие в v8 |
|---|---|---|
| N1 canon path | ✅ Применён | — |
| N2 TICK_COMPLETED event | ✅ Применён | — |
| N3 ambient routing | ✅ Применён | — |
| N4 _fallback_to_astar | ✅ Применён | — |
| N5 get_central_node | ✅ Применён | — |
| N6 duplicate _resolve_macro_relocation | ✅ Применён | — |
| N7 race condition | ✅ Применён | — |
| N9 eating in activity_map | ✅ Применён | — |
| N10 Borko tags | ✅ Применён | — |
| N11 FactionAlignmentTracker pre-seed | ✅ Применён | — |
| N12 Faction ID language | ⚠️ Частично (test_world_continuity ещё English) | V8-FC-01 |
| N13 Shadow day sleep | ⚠️ Не документирован | V8-FC-02 |
| N14 L3 Identity cascade | ❌ НЕ применён (все 4 шага) | V8-MEM-14 |
| N15 ContradictionResolver sign | ✅ Применён | — |
| M-02 discovered_secrets Set | ⚠️ Частично (поле есть, M-02b не применён) | V8-MVP-02 |
| M-07+M-08 DIALOGUE evidence | ❌ НЕ применён в caller | V8-MVP-07 |
| M-12 apply_delta wired | ✅ Применён | — |
| Mem-08 (false в v7) | N/A | — |
| Mem-09/10 (false в v7) | N/A | — |
| Mem-11 PromotionEngine templates | ❌ НЕ применён | V8-MEM-11 |
| Mem-13 (false в v7) | N/A | — |
| CPS-09 duplicate ADR-036 | ❌ НЕ применён | V8-DEC-09 |
| CPS-10 target_id assert | ⚠️ Логика есть, assert нет | V8-DEC-10 |
| CPS-11 EventBus retry/DLQ | ❌ НЕ применён | V8-DEC-11 |
| CPS-12 line_of_sight coords | ❌ НЕ применён | V8-PER-12 |

---

## §1. ДВИЖЕНИЕ / ПРОСТРАНСТВО

### V8-SP-1 ★★★ CRITICAL — `INV-TOPOLOGY-WALL-CROSS` hard raise на map error

**Файл:** `backend/app/services/spatial/graph_compiler.py:425-431`

```python
if _is_wall_block:
    raise SimulationIntegrityError(
        invariant_id="INV-TOPOLOGY-WALL-CROSS",
        message=f"Edge {from_id} -> {to_id} crosses solid wall. Missing door wall_id?",
        ...
    )
```

**Что происходит:** Навигационное ребро пересекает стену → жёсткий `raise` компиляции. В той же функции (строки 432-441) препятствия обрабатываются правильно: soft-remove ребра + `logger.warning`. **Несимметричная политика.**

**Эффект:** Каждый `compile_graph` (при смене fingerprint / первом билде) валит весь процесс. В `LAST_SESSION.md` — сотни одинаковых инвариантов.

**Fix:** Для map-error — soft: удалить ребро + `logger.error` + CDS event `MAP_TOPOLOGY_DEFECT`. `raise` оставить только в strict/CI mode (`ENIGMA_STRICT_MAP=1`).

```python
if _is_wall_block:
    logger.error(
        f"[MAP_TOPOLOGY_DEFECT] Edge {from_id} -> {to_id} crosses wall. "
        f"Removing edge. Set ENIGMA_STRICT_MAP=1 to crash."
    )
    if os.environ.get("ENIGMA_STRICT_MAP") == "1":
        raise SimulationIntegrityError(...)
    continue  # skip this edge
```

### V8-SP-2 ★★★ CRITICAL — `_segments_intersect` false positive на endpoint

**Файл:** `backend/app/services/spatial/graph_compiler.py:445-450`

`_segments_intersect` через CCW без ε-tolerance считает касание endpoint пересечением. Любое ребро, заканчивающееся на двери/угле стены, ложно триггерит WALL-CROSS.

**Verify:** сегменты `(0,0)-(1,0)` и `(1,0)-(2,1)` (общий endpoint в (1,0)) → возвращает `True` (FALSE POSITIVE). Сравнить с `spatial_runtime.py:211-237` и `movement_system.py:30-55` — там используется strict cross-product sign check.

**Fix:** Добавить ε-tolerance + proper intersection only:
```python
def _segments_intersect(p1, p2, p3, p4, eps=1e-6) -> bool:
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    if ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and \
       ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps)):
        return True
    return False  # no collinear / endpoint touch
```

**Комбо V8-SP-1 + V8-SP-2 = showstopper**: любая карта, где nav edge endpoint совпадает с wall endpoint (на дверях — это норма), крашит compile.

### V8-SP-3 ★★ HIGH — Player `coords=None` + traversal=❌

**Файлы:** `scene_state_manager.py:879`, `player_avatar_service.py:load_state`, `player_target_pipeline.py`

**Цепочка разрыва:**
1. `scene_state_manager.py:879` добавляет player в `npc_positions` ТОЛЬКО если `editor_data.get("player_spawn")` truthy
2. `player_avatar_service.load_state` создаёт `NPCState(npc_id=player_name)` без позиции (NPCState не имеет position field по ADR-0015)
3. `player_target_pipeline.py` извлекает target, но **не эмитит MovementIntent** для non-move intents
4. `npc_positions["player"]` остаётся без `local_position` → `coords=None` → UI/lerp не рисует игрока

**NPI = 86%** = 6/7 акторов с координатами. Player — единственный без позиции.

**Fix:**
1. В `scene_state_manager.initialize_scene` — гарантированно регистрировать player в `npc_positions` с дефолтной позицией (center of tavern)
2. В `player_target_pipeline` — эмитить MovementIntent для `request_service` (NPC подходит к target)
3. Проверить, что ключ `npc_positions` — `"player"` (не player_name "Патрик")

### V8-SP-4 ★★ HIGH — `CROSS_LOC_MATERIALIZE` ломается на dict active_traversals

**Файл:** `backend/app/services/spatial/movement_engine.py:275-279`

```python
for e in scene_state.get("active_traversals", []):
    if e.get("npc_id") == npc_id:
        ...
```

`active_traversals` — это **dict** везде кроме этого места. Итерация dict даёт ключи (строки), `e.get("npc_id")` → `AttributeError: 'str' object has no attribute 'get'`.

**Fix:**
```python
_traversals = scene_state.get("active_traversals", {})
# Если list — итерируем как list; если dict — по .values()
_traversal_items = _traversals.values() if isinstance(_traversals, dict) else _traversals
for e in _traversal_items:
    if e.get("npc_id") == npc_id:
        ...
```

### V8-SP-5 ★★ HIGH — `target_svc` None-check отсутствует

**Файл:** `backend/app/services/spatial/movement_engine.py:257-261`

```python
target_svc = self._resolve_spatial_service(...)
# НЕТ None-check
target_svc.get_node(...)  # AttributeError если target_svc is None
```

Параллельный блок (233-315) проверяет `if current_svc:`. Здесь — нет.

**Fix:**
```python
target_svc = self._resolve_spatial_service(...)
if not target_svc:
    logger.warning(f"target_svc is None for {npc_id}, skipping CROSS_LOC_INTERCEPT")
    continue
```

### V8-SP-6 ★ MEDIUM — `is_movement_blocked` over-restrictive

**Файл:** `backend/app/services/spatial/spatial_runtime.py:203`

```python
if _blocks_walk or obs.get("blocks_los", False):
```

Препятствие, блокирующее LOS но walkable (стеклянная перегородка, занавеска), считается блокирующим движение. NPC не проходит через стеклянные двери.

**Fix:** Убрать `or obs.get("blocks_los", False)` — движение должно проверять только `blocks_walk`.

### V8-SP-7 ★ MEDIUM — `find_path` cache без topology_version

**Файл:** `backend/app/services/spatial/spatial_service.py:536-546`

Cache key `(start, target, overlay_hash, urgency)`. Если walls/obstacles мутируют post-init — cache возвращает stale paths.

**Fix:** Добавить `topology_version` в cache key, инкрементировать при мутации графа.

### V8-SP-8 ★ LOW — `compile_graph` возвращает 4-tuple vs 8-tuple

**Файл:** `backend/app/services/spatial/graph_compiler.py`

Early-exits (строки 66, 173) возвращают `{}, {}, {}, {}` (4-tuple). Happy path (строка 366) — 8-tuple. Type annotation (строка 49) говорит 2-tuple. `build_for_location` (строки 76-89) defensively обрабатывает 4/5/7/8 — не крашится, но `boundary_map` и геометрия пустые → silent pathfinding degradation.

**Fix:** Унифицировать return arity — всегда 8-tuple (заполнять пустыми словарями для early-exit).

### V8-SP-9 ★ LOW — `print()` debug в production

**Файлы:** `movement_engine.py:237,239,432`; `graph_compiler.py:432`; `spatial_service.py:528,531,534,600`

Bypass logger, spam stdout.

**Fix:** Заменить на `logger.debug(...)`.

### V8-SP-10 ★ LOW — `movement_intent` priority по substring в reason

**Файл:** `backend/app/services/spatial/movement_engine.py:147-148,156`

`"schedule" in _reason`, `"flee" in _reason` — fragile. Любой reason с подстрокой "schedule" классифицируется как schedule-priority.

**Fix:** Использовать enum в reason или явное поле `priority_class`.

---

## §2. ВОЛЯ (`will.py`) И АВАТАР

### V8-WL-1 ★★ HIGH — Counter-offer `stealth`/`yield` actions не зарегистрированы

**Файл:** `backend/app/services/will.py:250-256`

```python
return IntentDTO(action="stealth", ...)
return IntentDTO(action="yield", ...)
```

Backend-wide search: `"yield"` — только в `will.py`; `"stealth"` — только как PLAYER_MOVED event mapping. Counter-offer action генерируется, но **нигде не исполняется**. Даже `"flee"` counter-offer — мёртвые данные.

**Fix:** Либо wire `counter_offer.action` к исполнителю (DecisionHub/MovementEngine), либо удалить dead returns для `stealth`/`yield`, оставить только `flee`.

### V8-WL-2 ★★ HIGH — Player pressure ≈ 0.05, WillpowerGate почти не сопротивляется

**Файл:** `backend/app/services/will.py:90-102`

Для `order`/`move`/`player_social`: pressure ≈ 0.05 (identity_deviation=0.05, social_exposure=0.05-0.1). Resistance ≈ 0.05 → COMPLY всегда. ADR «player is not god» нарушен.

**Дополнительно:** `player_avatar_service.py:119-122` комментарий «S-93 AVATAR_RESISTANCE: Пока заглушка». НО `CharacterFilter` (261 lines) реализован и подключён (`npc_orchestration.py:41`) — комментарий устарел.

**Fix:** Поднять player pressure для violence/self_risk/moral_violation до 0.3-0.5. Обновить комментарий.

### V8-WL-3 ★★ HIGH — Avatar `fear`/`willpower` никогда не доходят до WillpowerGate

**Файл:** `backend/app/services/game_loop/__init__.py:677-682`

```python
_live_psyche = {
    "stress": getattr(_avatar_state, "stress", 0.0),
    "fear": getattr(_avatar_state, "fear", 0.0),          # NPCState не имеет 'fear'
    "willpower": getattr(_avatar_state, "willpower", 1.0), # NPCState не имеет 'willpower'
    "emotion": getattr(_avatar_state, "emotion", "NEUTRAL"),
}
```

`NPCState` не имеет `fear` и `willpower` (они на `NPCPersonality` L0). Avatar's fear всегда 0.0, willpower всегда 1.0. WillpowerGate не видит реальные черты avatar'а — использует 0.5 defaults для `identity_rigidity`, `conviction`, `shame`, `aggression`, `curiosity`.

**Fix:** Построить полный `_live_psyche` из `_avatar_state` + CharacterProfile/NPCPersonality, включая все черты.

### V8-WL-4 ★ MEDIUM — Avatar `will_state`/`emotion` десериализуются строками

**Файл:** `backend/app/services/player_avatar_service.py:340, 355`

```python
will_state=data.get("will_state", "free"),
emotion=data.get("emotion", "neutral"),
```

`NPCState.will_state: WillState` typed as enum. Строки проходят сейчас (str-Enum semantics), но сломаются в `verbalization_context.py:149`, `npc_state.py:765,816`, `decision_hub.py:429,827,1967` если avatar state дойдёт до этих потребителей.

Сравнить: `npc_loader.py:627` корректно делает `WillState(will_str)`, `npc_state.py:1021` тоже.

**Fix:**
```python
will_state=WillState(data.get("will_state", "free")),
emotion=_emotion_from_str(data.get("emotion", "neutral")),
```

### V8-WL-5 ★ MEDIUM — `CharacterProfile.values.weights` default-empty отключает CharacterFilter

**Файл:** `backend/app/services/character/character_filter_applicator.py:40`

```python
if _profile.values.weights:
    # apply CharacterFilter
```

Empty weights (default для новых avatars) → filter skipped. New players get NO S-93 resistance until values явно установлены. Код, который устанавливает defaults, отсутствует.

**Fix:** Либо defaults `ValueSet.weights` per archetype при character creation, либо log warning когда filter skipped.

### V8-WL-6 ★ LOW — Missing imports `Dict`, `List` в player_avatar_service

**Файл:** `backend/app/services/player_avatar_service.py:1, 25, 53`

`from __future__ import annotations` (PEP 563) — annotations не evaluated. `Dict`/`List` не импортированы, но используются в аннотации (line 53). Runtime работает; mypy/pyright/`typing.get_type_hints()` упадут.

**Fix:** `from typing import Optional, Dict, List`.

### V8-WL-7 ★ LOW — `compose_pressure_from_tags` dead code

**Файл:** `backend/app/services/will.py:342-371`

Функция определена, но никогда не вызывается. Молча обнулила бы `social_exposure`/`trauma_trigger`/`taboo_intensity` из base_pressure (только 5 из 8 полей propagated).

**Fix:** Удалить или wire в `compute_pressure`.

### V8-WL-8 ★ LOW — Avatar `trauma_markers` не используется WillpowerGate

`NPCState.trauma_markers` существует и сериализуется, но `_live_psyche` не включает его. GAP2 FIX (trauma → rigidity, `will.py:155-162`) bypassed для avatar.

**Fix:** Добавить `trauma_markers` в `_live_psyche` dict.

---

## §3. ПСИХИКА / BreakProgress / DriveResolver

### V8-PSY-1 ★★★ CRITICAL — Trauma mutation pipeline полностью мёртв

**Файлы:** `backend/app/services/npc/state_applicator.py:820`, `break_progress_engine.py:197-221`

```python
# state_applicator.py:820
_chronicle = getattr(state, "_l1_chronicle", None)
if _chronicle is not None:
    _chronicle.commit_tick_buffer(_events, _tick)
else:
    # ADR-O-208: L3-P1. Прямая мутация drives_runtime запрещена.
    logging.getLogger(__name__).warning(...)
```

`NPCState` не имеет `_l1_chronicle` (grep подтверждает — только `npc_dialogue_subscriber` носит его как собственное поле). `else` ветка **всегда** срабатывает. Все trauma drive-mutations (`will_broken`, `humiliated`, `betrayed`, `near_death`) silently dropped.

**Дополнительно:** `compute_mutation` (break_progress_engine.py:210-214) пытается читать `state.psyche.identity_rigidity` — `NPCState` не имеет `psyche` → `hasattr` False → rigidity hardcodes 0.5 → plasticity = 0.5 для всех.

**Fix:**
1. Прикрепить L1Chronicle к StateApplicator (не к state)
2. Передавать `NPCPersonality` в `evaluate_behavior_and_identity`, чтобы willpower читался из `personality.willpower`

### V8-PSY-2 ★★★ CRITICAL — Per-NPC willpower никогда не читается BreakProgressEngine

**Файл:** `backend/app/services/phases/decision.py:55-59`

```python
_willpower = (
    getattr(_npc_state.psyche, "willpower", 50.0)
    if hasattr(_npc_state, "psyche")
    else 50.0
)
```

`NPCState` не имеет `psyche` → `hasattr` False → `_willpower = 50.0` всегда. NPCPersonality.willpower из JSON (Lusya=35, Borko=70, Goran=60) **не используется**. Весь commitment/anti-abuse model работает с одним глобальным значением 50.

Также ломает `decision.py:199`: `elif _fear > 60 and _trust < 0 and _willpower > 40:` — `_willpower > 40` всегда True.

**Fix:** Читать willpower из `state.personality.willpower` (NPCPersonality L0).

### V8-PSY-3 ★★★ CRITICAL — `WillState.BROKEN` permanment, без recovery

**Файл:** `backend/app/services/npc/break_progress_engine.py:153-158`

```python
if stage == "deformation":
    if pressure > BREAK_WILL_BROKEN_PRESSURE_THRESHOLD and state.will_state != WillState.BROKEN:
        will_override = WillState.BROKEN
```

`will_state_override` только устанавливается в `BROKEN`. Никакой код не возвращает `BROKEN → FREE/COERCED/LOYAL`. `identity_integrity` восстанавливается медленно (0.001/tick → 1000+ тиков), но `will_state` остаётся BROKEN навсегда. Once broken, always broken.

**Fix:** Добавить recovery path: при `identity_integrity > BREAK_STAGE_CRACKS` (0.8) и low pressure N тиков → revert `WillState.BROKEN → WillState.FREE` (или COERCED).

### V8-PSY-4 ★★★ CRITICAL — `REACTIVE_URGENCY_THRESHOLD` calibration mismatch

**Файлы:** `backend/app/services/npc/decision_hub.py:727-728`, `app/core/constants.py:114`

```python
# constants.py:114
REACTIVE_URGENCY_THRESHOLD: Final[float] = 0.8  # fear > this → force switch

# decision_hub.py:727-728
fear_value = state.stress if hasattr(state, "stress") else 0.0
force_switch = fear_value > REACTIVE_URGENCY_THRESHOLD
```

`state.stress` на шкале 0-100 (clamped в `__post_init__`). Threshold 0.8 — подразумевает 0-1 fear. Любой stress > 1.0 force-switch'ит intent, bypassing commitment model (`threshold = COMMITMENT_BASE_THRESHOLD * (1 + commitment²×K)`). Pressure accumulator и commitment threshold — dead на практике.

**Fix:** `force_switch = state.stress > 80.0` (или `state.stress / 100.0 > REACTIVE_URGENCY_THRESHOLD`).

### V8-PSY-5 ★★★ CRITICAL — Persistence round-trip data loss

**Файлы:** `backend/app/services/npc/npc_loader.py:263-307` vs `npc_state.py:write_to_legacy`

`write_to_legacy` пишет поля, но `_RUNTIME_PSYCHE_KEYS` / `_RUNTIME_TOP_LEVEL_KEYS` их не включают → `_apply_runtime_overlay` дропает на каждом save→reload цикле:

| Поле | Written at | Lost on reload |
|---|---|---|
| `psyche["recent_failures"]` | npc_state.py:819 | resets to 0 |
| `psyche["life_project"]` | npc_state.py:821 | resets to `core_orientation` (L0) |
| `psyche["life_project_state"]` | npc_state.py:822 | resets to "ACTIVE" — crises self-heal |
| `npc_dict["affective_memory"]` | npc_state.py:902 | SEL Baseline lost |
| `npc_dict["social_input_ema"]` | npc_state.py:904 | social pressure integrator lost |
| `npc_dict["behavior_mask"]` | decision.py:223 | resets to NONE |
| `npc_dict["behavior_mask_intensity"]` | decision.py:224 | resets to 0.0 |

Дополнительно: `NPCStateAdapter.from_legacy` никогда не читает `behavior_mask` → mask сбрасывается даже mid-session после `from_legacy(...)`.

**Fix:** Добавить поля в `_RUNTIME_PSYCHE_KEYS` и `_RUNTIME_TOP_LEVEL_KEYS`. Добавить чтение `behavior_mask` в `from_legacy`.

### V8-PSY-6 ★★ HIGH — BehaviorMask FAKE_SUBMISSION / BETRAYAL никогда не триггерятся

**Файл:** `backend/app/services/phases/decision.py:188-208`

```python
_rel_cache = getattr(_npc_state, "relationship_cache", {})
_player_rel = _rel_cache.get("player", {}) if isinstance(_rel_cache, dict) else {}
_trust = _player_rel.get("trust", 0.0)
_fear = _player_rel.get("fear", 0.0) * 100
_has_hidden = bool(getattr(_npc_state, "hidden_truth", None))
```

`from_legacy` всегда ставит `relationship_cache={}` → `_player_rel={}` → `_trust=0`, `_fear=0`. FAKE_SUBMISSION (`elif _fear > 60 and _trust < 0 and _willpower > 40`) никогда не срабатывает. BETRAYAL (`elif _trust < -50 and _fear < 30 and _has_hidden`) требует `hidden_truth` на NPCState — не существует → всегда None → никогда. Только COLLAPSE (от `will_state == BROKEN`) активируется.

**Fix:** Hydrate `relationship_cache["player"]` из RelationshipStore перед BehaviorMask logic.

### V8-PSY-7 ★★ HIGH — `support_present` всегда False

**Файл:** `backend/app/services/phases/decision.py:94`

```python
support_present=getattr(_npc_state, "support_present", False)
```

`NPCState` не имеет `support_present`. BreakProgressEngine's support mechanic (`BREAK_SUPPORT_PRESSURE_REDUCTION = 20.0`) — dead input. Allies никогда не уменьшают break pressure.

**Fix:** Читать из реального источника (NPCs в той же локации с positive relationship).

### V8-PSY-8 ★★ HIGH — `compute_mutation` возвращает `[]` вместо `{}`

**Файл:** `backend/app/services/npc/break_progress_engine.py:197-206`

```python
def compute_mutation(state: "NPCState", trauma_type: str) -> Dict[str, float]:
    ...
    if not drive_deltas:
        return []  # ← list literal, но сигнатура Dict[str, float]
```

Caller `state_applicator.py:804` делает `if _drive_mutations:` — falsy для обоих, не падает. Но type contract нарушен, downstream `.items()` упадёт если check убрать.

**Fix:** `return {}`.

### V8-PSY-9 ★★ HIGH — `NPCIdentityL1.overlay_drives` dead code

**Файл:** `backend/app/models/npc_state.py:393-402`

Метод определён, но нет callers (grep across backend). L1 crystallized traits никогда не доходят до DecisionHub через этот метод. DecisionHub получает `effective_drives` от `DriveResolver.resolve_drives(profile, beliefs)` — только L0 + L2.5(beliefs), не L1 traits.

**Fix:** Wire `overlay_drives` в `DriveResolver` или удалить.

### V8-PSY-10 ★★ HIGH — `life_engine.py:2228` читает root-level stress — всегда 0

**Файл:** `backend/app/services/npc/life_engine.py:2228`

```python
_stress = npc.get("stress", 0.0)
if _threat > 0.3 or _stress > 50:
```

Stress лежит на `npc["psyche"]["stress"]` (write_to_legacy:815). Root-level `npc["stress"]` никогда не устанавливается → `_stress = 0.0` всегда. GAP9 check (NPC can't sleep when stressed) срабатывает только на threat, не на stress. Тот же баг в `mvp_tavern_controller.py:110`.

**Fix:** `_stress = npc.get("psyche", {}).get("stress", 0.0)`.

### V8-PSY-11 ★★ HIGH — `gregariousness` всегда 0.5 — homeostasis setpoint broken

**Файлы:** `life_engine.py:734-738`, `npc_tick_pipeline.py:425-428`

```python
_psyche = getattr(state_l2, "psyche", {})
_greg = _psyche.get("gregariousness", 0.5) if isinstance(_psyche, dict) else 0.5
```

`NPCState` не имеет `psyche` → `_psyche = {}` → `_greg = 0.5` всегда. Ни один NPC config не устанавливает `gregariousness` (grep across `config/` — 0 matches). `pressure_translator.translate_kernel_to_context(gregariousness=0.5)` — у всех NPC идентичный social homeostasis setpoint.

**Fix:** Перенести `gregariousness` на `NPCPersonality`, добавить в JSON config.

### V8-PSY-12 ★★ HIGH — Will engine работает только для player avatar

**Файлы:** `app/services/will.py:131`, `app/services/phases/input.py:120`

`compute_willpower` (Cumulative Strain Model) вызывается только в `phases/input.py` и только для `player_dict.get("psyche", {})`. Регулярные NPC никогда не проходят через Will engine. Их `will_state` меняется только через:
- BreakProgressEngine → BROKEN (one-way, см. V8-PSY-3)
- Direct trauma application (dead, см. V8-PSY-1)

NPC `will_state` заморожен в `FREE` пока не hit BROKEN threshold.

**Fix:** Запустить Will engine для всех NPC (или документировать что Will только для player).

### V8-PSY-13 ★ MEDIUM — `affective_decay_handler` не decays `stress`

**Файл:** `backend/app/services/affective/affective_decay_handler.py:81-84`

```python
payload=EmotionPayload(
    stress_delta=0.0,  # stress не decays здесь
    emotion_delta=0.0,
    emotion_tag=new_emotion,
    affective_load=new_load,
),
```

Только `affective_load` decays (5%/tick). `stress` decays отдельно `life_engine.recover_stress_tick`, который мутирует `npc_dict["psyche"]["stress"]` напрямую. Две параллельные системы stress-decay (NPCState vs legacy dict) — risk drift если load/save timing misalign.

**Fix:** Консолидировать stress decay в `affective_decay_handler` или задокументировать two-path design.

### V8-PSY-14 ★ MEDIUM — `physiology_decay_handler._get_statuses` читает не туда

**Файл:** `backend/app/services/combat/physiology_decay_handler.py:286-288`

```python
def _get_statuses(npc: NPCStateSnapshot) -> list:
    return npc.get("statuses", [])
```

Statuses хранятся на `npc["body_state"]["statuses"]` (`BODY_STATE_HEALTHY` в npc_state.py:83, `state_applicator.py:882,885`). Root-level read возвращает `[]` всегда → `stagger` и `unconscious` statuses никогда не удаляются decay'ем.

**Fix:** `return npc.get("body_state", {}).get("statuses", [])`.

### V8-PSY-15 ★ MEDIUM — Reaction layer одномерный (только stress)

**Файлы:** `backend/app/services/reaction/reaction_rules.py`, `npc/domain_phases.py:239`

```python
composure = 1.0 - state_for_llm.stress / 100.0
```

Единственный psyche input. `fear`, `will_state`, `affective_load`, `behavior_mask` — игнорируются. NPC с stress=0 но fear=100 никогда не роняет предметы, никогда не прерывает взаимодействия.

**Fix:** Расширить composure формулу: `composure = 1.0 - (stress/100 * 0.4 + fear * 0.4 + affective_load * 0.2)`.

### V8-PSY-16 ★ MEDIUM — Direct emotion string assignment bypasses enum

**Файл:** `backend/app/services/phases/decision.py:86`

```python
_npc_state.emotion = "fearful" if _max_fear > 0.5 else "angry"
```

`NPCState.emotion: EmotionTag` typed as enum. Raw string работает только потому что `write_to_legacy:910` делает `_emo.value if hasattr(_emo, "value") else _emo` и `_emotion_from_str` handles strings on read. Brittle — любой `state.emotion.value` без `hasattr` check крашнется.

**Fix:** `_npc_state.emotion = EmotionTag.FEARFUL if _max_fear > 0.5 else EmotionTag.ANGRY`.

### V8-PSY-17 ★ MEDIUM — Synthetic psyche dict reconstruction drifts

**Файлы:** `phases/affective.py:109-114`, `phases/integration.py:158-163`

```python
psyche = {
    "fear": _drives_projection.get("fear", 0.25),
    "control": _drives_projection.get("control", 0.25),
    "significance": _drives_projection.get("significance", 0.25),
    "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
}
```

Hand-built dict передаётся в `integrate_affective_pressure`. Не включает `stress`, `affective_load`, `identity_integrity`, `pressure_resistance`, `recent_failures`, `trauma_markers`. Любое расширение integrator, читающее эти поля, получит nothing.

**Fix:** Стандартизировать psyche dict builder, использовать во всех местах.

### V8-PSY-18 ★ LOW — Double-truth writes в `decision.py:215-224`

Пишет `npc_dict["identity_integrity"]`, `npc_dict["pressure_resistance"]`, `npc_dict["will_state"]`, `npc_dict["behavior_mask"]`, `npc_dict["behavior_mask_intensity"]` в root. Но `write_to_legacy` (вызванный на line 128) пишет те же поля в `psyche` sub-dict. `from_legacy` читает только из `psyche`. Root-level writes — dead.

**Fix:** Удалить root-level writes, оставить только `psyche` sub-dict.

### V8-PSY-19 ★ LOW — `age_drives` никогда не вызывается

**Файл:** `backend/app/models/npc_state.py:500-518`

Функция определена для инкремента `tick_age` и prune expired drives. Grep — 0 callers в `app/`. `temporary_drives` никогда не expire (tick_age stays 0).

**Fix:** Wire `age_drives` в tick pipeline (например, в `life_engine.tick`).

---

## §4. ПАМЯТЬ / DecisionHub

### V8-MEM-1 ★★★ CRITICAL — `run_decay_and_resonance` никогда не вызывается в runtime

**Файл:** `backend/app/services/memory/working_memory_tick.py:102`

Функция определена, но grep показывает — только sandbox test вызывает её. Decay никогда не запускается, resonance никогда не запускается, `identity_weights` никогда не применяются. Весь L3 Identity cascade — функционально мёртв в production.

**Fix:** Wire `run_decay_and_resonance` в tick pipeline (например, `phases/memory.py` Block 4 или новый Block после Block 3).

### V8-MEM-2 ★★★ CRITICAL — `CommunicationIntent.target_id` не propagates → attack windup сломан

**Файлы:** `backend/app/services/npc/decision_hub.py:360-367`, `phases/post_decision.py:122`

`_build_communication` никогда не устанавливает `CommunicationIntent.target_id` (defaults to None). `post_decision.py:122` читает `getattr(intent, "target_id", "")` → returns None → `if _actor_id and _target_id:` False → **ATTACK windup никогда не создаётся**. Combat windup system сломан.

**Fix:** `_build_communication` должен принимать и forward `intent_target` как `target_id`.

### V8-MEM-3 ★★★ CRITICAL — `assess_beliefs` dead code, belief pipeline мёртв

**Файл:** `backend/app/services/memory/memory_manager.py:678`

`assess_beliefs` (SemanticTagEvidenceMapper → CoherenceBeliefAggregator) никогда не вызывается из `apply()`. Единственный belief path, который работает — `BeliefCrystallizationEngine` через `L1Chronicle` (отдельный path в `phases/integration.py:398-422`).

**Fix:** В `MemoryManager.apply()` после decay: `if self._belief_aggregator: self._belief_aggregator.assess(self._working, self._beliefs)`.

### V8-MEM-4 ★★ HIGH — Scale mismatch в `evaluate_behavior_and_identity`

**Файл:** `backend/app/services/phases/decision.py:67-79`

```python
_trust_pressure = max(0.0, (0.5 - _min_trust)) * 20.0
```

`RelationshipStore` использует шкалу `-100..100` (`relationship_store.py:22`). Код трактует как `-1..1` с `0.5` neutral. Real `trust=0` (neutral) → pressure=10 (half of max 20). BreakProgressEngine over-pressure → NPCs snap to BROKEN слишком быстро.

**Fix:** Делить RelationshipStore values на 100, ИЛИ переписать pressure formula для -100..100 scale (neutral=0).

### V8-MEM-5 ★★ HIGH — `get_weights_for_decision.recent_pressure` фильтрует по wrong field

**Файл:** `backend/app/services/memory/memory_manager.py:630-638`

```python
recent_pressure = [
    e for e in buffer
    if e.npc_id == npc_id  # НЕ фильтрует по target_id tid
]
```

`recent_pressure` идентичен для каждого target — просто сумма из всего buffer'а NPC. Target-specific pressure — fake.

**Fix:** `if e.target_id == tid or e.actor_id == tid`.

### V8-MEM-6 ★★ HIGH — `tick_decisions` dead code, hardcoded modifiers dropped

**Файлы:** `backend/app/services/npc/life_engine.py:601, 770-773`

`tick_decisions` — dead code (только sandbox test вызывает). Внутри: `social_modifiers=None, reputation_modifiers=None, reflex_constraints=None` hardcoded — preloaded modifiers из `assemble_preloaded_data` silently dropped.

**Fix:** Wire `tick_decisions` в production ИЛИ удалить и задокументировать что decision идёт через `phases/decision.py`.

### V8-MEM-7 ★★ HIGH — `_identity_cache` не персистится, теряется на restart

**Файл:** `backend/app/services/memory/memory_manager.py:42-45`

In-memory only. На restart все накопленные L3 traits — LOST. Комментарий говорит "in-memory", но не warn'ит о restart-loss.

**Fix:** Персистировать `_identity_cache` в SQLite (отдельная таблица `identity_cache_entries`).

### V8-MEM-8 ★ MEDIUM — `detect_npc_patterns` возвращает `None` вместо `[]`

**Файл:** `backend/app/services/memory/resonance_engine.py:335`

```python
def detect_npc_patterns(...) -> List[ResonancePattern]:
    ...
    if raw < threshold:
        return None  # ← signature: List
```

Caller итерирует result → ломается на `None`.

**Fix:** `return []`.

### V8-MEM-9 ★ MEDIUM — `AgentAction._get_rel_value` dead code

**Файл:** `backend/app/services/npc/decision_hub.py:165`

Static method, superseded by `DecisionHub._get_rel_value` (instance, line 307). Никогда не вызывается.

**Fix:** Удалить.

### V8-MEM-10 ★ MEDIUM — `save_event_memories_batch` dead code

**Файл:** `backend/app/services/memory/sqlite_store.py:250`

Никогда не вызывается. `apply()` вызывает `save_event_memory` one-by-one. Performance loss на больших buffer'ах.

**Fix:** Wire batch save в `apply()` для performance ИЛИ удалить.

### V8-MEM-11 ★ MEDIUM — `pattern_detector.detect` raises ValueError, kills integration phase

**Файлы:** `backend/app/services/memory/pattern_detector.py:77-80`, `phases/integration.py:398`

```python
def detect(self, event):
    if event.source_id in {"unknown", "", None}:
        raise ValueError(...)
```

Вызывается из `integration.py:398` без try/except. Один bad `TraitDriftEvent` убивает всю integration phase.

**Fix:** Wrap call в try/except, логировать и continue.

### V8-MEM-12 ★ MEDIUM — `load_narrative_from_sqlite` non-cumulative decay

**Файл:** `backend/app/services/memory/memory_manager.py:260`

```python
_mem.decayed(game_days=1.0)  # applied EVERY load
```

Decay применяется на каждом load, но **не пишет decayed version обратно в SQLite**. Storage остаётся на original stage; тот же 1-day decay reapplied каждый tick (non-cumulative).

**Fix:** Либо писать decayed version обратно, либо трекать last_decay_day в storage.

### V8-MEM-13 ★ MEDIUM — `detect_resonance` игнорирует npc_id, возвращает campaign-wide patterns

**Файлы:** `memory_manager.py:707-726`, `working_memory_tick.py:122-124`

`detect_resonance` возвращает ОДИН pattern list для всей campaign (actor=player). `post_decision.py:124` применяет те же resonance traits ко всем active NPC. Per-NPC resonance отсутствует.

**Fix:** `detect_resonance(npc_id=...)` — фильтровать buffer по `f"{campaign_id}:{npc_id}"`.

### V8-MEM-14 — N14 cascade (4 шага, всё ещё не применено)

**Step 1:** `memory_manager.py:717` — `detect_resonance` читает bare `campaign_id` buffer (всегда пусто)
**Step 2:** `npc_state.py:302-305` — `to_identity_weight` tags vocabulary не совпадает с `EventSemanticTagger` output (`social:aggression` не matches `aggression`) → всегда None
**Step 3:** `resonance_engine.py:154,186,224,327` — substring match, пропускает новые event types
**Step 4:** `working_memory_tick.py:124` — применяет `resonance` (всегда `[]`), не `identity_weights`

**Fix:** Все 4 шага последовательно (см. v7 §13 N14 fix).

### V8-MEM-11 (v7) ★ MEDIUM — PromotionEngine templates — всего 6

**Файл:** `backend/app/services/memory/promotion_engine.py:33-42`

6 templates: positive+dialogue, positive, negative+dialogue, negative, combat, trade. Нет: help, gift, theft, observation. События, не попадающие в 6 шаблонов, никогда не сжимаются. narrative_cache растёт линейно.

**Fix:** Добавить 4 шаблона: `help`, `gift`, `theft`, `observation`.

### V8-DEC-09 ★ MEDIUM — CPS-09 duplicate ADR-036 block

**Файл:** `backend/app/services/npc/decision_hub.py:450-471`

Первый блок читает `event.semantic_action`/`event.target_id`, второй перезаписывает их из `event.payload`. Первый блок — dead code. `action_to_intent` импортирован дважды (lines 452, 460).

**Fix:** Удалить первый блок (450-456), оставить только payload-based extraction.

### V8-DEC-10 ★ LOW — CPS-10 target_id assert не добавлен

**Файл:** `backend/app/services/npc/decision_hub.py:1429-1440`

Логика `_effective_tid` с payload fallback работает корректно. Но assert на consistency (`event.target_id != event.payload["target_id"]`) не добавлен.

**Fix:**
```python
if (event.target_id 
    and event.payload.get("target_id") 
    and event.target_id != event.payload["target_id"]):
    logger.warning(f"target_id mismatch: {event.target_id} vs {event.payload['target_id']}")
```

### V8-DEC-11 ★ MEDIUM — CPS-11 EventBus event loss on exception

**Файл:** `backend/app/services/events/event_bus.py:114-123`

```python
try:
    result = handler(event)
except Exception as e:
    logger.error(...)
    # NO retry, NO DLQ, NO error counter
```

Handler exceptions caught, logged, swallowed. События теряются.

**Fix:** Добавить retry (1-2 attempts), DLQ (dead-letter queue для failed events), error counter.

---

## §5. MVP EPISTEMIC CHAIN

### V8-MVP-1 ★★★ CRITICAL — `logger` не определён в MvpTavernController

**Файл:** `backend/app/services/social/mvp_tavern_controller.py:98, 104`

```python
logger.error(...)   # line 98 — НЕТ import logging
logger.warning(...) # line 104 — НЕТ logger = logging.getLogger(__name__)
```

NO `import logging` в файле. NO `logger = logging.getLogger(__name__)`.

**Trigger:** Line 98 fires если `factions.json` не найден (FileNotFoundError caught). Line 104 fires когда `event.payload.get("snapshot")` falsy.

**Reproduce:** `python -c "... c.on_tick_completed(E())"` → `NameError: name 'logger' is not defined`.

**Mitigation:** `event_bus.py:119-123` оборачивает subscribers в try/except → tick не падает, но `on_tick_completed` **silently fails every tick**.

**Effect:** FateTracker, DilemmaEngine, SocialFabric baseline **никогда не обновляются в production**. End-Screen `npc_fates` пустой.

**Fix (1 минута):**
```python
# В начало файла
import logging
logger = logging.getLogger(__name__)
```

### V8-MVP-2 ★★★ CRITICAL — M-02b не применён, EvaluationEngine не проверяет discovered_secrets

**Файл:** `backend/app/services/social/evaluation_engine.py:49`

```python
if belief and belief.belief_value == BeliefValue.TRUE and confidence >= 0.8:
    secrets_identified += 1
```

**НЕ** `secret.is_discovered`, **НЕ** `secret_id in truth.discovered_secrets`. Evaluation — чисто belief-based (confidence >= 0.8).

**Проблема:** Beliefs обновляются только через `update_from_evidence`, а evidence добавляется только при BLACKMAIL (V8-MVP-7). Игрок, раскрывший все 16 секретов через чистый DIALOGUE, получит «0 identified» на End-Screen.

**Canary test status:** `test_end_screen_api.py` PASSES для BLACKMAIL (1/16 identified). DIALOGUE-only path не тестируется.

**Fix:**
```python
if (secret_id in truth.discovered_secrets) or \
   (belief and belief.belief_value == BeliefValue.TRUE and confidence >= 0.8):
    secrets_identified += 1
```

### V8-MVP-7 ★★★ CRITICAL — M-07+M-08 не применён в caller, DIALOGUE без target не обрабатывается

**Файлы:** `backend/app/services/game_loop/__init__.py:1685`, `player_cognition/action_semantic_resolver.py:49-100`

`action_consequence_compiler.py:85-95` HAS DIALOGUE handler ✓. НО:

```python
# game_loop/__init__.py:1685
if self.mvp_controller and getattr(shared_context, "player_target_id", None):
    self.mvp_controller.action_compiler.process_action(_action)
```

Gate на `player_target_id` не убран. Если игрок говорит «Борко подглядывает» без выбора target — `process_action` не вызывается.

Дополнительно: `action_semantic_resolver.py:49-100` `_extract_secret_id` требует non-None `target_id` для match любого secret.

**Effect:** DIALOGUE without target NEVER reaches `process_action`. End-Screen для чистого dialogue playthrough — 0/16 identified.

**Fix:**
1. Убрать gate `getattr(shared_context, "player_target_id", None)` в `game_loop/__init__.py:1685`
2. Рефакторить `_extract_secret_id` для работы с `target_id=None` (search all NPCs' secrets by keyword)

### V8-MVP-3 ★★ HIGH — End-Screen API не expose fate/contradiction fields

**Файл:** `backend/app/api/routes.py:381-389`

`/api/game/end_screen/{campaign_id}` возвращает ТОЛЬКО: `score, secrets_total, secrets_identified, secrets_misidentified, secrets_missed, methods_used`. НЕ expose: `end_screen.npc_fates`, `end_screen.contradictions`, `faction_alignments`, `social_fabric_deltas`.

**Effect:** Даже если trackers работали бы, frontend End-Screen не отрисует fate/contradiction sections.

**Fix:**
```python
return {
    "score": end_screen.score,
    "secrets_total": ...,
    "secrets_identified": ...,
    "npc_fates": [f.to_dict() for f in end_screen.npc_fates],  # NEW
    "contradictions": [c.to_dict() for c in end_screen.contradictions],  # NEW
    "faction_alignments": end_screen.faction_alignments,  # NEW
    "social_fabric_deltas": end_screen.social_fabric_deltas,  # NEW
    ...
}
```

### V8-MVP-4 ★★ HIGH — `DilemmaEngine.register_dilemma` никогда не вызывается в production

**Файл:** `backend/app/services/social/dilemma_engine.py:18`

`register_dilemma` только вызывается из `tests/test_p7_07_dilemma_engine.py:33`. В production никто не регистрирует dilemmas.

**Effect:** `check_triggers` (called from `on_tick_completed:117`) всегда возвращает `[]` потому что `_dilemmas` dict пуст. DilemmaEngine effectively non-functional.

**Fix:** Wire `register_dilemma` к production triggers (например, из `truth_state_tavern.json` dilemma definitions).

### V8-MVP-5 ★★ HIGH — `FateTracker.trigger_fate` никогда не вызывается в production

**Файл:** `backend/app/services/social/fate_tracker.py:50`

`trigger_fate` только из tests. В production никто не trigger'ит fate outcomes.

**Effect:** `fate_state.resolved_fate` всегда None → `end_screen_builder.py:29` `if fate_state.resolved_fate:` пропускает ВСЕХ NPCs → `npc_fates` list всегда пуст.

**Fix:** Wire `trigger_fate` к production triggers (CRITICAL trajectory + world events).

### V8-MVP-6 ★★ HIGH — FateTracker validators reject unclamped inputs

**Файл:** `backend/app/services/social/fate_tracker.py:22-25`

```python
if not (0.0 <= stability <= 1.0): raise ValueError
if not (0.0 <= threat <= 1.0): raise ValueError
```

Caller `mvp_tavern_controller.py:110-111`:
```python
stability = 1.0 - (float(npc.get("stress", 0)) / 100.0)
threat = float(npc.get("perceptual_kernel", {}).get("threat_gradient", 0.0))
```

No clamping. Если `stress > 100` (legacy saves) → stability<0 → ValueError. Если `threat_gradient > 1.0` (unbounded) → ValueError.

**Effect:** ValueError caught by EventBus → silent tracker failure for that tick.

**Fix:**
```python
stability = max(0.0, min(1.0, 1.0 - (float(npc.get("stress", 0)) / 100.0)))
threat = max(0.0, min(1.0, float(npc.get("perceptual_kernel", {}).get("threat_gradient", 0.0))))
```

### V8-MVP-8 ★ MEDIUM — Operator precedence в ActionSemanticResolver

**Файл:** `backend/app/services/player_cognition/action_semantic_resolver.py:91`

```python
if "убил" in raw_lower or "первый" in raw_lower and "убийство" in raw_lower:
```

`and` binds tighter than `or` → parses as `("убил") or ("первый" and "убийство")`. Single keyword "убил" matches too broadly для `shadow_first_kill`.

**Fix:** `if "убил" in raw_lower or ("первый" in raw_lower and "убийство" in raw_lower):`

### V8-MVP-9 ★ LOW — SocialFabricTracker.set_baseline duplicate guard слишком strict

**Файл:** `backend/app/services/social/social_fabric_tracker.py:23-24`

Raises ValueError на duplicate baseline. `mvp_tavern_controller.py:133` вызывает `set_baseline` для обоих (id1,id2) и (id2,id1). Если `on_tick_completed` fires на tick_number==1 multiple times (campaign reset), ValueError crashes subscriber.

**Fix:** Idempotent set_baseline — skip if already set for this pair.

### V8-MVP-10 ★ LOW — `init_campaign` exception handling слишком узкий

**Файл:** `backend/app/services/social/mvp_tavern_controller.py:97`

```python
except FileNotFoundError:
```

Только один тип. Если factions.json corrupted (JSONDecodeError) или unreadable (PermissionError) — exception propagates → `init_campaign` fails → `truth_state` is None → все downstream calls fail.

**Fix:** `except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:`.

### V8-FC-01 ★ LOW — N12 partial: test_world_continuity ещё English IDs

**Файл:** `backend/tests/test_world_continuity.py:20, 23`

Использует `"thieves_guild"` (English), хотя factions.json и другие тесты используют `гильдия_воров` (Russian).

**Fix:** Заменить на `гильдия_воров`.

### V8-FC-02 ★ LOW — N13 Shadow schedule не документирован

**Файл:** `config/npc/individuals/shadow.json:55-58`

`"06:00-18:00": "sleeping"` — намеренно (nocturnal вор), но нет комментария в JSON. SLP-01 тест для 22:00 миграции не упоминает, что Shadow не должна мигрировать ночью.

**Fix:** Добавить комментарий в JSON: `"//_note": "Shadow — nocturnal, спит днём 06:00-18:00"`. Обновить SLP-01 тест.

### V8-PER-12 ★ MEDIUM — CPS-12 line_of_sight без coords (latent)

**Файлы:** `backend/app/services/npc/perception_filter.py:143`, `spatial/spatial_runtime.py:284-302`

```python
# perception_filter.py:143
if not line_of_sight(distance, scene_state):
    return False
# Без ax/ay/bx/by

# spatial_runtime.py:284-302
def line_of_sight(distance, scene_state, ax=0.0, ay=0.0, bx=0.0, by=0.0) -> bool:
    if ax != 0.0 or ay != 0.0 or bx != 0.0 or by != 0.0:
        if not is_line_of_sight_clear(ax, ay, bx, by, scene_state):
            return False
    # default 0.0 → wall check SKIPPED
```

Только lighting/density/danger check запускается. NPC видят сквозь стены.

**Note:** `extract_scene_for_npc` (spatial_runtime.py:384-386, 398-400) ПЕРЕДАЁТ real coordinates. Так NPC↔NPC perception в scene extraction имеет wall check; но EventBus-driven `filter_perceiving_npcs` path — НЕ имеет.

**Fix:**
```python
# perception_filter.py:143
if not line_of_sight(distance, scene_state, 
                     ax=observer_x, ay=observer_y, 
                     bx=target_x, by=target_y):
    return False
```

---

## §11. ТИК / ОРКЕСТРАТОР (v8.1 — новый аудит)

### V8-TICK-1 ★★★ CRITICAL — `NameError _movement_req` в `_process_player_dm_action`

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:604-749`

```python
# line 618:
if _movement_req:   # ← переменная нигде не объявлена в этом методе
# строки 641-642:
_sem_action, _sem_target = ...  # ← тоже не определены
```

Единственное определение `_movement_req` — в `phase_1_input.py:184` (local to `resolve_player_intent()`), возвращается как `movement_request` на `IntentResolution` (`models/will.py:97`).

**Production reachability:** НЕТ production caller'а `tick_orchestrator.execute()` с `dm_ctx=...`. Legacy bridge в `tick_orchestrator.py:371-378` создал бы dm_ctx-carrying InterventionEvent, но никто не вызывает. Код сломан, но сломанный path — мёртв в production.

**Архитектурный smell:** `_process_player_dm_action` (604-749) — рефактор-артефакт. Lines для извлечения переменных потеряны. Sibling `_process_player_action` (751+) — рабочий path, используется в `npc_orchestration.py:148-158`.

**Fix:** Удалить `_process_player_dm_action` полностью ИЛИ восстановить извлечение переменных:
```python
_movement_req = getattr(_intent_res, "movement_request", None)
_sem_action = getattr(_params, "semantic_action", None)
_sem_target = getattr(_params, "semantic_target", None)
```

### V8-TICK-2 ★★ HIGH — DRF scoring overlay только для movement intents

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:522-551`

`_run_core_phases` НЕ вызывает `_apply_drf_scoring_overlay` напрямую. Единственный caller — `phases/movement_bridge.py:89`, который запускается через `process_movement_intents` (`tick_orchestrator.py:1249`, внутри `_phase_5_decision`).

**Эффект:** Overlay применяется ТОЛЬКО к movement intents, проходящим через Movement Bridge. Non-movement intents (dialogue, observation, social) **bypass DRF scoring**. Противоречит docstring в `orchestrator.py:1447`: «Unified overlay for idle and player paths».

**Fix:** Вызывать `_apply_drf_scoring_overlay` из `_run_core_phases` для ВСЕХ intents (или обновить docstring, что это movement-only).

### V8-TICK-3 ★★ HIGH — Двойной счётчик времени (player ticks drift)

**Файлы:** `tick_orchestrator.py:1306-1355` (`_advance_idle_time`), `time_advance.py:23-105` (`advance_game_time`)

- `_advance_idle_time` — каждый тик, `+GAME_TICK_INTERVAL_SECONDS = 10`
- `advance_game_time` — из `dm_phase.py:161` (player path), `+5-30s` per action

Для player ticks: time = `action_delta + 10s`. Для idle: только `+10s`. **Player ticks drift ~+10s/tick быстрее.**

**INV-TIME-FREEZE** (`tick_orchestrator.py:1334`) ловит только backward/stuck time, не double-counting.

**Desync claim FALSE:** обе функции обновляют и `game_time_seconds`, и `environment.time_of_day` consistently. `game_time_seconds` vs `time_of_day` divergence нет.

**Fix:** Skip `_advance_idle_time` для player turns ИЛИ убрать `advance_game_time` из `dm_phase.py:161` и делегировать всё `_advance_idle_time`.

### V8-TICK-4 ★ MEDIUM — `UnboundLocalError state_l2` в hearing branch NpcTickPipeline

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:170`

Hearing branch (156-184) берётся когда `_is_player_turn and not (_los or _is_attack_target)` — NPC в player's tick, но вне LoS.

```python
# line 168-170:
_mem_evt = apply_perception_memory(None, state_l2, ...)
#                              ↑↑↑↑↑↑↑↑
# state_l2 впервые присваивается на line 200 (в NORMAL branch)
```

`NameError: name 'state_l2' is not defined`. Поймано try/except (180-183) → логирует `[MEMORY] hearing perception apply failed for {npc_id}` и `continue`.

**Эффект:** NPC которые слышат, но не видят player, **никогда не получают hearing perception в memory** в player turns.

**Fix:** Поднять `state_l2 = load_l2_state_from_runtime_dict(...)` перед line 156, ИЛИ hearing branch должен грузить свой state_l2.

### V8-TICK-5 ★ MEDIUM — `TypeError` в directive path для emotion["stress"]

**Файлы:** `backend/app/services/game_loop/tick_orchestrator.py:675, 863`

```python
_npc_state.setdefault("emotion", {})["stress"] = ...
```

`npc["emotion"]` обычно STRING (`npc_loader.py:659` loads as `_emotion_from_str(...)`, `life_engine.py:1212` ставит `"neutral"`, `commit_phase.py:68` пишет `frame.emotion_tag`).

`setdefault("emotion", {})` возвращает существующую строку → `"string"["stress"] = X` → **TypeError**. Поймано `try/except` (709-713, 879-883) → `[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed`.

**Эффект:** Aborts inline application `stress_delta`, `fear_delta` (social_stats["fear_of_player"], читается в `local_causal_solver.py:355`), `shock_impulse` (body_state). Канонический `psyche["stress"]` обновляется через delta_buffer → StateApplicator (orchestrator.py:825), но `fear_of_player` и `shock_impulse` теряют inline fast-path updates.

**Fix:** Заменить на канонический write:
```python
psyche = _npc_state.setdefault("psyche", {})
psyche["stress"] = max(0, min(100, psyche.get("stress", 0) + delta.payload.stress_delta))
```
ИЛИ убрать inline write полностью (delta_buffer уже обрабатывает stress через StateApplicator).

### V8-TICK-6 ★ MEDIUM — Phase exception leaks partial state

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:467-474`

```python
try:
    _run_core_phases(ctx)
except Exception:
    return TickResultDTO(status="error", final_scene_state=None)
```

Caller `npc_orchestration.py:174` проверяет `if _tick_result.final_scene_state is not None` → commit skipped.

НО `shared_context.scene_state` — тот же dict, что `ctx.scene_state` (passed at orchestrator.py:399). Mutations уже применённые (time advance в phase 0.5, scene_changes через `_apply_with_shadow_observation` в phase 0) **persist** в `shared_context.scene_state` хотя commit был пропущен → следующий тик начинается с partially-advanced time/state. Time может продвинуться +10s без NPC memory/decision updates committing.

**Fix:** На tick failure — rollback `shared_context.scene_state` mutations (deep-copy snapshot at start, restore on error).

### V8-TICK-7 ★ LOW — Per-claim import inside tight loop (perf)

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:1472`

```python
from app.services.drf_bus import _DRF_PRESSURE_WEIGHTS  # INSIDE per-claim loop
```

Re-imported for every claim of every NPC intent per tick. Должно быть hoisted to module level.

**Fix:** Перенести import в начало файла.

---

## §12. NPC↔NPC SOCIAL (v8.1 — новый аудит)

### V8-SOC-1 ★★★ CRITICAL — NPC↔NPC attack имеет нулевые социальные последствия

**Файл:** `backend/app/services/events/social_subscriber.py:33-47`

```python
_SOCIAL_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_INTERACTS,
    EventType.PLAYER_SPOKE,
    EventType.PLAYER_ATTACKED,
    EventType.PLAYER_ATTACKS,
    EventType.PLAYER_ATTACK,
    EventType.PLAYER_INSULTS,
    EventType.PLAYER_THREATENS,
    EventType.THEFT,
    EventType.COMBAT,
    EventType.HELP,
    EventType.INTIMIDATION,
    EventType.BETRAYAL,
    EventType.SAVED_LIFE,
]
```

**Missing:** `NPC_SPOKE`, `NPC_PROXIMITY_CLOSE`, `NPC_PROXIMITY_LEAVE`, `NPC_INTERACTS_NPC`, `NPC_MOVED`, `ACTOR_ATTACKS`.

Когда NPC A атакует NPC B, публикуется `actor_attacks` (из `intent_event_adapter.py:36-37`). SocialSubscriber **не подписан** на `ACTOR_ATTACKS`. Только CombatSubscriber подписан → применяет HP damage. **Нет trust/fear update, нет witness reaction, нет rumor propagation.**

**Эффект:** NPC A может атаковать NPC B многократно с нулевыми социальными последствиями. B не боится A, не доверяет меньше, свидетели не реагируют.

**Fix:**
1. Добавить `ACTOR_ATTACKS` в `_SOCIAL_EVENT_TYPES`
2. Подписать ReactionSubscriber, SocialInputProjector на `ACTOR_ATTACKS`
3. Снять `not _target_id` gate в `propagate_social_rumors` (V8-SOC-4)

### V8-SOC-2 ★★★ CRITICAL — Dead event types: COMBAT, THEFT, HELP, INTIMIDATION, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC

**Файл:** `backend/app/services/events/event_types.py`

Все 7 event types определены и подписаны (в SocialSubscriber, ReactionSubscriber, и др.), но **НИКОГДА НЕ ПУБЛИКУЮТСЯ** в production коде (grep по `app/` — 0 publish call sites).

**Эффект:** Соответствующие handler'ы (combat rumor, theft reaction, help social delta, betrayal long-term memory) — мёртвые. Любая логика, завязанная на эти events, не работает.

**Fix:** Либо publish эти events из правильных мест:
- `COMBAT` — из CombatSubscriber при применении damage
- `HELP` — из DecisionHub когда NPC помогает
- `THEFT` — из theft action handler
- `NPC_INTERACTS_NPC` — из DecisionHub при NPC-initiated social contact

Либо удалить event types и подписчиков (если функционал не нужен для MVP).

### V8-SOC-3 ★★★ CRITICAL — SocialDeltaEngine key case mismatch

**Файл:** `backend/app/services/social/social_delta_engine.py` (или аналогичный)

`_BASE_DELTAS` keys — lowercase: `"player_attacks"`, `"player_spoke"`. Published event types — UPPERCASE: `"PLAYER_ATTACKED"`, `"PLAYER_SPOKE"`.

```python
_BASE_DELTAS = {
    "player_attacks": {...},  # lowercase key
    "player_spoke": {...},    # lowercase key
}
# Lookup: deltas = _BASE_DELTAS.get(event_type.value)  # UPPERCASE — miss
```

DecisionHub's social deltas path — **мёртвый** для самых частых combat/dialogue events.

**Fix:** Нормализовать keys (или использовать `.lower()` при lookup, или добавить UPPERCASE aliases).

### V8-SOC-4 ★★ HIGH — `propagate_social_rumors` player-centric gate

**Файл:** `backend/app/services/social/propagation.py:72`

```python
if not _target_id:
    return  # _target_id = player_target_id
```

NPC↔NPC events имеют пустой `player_target_id` → propagation skipped **даже если** подписки добавлены (V8-SOC-1).

**Fix:** Split на два path:
- Player-target path (с `player_target_id`)
- NPC-target path (с `event.target_id` или `event.payload["target_id"]`)

### V8-SOC-5 ★★ HIGH — `_idle_pressure` — DEAD CODE в production

**Файлы:** `backend/app/services/npc/life_engine.py:601-1101`, `232, 780, 792, 1086`

`LifeEngine.tick_decisions` — единственный reader/accumulator `_idle_pressure`. **НИКОГДА НЕ ВЫЗЫВАЕТСЯ** в production (только `test_causal_bridge_integration.py:307`).

`NpcTickPipeline.run` (`npc_tick_pipeline.py:114`) — production phase 5 reducer, **не ссылается** на `_idle_pressure` или `IDLE_PRESSURE_*` константы.

`IDLE_DECISION_SCORE_THRESHOLD` trigger на line 1070 — в dead code.

**Эффект:** Нет «social urge accumulation» mechanism в production. NPC говорят на основе natural per-tick scoring, не «накопил и заговорил». Proactive talk мёртв.

**Fix:** Либо wire `_idle_pressure` в `NpcTickPipeline.run` (добавить `idle_pressure` параметр в `DecisionHub.compute`), либо удалить dead code (`_idle_pressure`, `tick_decisions`, `IDLE_PRESSURE_*`).

### V8-SOC-6 ★★ HIGH — WorldTickEngine filter excludes TALK intent

**Файл:** `backend/app/services/npc/world_tick_engine.py:113-122, 190-191`

```python
proactive_intents = {Intent.OBSERVE, Intent.WANDER, ...}  # НЕТ Intent.TALK
```

Но `DecisionHub.PROACTIVE_INTENTS` **включает** `Intent.TALK`. Proactive NPC talk **тихо дропается** на player turn (idle tick path — OK).

**Fix:** Добавить `Intent.TALK` в `WorldTickEngine.proactive_intents` (consistency с DecisionHub.PROACTIVE_INTENTS).

### V8-SOC-7 ★ MEDIUM — `SocialInputProjector listener_ids` never populated

**Файл:** `backend/app/services/social/social_input_projector.py:83, 87`

```python
for listener_id in payload.get("listener_ids", []):  # всегда []
    # listener delta loop
```

`DialogueMaterializer` не устанавливает `listener_ids` в payload. Loop никогда не исполняется. Только speaker получает +0.10 speak delta; target/listeners никогда не получают +0.15 listen delta через NPC_SPOKE path.

**Fix:** Populate `listener_ids` в `DialogueMaterializer` payload (список NPCs в earshot), ИЛИ `NpcDialogueSubscriber` должен notify `SocialInputProjector`.

### V8-SOC-8 ★ MEDIUM — `_MOVE_INTENTS` включает "talk" — NPC ходит на каждый разговор

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:518`

```python
_MOVE_INTENTS = {"approach", "follow", "flee", "talk", ...}
```

TALK intent triggers reactive movement goal. NPC идёт к conversation partner каждый раз, когда решает говорить.

**Fix:** Убрать `"talk"` из `_MOVE_INTENTS` — TALK не должен автоматически триггерить movement.

### V8-SOC-9 ★ MEDIUM — ClusterOccupancy rebuild дропает NPCs с пустой `position`

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:262-273`

NPCs со stale/empty `position` полем — невидимы для CFRM disturbance propagation. Микро-движения обновляют только `local_position`, не `position` → `position` может быть stale.

**Fix:** Использовать `local_position` fallback в rebuild, ИЛИ обновлять `position` при каждом micro-movement.

### V8-SOC-10 ★ MEDIUM — `propagate_social_rumors` skips witnesses в NPC-target path

**Файл:** `backend/app/services/social/propagation.py:97-99`

Разная trust targeting semantics между witnesses (player target) и non-witnesses (actor target). После fix V8-SOC-4 — нужно убедиться, что witnesses тоже обрабатываются для NPC↔NPC events.

### V8-SOC-11 ★ MEDIUM — NpcDialogueSubscriber canonical detection по "Stub LLM" substring

**Файл:** `backend/app/services/npc/npc_dialogue_subscriber.py:65`

Russian "[Заглушка]" stub **не матчит** → обрабатывается как canonical. Stub LLM responses не детектируются.

**Fix:** Добавить Russian stub в detection logic.

### V8-SOC-12 ★ LOW — Topic defaults to "наблюдение" для thief archetype

**Файл:** `backend/app/services/npc/topic_extractor.py:43`

Thief NPCs в idle produce observation-themed talk **к nobody in particular**. Без `response_targets` (V8-SOC-5 dead `_idle_pressure`) — talk ни к кому не адресован.

### V8-SOC-13 ★ LOW — ClusterOccupancy desync (position vs local_position)

**Файлы:** `cfrm.py:266-282`, `spatial_event_detector.py:49-61`, `scene_state_manager.py:1201-1207`

- `ClusterOccupancy.update_entity` keys по `position` string (e.g., `"tavern:main_hall"`)
- `SpatialEventDetector` использует `local_position` euclidean для proximity
- `scene_state_manager.py:1201-1207` micro-movements обновляют только `local_position`, НЕ `position`

`position` может быть stale, пока geometric location меняется. `_rebuild_cluster_occupancy` читает `data.get("position")` only — no consistency check. Two systems могут disagree.

**Fix:** Унифицировать — ClusterOccupancy должна использовать `local_position` для euclidean, или `position` должен обновляться при каждом micro-movement.

### V8-SOC-14 ★ LOW — DRF alignment string-based

**Файл:** `backend/app/services/game_loop/tick_orchestrator.py:1477`

```python
_vector = str(c.get("vector", ""))
_aligned = _vector in _reason  # substring
```

`"schedule"` в `"schedule:sleeping"` → True (семантически wrong). Topic prefix spuriously "aligns" с reason strings.

**Fix:** Tokenized match: `if _vector.split(":")[0] in _reason.split(":")[0]` или exact prefix match.

---

## §13. ПСИХИКА — INTEGRATION GAPS (v8.1 — новый аудит)

### V8-PSY-20 ★★ HIGH — CalibrationEngine pass-through + dead instantiation

**Файлы:** `backend/app/services/npc/calibration_engine.py:66`, `tick_orchestrator.py:1118, 1137, 1141`

```python
# calibration_engine.py:66
def stabilize(self, ...):
    return l3_raw, {}, {}  # pure pass-through

# tick_orchestrator.py:1118
_calibration = CalibrationEngine()  # создан
# line 1137:
l3_stable = l3_raw  # bypass stabilize()
# line 1141:
return effective_drives_map, {}, {}  # drives_update, strain_memory пустые
```

`drives_runtime` cache и `strain_memory` **НИКОГДА** не мутируют. L3 — purely ephemeral, no learning across ticks. Class docstring's TRAUMA/HEALING physics — dead code.

**Эффект:** L3 jitter тик-в-тик от body, без сглаживания. TSHL (стабилизация L3) фактически выключен.

**Fix:** Либо реализовать `CalibrationEngine.stabilize()` properly, ИЛИ удалить класс и dead instantiation.

### V8-PSY-21 ★★ HIGH — `stress` в `psyche` vs `emotion` (double-truth)

**Файлы:** `psyche["stress"]` (canonical) vs `emotion["stress"]` (written, never read)

**Canonical `psyche["stress"]`** читается в: `combat_subscriber.py:339`, `npc_loader.py:640`, `life_engine.py` (×4), `reaction_priority.py:197`, `behavior_manifestation_service.py:167`, `manifestation_physics_engine.py:49`, `reaction_subscriber.py:104`, `tick_utils.py:132`, `world_snapshot_builder.py:342`, `local_causal_solver.py:346`, `decision_hub.py:1824`. Маппится в `state.stress` на `models/npc_state.py:815`.

**`emotion["stress"]`** пишется ТОЛЬКО в `tick_orchestrator.py:675, 863` — и **НИКОГДА не читается**. Дополнительно ломается с TypeError (V8-TICK-5).

**Fix:** Удалить `emotion["stress"]` writes — stress должен быть только в `psyche["stress"]`.

### V8-PSY-22 ★ MEDIUM — LifeEngine viability vs DecisionHub perceptual_kernel рассинхрон

**Файлы:** `life_engine.py` (фаза 0), `decision_hub.py` (фаза 5)

Viability mask (threat > 0.3 → ROUTINE off) — в LifeEngine (фаза 0). DecisionHub (фаза 5) смотрит на **другой** perceptual_kernel (часто T−1 / после CFRM). Возможна рассинхронизация: LifeEngine уже не шлёт schedule intent, а DecisionHub ещё «спокойный» — или наоборот.

**Fix:** Использовать общий snapshot perceptual_kernel, передаваемый между фазами через shared_context.

### V8-PSY-23 ★ MEDIUM — DRF dual alignment constants (silent contract drift)

**Файлы:** `backend/app/services/drf_bus.py:75-76`, `tick_orchestrator.py:1478-1479`

```python
# drf_bus.py:75-76:
_DRF_ALIGNED = 1.0  # НИКОГДА не импортируется
_DRF_MISALIGNED = 0.3

# tick_orchestrator.py:1478-1479 (локально в _apply_drf_scoring_overlay):
_DRF_ALIGNED = 1.2   # используется
_DRF_MISALIGNED = 0.8
```

Silent contract drift: будущий maintainer, читая `drf_bus.py`, будет считать 1.0/0.3, actual — 1.2/0.8.

**Fix:** Удалить dead `_DRF_ALIGNED`/`_DRF_MISALIGNED` из `drf_bus.py:75-76`, ИЛИ перенести в orchestrator как module-level constants.

### V8-PSY-24 ★ LOW — `gregariousness` всегда 0.5 (повтор V8-PSY-11, дополнение)

**Файлы:** `life_engine.py:734-738`, `npc_tick_pipeline.py:425-428`

Ни один NPC config не устанавливает `gregariousness` (grep `config/` — 0 matches). `_psyche.get("gregariousness", 0.5)` — всегда 0.5. `pressure_translator.translate_kernel_to_context(gregariousness=0.5)` — у всех NPC идентичный social homeostasis setpoint.

**Fix:** Перенести `gregariousness` на `NPCPersonality`, добавить в JSON config (разные значения для разных архетипов: thief=0.2, merchant=0.8, и т.д.).

---

## §14. ДИАЛОГОВАЯ СИСТЕМА — НИТЬ ПАМЯТИ (v8.1 — новый аудит)

**Полный документ:** `ENIGMA_DIALOGUE_THREAD_SYSTEM.md`

Аудит диалоговой системы нашёл **12 точек разрыва** + **8 новых багов**. Главная проблема: «диалоги сейчас — монологи, нить теряется». NPC не помнит, что игрок сказал 2 хода назад, не продолжает темы, не помнит claims/open_questions после переключения темы.

### V8-DLG-01 ★★★ CRITICAL — Player-turn STM write — DEAD CODE

**Файл:** `backend/app/services/game_loop/dm_phase.py:122-138`

```python
_sem_payload = {}  # line 122 — пустой
_stm_target_id = _sem_payload.get("target_id")  # line 131 — всегда None
if _raw_type in ("dialogue", "player_interacts") and _stm_target_id:
    add_dialogue_turn(...)  # НИКОГДА не вызывается
```

**Эффект:** Реплика игрока **никогда** не пишется в STM. NPC не помнит, что игрок сказал 2 хода назад — потому что это никогда не было сохранено.

**Fix:** Заменить `_sem_payload.get("target_id")` на `shared_context.player_target_id`.

### V8-DLG-02 ★★★ CRITICAL — NPC↔NPC DialogueExecutor не включает STM

**Файл:** `backend/app/services/execution/dialogue_executor.py:100-156`

`_generate_with_router` строит LLM-промпт из static fields + `npc_npc_context` (всегда "" из-за V8-DLG-04). **NO STM block.** NPC↔NPC диалог = монологи.

**Fix:** Inject `memory_manager.get_stm_prompt_block_pair(campaign_id, speaker, target)` в user_prompt.

### V8-DLG-03 ★★★ CRITICAL — DM LLM видит mixed speech, не targeted NPC

**Файлы:** `backend/app/agents/dm_agent.py:221-226`, `memory_manager.py:275-289`

`npc_recent_speech` = mixed last-5 lines от ВСЕХ NPC sessions. DM видит смешанный контекст, не targeted NPC thread.

**Fix:** Добавить `get_stm_prompt_block_for_target(campaign_id, target_id, partner_id="player")` в dm_agent.

### V8-DLG-04 ★★ HIGH — `npc_npc_context` теряется при JSON roundtrip

**Файл:** `backend/app/services/game_loop/task_scheduler.py:266-272`

`DialogueRequest` реконструируется без `npc_npc_context` — поле теряется. Long-term memory context не доходит до executor.

**Fix:** Добавить `npc_npc_context=payload_dict.get("npc_npc_context", "")` в `_reconstruct_task`.

### V8-DLG-05 ★★ HIGH — Speaker STM не обновляется при NPC↔NPC

**Файл:** `backend/app/services/events/npc_dialogue_subscriber.py:108-129`

Только listener's STM обновляется. Speaker (NPC A) own STM не обновляется — NPC не помнит, что сам сказал.

**Fix:** Symmetric write — и listener, и speaker STM + pair session.

### V8-DLG-06 ★★ HIGH — NPC_SPOKE не создаёт EventMemory

**Файл:** `backend/app/services/events/npc_dialogue_subscriber.py:108-176`

Только L1Chronicle.commit_tick_buffer. Нет `MemoryManager.apply()` → нет EventMemory в `narrative_cache`. Диалог evaporates при clear.

**Fix:** Создать `DialogueMemorySubscriber` (новый файл) — подписывается на NPC_SPOKE/PLAYER_SPOKE, вызывает `MemoryManager.apply()`.

### V8-DLG-07 ★★ HIGH — `clear_dialogue_session` без consolidation

**Файл:** `backend/app/services/memory/memory_manager.py:71-76`

STM стирается без создания EventMemory summary. Диалог испаряется без следа.

**Fix:** Перед clear — `DialogueConsolidator.consolidate()` → EventMemory в narrative_cache.

### V8-DLG-08 ★★ HIGH — Любой "move" action стирает всю STM кампании

**Файл:** `backend/app/services/game_loop/dm_phase.py:158-159`

```python
if _raw_type in ("move", "stealth"):
    clear_all_dialogue_sessions(campaign_id)
```

Ходьба внутри комнаты стирает всю STM всех NPC, включая те, с кем игрок не говорит.

**Fix:** Distance + time-based expiry, не «любой move». Clear только при реальной смене локации.

### V8-DLG-09 ★★ HIGH — Keyword-only topic, «метель» не в словаре

**Файлы:** `dialogue_session.py:53-77`, `topic_extractor.py:85-111`

«метель», «погода», «снег» не в vocabulary → topic=None или «наблюдение». Две системы topic detection не синхронизированы.

**Fix:** Расширить vocabulary (+20 keywords) + LLM-based topic extraction для NPC replies (`DialogueUpdateExtractor`).

### V8-DLG-10 ★★ HIGH — `VerbalizationContext` dead code

**Файлы:** `verbalization_context.py:80-87`, `npc_tick_pipeline.py:791-881`

`build_verbalization_context` определён, но НИКОГДА не вызывается в production. `stm_buffer`, `recalled_facts`, `npc_npc_context`, `suppressed_secrets` — dead fields.

**Fix:** Wire в `DialogueExecutor._generate_with_router`.

### V8-DLG-11 ★ MEDIUM — `add_npc_l2_memory` никогда не вызывается

**Файл:** `backend/app/services/verbalization/dm_contract_builder.py:142-146`

Метод определён, но НИКТО не вызывает. DM никогда не видит `recall()` results.

**Fix:** Wire в `dm_agent._build_contract` после `add_npc_stm`.

### V8-DLG-12 ★ MEDIUM — Нет game-time TTL для `_recent_dialogues`

**Файл:** `backend/app/services/game_loop/task_scheduler.py:49, 61-71`

`_dialogue_ttl = 10.0` — wall-clock seconds. 10 секунд реального времени истекают независимо от game pace.

**Fix:** Game-time TTL (`game_time_seconds` instead of `time.time()`).

### Сводка диалоговых багов

| Категория | CRITICAL | HIGH | MEDIUM | LOW | Итого |
|---|:-:|:-:|:-:|:-:|:-:|
| §14 Dialogue (новое v8.1) | 3 | 7 | 2 | 0 | 12 |

### Архитектурные принципы (см. отдельный документ)

1. **Контекст диалога = Python-буфер**, не «модель помнит»
2. **Hard contract** — нет STM block в промпте → NPC не может говорить
3. **Claims и open_questions** — структурная память нити
4. **Per-pair session** (campaign_id:npc_a:npc_b), не per-NPC
5. **Dialogue consolidation** — STM → EventMemory на завершении

### Новые файлы (см. ENIGMA_DIALOGUE_THREAD_SYSTEM.md)

- `backend/app/services/memory/dialogue_consolidator.py` — LLM-суммаризация диалога в EventMemory
- `backend/app/services/memory/dialogue_update_extractor.py` — LLM-based topic/claims/questions extraction
- `backend/app/services/events/dialogue_memory_subscriber.py` — NPC_SPOKE → EventMemory

### План внедрения (из отдельного документа)

| Этап | Что | Время |
|---|---|---|
| 1 | Critical fixes (DLG-01..04, 08) | 1 день |
| 2 | Structured thread memory (Claim/OpenQuestion) | 1 день |
| 3 | Long-term linkage (DialogueMemorySubscriber, Consolidator) | 1 день |
| 4 | Per-pair sessions + thread_id | 1 день |
| 5 | Hard contract + polish | 1 день |
| **Итого** | | **~25 часов** |

---

## §6. ИТОГОВАЯ СВОДКА БАГОВ V8

| Категория | CRITICAL | HIGH | MEDIUM | LOW | Итого |
|---|:-:|:-:|:-:|:-:|:-:|
| §1 Movement/Space | 2 | 3 | 2 | 3 | 10 |
| §2 Will/Avatar | 0 | 3 | 2 | 3 | 8 |
| §3 Psyche/Break/Drive | 5 | 7 | 5 | 2 | 19 |
| §4 Memory/Decision | 3 | 4 | 6 | 2 | 15 |
| §5 MVP epistemic | 3 | 3 | 1 | 3 | 10 |
| §11 Tick/Orchestrator (v8.1) | 1 | 2 | 3 | 1 | 7 |
| §12 NPC↔NPC Social (v8.1) | 4 | 3 | 4 | 3 | 14 |
| §13 Psyche integration (v8.1) | 0 | 2 | 2 | 1 | 5 |
| §14 Dialogue thread (v8.1) | 3 | 7 | 2 | 0 | 12 |
| **Итого** | **21** | **34** | **27** | **18** | **100** |

(Включая v7 не применённые: N14 cascade = V8-MEM-14, Mem-11 = V8-MEM-11(v7), CPS-09/10/11, CPS-12 = V8-PER-12, M-02b = V8-MVP-2, M-07+M-08 = V8-MVP-7, N12 partial = V8-FC-01, N13 = V8-FC-02)

---

## §7. ПРИОРИТЕТ ПОЧИНКИ (Day Plan)

### День 1 (~4 ч) — Critical MVP blockers

Цель: End-Screen показывает >0 secrets для DIALOGUE-only playthrough.

| Баг | Время | Что даёт |
|---|---|---|
| **V8-MVP-1** logger в MvpTavernController | 1 мин | FateTracker/Dilemma/SocialFabric начинают обновляться |
| **V8-MVP-2** M-02b OR-condition | 5 мин | DIALOGUE-discovered secrets засчитываются |
| **V8-MVP-7** убрать player_target_id gate + refactor resolver | 30 мин | DIALOGUE без target доходит до process_action |
| **V8-MVP-3** End-Screen API expose fate/contradiction | 10 мин | Frontend может отрисовать полный End-Screen |
| **V8-SP-1** soft-remove wall-blocked edges | 30 мин | Compile не падает на map errors |
| **V8-SP-2** ε-tolerance в _segments_intersect | 30 мин | Endpoint touch не false-positive |
| Тест: 30-min playthrough, End-Screen >0 secrets | 15 мин | Canary |

### День 2 (~5 ч) — Critical psyche/memory

Цель: Trauma pipeline работает, NPC будут ломаться под давлением.

| Баг | Время | Что даёт |
|---|---|---|
| **V8-PSY-1** L1Chronicle на StateApplicator | 1 ч | Trauma mutations не дропаются |
| **V8-PSY-2** willpower из NPCPersonality | 30 мин | Per-NPC willpower используется |
| **V8-PSY-3** BROKEN recovery path | 30 мин | NPC могут восстановиться |
| **V8-PSY-4** REACTIVE_URGENCY_THRESHOLD scale | 5 мин | Stress > 1 не bypass commitment |
| **V8-PSY-5** persistence round-trip fields | 30 мин | recent_failures, life_project, behavior_mask survive reload |
| **V8-MEM-1** wire run_decay_and_resonance | 30 мин | L3 Identity cascade запускается |
| **V8-MEM-2** CommunicationIntent.target_id propagation | 30 мин | Attack windup создаётся |
| **V8-MEM-3** wire assess_beliefs | 15 мин | Belief pipeline работает |
| Тест: trauma event → drives mutation → behavior change | 30 мин | Canary |

### День 3 (~4 ч) — Player avatar & Will

Цель: Player проходит через WillpowerGate с реальными чертами.

| Баг | Время | Что даёт |
|---|---|---|
| **V8-SP-3** Player coords + spawn position | 1 ч | Player виден на карте |
| **V8-WL-3** avatar fear/willpower в _live_psyche | 1 ч | WillpowerGate видит avatar |
| **V8-WL-1** wire counter_offer или удалить dead returns | 30 мин | No dead branches |
| **V8-WL-2** player pressure calibration | 30 мин | Will сопротивляется player actions |
| **V8-WL-4** will_state/emotion as Enum | 15 мин | Type safety |
| **V8-WL-5** CharacterFilter defaults | 30 мин | S-93 работает для new players |
| Тест: player attack → Will RESIST → maybe RELUCTANT | 30 мин | Canary |

### День 4 (~4 ч) — Memory cleanup & DecisionHub

Цель: L3 Identity работает, DecisionHub без dead code.

| Баг | Время | Что даёт |
|---|---|---|
| **V8-MEM-14** N14 cascade (4 шага) | 1.5 ч | L3 Identity кристаллизует traits |
| **V8-MEM-4** scale mismatch в evaluate_behavior_and_identity | 30 мин | NPCs не snap to BROKEN слишком быстро |
| **V8-MEM-5** recent_pressure filter by target_id | 15 мин | Target-specific pressure работает |
| **V8-MEM-7** _identity_cache persistence | 30 мин | L3 traits survive restart |
| **V8-DEC-09** удалить duplicate ADR-036 block | 10 мин | No dead code |
| **V8-DEC-11** EventBus retry/DLQ | 45 мин | Events не теряются |
| **V8-MVP-4** wire register_dilemma | 30 мин | DilemmaEngine работает |
| **V8-MVP-5** wire trigger_fate | 30 мин | End-Screen npc_fates non-empty |
| Тест: 50-tick simulation → NPC имеет active_traits | 30 мин | Canary |

### День 5 (~3 ч) — Polish & remaining

Цель: Все MEDIUM/LOW bugs закрыты.

| Баг | Время |
|---|---|
| V8-SP-4 active_traversals dict/list | 15 мин |
| V8-SP-5 target_svc None-check | 5 мин |
| V8-SP-6 is_movement_blocked LOS | 5 мин |
| V8-SP-7 find_path cache topology_version | 15 мин |
| V8-SP-8 compile_graph arity | 15 мин |
| V8-SP-9 print → logger | 15 мин |
| V8-PSY-6 relationship_cache hydration | 30 мин |
| V8-PSY-7 support_present | 15 мин |
| V8-PSY-8 compute_mutation return {} | 1 мин |
| V8-PSY-9 overlay_drives wire или удалить | 15 мин |
| V8-PSY-10 life_engine stress from psyche | 5 мин |
| V8-PSY-11 gregariousness на NPCPersonality | 30 мин |
| V8-PSY-12 Will engine для всех NPC | 30 мин |
| V8-PSY-13 affective_decay_handler stress | 15 мин |
| V8-PSY-14 _get_statuses from body_state | 5 мин |
| V8-PSY-15 reaction composure multi-dim | 30 мин |
| V8-PSY-16 emotion as EmotionTag | 10 мин |
| V8-PSY-18 double-truth writes | 10 мин |
| V8-PSY-19 age_drives wire | 15 мин |
| V8-PSY-22 viability/perceptual_kernel sync | 20 мин |
| V8-PSY-23 DRF dual constants cleanup | 5 мин |
| V8-PSY-24 gregariousness в JSON config | 15 мин |
| V8-MEM-8 detect_npc_patterns return [] | 1 мин |
| V8-MEM-9 удалить _get_rel_value static | 1 мин |
| V8-MEM-10 wire save_event_memories_batch | 15 мин |
| V8-MEM-11 pattern_detector try/except | 5 мин |
| V8-MEM-12 cumulative decay | 15 мин |
| V8-MEM-13 detect_resonance per-NPC | 30 мин |
| V8-MEM-11(v7) PromotionEngine +4 templates | 30 мин |
| V8-DEC-09 удалить duplicate ADR-036 block | 10 мин |
| V8-DEC-10 target_id assert | 5 мин |
| V8-DEC-11 EventBus retry/DLQ | 45 мин |
| V8-MVP-6 FateTracker clamping | 5 мин |
| V8-MVP-8 operator precedence | 1 мин |
| V8-MVP-9 set_baseline idempotent | 5 мин |
| V8-MVP-10 broaden exception | 5 мин |
| V8-FC-01 test_world_continuity IDs | 5 мин |
| V8-FC-02 Shadow schedule comment | 5 мин |
| V8-PER-12 line_of_sight coords | 30 мин |
| V8-WL-6 imports Dict/List | 1 мин |
| V8-WL-7 удалить compose_pressure_from_tags | 5 мин |
| V8-WL-8 trauma_markers в _live_psyche | 5 мин |
| V8-TICK-1 удалить/fix _process_player_dm_action | 15 мин |
| V8-TICK-2 DRF overlay для всех intents | 30 мин |
| V8-TICK-3 двойной time counter | 30 мин |
| V8-TICK-4 state_l2 UnboundLocalError | 10 мин |
| V8-TICK-5 emotion["stress"] TypeError | 10 мин |
| V8-TICK-6 phase exception rollback | 30 мин |
| V8-TICK-7 hoist DRF import | 1 мин |
| V8-SOC-1 NPC↔NPC attack social consequences | 1 ч |
| V8-SOC-2 publish dead event types (или удалить) | 1 ч |
| V8-SOC-3 SocialDeltaEngine key case | 10 мин |
| V8-SOC-4 propagate_social_rumors NPC-target path | 30 мин |
| V8-SOC-5 _idle_pressure wire или удалить | 30 мин |
| V8-SOC-6 WorldTickEngine TALK intent | 5 мин |
| V8-SOC-7 SocialInputProjector listener_ids | 30 мин |
| V8-SOC-8 убрать "talk" из _MOVE_INTENTS | 5 мин |
| V8-SOC-9 ClusterOccupancy local_position fallback | 20 мин |
| V8-SOC-10 propagate witnesses NPC↔NPC | 20 мин |
| V8-SOC-11 NpcDialogueSubscriber Russian stub | 5 мин |
| V8-SOC-12 topic default для thief | 10 мин |
| V8-SOC-13 ClusterOccupancy desync | 30 мин |
| V8-SOC-14 DRF alignment tokenized | 15 мин |

### День 6 (~2 ч) — Финальные тесты и релиз

- Full 30-min playthrough canary
- Save/load roundtrip test
- End-Screen: ≥5/16 secrets identified, 6 fate_states, faction_alignments non-empty
- NPC↔NPC attack → trust/fear change (V8-SOC-1 canary)
- Production server (uvicorn) smoke test
- Release

**Итого v8.1:** ~32 часов работы (vs 22 ч в v8.0). После 6 дней — MVP полностью работоспособен, NPC↔NPC социалка живая.

---

## §8. CANARY ТЕСТЫ (обязательные перед релизом)

### Canary 1: DIALOGUE-only playthrough

```python
def test_dialogue_only_end_screen_non_empty():
    """V8-MVP-1, V8-MVP-2, V8-MVP-7 — DIALOGUE без target."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_canary")
    
    # 5 тиков наблюдения
    for _ in range(5):
        game.idle_tick()
    
    # DIALOGUE без target — раскрываем 5 секретов
    secrets_to_discover = [
        "Люся, что ты скрываешь от мужа?",
        "Борко, ты подглядываешь?",  # без target
        "Горан, откуда у тебя такой товар?",
        "Торнин, у тебя долги перед гильдией?",
        "Тень, ты убил того человека?",
    ]
    for text in secrets_to_discover:
        game.player_action(text=text)  # БЕЗ target
        game.idle_tick()
    
    # 20 тиков для subsystem updates
    for _ in range(20):
        game.idle_tick()
    
    game.player_exit_tavern()
    end_screen = game.get_end_screen()
    
    assert end_screen.secrets_identified >= 5, (
        f"Expected >=5, got {end_screen.secrets_identified}. "
        "Check V8-MVP-7 (gate removed), V8-MVP-2 (M-02b OR-condition)."
    )
```

### Canary 2: Fate/Dilemma populated

```python
def test_fate_dilemma_populated():
    """V8-MVP-1 (logger), V8-MVP-4 (register_dilemma), V8-MVP-5 (trigger_fate)."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_fate")
    
    for _ in range(30):
        game.idle_tick()
    
    end_screen = game.get_end_screen()
    
    assert len(end_screen.npc_fates) >= 1, (
        "No fate_states — check V8-MVP-1 (logger), V8-MVP-5 (trigger_fate)"
    )
```

### Canary 3: Trauma → drives mutation

```python
def test_trauma_mutates_drives():
    """V8-PSY-1 (L1Chronicle), V8-PSY-2 (willpower), V8-MEM-1 (decay/resonance)."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_trauma")
    
    # Trigger trauma event
    game.apply_trauma("maid_lusya", "humiliated")
    
    for _ in range(10):
        game.idle_tick()
    
    lusya = game.get_npc("maid_lusya")
    assert lusya.drives_runtime["control"] != lusya.initial_drives["control"], (
        "Drives not mutated — V8-PSY-1 not fixed"
    )
```

### Canary 4: L3 Identity active_traits non-empty

```python
def test_l3_identity_non_empty():
    """V8-MEM-1, V8-MEM-14 (N14 cascade)."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_l3")
    
    # Generate events
    for _ in range(50):
        game.idle_tick()
    
    for npc_id in ALL_NPC_IDS:
        npc = game.get_npc(npc_id)
        if hasattr(npc, 'identity_l1'):
            assert len(npc.identity_l1.active_traits) > 0, (
                f"NPC {npc_id} has empty active_traits after 50 ticks — "
                "V8-MEM-14 cascade not fixed"
            )
```

### Canary 5: Player visible on map

```python
def test_player_has_coords():
    """V8-SP-3 — player coords not None."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_player")
    
    game.idle_tick()
    
    player_pos = game.scene_state["npc_positions"].get("player", {})
    assert player_pos.get("local_position") is not None, (
        "Player has no local_position — V8-SP-3 not fixed"
    )
```

### Canary 6: Save/load roundtrip preserves all fields

```python
def test_save_load_roundtrip():
    """V8-PSY-5 — recent_failures, life_project, behavior_mask survive."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_roundtrip")
    
    # Apply some state changes
    game.apply_trauma("maid_lusya", "humiliated")
    game.set_behavior_mask("tavern_keeper_tornin", "FAKE_SUBMISSION")
    for _ in range(20):
        game.idle_tick()
    
    # Save
    save_data = game.serialize()
    
    # Load
    game2 = GameLoop(test_mode=True)
    game2.deserialize(save_data)
    
    # Verify
    lusya = game2.get_npc("maid_lusya")
    assert lusya.psyche["recent_failures"] > 0, "recent_failures lost — V8-PSY-5"
    
    tornin = game2.get_npc("tavern_keeper_tornin")
    assert tornin.behavior_mask == "FAKE_SUBMISSION", "behavior_mask lost — V8-PSY-5"
```

### Canary 7: Compile_graph не падает на map errors

```python
def test_compile_graph_soft_fail():
    """V8-SP-1, V8-SP-2 — compile не падает на wall-blocked edges."""
    # Создать map с wall, пересекающей nav edge
    result = subprocess.run(
        ["python", "build_graph.py", "--campaign", "test_wall_cross"],
        capture_output=True
    )
    assert result.returncode == 0, (
        f"build_graph crashed: {result.stderr} — V8-SP-1 not fixed"
    )
```

### Canary 8: NPC↔NPC attack имеет социальные последствия

```python
def test_npc_npc_attack_social_consequence():
    """V8-SOC-1, V8-SOC-3, V8-SOC-4 — NPC A атакует B → B боится A."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_npc_social")
    
    borko = game.get_npc("guard_borko")
    tornin = game.get_npc("tavern_keeper_tornin")
    initial_trust = game.get_trust(tornin.npc_id, borko.npc_id)
    initial_fear = game.get_fear(tornin.npc_id, borko.npc_id)
    
    # NPC A (Borko) attacks NPC B (Tornin)
    game.npc_attack(attacker="guard_borko", target="tavern_keeper_tornin")
    
    # Run ticks for event propagation
    for _ in range(5):
        game.idle_tick()
    
    final_trust = game.get_trust(tornin.npc_id, borko.npc_id)
    final_fear = game.get_fear(tornin.npc_id, borko.npc_id)
    
    assert final_fear > initial_fear, (
        f"Tornin's fear of Borko didn't change after attack: "
        f"{initial_fear} → {final_fear}. Check V8-SOC-1 (ACTOR_ATTACKS subscription), "
        f"V8-SOC-3 (case mismatch), V8-SOC-4 (player-centric gate)."
    )
    assert final_trust < initial_trust, (
        f"Tornin's trust of Borko didn't drop after attack: "
        f"{initial_trust} → {final_trust}."
    )
```

### Canary 9: Proactive NPC talk в player turn

```python
def test_proactive_npc_talk_player_turn():
    """V8-SOC-5, V8-SOC-6 — NPC может заговорить в player turn."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_proactive")
    
    npc_speak_events = []
    game.event_bus.subscribe(EventType.NPC_SPOKE, 
                              lambda e: npc_speak_events.append(e))
    
    # Player talks to one NPC, others should be able to talk too
    game.player_action(target="lusya", text="Привет, Люся")
    for _ in range(10):
        game.idle_tick()
    
    # At least one NPC (not Lusya) should speak proactively
    proactive_speaks = [e for e in npc_speak_events 
                        if e.payload.get("speaker_id") != "maid_lusya"]
    assert len(proactive_speaks) > 0, (
        "No proactive NPC talk in player turn — check V8-SOC-5 (_idle_pressure), "
        "V8-SOC-6 (WorldTickEngine TALK intent filter)"
    )
```

### Canary 10: Hearing perception для NPCs вне LoS

```python
def test_hearing_perception_recorded():
    """V8-TICK-4 — NPC слышит, но не видит player → memory write."""
    game = GameLoop(test_mode=True)
    game.new_campaign("test_hearing")
    
    # Place NPC in adjacent room (no LoS but in earshot)
    game.set_npc_position("merchant_goran", "tavern:storage_room")
    game.set_player_position("tavern:main_hall")
    
    # Player does loud action
    game.player_action(text="ГРОМКО КРИЧУ!")
    game.idle_tick()
    
    goran_memories = game.get_npc_memories("merchant_goran")
    hearing_memories = [m for m in goran_memories if m.source == "hearing"]
    
    assert len(hearing_memories) > 0, (
        "Goran didn't hear player shout — V8-TICK-4 (state_l2 UnboundLocalError)"
    )
```

---

## §9. ЧТО УЖЕ РАБОТАЕТ (контекст)

После v7 фиксов в V.0.5.3.6.2:

- **N1, N2, N3, N4, N5, N6, N7, N9, N10, N11, N15** — применены
- **M-12** (apply_delta wired) — применён
- **Mem-09/10** (SQLite wired) — подтверждено, что не было багом
- **N15** (ContradictionResolver sign) — применён
- **Memory → SQLite** — работает (`game_loop_builder.py:37` использует `SqliteMemoryStore`)
- **L1Chronicle** — работает (создаётся, decay'ится, сериализуется)
- **BLACKMAIL → mark_discovered → belief → EvaluationEngine → End-Screen** — работает end-to-end (canary test PASSES, 1/16 identified)
- **Perception → Reaction** через `shared_context.perceiving_npcs` (phases/reduction.py:251) — работает
- **Player perception** через `perception_projector.py` — отдельная система, работает
- **FactionAlignmentTracker pre-seed** из `factions.json` (N11) — работает
- **HELP → faction_tracker.apply_delta** (M-12) — работает
- **TICK_COMPLETED event** — публикуется и подписывается (но V8-MVP-1 ломает подписчика)

---

## §10. CHANGELOG

### v8.2 (V.0.5.3.6.8.2) — 2026-07-28

**Дополнительный аудит диалоговой системы:** 2 параллельных агента углубились в `DialogueSession`, `DialogueExecutor`, `dm_phase`, `npc_dialogue_subscriber`, LLM prompt assembly. Найдено **12 новых багов** (3 CRITICAL, 7 HIGH, 2 MEDIUM) + 12 точек разрыва нити.

**Полный документ:** `ENIGMA_DIALOGUE_THREAD_SYSTEM.md` — спецификация новой диалоговой системы с structured thread memory (claims/open_questions), per-pair sessions, thread_id, dialogue consolidation, hard contract «no STM → can't speak».

**Критические диалоговые баги:**
- **V8-DLG-01**: Player-turn STM write — DEAD CODE (`dm_phase.py:131`). Реплика игрока **никогда** не пишется в STM. NPC не может помнить то, что никогда не было сохранено.
- **V8-DLG-02**: NPC↔NPC `DialogueExecutor` не включает STM block в LLM-промпт. NPC↔NPC диалог = монологи.
- **V8-DLG-03**: DM LLM видит mixed speech от ВСЕХ NPC sessions, не targeted NPC thread.

**High-приоритетные:**
- V8-DLG-04: `npc_npc_context` теряется при JSON roundtrip
- V8-DLG-05: Speaker STM не обновляется при NPC↔NPC (asymmetric)
- V8-DLG-06: NPC_SPOKE не создаёт EventMemory (диалог evaporates)
- V8-DLG-07: `clear_dialogue_session` без consolidation
- V8-DLG-08: Любой "move" action стирает всю STM кампании
- V8-DLG-09: Keyword-only topic, «метель» не в словаре
- V8-DLG-10: `VerbalizationContext` dead code

**Итоговое число багов v8.2:** 100 (21 CRITICAL, 34 HIGH, 27 MEDIUM, 18 LOW)

**Day plan v8.2:** 6 дней (~32 ч) + 5 дней (~25 ч) для диалоговой системы = ~11 дней полного fixed. После — MVP «Секреты Люси» полностью работоспособен, NPC помнит нить диалога через 20 ходов, через переключение темы, через отход и возвращение.

### v8.1 (V.0.5.3.6.8.1) — 2026-07-28

**Дополнительный аудит тик/память/психика/NPC↔NPC:** 2 параллельных агента углубились в `NpcTickPipeline`, `DecisionHub`, `SocialSubscriber`, propagation, DRF bus, CalibrationEngine. Найдено **26 новых багов** (5 CRITICAL, 7 HIGH, 9 MEDIUM, 5 LOW).

**Новые CRITICAL баги:**
- **V8-TICK-1**: `NameError _movement_req` в `_process_player_dm_action` — сломанный код, но мёртвый path в production
- **V8-SOC-1**: NPC↔NPC attack имеет нулевые социальные последствия — `ACTOR_ATTACKS` не подписан SocialSubscriber'ом
- **V8-SOC-2**: 7 dead event types (COMBAT, THEFT, HELP, INTIMIDATION, BETRAYAL, SAVED_LIFE, NPC_INTERACTS_NPC) — определены, подписаны, никогда не публикуются
- **V8-SOC-3**: SocialDeltaEngine key case mismatch — lowercase keys vs UPPERCASE event types → social deltas path мёртв

**Новые HIGH баги:**
- **V8-TICK-2**: DRF scoring overlay только для movement intents
- **V8-TICK-3**: Двойной счётчик времени (player ticks drift +10s/tick)
- **V8-SOC-4**: `propagate_social_rumors` player-centric gate блокирует NPC↔NPC propagation
- **V8-SOC-5**: `_idle_pressure` — DEAD CODE в production (tick_decisions никогда не вызывается)
- **V8-SOC-6**: WorldTickEngine filter excludes TALK intent — proactive NPC talk дропается
- **V8-PSY-20**: CalibrationEngine pass-through + dead instantiation
- **V8-PSY-21**: stress в psyche vs emotion (double-truth, + TypeError)

**Новые MEDIUM баги:** V8-TICK-4 (state_l2 UnboundLocalError), V8-TICK-5 (emotion["stress"] TypeError), V8-TICK-6 (phase exception leaks partial state), V8-SOC-7..11 (SocialInputProjector listener_ids, _MOVE_INTENTS "talk", ClusterOccupancy, propagation witnesses, Russian stub detection), V8-PSY-22 (viability/perceptual_kernel рассинхрон), V8-PSY-23 (DRF dual constants)

**Новые LOW баги:** V8-TICK-7 (per-claim import), V8-SOC-12..14 (topic default, ClusterOccupancy desync, DRF alignment string-based), V8-PSY-24 (gregariousness)

**Итоговое число багов v8.1:** 88 (18 CRITICAL, 27 HIGH, 25 MEDIUM, 18 LOW)

**Day plan v8.1:** 6 дней, ~32 часа. День 5 расширен — добавлены V8-TICK-* и V8-SOC-* фиксы. День 6 — canary тесты (10 шт., включая NPC↔NPC attack, proactive talk, hearing perception).

### v8 (V.0.5.3.6.8) — 2026-07-28

**Повторный код-аудит V.0.5.3.6.2:** 5 параллельных агентов проследили всю цепочку кода. Удалили всё починенное в v7, нашли **62 активных бага** (13 CRITICAL, 20 HIGH, 16 MEDIUM, 13 LOW).

**Критические изменения:**
- V8-MVP-1: `logger` не определён в MvpTavernController → все подписчики TICK_COMPLETED silently fail
- V8-MVP-2: M-02b не применён → DIALOGUE-only playthrough даёт 0 identified
- V8-MVP-7: M-07+M-08 не применён в caller → DIALOGUE без target не обрабатывается
- V8-PSY-1: Trauma mutation pipeline полностью мёртв (L1Chronicle не прикреплён)
- V8-PSY-2: Per-NPC willpower никогда не читается (всегда 50.0)
- V8-PSY-3: WillState.BROKEN permanent, без recovery
- V8-PSY-4: REACTIVE_URGENCY_THRESHOLD scale mismatch (0.8 vs 0-100)
- V8-PSY-5: Persistence round-trip теряет 7 полей
- V8-MEM-1: `run_decay_and_resonance` никогда не вызывается → L3 cascade мёртв
- V8-MEM-2: `CommunicationIntent.target_id` не propagates → attack windup сломан
- V8-MEM-3: `assess_beliefs` dead code → belief pipeline мёртв
- V8-SP-1: `INV-TOPOLOGY-WALL-CROSS` hard raise на map error
- V8-SP-2: `_segments_intersect` false positive на endpoint touch

**Архитектурная позиция v8:** Без удаления кода (как в v7). BedRegistry и умный редактор карт — отдельный документ `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`. Этот контракт фокусируется на runtime bugs и MVP epistemic chain.

**Day plan v8:** 5 дней, ~22 часа. День 1 — MVP blockers. День 2 — psyche/memory. День 3 — avatar/will. День 4 — memory cleanup. День 5 — polish. День 6 — canary тесты и релиз.

---

*Этот документ — спецификация активных багов. После применения Day plan v8.2 + Day plan из `ENIGMA_DIALOGUE_THREAD_SYSTEM.md` MVP «Секреты Люси» полностью работоспособен: End-Screen показывает >0 secrets для DIALOGUE playthrough, fate_states populated, NPC спят (после применения fixes из `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`), trauma pipeline работает, L3 Identity кристаллизует traits, NPC↔NPC социалка живая (attack → fear/trust change, proactive talk), **диалоги — не монологи** (NPC помнит нить через 20 ходов, через переключение темы, через отход и возвращение, через save/load).*

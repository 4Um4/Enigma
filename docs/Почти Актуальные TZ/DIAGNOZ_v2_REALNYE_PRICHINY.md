# Диагноз v2.0 — реальные корневые причины бага сна

**Дата:** 2026-08-11
**Статус:** пересмотр v1.0 после тестового прогона патчей
**Вердикт v1.0 был:** ❌ неверный. Патчи не сработали.
**Вердикт v2.0:** опирается на фактический код + log `sleep_test2.log` + находки пользователя.

---

## Почему v1.0 провалился

Мои 7 патчей были **верными по смыслу**, но:
1. Они чинили **инварианты нижнего уровня** (ProjectionEngine, segment_modes, is_sleeping flag).
2. Но **не трогали** главный каузальный разрыв: **Фаза 0 и Фаза 5 работают с РАЗНЫМИ копиями NPC-данных**.
3. Плюс мой фикс #1 (ProjectionEngine suppress in-flight) на самом деле **не спасал**, потому что в `apply_with_shadow_observation` (строка 227) `SSM.apply_changes` вызывается **после** `ProjectionEngine.apply` и всё равно затирал traversal через `build_traversal_dict` (строка 1244-1248 scene_state_manager.py).

**Лог-доказательство:** после применения патчей v1.0 `sleep_test2.log` показывает тот же результат:
```
❌ guard_borko: city_gate:exit_west  (ожидался guard_bed)
❌ blacksmith_orm: city_gate:exit_west  (ожидался tent_1)
❌ merchant_goran: city_gate:exit_west  (ожидался tent_2)
```

Это значит, что NPC **доходят до boundary `exit_west`** в своей локации, но **не материализуются** в target-локации. Проблема не в `active_traversals` lifecycle (как я думал в v1.0), а в **другом месте**.

---

## Реальные корневые причины (4 шт.)

### ПРИЧИНА A [КРИТИЧНО] — `build_tick_state` deepcopy разрывает routine-обновления Фазы 0

**Файл:** `backend/app/services/pipeline_runner.py:57`

```python
_tick_state = create_tick_state(
    ...
    all_npcs_raw=copy.deepcopy(alive_npcs),  # S-143 FIX: Deep copy
    ...
)
```

**Ситуация:**
1. Фаза 0: `LifeEngine._simulate_major` мутирует `npc["routine"]["current"] = "sleeping"` **в `_npc_cache[campaign_id]`** (потому что `npc` — это ссылка на dict из кэша).
2. Фаза 1: `_phase_1_input_merge` вызывает `_life_engine.get_npc_states()`, который возвращает `copy.deepcopy(_npc_cache[campaign_id])` — **с актуальным routine**.
3. `_run_core_phases:612-616` фильтрует `ctx.all_npcs_raw` по текущей локации — оставляя только NPC в текущей локации, **с актуальным routine**.
4. Фаза 5: `build_tick_state(alive_npcs=ctx.all_npcs_raw)` делает **ещё один deepcopy**.
5. В `NpcTickPipeline.run` `_current_activity = npc.get("routine", {}).get("current", "")` (строка 350) читает эту **вторую копию** — routine **должен** быть "sleeping".

**То есть формально routine виден.** Но ваш лог показывает, что `guard_borko` получает `SPREAD_RUMOR`. Значит, либо:
- **(a)** routine["current"] НЕ равен "sleeping" в момент чтения (GAP9 bypass не сработал, потому что мой фикс #5 убрал `npc["routine"]["current"] = "sleeping"` — а это была **единственная** точка, где спящий статус записывался при блокировке!)
- **(b)** `guard_borko` не симулировался в Фазе 0 (потому что его нет в scene_state[tavern] — он в city_gate), и его routine остался с предыдущего тика.

**Вариант (b) — это реальная проблема.** Когда `idle_tick(location_id="tavern")` тикает:
- `LifeEngine` пропускает `guard_borko` (он в city_gate, не в scene_state[tavern])
- `routine["current"]` для `guard_borko` остаётся с прошлого city_gate-тика
- Если в том тике GAP9 сработал (стресс высокий), мой фикс #5 **убрал** пометку "sleeping"
- Теперь routine["current"] — это, скажем, "guarding_gate"
- SLEEP_GUARD не срабатывает → DecisionHub свободно выдаёт SPREAD_RUMOR

**Корень:** мой фикс #5 сломал GAP9-механизм пометки, и теперь SLEEP_GUARD теряет состояние сна между локациями.

---

### ПРИЧИНА B [КРИТИЧНО] — `build_npc_contexts_from_intents` перезаписывает `ctx.movement_intents`

**Файл:** `backend/app/services/pipeline_runner.py:102`

```python
def build_npc_contexts_from_intents(ctx, mutation):
    ctx.communication_intents = mutation.communication_intents or []
    ctx.movement_intents = mutation.movement_intents or []  # ← ПЕРЕЗАПИСЬ
    ctx.significant_events = mutation.npc_deltas or []
```

**Фаза 0 уже обработала** `life_intents` напрямую через `MovementEngine.process_intents` и создала `TraversalState` (см. `simulation.py:74-98`). TraversalState **персистирует в `scene_state["active_traversals"]`**.

Но Фаза 5 `process_movement_intents` (movement_bridge.py) тоже вызывает `MovementEngine.process_intents` с интентами из `mutation.movement_intents`. Если для NPC уже есть active_traversal, а Фаза 5 даёт новый intent с другой целью — `MovementEngine` создаст **новый** TraversalState (через `apply_with_shadow_observation` → SSM), который **затрёт** старый.

**Конкретно для `blacksmith_orm`:**
- Фаза 0: LifeEngine видит, что time=02:00, activity=sleeping, цель=`city_gate:tent_1`. NPC в tavern. Создаёт MacroMovementGoal с reason="schedule:sleeping". MovementEngine видит cross-loc → перенаправляет на `exit_east`. Создаёт TraversalState от bar_area к exit_east.
- Фаза 0.5: `TraversalExecutionSystem.advance` двигает NPC по пути.
- Фаза 5: DecisionHub выдаёт IDLE (потому что `routine["current"]="sleeping"` + SLEEP_GUARD блокирует proactive). `mutation.movement_intents = []`. `ctx.movement_intents = []`.
- Phase 5 Movement Bridge: `process_movement_intents([])` — пустой список, ничего не делает.

**То есть для `blacksmith_orm` проблема НЕ в перезаписи.** TraversalState живёт в `scene_state["active_traversals"]` и **должен** продолжать двигать NPC.

**Реальная проблема для `blacksmith_orm`** — traversal **никогда не завершается**. Это та самая ПРИЧИНА #1 из v1.0 — но она всё ещё актуальнана. Мой фикс #1 не сработал, потому что **legacy SSM path** (`scene_state_manager.py:1244-1248`) всё равно перезаписывает traversal через `build_traversal_dict`, и мой `suppress in-flight` в ProjectionEngine **не спасает** — SSM просто не видит suppress'а.

---

### ПРИЧИНА C [КРИТИЧНО] — `LifeEngine` пропускает NPC не в текущей локации

**Файл:** `backend/app/services/npc/life_engine.py:580-597`

```python
_in_scene = npc_id in scene_state.get("npc_positions", {})
if not _in_scene and _current_loc:
    logger.debug(f"[LIFE_ENGINE][OFFSCREEN] npc={npc_id} ... — skipped")
    continue
```

**Ситуация:** `test_sleep_routing.py` тикает `tavern` и `city_gate` по очереди:
- `idle_tick(tavern)`: LifeEngine видит только NPC в tavern. `guard_borko` (city_gate) пропущен.
- `idle_tick(city_gate)`: LifeEngine видит только NPC в city_gate. `tavern_keeper_tornin` (tavern) пропущен.

**Когда NPC в active traversal из tavern в city_gate:**
- На тике tavern: NPC ещё в `scene_state[tavern]["npc_positions"]` → LifeEngine симулирует, обновляет routine, генерирует intent.
- На следующем тике city_gate: NPC **уже не в** `scene_state[city_gate]["npc_positions"]` (он ещё не материализовался) → LifeEngine пропускает.
- Если traversal завершается на тике city_gate, NPC попадает в `scene_state[city_gate]["npc_positions"]` только в **следующем** тике.

**Это создаёт «слепую зону»:** NPC в transit между локациями **не симулируется ни одним из LifeEngine-тиков**. Его routine не обновляется, потребности не растут, стресс не падает.

---

### ПРИЧИНА D [ВЫСОКО] — `SLEEP_GUARD` неэффективен для NPC в transit

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:476-480`

```python
if _current_activity in ("sleeping", "resting", "спит"):
    from app.services.npc.decision_hub import PROACTIVE_INTENTS
    for _p_intent in PROACTIVE_INTENTS:
        _all_modifiers[_p_intent] = _all_modifiers.get(_p_intent, 0.0) - 10.0
    _all_modifiers["flee"] = _all_modifiers.get("flee", 0.0) - -10.0
```

**Проблема 1:** `PROACTIVE_INTENTS` — это множество **Enum** значений (`Intent.SPREAD_RUMOR` и т.д.). Но `_all_modifiers` — словарь, где ключи — **строки** ("spread_rumor", "ambush"). Когда мы пишем `_all_modifiers[_p_intent] = ... - 10.0`, мы добавляем ключ-Enum в словарь, но DecisionHub ищет по строковому ключу. **Штраф не применяется.**

**Проблема 2:** `_current_activity` читается из `state.all_npcs_raw[i]["routine"]["current"]`. Это **deepcopy** (см. ПРИЧИНА A). Если GAP9 bypass не поставил "sleeping" (потому что мой фикс #5 убрал эту строку), то `_current_activity` — это **предыдущая** активность ("guarding_gate" для borko). SLEEP_GUARD не срабатывает.

**Доказательство из лога:** `guard_borko: Intent.SPREAD_RUMOR score=0.187` — штраф -10.0 **не применился**, иначе score был бы отрицательным.

---

## Цепочка для `guard_borko` (конкретный разбор)

1. Тик `idle_tick(tavern)`:
   - `guard_borko` в `scene_state[city_gate]` → LifeEngine **пропускает** (ПРИЧИНА C)
   - `routine["current"]` остаётся с прошлого city_gate-тика
   - В `_phase_5_decision` (для tavern) `guard_borko` **не обрабатывается** (он не в `ctx.all_npcs_raw` после фильтра по локации)
2. Тик `idle_tick(city_gate)`:
   - `guard_borko` в `scene_state[city_gate]` → LifeEngine симулирует
   - time=02:00 → activity=sleeping
   - GAP9 bypass: threat/stress высокий (test не обнулил, потому что обнулял только для tavern) → **ДО моего фикса #5**: `routine["current"]="sleeping"`, return. **ПОСЛЕ фикса #5**: routine не меняется, return.
   - В Фазе 5 (city_gate): `_current_activity` = "guarding_gate" (или другая старая) — **НЕ "sleeping"**
   - SLEEP_GUARD не срабатывает (ПРИЧИНА D)
   - DecisionHub выдаёт `SPREAD_RUMOR` (score=0.187)
   - `movement_intents.append(MacroMovementGoal(reason="proactive_spread_rumor"))`
   - Phase 5 Movement Bridge: MovementEngine.process_intents → новый TraversalState для `proactive_spread_rumor` → **затирает** schedule:sleeping traversal (если он был)

3. Итог: `guard_borko` стоит на `exit_west` (или другом boundary) и bounce'ит между локациями.

---

## Цепочка для `blacksmith_orm` (конкретный разбор)

1. Тик `idle_tick(tavern)`:
   - `blacksmith_orm` в `scene_state[tavern]` → LifeEngine симулирует
   - time=02:00 → activity=sleeping, цель=`city_gate:tent_1`
   - Стресс обнулён тестом → GAP9 не срабатывает
   - LifeEngine создаёт `MacroMovementGoal(reason="schedule:sleeping")`
   - MovementEngine видит cross-loc → redirect на `tavern:exit_east`
   - Создаёт TraversalState от `bar_area` к `exit_east`, duration_ticks=3
2. Тик `idle_tick(city_gate)`:
   - `blacksmith_orm` **не в** `scene_state[city_gate]` (он ещё в tavern transit) → LifeEngine пропускает (ПРИЧИНА C)
   - В Фазе 5 city_gate: `blacksmith_orm` не в `ctx.all_npcs_raw` (фильтр по локации) → не обрабатывается
3. Тик `idle_tick(tavern)` (следующая итерация):
   - `blacksmith_orm` всё ещё в `scene_state[tavern]["npc_positions"]` (потому что traversal ещё не завершён)
   - **Но!** Traversal уже создан в `scene_state[tavern]["active_traversals"]`
   - LifeEngine видит active traversal → early return (строки 1112-1119): "Major cycle bypassed — active traversal"
   - routine не обновляется, новый intent не генерируется
   - Фаза 5: `_current_activity` = "sleeping" (мутация прошла в прошлом тике) → SLEEP_GUARD работает → DecisionHub выдаёт IDLE → movement_intents=[]
4. **Traversal должен завершиться через 3 тика** и materialize в city_gate.
5. Но **лог показывает**, что traversal не завершается. NPC остаётся на `exit_west`.

**Почему traversal не завершается?**
- TraversalState был создан с `started_tick=T`, `duration_ticks=3`
- На тике T+1 `TraversalExecutionSystem.advance` должен интерполировать позицию
- На тике T+3 `elapsed_ticks >= duration_ticks` → transition_traversal("COMPLETED") → snap позиции → удалить из active_traversals
- Materialize scene_change отправляется в `apply_with_shadow_observation`
- `SSM.apply_change` обрабатывает `cause="cross_loc_materialize"` → обновляет `entry["position"]`, `entry["location_id"]`

**В коде `movement_engine.py:266`** есть materialize-condition:
```python
_is_at_boundary = (_npc_pos_data.get("position", "") == boundary_node.node_id)
if _is_at_boundary or _dist_to_boundary < 1.5:
    # materialize
```

**Но это условие проверяется только при обработке НОВОГО intent!** Если в этом тике нет нового intent (например, SLEEP_GUARD выдал IDLE), `MovementEngine.process_intents` не вызывается с этим NPC — materialize **не происходит**.

**Это ПРИЧИНА E — materialize требует нового intent, а не завершения traversal.**

---

## ПРИЧИНА E [КРИТИЧНО] — Cross-loc materialize работает только при наличии нового intent

**Файл:** `backend/app/services/spatial/movement_engine.py:237-325`

Cross-loc materialize — это логика внутри `process_intents`, которая проверяет «NPC стоит на boundary node» и порождает `cross_loc_materialize` SceneChange. **Если в этом тике для этого NPC нет нового intent — materialize не вызывается.**

**Цикл жизни:**
1. Tick T: `blacksmith_orm` в tavern, LifeEngine даёт intent спать в city_gate. MovementEngine видит cross-loc, redirect на `exit_east`, создаёт TraversalState.
2. Tick T+1..T+2: TraversalExecutionSystem интерполирует local_position. NPC ещё в scene_state[tavern]. LifeEngine early-return (active traversal). No new intent.
3. Tick T+3: `process_traversals` видит `elapsed_ticks >= duration_ticks` → transition COMPLETED → `snap to target_xy`. **Но target_xy — это `exit_east` в tavern**, не `tent_1` в city_gate!**
4. TraversalState удалён. NPC теперь стоит на `exit_east` (физически), но `position` в `npc_positions` всё ещё `bar_area` (или что-то ещё).
5. Tick T+4: LifeEngine видит, что activity=sleeping, цель=`city_gate:tent_1`. NPC не на цели. Создаёт **новый** intent. MovementEngine видит cross-loc, redirect на `exit_east` (опять). NPC уже на exit_east → `_is_at_boundary=True` → **materialize!**
6. Materialize создаёт SceneChange(`cross_loc_materialize`) → NPC попадает в city_gate.
7. Но... в логах NPC застрял на `exit_west`. Это значит, что шаг 5 или 6 не произошёл.

**Гипотеза:** на шаге 5 LifeEngine не создаёт intent, потому что:
- Либо `_resolve_position` возвращает None (нет activity_map.sleeping)
- Либо `new_activity == prev_activity` и S140 spatial verification думает, что NPC уже на месте
- Либо GAP9 bypass сработал

**Вторая гипотеза (более вероятная):** на шаге 5 Phase 0 создаёт intent, но Фаза 5 **не трогает** его — и `process_traversals` (Фаза 0.75) видит, что traversal уже COMPLETED и удалён. Новый intent не обрабатывается, потому что `me.process_intents` в Фазе 0 создаёт новый traversal — но на этот раз **от `exit_east` к `exit_east`** (т.к. целевая локация та же). A* возвращает пустой путь → traversal не создаётся → materialize не происходит.

---

## Что нужно чинить (новый план)

### ШАГ 1 (ПРИЧИНА D) — SLEEP_GUARD: использовать строковые ключи

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py:476-480`

```python
# БЫЛО:
for _p_intent in PROACTIVE_INTENTS:
    _all_modifiers[_p_intent] = _all_modifiers.get(_p_intent, 0.0) - 10.0

# НАДО:
for _p_intent in PROACTIVE_INTENTS:
    _intent_str = _p_intent.value  # Intent.SPREAD_RUMOR → "spread_rumor"
    _all_modifiers[_intent_str] = _all_modifiers.get(_intent_str, 0.0) - 10.0
```

Это **точно починит** `guard_borko` SPREAD_RUMOR — score станет -9.813 вместо 0.187, DecisionHub не выберет этот intent.

### ШАГ 2 (ПРИЧИНА A + мой фикс #5) — Восстановить пометку routine["current"]="sleeping" в GAP9

**Файл:** `backend/app/services/npc/life_engine.py:1786-1793` (после моего фикса #5)

Мой фикс #5 был **неправильным**. Убрав `npc["routine"]["current"] = "sleeping"`, я сломал SLEEP_GUARD для NPC в transit между локациями. **Вернуть пометку**, но с оговоркой: это **поведенческий** статус, не физиологический.

```python
# ВЕРНУТЬ (откатить фикс #5):
if _threat > 0.3 or _stress > 50:
    logger.debug(f"[DIAG_GAP9] {npc_id}: SLEEP BYPASSED!")
    # Помечаем sleeping, чтобы SLEEP_GUARD блокировал социализацию.
    # NPC не идёт к кровати, но и не должен получать proactive intents.
    npc["routine"]["current"] = "sleeping"
    return [], None
```

### ШАГ 3 (ПРИЧИНА C) — LifeEngine должен симулировать NPC в active traversal

**Файл:** `backend/app/services/npc/life_engine.py:580-597`

```python
# БЫЛО:
_in_scene = npc_id in scene_state.get("npc_positions", {})
if not _in_scene and _current_loc:
    continue  # skip offscreen

# НАДО: не пропускать NPC в active traversal, даже если он не в npc_positions
_active_travs = scene_state.get("active_traversals", {})
_in_transit = npc_id in _active_travs
if not _in_scene and not _in_transit and _current_loc:
    continue
```

Это позволит LifeEngine обновлять routine для NPC, которые в transit между локациями.

### ШАГ 4 (ПРИЧИНА E) — Materialize должен работать без нового intent

**Файл:** `backend/app/services/spatial/movement_engine.py` + `phases/traversal.py`

Когда `process_traversals` завершает traversal (transition COMPLETED), нужно проверить: целевой узел — это boundary? Если да, вызвать materialize logic.

**Альтернатива (проще):** в `process_traversals`, при завершении traversal, если целевая локация != текущая — породить `cross_loc_materialize` SceneChange напрямую.

Это сложный фикс, требует понимания traversal completion flow.

### ШАГ 5 (ПРИЧИНА B) — Не перезаписывать ctx.movement_intents пустым списком

**Файл:** `backend/app/services/pipeline_runner.py:102`

```python
# БЫЛО:
ctx.movement_intents = mutation.movement_intents or []

# НАДО: расширять, а не перезаписывать
_new_movement = mutation.movement_intents or []
# Сохраняем интенты от Фазы 0 (LifeEngine), если Фаза 5 ничего не добавила
_existing = getattr(ctx, 'movement_intents', []) or []
ctx.movement_intents = _existing + _new_movement
```

Хотя — после анализа выше — Фаза 0 **не кладёт** life_intents в `ctx.movement_intents`. Она обрабатывает их напрямую. Так что этот фикс **не нужен** для починки бага, но **нужен** для семантической чистоты (на случай, если future code будет читать `ctx.movement_intents` после Фазы 0).

### ШАГ 6 — `test_sleep_routing.py` должен обнулять стресс во ВСЕХ локациях

**Файл:** `scripts/test_sleep_routing.py:64-68`

```python
# БЫЛО:
for npc in scene_state.get("npcs", []):
    npc.setdefault("psyche", {})["stress"] = 0.0
    _pk = npc.setdefault("perceptual_kernel", {})
    if isinstance(_pk, dict):
        _pk["threat_gradient"] = 0.0

# НАДО: то же самое для city_gate
for _loc in ["tavern", "city_gate"]:
    _ss = scene_manager.get_scene_state(campaign_id, _loc)
    if not _ss:
        continue
    for npc in _ss.get("npcs", []):
        npc.setdefault("psyche", {})["stress"] = 0.0
        _pk = npc.setdefault("perceptual_kernel", {})
        if isinstance(_pk, dict):
            _pk["threat_gradient"] = 0.0
    scene_manager.save_scene_state(campaign_id, _ss)
```

---

## Резюме: что было не так в v1.0

| Патч v1.0 | Реальный эффект | Вердикт |
|-----------|-----------------|---------|
| #1 (ProjectionEngine suppress in-flight) | Не работает, потому что legacy SSM всё равно перезаписывает | ❌ бесполезен |
| #2 (segment_modes в shadow fields) | Чинит предупреждение, но не сам баг | ⚠️ косметика |
| #3 (WorldTickEngine skip sleeping) | Бесполезен, потому что `guard_borko` не помечен как sleeping (ПРИЧИНА A) | ❌ бесполезен |
| #4 (is_sleeping flag) | Бесполезен, потому что routine["current"] не "sleeping" | ❌ бесполезен |
| #5 (убрать routine="sleeping" в GAP9) | **СЛОМАЛ** SLEEP_GUARD для transit NPC | 🔥 регрессия |
| #6 (_sleep_start_tick) | Не вредит, но и не помогает, пока SLEEP_GUARD не работает | ⚠️ нейтрален |
| #7 (maid_lusya config) | Чинит расписание Люси | ✅ работает |

**Только патч #7 был полезным.** Остальные либо бесполезны, либо вредны.

---

## Что делать дальше

**Откатить все патчи v1.0**, кроме #7 (maid_lusya config). Применить новые ШАГИ 1-6.

Особенно критичны:
- **ШАГ 1** (SLEEP_GUARD string keys) — точно починит SPREAD_RUMOR для borko
- **ШАГ 2** (вернуть routine="sleeping" в GAP9) — откат регрессии v1.0
- **ШАГ 3** (LifeEngine simulates transit NPC) — починит «слепую зону» между локациями
- **ШАГ 4** (materialize без нового intent) — починит blacksmith_orm/goran застревание на exit_west

После ШАГОВ 1-3 запуск `test_sleep_routing.py` должен показать прогресс. ШАГ 4 требует более глубокой переработки traversal completion flow.

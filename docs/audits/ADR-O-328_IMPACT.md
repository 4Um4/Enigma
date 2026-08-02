## ADR-O-328: Dual Rail Boundary Consistency [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-04 (Spatial & Locomotion), DOM-08 (Observability)
> **Сессия:** S148

**Контекст:** 
При `cross_loc_materialize` возникал Causal Drift (Class D), так как `EquivalenceValidator` сравнивал мутированное состояние Legacy (где локация уже обновлена) со снимком Shadow (где локация старая). Это приводило к `True != False` и блокировало ФАЗУ 3.

**Решение:**
1. Вычисление `is_boundary` в `validation.py` основывается на `SceneChange.cause` (`"cross_loc_materialize" in cause`), а не на сравнении мутированного state с snapshot.
2. `EventCompiler` гарантирует `is_boundary=True` для `cross_loc_materialize`.
3. `MovementEngine` не создаёт `SceneChange` с `cross_loc_materialize` без `target_location_id`.
4. `DriftLaboratory` внедряет *Ground Truth Validator* и *Valid Comparisons Tracking* для честной оценки готовности ФАЗЫ 3.

**Taboo:**
- ❌ Вычисление `legacy_is_boundary` на основе `scene_state["npc_positions"][npc_id]["location_id"]` (мутированное состояние).
- ❌ Создание `SceneChange` с `cause="cross_loc_materialize"` без `target_location_id`.
- ❌ Объявление ФАЗЫ 3 готовой при наличии крашнувшихся тиков или < 100k comparisons.
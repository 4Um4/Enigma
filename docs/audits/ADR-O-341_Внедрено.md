# ADR-O-341 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-341` [STANDARD] **Внедрено**
## ADR-O-341: Dual Rail Boundary Consistency [ONTO]
> **Статус:** ACTIVE
> **Домен:** DOM-04 (Spatial & Locomotion), DOM-08 (Observability)
> **Сессия:** S149

**Контекст:** 
При `cross_loc_materialize` возникал Causal Drift (Class D), так как `EquivalenceValidator` сравнивал мутированное состояние Legacy со снимком Shadow.

**Решение:**
1. Вычисление `is_boundary` в `validation.py` основывается на `SceneChange.cause` (`"cross_loc_materialize" in cause`), а не на сравнении мутированного state с snapshot.
2. `DriftLaboratory` внедряет *Ground Truth Validator* и *Valid Comparisons Tracking* для честной оценки готовности ФАЗЫ 3.

**Taboo:**
- ❌ Вычисление `legacy_is_boundary` на основе мутированного `location_id`.
- ❌ Объявление ФАЗЫ 3 готовой при наличии крашнувшихся тиков или < 100k comparisons.


Files: N/A

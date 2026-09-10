# ADR-O-384 Impact Audit
> Детальный аудит одного ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
intent (Desire/Activity как давления и факты), memory (outcome-событие; проводка в память — открытый пункт), identity (current_role-проводка в адаптер), потребности (двухрежимное насыщение), world (food_portion-субстрат).

## Downstream Consumers
NpcTickPipeline (через simulation.py: продюсер+конвертер ДО Гейта①), CommitmentRegistry/Arbiter (reconcile_activity_ownership + арбитраж MOVE-целей), R3/DM (блок занятости → SceneContinuity), WorldObjectStore (типизированные мутации TAKE/damage/release), HUD (npc_positions.activity), DecisionHub (косвенно: подавление легаси-движения; AffordanceSet НЕ параметр — taboo O-378 соблюдён).

## Runtime Impact
ON: генератор O(N) + конвертер O(N) + linear-scan world query ≈ +1-2мс/тик на 6 NPC. OFF: 0 (no-op; доказано SUPERBOX C1 + IPT 45/45). Персистенция: 2 новых npc-ключа (desires, activity_state) через Foundation-Freeze deep-merge — миграция сейвов ленивая.

## Sandbox Tests
SUPERBOX eat_vertical_test 12/12; юнит-сьюты 39 (domain 8, generator 6, food 9, lifecycle 8, needs 5, visibility 3); test_npc_state_r6 5/5 (адаптер).

## Rollback
Флаги DESIRES_ENABLED/ACTIVITY_LIFECYCLE_ENABLED default OFF = полный no-op. Код реверсивен: 5 новых файлов + точечные правки (life_engine/simulation/r3/registry/adapter/event_types). Контент: 3 объекта tavern.json + SpawnMapping-строка. R1-фикс current_role — автономный (оставить: порог ТЗ 9.2).

## Открытые пункты (честно)
1. CONSEQUENCE_REACHES_MEMORY: событие на шине ✓ — подписка MemoryManager НЕ проведена.
2. Метрики ТЗ 2.1 (пустые прибытия ≤10%, пинг-понг ≤×5): замер в живой игровой сессии.
3. SpatialTargetType+OBJECT: мини-ADR отложен (конвертер резолвит узлы через resolve_node).
4. INTERRUPT-сценарий: reconcile написан, возобновление цели прогоном не покрыто.
5. PREFERENCE_STABLE: sleep-домен, вне EAT.

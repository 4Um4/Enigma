# ADR-O-376 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- WORLD (Object FSM: домен/стор/спавнер), SIMULATION (G1-shadow врезка в оркестратор, initialize_scene-спавн)

## Downstream Consumers
- AffordanceResolver (W2): effective_state остаётся источником W2; W3 его НЕ канонизирует — деривация отношений (О2)
- WorldSnapshotBuilder: deepcopy-мост world_objects (S215-паттерн) — теперь несёт реальные данные
- TickOrchestrator: G1-врезка после build_snapshot (до PRE-TICK)
- graph_compiler/spatial: НЕ затронуты (порталы/рёбра — их зона; О8-факт topology_effect — их будущий вход)
- CommitmentRegistry/Arbiter: не затронуты (G2/G3 — будущие гейты)

## Runtime Impact
- Спавнер: единожды на рождение сцены (18 объектов, ms-масштаб); персистенция — существующий atomic_commit (ноль нового кода)
- G1-тень (OFF default): ноль; ON: 7 NPC × 18 объектов resolve/тик — мкс-масштаб; ноль allocation в тик-контуре кроме метрик
- IPT: +0 инвариантов (live-часть существующего INV-WORLD-OBJECT-TOPOLOGY ожила: live=18)

## Sandbox Tests
- tests/test_object_fsms.py (30), tests/test_world_object_spawner.py (10, 1 skip — campaign-JSON вне CI-окружения), tests/test_affordance_shadow.py (8)
- scripts/w3_shadow_simple.py: GORAN β G1 — 2 прогона × (A/B/C + A2/B2 + A3/B3) = 10 профилей; вердикт GREEN + ambient qualification

## Rollback
- Удалить врезку G1 в tick_orchestrator (:797) + спавн-вызов в initialize_scene + world_objects-корень; домен/спавнер/тень/тесты — удалить файлы; стор: revert apply_transition/apply_damage + импортов. W1/W2 не задеты (их сьюты остаются зелёными при откате W3-файлов).

## Известные ограничения / вердикты Мастера
- О8: runtime OPEN/CLOSE не перекомпилирует граф (topology_effect — факт, invalidation W5)
- О4: bed/stool/table — вне SpawnMapping v1 (нет W2-таблиц)
- DEBT-QUIESCE (ambient qualification) — внешний долг, не W3-scope
- G2/G3 — контракт, не реализация
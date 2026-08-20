# ADR-159 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-159` [STANDARD] **IMPACT**
# ADR-159 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Combat (RNG Isolation, Attack Roll, AC Calculation)
- Memory (Pipeline Runner, MemoryManager.apply)
- Identity (CrystallizedBeliefStore SQLite persistence)

## Downstream Consumers
- ackend/tests/test_impact_engine.py (раскрыты flaky-тесты, обновлены ассерты)
- ackend/tests/test_physiology_flow.py (обновлен ng_seed для гарантированного попадания)
- ackend/app/services/game/combat_math.py (добавлен ng параметр)
- ackend/app/services/combat/impact_engine.py (добавлен адаптер snapshot -> dict, проброс ng)
- ackend/app/services/npc/npc_tick_pipeline.py (apply_perception_memory → pure function)
- ackend/app/services/pipeline_runner.py (прямые вызовы MemoryManager.apply)
- ackend/app/services/npc/crystallized_belief_store.py (SQLite backing)
- ackend/app/services/tick_orchestrator.py (передача store в CrystallizedBeliefStore)

## Runtime Impact
- RAM: 0 (изменения не требуют дополнительной памяти)
- Latency: 0 (передача объекта ng не влияет на производительность)
- SQLite I/O: +1 INSERT/DELETE per NPC per tick (для убеждений) — минимальное влияние

## Sandbox Tests
- ackend/tests/test_impact_engine.py::TestContactResolution::test_high_dexterity_dodge (PASSED)
- ackend/tests/test_impact_engine.py::TestContactResolution::test_low_dexterity_hit (PASSED)
- ackend/tests/test_impact_engine.py::TestZoneModifiers::test_head_hit_high_pain (PASSED)
- ackend/tests/test_impact_engine.py::TestZoneModifiers::test_groin_hit_massive_pain_low_bleed (PASSED)
- ackend/tests/test_physiology_flow.py::TestCombatEmotionCascade::test_violence_generates_fear (PASSED)
- ackend/tests/sandbox/persistence/test_crystallized_belief_persistence.py::test_beliefs_survive_restart (PASSED)
- ackend/tests/sandbox/persistence/test_l1_chronicle_archival.py::test_archive_old_events_does_not_crash (PASSED)

## Rollback
- Убрать параметр ng из вызовов combat_math.py в impact_engine.py.
- Вернуть @pytest.mark.skip к тестам в 	est_impact_engine.py.
- Вернуть pply_perception_memory к вызову memory_manager.apply() внутри reducer.
- Вернуть CrystallizedBeliefStore к in-memory only (убрать store параметр).



Files: N/A

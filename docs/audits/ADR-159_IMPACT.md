# ADR-159 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Combat (RNG Isolation, Attack Roll, AC Calculation)

## Downstream Consumers
- ackend/tests/test_impact_engine.py (раскрыты flaky-тесты, обновлены ассерты)
- ackend/tests/test_physiology_flow.py (обновлен ng_seed для гарантированного попадания)
- ackend/app/services/game/combat_math.py (добавлен ng параметр)
- ackend/app/services/combat/impact_engine.py (добавлен адаптер snapshot -> dict, проброс ng)

## Runtime Impact
- RAM: 0 (изменения не требуют дополнительной памяти)
- Latency: 0 (передача объекта ng не влияет на производительность)

## Sandbox Tests
- ackend/tests/test_impact_engine.py::TestContactResolution::test_high_dexterity_dodge (PASSED)
- ackend/tests/test_impact_engine.py::TestContactResolution::test_low_dexterity_hit (PASSED)
- ackend/tests/test_impact_engine.py::TestZoneModifiers::test_head_hit_high_pain (PASSED)
- ackend/tests/test_impact_engine.py::TestZoneModifiers::test_groin_hit_massive_pain_low_bleed (PASSED)
- ackend/tests/test_physiology_flow.py::TestCombatEmotionCascade::test_violence_generates_fear (PASSED)

## Rollback
- Убрать параметр ng из вызовов combat_math.py в impact_engine.py.
- Вернуть @pytest.mark.skip к тестам в 	est_impact_engine.py.

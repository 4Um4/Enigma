# ADR-O-305 Impact Audit: Belief Crystallization Engine (L2.5)
> Этот файл — детальный аудит ADR-O-305. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-10: IDENTITY & ONTOLOGY (L2.5 Belief Layer)

## Context
L1.5 (PatternDetector) генерирует чистую статистику (`EvidenceOfPersistence`), лишённую психологии. Если L3 или DecisionHub будут читать её напрямую, они либо сломаются от перегрузки, либо начнут галлюцинировать "скалярный страх" (страх без источника). Нужен мост, который переводит статистику в психологическую проекцию (`CrystallizedBelief`), строго модулированную личностью.

## Decision
1. Внедряется `BeliefCrystallizationEngine` (L2.5).
2. Он читает ТОЛЬКО `EvidenceOfPersistence` и `NPCPersonality.drives_base` (L0).
3. `CrystallizedBelief` содержит `source_id` (строго обязательно), `trait` (fear, trust) и `weight` (0.0-1.0).
4. Асимметричная травма (ADR-O-307): Если `cumulative_effect` подтверждает существующий `trait`, `weight` растёт линейно. Если опровергает (меняет знак) — `weight` пересчитывается с множителем `x6`.

## Downstream Consumers
- DecisionHub (через BeliefAggregator или напрямую как belief_modifiers)
- DriveResolver (L3) — для учёта кристаллизованных убеждений при проекции драйвов.

## Runtime Impact
- RAM: Умеренное (хранение `CrystallizedBelief` на NPC).
- Latency: Минимальное (вызов `crystallize()` один раз за тик/сессию для каждого NPC).

## Sandbox Tests
- `test_belief_crystallization_math` (проверка модуляции drives_base)
- `test_asymmetric_trauma_x6` (проверка ADR-O-307)
- `test_no_belief_without_source` (проверка запрета скалярного страха)

## Rollback
Удалить `BeliefCrystallizationEngine` и `CrystallizedBelief`. DecisionHub вернётся к чтению сырых драйвов. L1.5 остаётся нетронутым.
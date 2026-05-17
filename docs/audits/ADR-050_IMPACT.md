# ADR-050 Impact Audit

## Измененный АДР
ADR-050 (Causal Observatory & Epistemic Divergence Sandbox)

## Тип изменения
ONTOLOGY (ADR-O)

## Измененные домены (Changed Domains)
- perception (введение метрик certainty и mutation_stage)
- decision (модуляция utility на основе PsychologicalPressure и DecisionContext)
- social (directive_obedience балансировка)

## Связанные потребители (Downstream Consumers)
- LocalCausalSolver (генерация PerceivedPhenomenon с certainty)
- DecisionHub (чтение DecisionContext.deformation для модуляции utility)
- pressure_translator (мост PsychologicalPressure -> DecisionContext)
- CausalTrace (глобальный наблюдатель в песочницах)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.1MB (в тестовом окружении на фреймы логгера)
- VRAM Delta: 0
- Tick Latency Delta: 0 (инфраструктура изолирована в sandbox)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/phenomenology/test_rumor_mutation.py — Эпистемическое расхождение: слух теряет certainty относительно факта.
- tests/sandbox/phenomenology/test_balance_scales.py — Изолированная верификация математики мембран (экспонента, инференс, драматизация).
- tests/sandbox/system/test_causal_closure.py — Вертикальный срез: Возмущение -> Давление -> Решение (для труса и смельчака).
- tests/sandbox/stress/test_authority_erosion.py — Деградация и восстановление весов при хроническом давлении.

## Откат (Rollback)
1. Удалить директории tests/sandbox/phenomenology/, tests/sandbox/system/, tests/sandbox/stress/.
2. Удалить данный файл.

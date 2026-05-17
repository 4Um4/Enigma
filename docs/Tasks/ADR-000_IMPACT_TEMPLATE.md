# ADR-0XX Impact Audit

## Измененный АДР
[Ссылка на ADR в docs/Tasks/ADR (Architecture Decision Records).md]

## Тип изменения
[STANDARD | ONTOLOGY (ADR-O)]

## Измененные домены (Changed Domains)
- [domain_1]
- [domain_2]

## Связанные потребители (Downstream Consumers)
- [Service/Class, который читает эти данные]
- [Service/Class, который зависит от этого потока]

## Влияние на производительность (Runtime Impact)
- RAM Delta: [оценка]
- VRAM Delta: [оценка]
- Tick Latency Delta: [оценка]

## Песочные тесты (Sandbox Tests)
- tests/sandbox/test_XXX.py — [описание проверяемой каузальной линии]

## Откат (Rollback)
1. [Шаг 1: какие файлы вернуть]
2. [Шаг 2: какие DTO удалить]
3. [Шаг 3: какие тесты удалить]

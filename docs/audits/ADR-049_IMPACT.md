# ADR-049 Impact Audit

## Измененный АДР
ADR-049: Causal Pressure Pipeline & DecisionContext Geometry (Замыкание контуров)

## Тип изменения
ONTOLOGY (ADR-O)

## Измененные домены (Changed Domains)
- perception (Врезка PerceptualKernel в скоринг DecisionHub)
- emotion (Конвертация PerceptionPayload в Legacy Adapter)
- temporal (Cognitive Override Guard в LifeEngine)
- spatial (Устранение player_spatial и denormalize_id)

## Связанные потребители (Downstream Consumers)
- DecisionHub (теперь читает threat_gradient для APPROACH и FLEE)
- LifeEngine (теперь уважает когнитивное давление выше 0.4)
- LegacyStateDeltaAdapter (теперь конвертирует PerceptionPayload в v1 стресс/страх)
- npc_tick_pipeline._resolve_reactive_movement (теперь читает игрока из единого авторитета)

## Влияние на производительность (Runtime Impact)
- RAM Delta: 0
- VRAM Delta: 0
- Tick Latency Delta: +0.1ms (чтение kernel в DecisionHub), -1.5ms (отмена расписания при стрессе экономит тики)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/oscilloscope_closed_loop.py — Проверка замкнутости: Команда → fear_delta → Резолв позиции Игрока → Движение
- tests/sandbox/minimal_obedience_field.py — Валидация Физики Власти с учетом PerceptualKernel

## Откат (Rollback)
1. Вернуть scene_state.get("player_spatial", {}) в _resolve_reactive_movement (ветки approach и flee).
2. Удалить чтение state.perceptual_kernel из _relationship_modifier и risk_penalty в decision_hub.py.
3. Удалить Cognitive Override Guard из life_engine.py.
4. Удалить блок DeltaDomain.PERCEPTION из legacy_delta_adapter.py.

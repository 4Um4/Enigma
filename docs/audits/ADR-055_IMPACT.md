# ADR-055 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-055` [STANDARD] **IMPACT**
# ADR-055 Impact Audit: Affective Pressure Pipeline (Perception → Emotion Converter)

## Измененный АДР
ADR-O (Affective Pressure Domain) — Внедрение нового каузального слоя между Восприятием и Эмоцией.

## Тип изменения
ONTOLOGY (ADR-O) — Смена парадигмы: прямой прыжок Perception→Emotion запрещен. Внедрен промежуточный слой AffectivePressure.

## Измененные домены (Changed Domains)
- perception (входной контур для нового слоя)
- affect (НОВЫЙ домен: давление системы на организм)
- emotion (теперь порождается исключительно через resolve_emotion_from_pressure)
- legacy (adapted: убит procedural collapse в legacy_delta_adapter)

## Связанные потребители (Downstream Consumers)
- TickOrchestrator (Фаза 9: вызывает derive_affective_pressure и resolve_emotion_from_pressure после обновления PerceptualKernel)
- DecisionHub (читает EmotionPayload, порожденную аффективным слоем, на следующем тике T+1)
- LegacyStateDeltaAdapter (теперь корректно схлопывает PerceptionPayload в фоновый стресс без генерации фальшивых эмоций)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.01MB (AffectivePressureDTO на NPC в рамках тика)
- VRAM Delta: 0
- Tick Latency Delta: +0.5ms (вычисление давления и резолюция эмоций в Фазе 9 для каждого NPC)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/phenomenology/test_affective_pressure.py (6 passed) — Вертикальный срез: Perception → Pressure → Panic/Rage

## Откат (Rollback)
1. Удалить директорию `backend/app/services/affective/`.
2. Удалить `AffectivePressureDTO` из `backend/app/models/affect.py`.
3. В `tick_orchestrator.py` (Фаза 9) удалить блок `ADR-O: Affective Pressure Pipeline` после `ctx.delta_buffer.append(delta)`.
4. В `legacy_delta_adapter.py` вернуть процедурный коллапс `threat_gradient_delta * 20.0 -> stress_delta`.

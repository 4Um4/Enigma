Файл: docs\Tasks\ADR-000_IMPACT_TEMPLATE.md
Назначение: Шаблон для фиксации каузального следа архитектурных изменений. Защита от амнезии LLM и усталости архитектора.
Зависимости: АРХИТЕКТУРНЫЙ УСТАВ.md, РЕЖИМ РАБОТЫ.md (Секция 12)
Основные сущности: Impact Audit Log

```
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
- `tests/sandbox/test_XXX.py` — [описание проверяемой каузальной линии]

## Откат (Rollback)
1. [Шаг 1: какие файлы вернуть]
2. [Шаг 2: какие DTO удалить]
3. [Шаг 3: какие тесты удалить]
```

---

# ADR-044 Impact Audit

## Измененный АДР
ADR-044 (Single Source Spatial Authority) & ADR-045 (Spatial Macro-Zone Direct Resolution)

## Тип изменения
STANDARD

## Измененные домены (Changed Domains)
- SPATIAL
- SOCIAL (utility calculation)

## Связанные потребители (Downstream Consumers)
- `MovementEngine` (читает `MovementIntent.target_node_id`)
- `SceneStateManager` (читает `MovementIntent.local_target_xy`)
- `TransitTracker` (вычисляет длительность транзита)
- Frontend `SceneRenderer` (читает `active_traversals`)

## Влияние на производительность (Runtime Impact)
- RAM Delta: 0
- VRAM Delta: 0
- Tick Latency Delta: -0.5ms (устранен вызов `spatial_service.get_nearest` для известных сущностей)

## Песочные тесты (Sandbox Tests)
- `tests/sandbox/oscilloscope_closed_loop.py` — Проверка замкнутости: Команда → fear_delta → Резолв позиции Игрока → Движение

## Откат (Rollback)
1. Вернуть чтение `scene_state.get("player_spatial", {})` в `_resolve_reactive_movement`
2. Вернуть хардкод `_MACRO_ZONES` и поиск через `get_nearest(x, y)`
3. Удалить тест `oscilloscope_closed_loop.py`


---


# ADR-040 Impact Audit

## Измененный АДР
[ADR-040: PerceptualKernel Integration & Perception Domain](docs/Tasks/ADR%20(Architecture%20Decision%20Records).md)

## Тип изменения
ONTOLOGY (ADR-O)

## Измененные домены (Changed Domains)
- `perception` (PerceptualKernel: threat_gradient, uncertainty, anomaly_score, dominant_emotion)
- `emotion` (Генерация PsychologicalPressure в _phase_9_integration перенаправлена через PERCEPTION)

## Связанные потребители (Downstream Consumers)
- `LocalCausalSolver` (читает `observer_kernel` для проекций)
- `CognitiveProjection` (читает `anomaly_score`, `threat_gradient`)
- `StateApplicator` (применяет `PerceptionPayload` к `NPCState.perceptual_kernel`)
- `DecisionHub` (потенциальный потребитель `threat_gradient` для утилити)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.05MB (хранение PerceptionPayload в delta_buffer)
- VRAM Delta: 0
- Tick Latency Delta: +0.2ms (сборка PerceptionPayload в Фазе 9)

## Песочные тесты (Sandbox Tests)
- `tests/sandbox/sandbox_cfrm_vertical.py` — Проверка каузальной линии: Возмущение → Мембрана → Феномен → Давление → Восприятие.
- `tests/test_cfrm_models.py` — Целостность доменов CFRM.

## Откат (Rollback)
1. Удалить `DeltaDomain.PERCEPTION` из `state_delta.py`.
2. Удалить `PerceptionPayload` из `delta_payloads.py`.
3. Вернуть генерацию `EmotionPayload` напрямую из `PhenomenologicalState` в `tick_orchestrator.py` (_phase_9_integration).
4. Удалить блок `DeltaDomain.PERCEPTION` из `state_applicator.py`.
5. Удалить данный файл `docs/audits/ADR-040_IMPACT.md`.


---


### ADR-049 PRE-FLIGHT CHECKLIST: LifeEngine De-godification & Intent-Based Scheduling

**1. Тип АДР:** ONTOLOGY (ADR-O) — Смена парадигмы перемещения от мутации к локомоции.

**2. Затронутые домены:**
- `spatial` (перемещение)
- `cognition` (расписание как давление, а не команда)
- `time` (продвижение времени)

**3. Связанные потребители (Downstream):**
- `MovementEngine` (начнет получать Schedule Intents)
- `SceneStateManager` (перестанет получать уже примененные SceneChange)
- `TransitTracker` (появятся новые транзиты)
- Фронтенд (`SceneRenderer` — наконец-то увидит идущих NPC)

**4. Бюджет ресурсов:**
- RAM Delta: 0
- Tick Latency Delta: +1-2ms (добавление MovementIntent в пайплайн MovementEngine)

**5. Откат (Rollback):**
Вернуть прямую мутацию `npc["position"]` и ранний возврат из `update_routine`.

**6. Регрессия:**
`tests/sandbox/test_schedule_locomotion.py` — Расписание генерирует Intent, NPC начинает Транзит.


---


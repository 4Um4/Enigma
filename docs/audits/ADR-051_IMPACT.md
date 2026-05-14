# ADR-051 Impact Audit

## Измененный АДР
ADR-051: LifeEngine De-godification & Intent-Driven Locomotion

## Тип изменения
ONTOLOGY (ADR-O) — Смена парадигмы перемещения от диктаторской мутации к лоббизму намерений.

## Измененные домены (Changed Domains)
- spatial (LifeEngine лишен права прямой мутации позиции и генерации телепортационных SceneChange(field="location"))
- cognition (Внедрение Когнитивного Стража: расписание подавляется perceptual_kernel.threat_gradient > 0.4)
- social (Труба давления DirectiveInterpretationSubscriber замкнута: получает ctx.all_npcs_raw)

## Связанные потребители (Downstream Consumers)
- TickOrchestrator (Фаза 0: распаковывает life_intents, вызывает MovementEngine)
- SceneInit (Распаковывает life_intents при загрузке сцены)
- SceneStateManager (Перестал получать телепортационные SceneChange из LifeEngine)
- MovementEngine (Начинает получать Schedule Intents через правильный конвейер)
- DirectiveInterpretationSubscriber (Получает ctx.all_npcs_raw вместо пустого списка)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.01MB (хранение списка intents в TickContext)
- VRAM Delta: 0
- Tick Latency Delta: +1-2ms (появление транзитов от расписания в MovementEngine), -1.5ms (отмена расписания при стрессе экономит тики)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/test_schedule_locomotion.py — Планируемый тест: Расписание генерирует Intent, NPC начинает Транзит.
- tests/sandbox/oscilloscope_closed_loop.py — Проверка замкнутости: Команда → fear_delta → Резолв позиции Игрока → Движение

## Откат (Rollback)
1. Вернуть `LifeEngine.tick()` к возврату `all_changes` (один список).
2. Раскомментировать `npc["position"] = new_position` и `npc["location"] = new_location` в `update_routine` и `_check_need_driven_movement`.
3. Вернуть вызовы `self._movement_engine.process_intents()` внутрь `_simulate_major`, `_simulate_minor` и `check_random_events`.
4. В `TickOrchestrator._phase_0_simulation` заменить `changes, life_intents = engine.tick(...)` на `changes = engine.tick(...)` и удалить блок `if life_intents:`.
5. В `SceneInit` заменить `_life_changes, _life_intents = _life_engine.tick(...)` на `_life_changes = _life_engine.tick(...)`.
6. Вернуть `DirectiveInterpretationSubscriber().handle(_mock_event, [])`.
```
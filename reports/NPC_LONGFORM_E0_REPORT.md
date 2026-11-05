# NPC_LONGFORM E0 — Diagnostic Harness

**Трек:** NPC_AUTONOMOUS_LONGFORM_INTERACTION_EXPERIMENT (E0)
**Дата:** 2026-11-05
**Предыдущий коммит:** 16ab8bf4 S415.2: A/B v9

## Архитектура

ExperimentRunner (tests/sandbox/experiment_runner.py) — composition over
TavernGameplayHarness. Production lifecycle не подменяется. Observation
taps — read-only (NpcTickPipeline.run staticmethod + MovementEngine.process_intents).

## Production-компоненты (переиспользуются)

- TavernGameplayHarness: new_game, advance_ticks, inspect_npc, dispose
- GameLoop.idle_tick (game_loop.py:1157)
- TaskScheduler.get_recent_dialogues (task_scheduler.py:298)
- _scene_after_tick (harness.py:221)

## Новые файлы

- backend/tests/sandbox/experiment_runner.py (15779 bytes)
- backend/tests/sandbox/test_experiment_runner.py (7689 bytes)
- reports/NPC_LONGFORM_E0_REPORT.md (этот файл)

Изменений production-кода: НЕТ.

## Тесты: 8/8 PASSED (7.28s)

1. Smoke — run completes
2. Pre-flight snapshots (static + runtime)
3. Ticks captured (3 ticks)
4. Movement intents captured (observation tap)
5. Scene changes captured (SceneChange)
6. Errors isolated (one tick error does not destroy run)
7. Report saved (JSON file)
8. get_movement_intents flattened (convenience)

## Пример

    from tests.sandbox.experiment_runner import ExperimentRunner
    runner = ExperimentRunner(seed=42, target_npcs=["maid_lusya", ...])
    runner.setup(n_ticks=10, experiment_id="pilot")
    trace = runner.run(n_ticks=10)
    runner.save_report()

## БЫЛО/СТАЛО

БЫЛО: нет диагностического harness для длительных экспериментов.
СТАЛО: ExperimentRunner — composition, trace collection, JSON report.

## Соответствие ТЗ E0

- Археология: ✅ harness.py, GameLoop, TaskScheduler
- Не дублировать: ✅ composition over TavernGameplayHarness
- API: ✅ setup, run, get_trace, get_dialogues, save_report
- Observation taps read-only: ✅
- 7 сценариев: ✅ 8/8 PASSED
- Не менять production: ✅ 0 changes
- Не создавать truth stores: ✅ trace — passive observer

## Ограничения

1. Pre-flight runtime может быть пустым (LifeEngine cache заполняется
   при первом idle_tick, не после new_game).
2. E0 не тестирует dialogue between NPCs — нужен стимул (E2).
3. LLM offline — dialogues не материализуются (idle работает LLM-free).

## Следующие шаги

NPC_LONGFORM E2 — гарантированный ответ + thread_id (R-3).
USL-2 закрытие — фикс persistence narrative_cache overwrite (отдельная задача).
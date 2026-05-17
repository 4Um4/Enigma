# ADR-047 Impact Audit: Temporal Reconciliation & TICK_CATCHUP Elimination

## Измененный АДР
ADR-047 (Principle of Observed Causality и Temporal Reconciliation)

## Тип изменения
ONTOLOGY (ADR-O) — Убита ретро-симуляция, внедрен аналитический декэй.

## Измененные домены (Changed Domains)
- temporal (отказ от TICK_CATCHUP, аналитический декэй)
- npc (состояние стресса, голода, усталости при загрузке)
- persistence (добавлена метка реального времени last_save_real_time)

## Связанные потребители (Downstream Consumers)
- SceneInit (вызывает reconcile_state при загрузке сцены, если прошло > 60 сек)
- SceneStateManager.commit() (пишет last_save_real_time в scene_state)
- LifeEngine (предоставляет метод reconcile_state)

## Влияние на производительность (Runtime Impact)
- RAM Delta: 0
- VRAM Delta: 0
- Tick Latency Delta: 0 (аналитический декэй применяется 1 раз при загрузке, O(N) по кол-ву NPC)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/system/test_temporal_reconciliation.py (новый) — Верификация экспоненциального затухания стресса и линейного роста потребностей.

## Откат (Rollback)
1. Вернуть константу `MAX_CATCH_UP_TICKS` в `constants.py`.
2. Удалить метод `reconcile_state` из `LifeEngine`.
3. Удалить блок `ADR-047` из `scene_init.py`.
4. Удалить `scene_state["last_save_real_time"] = _time.time()` из `SceneStateManager.commit()`.
5. Вернуть тесты `test_persistence_port.py` к жестко заданным словарям без `last_save_real_time`.
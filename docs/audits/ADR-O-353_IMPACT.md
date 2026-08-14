# ADR-O-353 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- **DOM-01 (Foundation):** Добавлена новая фаза в `TickOrchestrator` (Phase 0.6 Sleep Lifecycle).
- **DOM-05 (Physiology & Combat):** Логика физиологического восстановления (стресс, усталость) и Arousal Gate вынесена из `LifeEngine` в `SleepLifecycleService`.
- **DOM-08 (Observability):** `TimeSkipExecutor` теперь отслеживает события сна для прерывания ускорения времени (BUG-SLEEP-012).

## Downstream Consumers
- **TickOrchestrator (`tick_orchestrator.py`):** Вызывает `SleepLifecycleService` на Фазе 0.6 и применяет `SceneChange` через `_apply_with_shadow_observation`.
- **TimeSkipExecutor (`time_skip_executor.py`):** Читает новые типы событий из `EventDTO.type` для остановки макро-симуляции.
- **EventBus / MemoryManager:** Получают `EventDTO` (тип `sleep_end` и др.) для фиксации в памяти NPC и UI.
- **LifeEngine (`life_engine.py`):** Больше не владеет логикой пробуждения. Оставлена только генерация интента "пойти спать" (Phase 0).

## Runtime Impact
- **RAM:** Незначительное увеличение из-за создания инстанса `SleepLifecycleService` на каждый тик локации (можно оптимизировать в будущем через DI).
- **Latency:** Почти нулевая. Логика перенесена как есть, добавлена только публикация `EventDTO` при пробуждении.
- **Тесты:** `tests/system/test_sleep_routing.py` остаётся зелёным. IPT 39/39 passed.

## Sandbox Tests
- `backend/tests/IPT.py` (Инвариант `INV-COMMIT-CARDINALITY`)
- `backend/tests/system/test_sleep_routing.py`

## Rollback
1. Удалить вызов `self._phase_0_6_sleep_lifecycle(ctx)` из `tick_orchestrator.py` (строка ~736).
2. Удалить методы `_phase_0_6_sleep_lifecycle` и `_apply_with_shadow_observation` из `TickOrchestrator` (если они не используются другими фазами).
3. Восстановить методы `_arousal_gate` и `recover_stress_tick` в `life_engine.py` и их вызовы.
4. Удалить события сна из `SIGNIFICANT_EVENT_TYPES` в `time_skip_executor.py`.
5. Удалить файл `backend/app/services/npc/sleep_lifecycle_service.py`.
6. Удалить `ADR-O-353` из `docs/ADR (Architecture Decision Records).md` и этот файл.
```

Примените создание этого файла.

После этого у нас остаётся только обновить `MUTATIONS.md` и проверить, нужно ли обновлять `DTO Registry`. Я подготовлю `БЫЛО/СТАЛО` для `MUTATIONS.md` сразу после твоего подтверждения.
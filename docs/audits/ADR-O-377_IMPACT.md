# ADR-O-377 Impact Audit — Non-Blocking Intelligence
> Атлас: `docs/ADR (Architecture Decision Records).md`. Возник из инцидента: `wait 12` в кокпите занял 30+ минут (12 тиков × канонические LLM-диалоги × future.result(60) синхронно в стеке idle_tick — traceback при Ctrl+C зафиксировал шлагбаум). Формулировка закона — владелец проекта (вердикт «LLM не должен быть условием продолжения жизни мира»).

## Changed Domains
- TaskScheduler / execution (production-план, не тронут)
- Observability: EXPERIENCE_DELTA_COMMITTED — первый потребитель
- Cockpit-инструментарий (реализовано)

## Current State (cockpit-форма, live)
- wait N: класс-отцепление DialogueUpdateExtractor.extract → тики за секунды, 12/12, ноль TICK_CRASH (живой прогон 2026-09-03);
- new/restart: health-чек llama-server + переподъём (урок 10061: менеджер кеширует состояние мёртвого чужого сервера);
- Быстрые следствия без экстракции: сырой текст в EventMemory — доказано Фазой A («Надеюсь, они не придут» — proposition сохранился).

## Production Plan (open)
1. `_process_tasks_async`: LLM-вызовы → executor-поток (не главный стек тика);
2. Результат → commitment-outbox (прецедент S203.4 drain — рельс уже существует);
3. Stale-валидация при дренаже: актор жив/в сцене/интент активен/тик-возраст ≤ N; протухшее — наблюдаемое отбрасывание (лог+метрика), не молчание;
4. Координация: зона S203.4 — владелец TaskScheduler; изменения по мини-ADR.
Критерий готовности production-формы: `wait 20` в живой uvicorn-сессии ≤ 10с без отцепления экстрактора; 1000-tick LLM-free survival (P12) зелёный.

## Rollback
- Cockpit-форма: finally-восстановление уже гарантирует откат per-wait;
- Production-форма: возврат к sync-пути — исключён табу; отккач = отключение executor-пути флагом (как ARBITER_ENFORCEMENT-прецедент).

## Sandbox Tests
- terminal_cockpit.py: wait 12 (fast) — живой прогон владельца;
- test_phase_a_memory_fixes.py: 40/40 (провод E2.0-b не зависит от LLM — доказательство каузальности не должно требовать интеллекта).
# ADR-INV-DEF Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-INV-DEF` [STANDARD] **IMPACT**
# ADR-INV-DEF Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `backend/tests/` (новый файл `IPT.py` — слой ДО)
- `backend/app/errors.py` (новый файл — `SimulationIntegrityError`)
- `diagnostics/health_checkers/invariant_health.py` (новый файл — слой ПОСЛЕ)
- `diagnostics/pattern_registry.py` (3 новых паттерна)
- `diagnostics/causal_observer.py` (интеграция чекера)
- `diagnostics/report_renderer.py` (секция красных инвариантов)
- `diagnostics/dna_metrics.py` (2 новых поля в DNASnapshot)
- `backend/app/services/phases/post_decision.py` (runtime assert)
- `backend/app/services/tick_orchestrator.py` (runtime assert + эмиттер `[TICK_ORCH]`)
- `backend/app/services/integration/world_snapshot_builder.py` (2 runtime assert)
- `docs/РЕЖИМ РАБОТЫ.md` (§3.7, §3.8, §4)

## Downstream Consumers
- **LLM-архитекторы:** обязаны читать красные инварианты в `LAST_SESSION.md` перед стартом и запускать IPT до закрытия шага.
- **CausalObserver:** парсит новые паттерны `[SIM_INTEGRITY]` и `[TICK_ORCH]`.
- **ReportRenderer:** рендерит секцию `🔴 КРАСНЫЕ ИНВАРИАНТЫ`.
- **DNAComputer:** агрегирует `invariant_violations` и `invariant_warning_count`.

## Runtime Impact
- **IPT:** +5 секунд при разработке (не влияет на production-перформанс).
- **InvariantHealthChecker:** +~5МБ RAM в процессе пост-мортема CausalObserver (скользящее окно 10 тиков).
- **Runtime assertions:** <1мс на тик (проверка `isinstance` и полей DTO).
- **Эмиттер `[TICK_ORCH]`:** 1 строка текста в stdout на тик.

## Sandbox Tests
- `python backend/tests/IPT.py` (baseline: 2 red invariants: INV-TIME-GROW, INV-NPC-MOVE. 3 passed).
- Сквозной тест CausalObserver с синтетическим логом (проверена генерация LAST_SESSION.md).

## Rollback
1. Удалить файлы: `backend/tests/IPT.py`, `backend/app/errors.py`, `diagnostics/health_checkers/invariant_health.py`.
2. Откатить патчи в `diagnostics/*` (удалить инъекции `InvariantHealthChecker` из `CausalObserver`, `ReportRenderer`, `DNAComputer` и `pattern_registry`).
3. Откатить ассерты в `post_decision.py`, `tick_orchestrator.py`, `world_snapshot_builder.py`.
4. Вернуть §3.7 и §4 в `docs/РЕЖИМ РАБОТЫ.md` к исходному виду, удалить §3.8.


Files: N/A

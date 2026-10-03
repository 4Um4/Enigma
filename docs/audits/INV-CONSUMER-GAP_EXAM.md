
# INV-CONSUMER-GAP — Экзамен Stage 1 (ADR-O-414)

> Прецедент стиля: SUPERBOX causal_state_test D-атаки (S243). Каждый кейс =
> манипуляция живого дерева → RED → коммит-возврат → GREEN. Сессия S317.

| # | Манипуляция | RED (факт) | GREEN (факт) |
|---|---|---|---|
| E1 | `pleasere: float = 0.0` в NPCState (npc_state.py:877), деклараций нет | exit=1; census typed 174→175; ровно 2 нарушения: NO_READER + NO_WRITER `npc_state.pleasere` | exit=0; census 174; подавлено реестром 31 |
| E3 | pleasere + writer-факт в StateApplicator (`new_state.pleasere = 0.0` в apply_physical) | exit=1; ровно 1 нарушение: NO_READER. NO_WRITER ОТСУТСТВУЕТ — writer найден сканером → различение Store/Load доказано | откат → exit=0 |
| D2 | debt-реестр: authority CG-D-01 → "fixme" | exit=1; 2 нарушения: DEBT-FORMAT («authority 'fixme' без ссылки») + NO_READER `perceptual_kernel.trust_gradient` — орфан ВЫЖИЛ: невалидная запись не легализует подавление (двойная защита против молчаливых исключений — сильнее ТЗ) | откат → exit=0 |

Финал: IPT ИТОГО 50 passed / 0 failed (0 CRITICAL); линтер GREEN (18/13 RAW, 31 подавлено, parse_errors=0).

## Stage 2 (S317): манифест-гейты — M-семейство

База: manifest=198 (3 CAUSAL / 4 PROJECTION / 27 INPUT / 164 DEBT), прогон №10ter exit=0.

| # | Манипуляция | RED (факт) | GREEN (факт) |
|---|---|---|---|
| E2 | pleasere + CAUSAL-декларация без proof | M-PROOF (+NO_READER/NO_WRITER Слоя 1) | откат → exit 0 |
| E6 | манифест-призрак pleasere_ghost | ровно M-STALE | откат → exit 0 |
| E7 | PROJECTION relationship_cache без authority | ровно M-AUTH | откат → exit 0 |
| E9 | rename cache_timestamp→cache_ts (адаптация на typed) | M-STALE + M-UNDECLARED + NO_READER + NO_WRITER (двойной CRITICAL) | откат → exit 0 |
| D1 | setattr(new_state, "pleasere", ...) литералом | ровно NO_READER — NO_WRITER гаснет (литеральный детектор ловит bypass) | откат → exit 0 |


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

## Stage 2b (S317; внесено S321 — хвост реестра)

Census 198→291 (+93: relationship_contracts [need_slot/need_level/preference_model/hard_constraint/exclusivity_requirement], desired_change, epistemology [claim_event/epistemic_record/epistemic_context/proposition], memory_crystal, experience_trace); schema-self-exclusion (схемы domain/ — не свои consumers). Свежая верификация (S321): typed=267 container=24 manifest=291 parse_errors=0; NO_READER=44 NO_WRITER=33; подавлено декларациями 77; exit=0. Bidirectional census↔manifest GREEN. Орган-отчёт: reports/ORGAN_REPORT_S2B.txt — 10/10 органов, 3 CAUSAL. Урожай экспансии ~45 orphan; именованные: need_slot NO_WRITER×9 (substrate dormant, ADR-O-370); experience_trace NO_WRITER×13 (NL-D4 независимо); claim_event.listener_id NO_READER; experience_trace.timestamp самопойман (INPUT не легализует сиротство).

## Stage 3 (S321) — PerturbationHarness (proof-слой)

Контракт Мастера: INVALID / INJECTION_FAILED / GAP / WIRED; INJECTION_FAILED ≠ GAP; scores_trace — параллельный канал; CAUSAL = семантика A (проводимость до вычисления; argmax_flip — annotation); GAP не чинится машиной; state-level only; WIRED без универсального окна. Прибор: tests/gameplay/perturbation_harness.py — адаптер над TavernGameplayHarness (§9.2; второго engine нет); production write-paths (PHYSIOLOGY=apply_deltas_only+Cause; RELATIONSHIP_V2=update_relationships→WriteGate→V2); uuid5; noise-off; тик-чётность.

| # | Проба | Результат | Доказано |
|---|---|---|---|
| S | A/A smoke 2×4 тика | GREEN (rows 24/24 + scores ≡) | прибор детерминирован; не слеп |
| B | fatigue +90 (bring-up) | GAP+utility (57 осей); дельта выживает до N | прибор валидирован end-to-end; BodyEngine добавляет, не перезаписывает |
| Q2 | trust +60 V2 (санкция) | GAP+utility (52 оси, 1-й пост-инъекц. тик); 60.0 персистентен; baseline-Vacuum (read_trust=None) | S1 опровергнут для находки S320: store→utility проводит; ноль = S2/S3; домены body/relationship сопоставлены на уровне state→utility |
| RF1 | re-proof fatigue (capped≈×0.3±0.30) | GREEN | CAUSAL-проводимость в полном тике; двухтрактовая анатомия: cap (O-383) + sleep_pressure→CouplingProfile (O-375) |
| RF2 | re-proof energy (razor+паттерн) | GREEN (11 осей; 9.9<10.0) | availability-тракт; асимметрия 57/11 → CG-D-17 |
| BL | beliefs — археология | S243-миссматч (proof доказывал threat_gradient) | вердикт: миграция proof→epistemic_decision_divergence_test.py (S194; event-level вход — вопрос канона). Исполнение — хвост |

Находки (без фиксов): energy razor-margin → CG-D-15; hub ФАЗА-1 dead-continue → CG-D-16; асимметрия 57/11 → CG-D-17. Не исполнено → roadmap §7.8: E4, E8+M-PROOF-LIVE, манифест-хирургия, досье M2/D, F5-вкладка, behavior_mask, (none)-memo. Формулировки E-атак реконструированы (исходное ТЗ на диске не существует — три независимых поиска).

## Stage 4 (S334): const-резолв + relationship_state-домен (мини-ADR ADR-O-414-контура)

Вердикт Мастера C/GO: сканер перестаёт быть слепым к каноническому AST-паттерну Устава §12.1 (ключи-константы), не превращаясь в evaluator. Границы: ТОЛЬКО top-level статические строковые константы текущего файла (`NAME = "str"` / `NAME: Final[str] = "str"`); цепочки (`A = B`), вызовы, env, import, межфайловый inference — вне резолва. Плюс `CONTAINER_DOMAINS += {"relationship_state"}` (RE-домен, писатель-маршрут O-370/O-419). Порядок: резолв → EXAM → фактический урожай → триаж → декларации → GREEN (жизненный цикл данных ≠ работа анализатора; directed writers=0 → DEBT без искусственных writers).

| # | Манипуляция/проба | RED/факт | GREEN/факт |
|---|---|---|---|
| E-C1 | живой урожай (сканер+домен, деклараций нет) | exit=1; census container 24→26; ровно 4 нарушения: NO_WRITER×2 (directed, dynamics) + M-UNDECLARED×2 | декларации DEBT (dynamics: вербатим NOTE S329, authority ADR-O-419; directed: authority ADR-O-370) → exit=0; manifest 297→299; подавлено 73→75 |
| E-C2 | NEG-граница: цепочка констант (`CHAIN = KEY`) | `_key` → None (не резолвится) — слепота к не-литеральным значениям сохранена | — |
| E-C3 | NEG-граница: вызов (`FUNC = get_key()`) | `_key` → None — evaluator-семантика не введена | — |

Финал: IPT ИТОГО 51 passed / 0 failed (0 CRITICAL); линтер GREEN (container=26, manifest=299, parse_errors=0). M-STALE-хвост S329 (книга кванта вне census) закрыт: `relationship_state.dynamics` легально декларирован по NOTE-вербатиму ADR-O-419.

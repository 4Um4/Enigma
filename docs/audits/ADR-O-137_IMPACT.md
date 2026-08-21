# ADR-O-137 Impact Audit: Viability Pre-Generation Gate (ДОЛГ 4.3)

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs\Tasks\ADR (Architecture Decision Records).md`

## Changed Domains
- **DOM-02:** Will, Pressure & Decision — viability gate в LifeEngine
- **DOM-04:** Spatial & Locomotion — IntentDomain enum в domain/movement.py
- **DOM-08:** Observability — 11 новых sandbox-тестов

## Downstream Consumers
- **LifeEngine._simulate_major()** — генерация кандидатов теперь gated
- **LifeEngine._simulate_minor()** — аналогично
- **TickOrchestrator._apply_drf_scoring_overlay()** — читает `domain` из MovementIntent
- **DRF CausalClaim** — `pressure_type` теперь из `winner.domain.value`

## Runtime Impact
- **RAM:** 0 (enum + set — пренебрежимо)
- **Tick Latency:** +0.05ms/NPC (_compute_viability_mask + conditional skips)
- **Behavioral:** NPC не генерирует ROUTINE intents при threat > 0.3

## Sandbox Tests
- `test_calm_npc_all_domains_viable` — все 4 домена при peace
- `test_threatened_npc_routine_pruned` — threat > 0.3 → ROUTINE исключён
- `test_paralyzed_npc_only_survival` — init_sup > 0.7 → только SURVIVAL
- `test_no_kernel_all_domains_viable` — VACUUM = NEUTRAL (§ENIGMA-003)
- `test_threat_exact_threshold` — threat=0.3 не исключает (порог строгий >)
- `test_calm_npc_generates_routine_intent` — gate не блокирует при peace
- `test_threatened_npc_no_routine_intent` — ROUTINE не рождается при threat
- `test_paralyzed_npc_no_intents_at_all` — полная блокировка генерации
- `test_schedule_intent_is_routine` — schedule → ROUTINE domain
- `test_default_domain_is_routine` — MacroMovementGoal дефолт = ROUTINE
- `test_flee_is_survival` — FLEE → SURVIVAL domain

## Rollback
1. Удалить поле `domain` из `MacroMovementGoal` в `domain/movement.py`
2. Удалить `IntentDomain` enum из `domain/movement.py`
3. Удалить `_compute_viability_mask()` из `life_engine.py`
4. Вернуть безусловные вызовы `update_routine()`, `_check_need_driven_movement()`, `check_random_events()` в `_simulate_major/minor`
5. Вернуть хардкод `"ROUTINE"` в DRF claim
6. Удалить `test_viability_compression.py`

## Key Risks
1. **Переусиление SURVIVAL** — 4 механизма влияния (threat guard, viability mask, DRF scoring, initiative_suppression). Мониторить: NPC не должен быть парализован при threat=0.35
2. **Бинарность viability** — текущая маска: 0 или 1. Нет градации (threat=0.31 = ROUTINE удалён, threat=0.29 = ROUTINE жив). Целевая архитектура: viability tensor с непрерывным сжатием
3. **Domain drift** — `domain` поле может не соответствовать реальной семантике при росте системы. Нужен аудит при добавлении новых генераторов интентов
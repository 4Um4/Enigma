# ADR-O-378 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- WORLD→DECISION: pure продюсер производных фактов W2 (read-only мост; mutation-free by contract)
- SIMULATION: врезка оркестратора (до build_tick_state) + preloaded-поле TickState

## Downstream Consumers
- OpportunityEngine: weapon_access из DATA-стаба становится вычислимым фактом (DEBT-OPP-PRODUCER закрыт; формула/веса не менялись)
- NpcTickPipeline: сборка OpportunityContext (минимальный дифф, getattr-гвард)
- G1-тень: общий вход (снапшот), код не пересекается
- G3 (будущее): ревалидация precondition-кортежей — не тронут

## Runtime Impact
- OFF (default): ноль (no-op до вычислений); ON: 7 NPC × (оружия сцены) предикатных вызовов/тик — мкс; +1 frozen map/тик
- Поведение: production honest-zero (weapon-архетипов в кампании нет — editor-JSON 18 типов)

## Sandbox Tests
- tests/test_affordance_facts.py (23): truth table D6, гварды D3/D5, чистота/детерминизм, engine-флип, негативные контроли
- scripts/w3_g2_simple.py: GORAN β G2, 7×200 изолированных профилей — GREEN
- W-контур 124+1; IPT 45/45

## Rollback
- Удалить: продюсер-вызов в tick_orchestrator + поле tick.py + pass-through pipeline_runner + факт-строку npc_tick_pipeline + файлы affordance_facts/test/harness. W1/W2/G1 не задеты; ноль миграций (G2 ничего не пишет).

## Известные ограничения / вердикты Мастера
- steal-флип условен (will-гейт broken/deceptive; engine-звено доказано юнит-уровнем)
- B1 trav=120 vs 172 — одиночный ambient-выброс (DEBT-QUIESCE; ось не гейт)
- world.yaml не расширяется (G2 — сервисный мост, не топология мира)
- Хроника 4 отказов + G1-методологическая оговорка — в атласе
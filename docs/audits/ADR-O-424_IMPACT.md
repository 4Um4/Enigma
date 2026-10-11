# ADR-O-424 Impact Audit

ADR-O-424 [FIX] **IMPACT**

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Исполнение player-вмешательств: диспетчеризация INPUT_MERGE (M1/S122/dm_ctx/FAST_PATH)
- Rules/экономика хода: turn_pipeline._finalize (синтез rules-события, применение money_delta)
- L1-хроника: player-driven attack/damage-дрифт (npc_orchestration)

## Downstream Consumers
- CombatSubscriber → ImpactEngine (PLAYER_ATTACKED-контур): не-RESOLVED атаки не поступают
- ActionConsequenceCompiler (M1: HELP/BLACKMAIL/ACCUSE): аналогично
- RulesSubscriber (чексы/экономика): аналогично
- L1Chronicle → PatternDetector → BeliefCrystallization: attack/damage-дрифт gated
- DM-слой: без изменений (readiness в DM-контекст не добавлен — дифф B UX-фронта)
- WV-контур (action_rejected/physics_validation): не тронут — иная семантика (подавление публикации)

## Runtime Impact
- RESOLVED-пути: +1-2 getattr на player-вмешательство (нулевая семантика)
- Не-RESOLVED: пропуск диспетчеризации + гейты Rules/L1
- Легаси (intent_readiness=None): fail-open — байт-нейтрально
- RAM/latency: несущественно (атрибутные проверки существующего объекта)

## Sandbox Tests
- tests/sandbox/micro/test_ue_d4_kernel_red.py — 8/8 (4 репродукции закрыты границей; контроли RESOLVED зелёные; xfail снят по XPASS×4)
- UE-сьюта: 56 passed + 7 xfailed; боевые: 24 passed + 1 skipped; IPT: 52/0

## Rollback
- git revert 0508008e; красные тесты возвращаются в сигнальное xfail-RED состояние

## Остатки
- Сиблинг directive-ветки L1 (MOVE/THREATEN/PERSUADE/GIVE → дрифт +0.3) — решение Мастера
- Ручная интеграционная приёмка (маркеры UE-GATE-KERNEL/UE-GATE-L1) — до записи реестра

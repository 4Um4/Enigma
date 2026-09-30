# ADR-O-394 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Причинный слой: DesiredChange (домен) + ThreatDesiredChangeProducer + проводка
- Чтение (не запись): threat_gradient (PerceptualKernel), fear-оси SSOT, disposition S211, drives L3

## Downstream Consumers
- R6 (ADR-O-395): hunger-продюсер по образцу threat (каскад причин ниже по потоку)
- R7 (ADR-O-397): grievance — горячая фаза осталась территорией R5 (CS15)
- R8 (ADR-O-400): каскад threat > hunger > grievance > affection
- DecisionHub: 8-й модификатор causal_modifiers (Modifier Contract)

## Runtime Impact
- O(пары отношений) на NPC с threat ≥ 0.35; микросекунды; RAM ноль

## Sandbox Tests
- tests/gameplay/test_r5_causal_slice_threat.py: 8 (пины/контрфакты/A-A);
  исходно: ядро «одна цель → разные способы», регрессия 82/83 (gc09b pre-existing), IPT-дельта 0

## Rollback
- Удалить causal_slice_threat.py + тест; из desired_change.py — stop_hostile + REASON_THREAT;
  из npc_tick_pipeline.py — блок R5. Ядро не задето.

## Пост-фактум (R6-сессия, S263)
- Проводка R5 была МЕРТВА в живом конвейере с мержа S261 (_allies_cache NameError →
  no-op каждый тик) — юнит-сьюты этого не видят (продюсер вызывается напрямую).
  Воскрешена (allies=0, DEBT-R5-ALLIES). Урок D-R6-LIVE-PROBE родился здесь.
- Горячий контур жив: SPREAD_RUMOR/исполнение grievance-срезом подтверждает, что
  threat-каскад не блокирует нижележащие причины.

## Уроки
- Продюсерные тесты зелёные ≠ проводка живая: только production probe говорит правду.
- Контракт threat-продюсера (state.npc_id) не масштабируется на TickState-проводку —
  исправлен в R7 контрактом who-явным-аргументом (D-R7-WHO-CONTRACT).

# ADR-O-386 Impact Audit
> Детальный аудит одного ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
space (NodeRef.owner, компиляция, zone_owner/territory_owners), events (EventType.TRESPASSED, детектор Фазы 2), decision (territory_pass — факт предвычислен в пайплайне, гейт COMBAT_CAPABLE — L-A1: территория ИЛИ роль), social (case-фикс ключей + ремап THREATEN→INTIMIDATE), world-контент (tavern.json).

## Downstream Consumers
SpatialEventDetector (zone_owner-lookup, опциональный параметр), TickOrchestrator._phase_2_event_bus_primary, npc_tick_pipeline (факт из read-only spatial_service TickState), DecisionHub (compute/_get_possible_intents/_is_intent_available), SocialEngine.compute_social_modifiers → apply_modifiers, graph_compiler, SUPERBOX protect_vertical_test.

## Runtime Impact
ON: territory_owners() O(N) на NPC/тик (19 узлов × 7 NPC — тривиально); TRESPASSED — редкие события. OFF: no-op (детектор не ищет, пайплайн не обращается к сервису, гейт не получает pass). Персистенции новых полей состояния нет — owner живёт в контенте и графе.

## Sandbox Tests
SUPERBOX protect_vertical_test 5/5; test_territory_owner 11/11; test_social_modifiers_case_fix 6/6 (инвариант Мастера: применение + баланс); IPT 45/45 (после шага 4).

## Rollback
TERRITORY_ENABLED default OFF = no-op; owner-поля контента игнорируются при OFF; case-фикс автономен (прецедент R1), реверсивен; все правки кода аддитивны (Optional/дефолты).

## Коррекция против ADR-текста (по полной карте)
Членство узлов: ADR-текст (частичное прочтение) называл bar_area/bar_west/bar_pass_north; полная карта: bar_area — клиентская сторона (NodeRole.BAR «для гостей»); приватная зона — behind_bar («За стойкой», inn_desk, workplace:tavern_keeper) + bar_side + bar_pass_north. bar_west — публичный транзит. Архитектура не менялась — только контент.

## Открытые пункты (честно)
1. TRESPASSED → давление на владельца (восприятие → скоринг) — калибровка.
2. Эмерджентный выбор block_path — не гарантирован v1; право доказано.
3. Evict NPC→игрок (v1.5) — продюсер через существующий директивный канал на аватар.
4. Автономные нарушители — причины родят WORK/SOCIAL-срезы.

# ADR-O-362 Impact Audit: NPC Action Materialization — Steal
> Атлас: L19.1. Сессия: S209 (Vertical Slice, звено 1). Номер сверить по атласу (anti-race).

## Changed Domains
- **DOM-ECONOMY:** OpportunityEngine R6.3 получил первого реального потребителя (до S209 — unlockable-строки без enum-домов).
- **DOM-EVENTS:** `_INTENT_EVENT_MAP += steal→THEFT`; маршрутизатор Фазы 6 windowed=(attack|steal); Фаза 7 — object-action цель.
- **DOM-DECISION:** `Intent.STEAL` (PROACTIVE, WORLD_TICK only); unlock-ветка `_is_intent_available`; `_steal_affinity` (archetype×desire).

## Downstream
- ObservationSubscriber (готов, ADR-O-360): THEFT NPC-источника → belief свидетелей.
- Reaction/Social subscribers (THEFT, уже подписаны): получат NPC-кражи; whisper-radius — честная мембрана.
- `INV-INTENT-EVENT-COMPLETENESS`: покрывает новый маппинг.

## Runtime Impact
~30 строк; +1 enum-член; latency ≈ 0 (один affinity-расчёт на тик при unlock).

## Sandbox Tests
`SUPERBOX-AGENCY-STEAL` 6/6: opportunity-гейт (A1/A2), контроль натуры (A3), windowed-маршрутизация (A4), THEFT-материализация (A5), эмерджентное Goran-замыкание + no-telepathy (A6). IPT 44/44.

## Rollback
Удалить: enum-член, affinity+unlock, маппинг, профиль, константу, параметризацию Фаз 6/7. Атомарно; труба не задета.

## История инцидентов внедрения (для протокола)
Двойное применение патча; `_intent_val` из черновика (Pylance поймал); мёртвый placeholder-блок скоринга; 3 ложных предположения об ExposureLevel (оказался dataclass с from_semantic); маршрутизатор Фазы 6 съедал steal в диалоговый слой (пойман сквозным тестом, не IPT/smoke). Урок: сквозной SUPERBOX — единственная защита от межкомпонентных разрывов.MUTATIONS 
# ADR-404 Impact Audit — Event Identity
## Changed Domains
- events (identity seed), scene_state (новый корень event_ordinals),
  event_bus (финализация на входе), dialogue materialization (claim_id)
## Downstream Consumers (все потребители event.id — проверены, получают
  финальный id начиная с момента publish)
- claim_event_subscriber (ClaimEvent.event_id/claim_id — теперь уникальны)
- memory/intelligence_queue (Q5-идемпотентность — коллизии устранены)
- events/reaction_subscriber (trace_id/causal_parent, AG1-INV-TRACE-ONCE)
- memory/conclusion_engine + conclusion_gate + delta_gate (идемпотентность)
- memory/memory_manager (_mem_id = event.id:npc:digest — дайджест-защита
  была и остаётся)
- npc_dialogue_subscriber (D8P enqueue-дедуп — коллизии устранены)
- integration/world_snapshot_builder (PerceivedNarrativeDTO.event_id —
  в Фазе 2 будет заменён синтетический id на сквозной)
## Runtime Impact
- RAM: +dict счётчиков (O(число type:source пар), единицы записей)
- Latency: +1 dict-lookup + md5 на событие (наносекунды); publish-путь
  без изменений по сложности
## Sandbox Tests
- tests/micro/test_event_identity.py (8 кейсов A–H)
- tests/IPT.py: INV-EVENT-IDENTITY (постоянный, CRITICAL)
- DriftLab mass_traversal 200 тиков: 0 крашей, 0 C/D/E
## Rollback
1. game_loop: удалить блок wiring провайдера (EventBus возвращается в
   provisional-режим = поведение идентично до-фиксовому на новых путях)
2. dialogue_materializer: вернуть claim_id-строку
3. seed в EventDTO.create — одна строка
Полный откат — 3 патча, ни одного миграционного изменения данных.
## Known Gaps (честно)
- Живой replay-MATCH не верифицирован (replay-инфраструктура не пишет —
  отдельное ТЗ); INV-EVENT-IDENTITY покрывает replay-детерминизм identity
  на уровне контракта.
- Provisional-режим вне lock-окон задокументирован; таких путей в
  production не обнаружено (карта окон в ADR).
# ADR-O-438 Impact Audit — A4-K.1: dual-init self._relationships устранён

> Единственный атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Суть изменения

В MemoryManager.__init__ устранён dual-init атрибута self._relationships:
- Было: RelationshipStore(data_dir) (legacy) -> switch_to_v2_relationships() переписывал на V2RelationshipBackend
- Стало: V2RelationshipBackend сразу в __init__ через lazy lambda

## Changed Domains

- services/memory/memory_manager.py (RE-01 track)

## Downstream Consumers

- state.relationship_store (TickState) -> npc_tick_pipeline.py:366, 631 (V2 backend, duck-typed)
- state_applicator.py:62 (type hint import — A4-K.2 candidate)
- RelationshipWriteGate(relationship_store) в state_applicator.py:96
- RelationshipStateStore.migrate_legacy_relationships (standalone JSON reader)

## Runtime Impact

- RAM: нет изменений
- Latency: нет изменений
- VRAM: нет изменений

## Что НЕ удаляется

- Класс RelationshipStore — сохранён для 18+ тест-фикстур (mock backend)
- Импорт RelationshipStore в state_applicator.py:62 — отдельный шаг A4-K.2
- Метод switch_to_v2_relationships() — сохранён для обратной совместимости

## Sandbox Tests

- pytest 257 passed (2026-11-08)
- IPT baseline: 52 passed / 2 failed (чужие CRITICAL, Branch B Avatar WIP)

## Rollback

Revert to dual-init via git checkout memory_manager.py:
- :44 self._relationships = RelationshipStore(data_dir=data_dir)
- :74 def switch_to_v2_relationships(self, npc_provider=None)

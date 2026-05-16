# ADR-048 Impact Audit: Authoritative Spatial Spine

## Измененный АДР
ADR-048 (Single Source Spatial Authority)

## Тип изменения
ONTOLOGY (ADR-O) — Смена парадигмы: scene_state больше не authority layer для пространственных решений.

## Измененные домены (Changed Domains)
- spatial (введение QueryService как единственного авторитета)
- decision (npc_tick_pipeline переведён на QueryService)
- perception (пока читает из scene_state — требует миграции на Этапе 2)

## Связанные потребители (Downstream Consumers)
- npc_tick_pipeline (использует spatial_query.player_distances)
- DecisionHub (пока не изменён, не читает пространственные данные напрямую)
- TickOrchestrator (должен инстанцировать SpatialQueryService и пробрасывать в пайплайн)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.01MB (кэш дистанций в SpatialQueryService)
- VRAM Delta: 0
- Tick Latency Delta: +0.1ms (вычисление дистанций через фасад вместо чтения из кэша scene_state)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/system/test_spatial_authority.py (новый — верификация Query-driven доступа)

## Откат (Rollback)
1. Удалить `backend/app/services/spatial/spatial_query_service.py`.
2. В `npc_tick_pipeline.py` вернуть `inp.scene_state.get("player_distances", {})`.
3. Удалить `spatial_query` из входных DTO.
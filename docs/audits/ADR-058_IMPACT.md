# ADR-058 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-058` [STANDARD] **IMPACT**
# ADR-058 Impact Audit: Frontend Dual-Time Ontology (Sprint 30)

## Измененный АДР
Sprint 30 — Переход фронтенда на Dual-Time Ontology и Каузальную Презентацию.

## Тип изменения
ARCHITECTURE (Frontend) — Смена парадигмы: фронтенд из предсказателя превратился в интерполятор.

## Измененные домены (Changed Domains)
- presentation (появился слой непрерывной интерполяции TraversalState)
- cognition (визуализация Cognitive Freeze / паралича воли)
- movement (уничтожен клиентский pathfinding, единственный источник правды — бэкенд)

## Связанные потребители (Downstream Consumers)
- SceneRenderer (теперь принимает dt и kinematics для непрерывного lerp)
- GameScreen (удален find_path, движение к NPC — через Intent)
- Backend API (требует проброса initiative_suppression в NPCPositionDTO)

## Влияние на производительность (Runtime Impact)
- RAM: +0.01MB (поля TraversalState в PerceivedEntity)
- VRAM: 0
- FPS: 0 (интерполяция линейная, O(1) на NPC)

## Песочные тесты (Sandbox Tests)
- Визуальная проверка: NPC плавно идут по waypoints, дрожат при подавлении воли.

## Откат (Rollback)
1. Вернуть импорт `find_path` в `game_screen.py`.
2. Удалить поля `traversal_*` и `initiative_suppression` из `PerceivedEntity`.
3. Откатить `_draw_npcs` к наивному `delay_factor` без `dt`.

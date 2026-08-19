# ADR-130 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-130` [STANDARD] **IMPACT**
# ADR-130 Impact Audit: Movement Lock & Target Resolution

## Changed Domains
- Movement (update_routine, MovementIntent arbitration)
- Decision (DecisionHub._context_relevance, EventContext.target_id)

## Downstream Consumers
- LifeEngine.update_routine() — теперь traversal-aware (читает scene_state)
- DecisionHub._context_relevance() — теперь проверяет payload target_id fallback
- MovementEngine — не изменён, но получает меньше конфликтующих интентов
- TickOrchestrator — не изменён, но behaviour более стабилен

## Runtime Impact
- RAM: +0 (scene_state уже существует, только передаётся ниже)
- Tick Latency: +0.01ms (проверка active_traversals dict lookup)
- VRAM: 0

## Sandbox Tests
- Smoke-test: update_routine без scene_state → backward compat (changes=2, current=sleeping)
- Smoke-test: update_routine с пустыми traversals → backward compat (changes=2, current=sleeping)
- Smoke-test: update_routine с MOVING traversal → LOCK ACTIVE (changes=0, current=working)
- Smoke-test: update_routine с ARRIVED traversal → lock released (changes=2, current=sleeping)
- Smoke-test: target_id None + payload empty → all targeted (general interaction)
- Smoke-test: target_id None + payload target_id → only specific NPC targeted
- Smoke-test: target_id set directly → works as before

## Rollback
1. Удалить scene_state параметр из update_routine(), _simulate_major(), _simulate_minor()
2. Удалить Movement Lock guard (строки ADR-130 в update_routine)
3. Убрать _effective_tid fallback в _context_relevance()
4. Вернуть `is_targeted = (event.target_id is None or ...)`

## Files Changed
| File | Change | Lines |
|------|--------|-------|
| life_engine.py | _simulate_major: +scene_state param | ~975 |
| life_engine.py | _simulate_major: pass scene_state to update_routine | ~1006 |
| life_engine.py | _simulate_minor: +scene_state param | ~1150 |
| life_engine.py | _simulate_minor: pass scene_state to update_routine | ~1165 |
| life_engine.py | engine.tick: pass scene_state to _simulate_major | ~471 |
| life_engine.py | engine.tick: pass scene_state to _simulate_minor | ~482 |
| life_engine.py | update_routine: +scene_state param | ~1180 |
| life_engine.py | update_routine: Movement Lock guard | ~1227-1233 |
| decision_hub.py | _context_relevance: _effective_tid fallback | ~1039-1049 |

## Root Causes Closed
| Bug | Root Cause | Fix |
|-----|-----------|-----|
| G1: Schedule overrides reactive movement | update_routine() не видел active_traversals → мутировал routine["current"] и создавал schedule intent поверх активного транзита | ADR-130 Movement Lock: scene_state traversal-aware guard |
| G2: Uninvited NPC approach | _context_relevance() читал event.target_id (None) без fallback на payload.target_id → все NPC считались целевыми | ADR-130 target_id fallback: payload["target_id"] as secondary source |

# ADR-056 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-056` [STANDARD] **IMPACT**
# ADR-056 Impact Audit: Attention Capture & Safe Spatial Fallback

## Changed Domains
- PERCEPTION (PerceptualKernel.recent_directive)
- IDENTITY (IdentityPayload.recent_directive_data)
- MOVEMENT (MovementEngine fallback logic)
- LIFE_ENGINE (Routine evaluation guard)

## Downstream Consumers
- `LifeEngine`: Читает `recent_directive` вместо `initiative_suppression > 0.7` для блокировки расписания. Сжигает директиву после использования.
- `DecisionHub`: Должен учитывать `recent_directive.salience` для повышения веса `APPROACH` или `FLEE` (наследующая задача).
- `StateApplicator`: Мутирует `perceptual_kernel.recent_directive`.
- `MovementEngine`: Читает `npc_positions` для LOD0 Collision Avoidance. Отклоняет перемещения в несуществующие узлы (Safe Spatial Fallback).

## Runtime Impact
- RAM: +0.1KB на NPC (словарь `recent_directive`).
- CPU: Снижение нагрузки (отмена макро-перемещений в несуществующие узлы предотвращает расчёт пути).

## Sandbox Tests
- `backend/tests/sandbox/test_schedule_locomotion.py` (Требует обновления: `initiative_suppression: 0.9` заменить на `recent_directive: {"source": "player", "salience": 0.9, "interrupts_routine": True}`)

## Rollback
1. Вернуть `target_ref = svc.get_node(...entrance...)` в `MovementEngine`.
2. Вернуть проверку `initiative_suppression > 0.7` в `LifeEngine`.
3. Удалить поля `recent_directive` из моделей.

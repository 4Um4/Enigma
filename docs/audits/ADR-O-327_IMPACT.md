# ADR-O-327 Impact Audit: BodyTopology Vertical Slice (Lower Limb)
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Physiology (Wounds reading)
- Perception (Motor Projection)

## Downstream Consumers
- `PhenomenologyProjectionService` (маппит в cue_key)
- Frontend (рендерит анимацию хромоты в будущем)

## Runtime Impact
- RAM: +1 поле на DTO (minimal).
- Latency: Итерация по списку `wounds` (< 1ms на NPC).

## Sandbox Tests
- IPT (INV-NPC-MOVE, INV-TIME-GROW)

## Rollback
- Удалить вычисление `gait_asymmetry` и `cue_key="LIMPING"`.
- Убрать поле `gait_asymmetry` из `EmbodiedTraceDTO`.
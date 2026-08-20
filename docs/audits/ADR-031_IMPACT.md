# ADR-031 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-031` [STANDARD] **IMPACT**
### ADR-031: Player Movement Intent (WASD De-localization)

1. **Тип АДР:** STANDARD
2. **Затронутые домены:** `intent`, `player_position`
3. **Связанные потребители (Downstream):** 
   - Бэкенд: `phase_1_input.py` (Semantic Bridge), `EventBus`
   - Фронтенд: `scene_renderer.py` (ожидает подтвержденную позицию через `WorldSnapshotDTO`)
4. **Бюджет ресурсов:** RAM 0 / VRAM 0. Tick Latency: +20-50ms (сетевой round-trip вместо локального вычисления).
5. **Откат (Rollback):** Вернуть локальные вызовы `try_move`/`move_towards` (восстановить `movement_system.py` из Git). Временно отключить оптимистичный рендеринг.
6. **Регрессия:** `backend/tests/sandbox/system/test_player_movement_intent.py`


Files: N/A

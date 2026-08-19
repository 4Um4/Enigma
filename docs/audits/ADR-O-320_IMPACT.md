# ADR-O-320 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-320` [STANDARD] **IMPACT**
# ADR-O-320 Impact Audit: RecognitionMemory (Persistent Recognition)
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
## Changed Domains
- Perception (Memory Layer)
- SceneState (Persistence)
- Frontend (UI Rendering)
## Downstream Consumers
- `WorldSnapshotBuilder` (читает `player_recognition` и формирует `display_name`)
- `game_screen.py` (рендерит `display_name` вместо хардкода)
## Runtime Impact
- RAM: Обновление словаря `scene_state["player_recognition"]` каждый тик.
- Persistence: Словарь сохраняется в SQLite вместе с `scene_state`.
## Sandbox Tests
- IPT (INV-NPC-NAME)
## Rollback
- Удалить блок обновления `player_recognition` из `phases/integration.py`.
- Удалить поля `display_name`, `recognition_confidence` из `NPCPositionDTO`.
- Вернуть хардкод `npc_id.split("_")` во фронтенд.

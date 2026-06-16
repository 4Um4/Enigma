### 📜 ADR-148: EventDTO Default Radius Sentinel

`ADR-148` [STD] **EventDTO Default Radius Sentinel** — Дефолтный `radius=999.0` в `EventDTO.create` является латентным риском для аудио-событий (пробивает мембраны `_can_hear`), но не влияет на визуальные (`_can_see` игнорирует поле). Замена на `PERCEPTION_RADIUS["major"]` разрешена только при появлении runtime-бага со слухом.
  Files: `domain/events.py`, `services/npc/perception_filter.py`, `services/spatial/player_target_pipeline.py`

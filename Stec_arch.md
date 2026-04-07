# Stec_arch — архитектурные стеки и ключевые файлы

> Цель: зафиксировать **главные существующие файлы** по каждому слою системы в текущем состоянии репозитория.
> Если слой реализован частично — отмечено как `PARTIAL`.

---

## L0 — FOUNDATION

### R1 Memory Core (`PARTIAL`)
- `backend/app/services/memory/memory_manager.py`
- `backend/app/services/memory/layered_memory.py`
- `backend/app/services/memory/working_memory.py`
- `backend/app/services/memory/resonance_engine.py`
- `backend/app/services/memory/importance_engine.py`
- `backend/app/services/memory/relationship_store.py`
- `backend/app/services/memory/contradiction_resolver.py`
- `backend/app/services/memory/__init__.py`
- `backend/app/services/events/event_types.py`
- `backend/app/services/events/event_bus.py`

### R2 Decision Core (`PARTIAL`)
- `backend/app/services/npc/decision_hub.py`
- `backend/app/services/npc/opportunity_engine.py`
- `backend/app/services/npc/reaction_priority.py`
- `backend/app/services/npc/threat_assessor.py`
- `backend/app/services/npc/npc_cognition.py`
- `backend/app/services/npc/psyche_engine.py`

### R3 Verbalization Layer (`PARTIAL`)
- `backend/app/services/npc/verbalization_context.py`
- `backend/app/services/prompt_loader.py`
- `backend/app/services/llm_service.py`
- `backend/app/services/llm/router.py`
- `backend/app/services/llm/provider_manager.py`

---

## L0.5 — ПЕРСИСТЕНТНОСТЬ

### R1.8 Strict Persistence Engine (`PARTIAL`)
- `backend/app/services/scene_state_manager.py`
- `backend/app/services/campaign_state_service.py`
- `backend/app/services/player_session_service.py`
- `backend/app/services/scene_change.py`
- `backend/data/campaigns/` *(runtime storage)*
- `backend/data/logs/` *(change logs)*

### Anti Save-Scumming / rewards (`PARTIAL`)
- `backend/app/services/action/python_engines.py`
- `backend/app/services/action/processor.py`
- `backend/app/services/game/combat_math.py`

---

## L1 — ПРОСТРАНСТВО

### R4 Spatial System (`IMPLEMENTED BASELINE`)
- `backend/app/services/npc/location_graph.py`
- `backend/app/services/npc/spatial_runtime.py`
- `backend/app/services/npc/perception_filter.py`
- `backend/app/services/action/player_target_extractor.py`
- `backend/app/services/scene_state_manager.py`
- `backend/data/locations/location_templates.json`

---

## L2 — МЕХАНИКА ИСХОДОВ

### R5 Resolution Layer (`PARTIAL`)
- `backend/app/services/game/combat_math.py`
- `backend/app/services/game/physics_validator.py`
- `backend/app/services/action/processor.py`
- `backend/app/services/npc/math_utils.py`

### Gap / Trauma effects (`PARTIAL`)
- `backend/app/services/npc/break_progress_engine.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/state_applicator.py`

---

## L3 & L3.5 — АВАТАР И ОГРАНИЧЕНИЯ

### R6 Character Constraint (`PARTIAL`)
- `backend/app/services/character_service.py`
- `backend/app/services/npc/npc_state.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/life_engine.py`

### R6.4 Ego Resistance (`PARTIAL`)
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/decision_hub.py`
- `backend/app/services/npc/psyche_engine.py`

### R6.5 Hardcore Death (`PARTIAL`)
- `backend/app/services/combat_service.py`
- `backend/app/services/game/combat_math.py`
- `backend/app/services/npc/state_applicator.py`

---

## L4 — СОЦИАЛЬНАЯ СЕТЬ

### R7 Social System (`PARTIAL`)
- `backend/app/services/memory/relationship_store.py`
- `backend/app/services/memory/memory_manager.py`
- `backend/app/services/npc/opportunity_engine.py`
- `backend/app/services/events/event_bus.py`

---

## L5 — СЛОМ

### R8 Break System (`PARTIAL`)
- `backend/app/services/npc/break_progress_engine.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/psyche_engine.py`
- `backend/app/services/npc/state_applicator.py`

---

## L6 — МИР

### R9 World Director (`PARTIAL`)
- `backend/app/services/world_scheduler.py`
- `backend/app/services/simulation/world_state.py`
- `backend/app/services/events/event_types.py`
- `backend/app/services/events/event_bus.py`

### R9.8 Economy (`EARLY/PARTIAL`)
- `backend/app/services/simulation/world_state.py`
- `backend/app/services/adventure_loader.py`

---

## L8.5 — GAME LOOP

### R13 Tick-Based Engine (`PARTIAL`)
- `backend/app/services/game_loop.py`
- `backend/app/services/game_loop_factory.py`
- `backend/app/services/world_scheduler.py`
- `backend/app/services/action/processor.py`

### Campaign Manager (`PARTIAL`)
- `backend/app/services/campaign_state_service.py`
- `backend/app/services/player_session_service.py`
- `backend/app/services/scene_state_manager.py`

---

## L9 — FRONTEND & UX

### R14.* UI / FOW (`EARLY`)
- `frontend/ui/index.html`
- `frontend/run_frontend.bat`

---

## L10 — DEVTOOLS

### R15.1 God Mode / diagnostics (`PARTIAL`)
- `backend/app/services/logging_tools.py`
- `backend/app/services/error_interpreter.py`
- `backend/app/services/system_requirements.py`
- `backend/app/services/vram_monitor.py`

### R15.2 Central Math Config (`PARTIAL`)
- `backend/app/core/config.py`
- `backend/app/services/game/combat_math.py`
- `backend/app/services/npc/math_utils.py`

---

## Быстрый индекс «с чего читать в первую очередь»
1. Пространство: `location_graph.py` → `spatial_runtime.py` → `perception_filter.py`
2. Решения NPC: `decision_hub.py` → `opportunity_engine.py` → `reaction_priority.py`
3. Память: `memory_manager.py` → `layered_memory.py` → `resonance_engine.py`
4. Персистентность: `scene_state_manager.py` → `campaign_state_service.py`

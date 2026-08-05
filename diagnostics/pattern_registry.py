"""
path: diagnostics/pattern_registry.py
Назначение: Реестр регулярных выражений для парсинга backend-логов.
            Паттерны откалиброваны под реальный формат логов проекта ENIGMA.
            Все паттерны — компилированные объекты re.Pattern для скорости.
Зависимости: re (stdlib)
Основные сущности: PATTERNS, COMPILED
"""

import re
from typing import Dict

# ---------------------------------------------------------------------------
# Сырые паттерны (строки) — для документации и тестов
# ---------------------------------------------------------------------------
PATTERNS: Dict[str, str] = {
    # --- Tick / Decision health ---
    # [R3_DIRECT] 5 decisions → DMFrame (focus=2, bg=3)
    "decisions_count": r"\[R3_DIRECT\] (\d+) decisions",
    # [DECISION_HUB] thief_shadow: intent=Intent.IDLE score=0.0 event=player_interacts
    "decision_hub": r"\[DECISION_HUB\] (\w+): intent=Intent\.(\w+) score=(-?[\d.]+) event=([\w.]+)",
    # [TRACE][DECISION_SCORE] npc=blacksmith_orm winner=Intent.OFFER_JOB top3=[...]
    "decision_score": r"\[TRACE\]\[DECISION_SCORE\] npc=(\w+) winner=Intent\.(\w+)",
    # [SCENE] Найден editor JSON: ... для location_id=tavern_silver_wolf
    "editor_json_found": r"\[SCENE\] Найден editor JSON.*location_id=(\w+)",
    # --- State / Emotion ---
    # [STATE_APPLIED] maid_lusya: stress=0.2 intent=Intent.OBSERVE
    "state_applied": r"\[STATE_APPLIED\] (\w+): stress=([\d.]+) intent=Intent\.(\w+)",
    # [SESSION_RESET] maid_lusya: stress=0 emotion=NEUTRAL mask=NONE
    "session_reset": r"\[SESSION_RESET\] (\w+): stress=([\d.]+) emotion=(\w+) mask=(\w+)",
    # [DISTORTION] threat=0.006 trust=0.0 salience=0.0 (governor=ok)
    "distortion": r"\[DISTORTION\] threat=([\d.]+) trust=([\d.]+) salience=([\d.]+)",
    # --- Movement / Traversal ---
    # [SCENE] location_templates.json недоступен
    "spatial_fallback": r"\[SCENE\] location_templates\.json недоступен",
    # [LocationGraph] fallback-граф для 'tavern_silver_wolf'
    "graph_fallback": r"\[LocationGraph\] fallback-граф для '(\w+)'",
    # [MOVEMENT_ENGINE] Узел 'bed' не найден для thief_shadow в inn_rooms
    "node_not_found": r"\[MOVEMENT_ENGINE\] Узел '(\w+)' не найден для (\w+) в (\w+)",
    # [TRAVERSAL] Start: npc=thief_shadow to_node=bed  (если появится в новых логах)
    "traversal_start": r"\[TRAVERSAL\] Start: npc=(\w+) to_node=(\w+)",
    # [TRAVERSAL] Complete: npc=thief_shadow at_node=bed
    "traversal_complete": r"\[TRAVERSAL\] Complete: npc=(\w+) at_node=(\w+)",
    # --- Spatial / Snapshot ---
    # [DEBUG SPATIAL] location=tavern_silver_wolf, npc_positions keys=[...]
    "spatial_snapshot": r"\[DEBUG SPATIAL\] location=(\w+), npc_positions keys=(\[.+?\])",
    "trace_snapshot": r"\[TRACE\]\[SNAPSHOT\] npc=(\w+) x=([\d.]+) y=([\d.]+)",
    "engine_received": r"\[TRACE\]\[ENGINE_RECEIVED\] npc=(\w+) reason=(\S+)",
    "tick_decisions_end": r"\[TICK_DECISIONS\] end: (\d+) decisions",
    # [PERCEPTION_FILTER] 1/6 NPC: ['thief_shadow']
    "perception_filter": r"\[PERCEPTION_FILTER\] (\d+)/(\d+) NPC: (\[.+?\])",
    # [PERCEPTION_SKIP] maid_lusya: dist=12.1m (not visible)
    "perception_skip": r"\[PERCEPTION_SKIP\] (\w+): dist=([\d.]+)m",
    # --- Directive pipeline ---
    # [S.0 MATCH] name_form 'торнин' at pos 10 → tavern_keeper_tornin
    "target_match": r"\[S\.0 MATCH\] name_form '(.+?)' at pos \d+ → (\w+)",
    # [TARGET] Selected Торнин Серебряная Луна (tavern_keeper_tornin) from 1 candidates
    "target_selected": r"\[TARGET\] Selected .+? \((\w+)\) from (\d+) candidates",
    # [TARGET] No target found in: ...
    "target_not_found": r"\[TARGET\] No target found in: (.+)",
    # [DIRECTIVE_INTERPRET] — если появится
    "obedience_pressure": r"\[DIRECTIVE_INTERPRET\] Target=(\w+), Action=(\w+), ObediencePressure=([\d.]+)",
    # [COGNITIVE_OVERLAY] Applied N directive deltas
    "cognitive_overlay": r"\[COGNITIVE_OVERLAY\] Applied (\d+) directive deltas",
    # --- LLM health ---
    # [R4A_POOL] calling complete() / complete() returned N chars
    "llm_call": r"\[R4A_POOL\] calling complete\(\)",
    "llm_response": r"\[R4A_POOL\] complete\(\) returned (\d+) chars",
    # [R4A_WORKER] direct sync call / returned N chars (DirectBridge path)
    "llm_worker_call": r"\[R4A_WORKER\] direct sync call",
    "llm_worker_response": r"\[R4A_WORKER\] returned (\d+) chars",
    # [R4A_STREAM] calling stream_tokens() / stream complete, N chars (Streaming path — ADR-147)
    "llm_stream_call": r"\[R4A_STREAM\] calling stream_tokens\(\)",
    "llm_stream_response": r"\[R4A_STREAM\] stream complete, (\d+) chars",
    # dm_resp='Ничего не произошло.'
    # --- Invariant Defense System ---
    "sim_integrity": r"\[SIM_INTEGRITY\] id=(\S+) severity=(\S+) file=(\S+) line=(\d+)",
    "tick_complete": r"\[TICK_ORCH\] tick=(\d+) game_time=([\d.]+) decisions=(\d+) verbal=(\d+) moved=(\d+)",
    "scene_events_verbal": r"\[SCENE_EVENTS\] (\d+) events emitted.*'verbal'",
    "llm_nothing": r"dm_resp='Ничего не произошло\.'",
    "llm_pool_fail": r"\[R4A_WORKER\] exception: Все модели пула недоступны для capability=\w+",
    # 3+ подряд идущих CJK-символа = галлюцинация на китайском
    "llm_cjk": r"[\u4e00-\u9fff]{3,}",
    # --- EventBus / Scene events ---
    # [EVENT_BUS] Published: PLAYER_SPOKE, target=None
    "event_bus": r"\[EVENT_BUS\] Published: (\w+), target=(\w+|None)",
    # [SCENE_EVENTS] 1 events emitted: ['verbal']
    "scene_events": r"\[SCENE_EVENTS\] (\d+) events emitted: (\[.+?\])",
    # --- R5 Physics ---
    # [R5] Physical action: success=True result=частичный успех
    "r5_result": r"\[R5\] Physical action: success=(\w+) result=(.+)",
    # --- Delta pipeline ---
    # [DELTA] thief_shadow: intent=idle stress_d=0.0 trust_d=0.0 fear_d=0.0
    "delta": r"\[DELTA\] (\w+): intent=(\w+) stress_d=([\d.-]+) trust_d=([\d.-]+) fear_d=([\d.-]+)",
    # --- Pipeline pre-bus failures (Инвариант 3: Наблюдаемость отказа) ---
    # [PIPELINE][CRITICAL] phase=8 handler=AffectivePipeline error=AttributeError: ...
    "pipeline_critical": r"\[PIPELINE\]\[CRITICAL\] phase=(\w+) handler=(\w+) error=(\w+):",
    # [CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: ...
    "causality_crash": r"\[CAUSALITY_CRASH\] (\w+) failed:",
    # [PHASE8_CRASH] handler=ReactionSubscriber error=KeyError: ...
    "phase8_crash": r"\[PHASE8_CRASH\] handler=(\w+) error=(\w+):",
    # [TICK_ORCH] Ошибка в тике ... — главный catch-all
    "tick_orch_error": r"\[TICK_ORCH\] Ошибка в тике (\w+):",
    # [AFFECT_DECAY] Failed for ... — потеря аффективных отпечатков
    "affect_decay_fail": r"\[AFFECT_DECAY\] Failed for (\w+):",
    # --- Session / startup ---
    # [PLAYER_SELECT] Campaign: Open_road, Player: Демеург
    "player_select": r"\[PLAYER_SELECT\] Campaign: (\w+), Player: (.+)",
    "session_loaded": r"\[SESSION_LOADED\] Campaign: (\w+), Player: (.+)",
    # Application startup complete
    "startup_complete": r"Application startup complete",
    "llm_server_ok": r"llama-server.{1,30}запущен|LLM.{1,30}доступен",
}

# ---------------------------------------------------------------------------
# Компилированные паттерны — используются в hot-path парсера
# ---------------------------------------------------------------------------
COMPILED: Dict[str, re.Pattern] = {
    name: re.compile(pattern) for name, pattern in PATTERNS.items()
}

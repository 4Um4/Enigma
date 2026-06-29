# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\r3_direct_builder.py
"""
R3 Direct Mode: DecisionResult → SceneOutcome → DMFrame.

Альтернативный путь — npc_agent BYPASSED, DM генерирует сам.
Собирает контексты из shared_context, строит DMFrame через SceneOutcomeBuilder.

Назначение: Сборка DMFrame из DecisionResult[] для R3 Direct Mode
Зависимости: logging, app.services.verbalization.scene_outcome_builder, app.services.verbalization.scene_continuity
Основные сущности: build_r3_dm_frame
"""

import logging
from typing import Any
from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter

logger = logging.getLogger(__name__)


def build_r3_dm_frame(
    shared_context: Any,
    actions: list,
    rules_result: Any | None,
) -> dict:
    """Строит DMFrame из DecisionResult[] + обновляет SceneContinuity.

    Мутирует shared_context (scene_continuity).
    Возвращает npc_result dict для дальнейшей обработки в game_loop.
    """
    from app.services.verbalization.scene_outcome_builder import (
        SceneOutcomeBuilder,
        SceneContext,
    )
    from app.services.verbalization.scene_continuity import SceneContinuity

    _builder = SceneOutcomeBuilder()
    _filtered_ctxs = shared_context.npc_contexts or []
    _target_id = shared_context.player_target_id or ""

    # Собираем DecisionResult[] из отфильтрованных контекстов
    _decisions = []
    for ctx in _filtered_ctxs:
        dr = ctx.get("decision_result")
        if dr is not None:
            _decisions.append(dr)

    # Собираем SceneContext для salience/visibility
    _scene_state = shared_context.scene_state or {}
    # A2-FIX: zombie reader → SpatialQueryService.
    # Раньше: _distances всегда {} → SceneContext.distances пустой → DM слеп к дистанциям.
    _distances = {}
    _spatial_query = getattr(shared_context, 'spatial_query', None)
    if _spatial_query is not None:
        _npc_ids = [n.get("npc_id", n.get("id", "")) for n in _scene_state.get("npc_positions", {}).values()]
        _distances = _spatial_query.player_distances(_npc_ids)
    _visible = {
        npc_id for npc_id, is_visible
        in _scene_state.get("line_of_sight", {}).items()
        if is_visible
    }
    # Epistemic Boundary: DM не читает внутренние уровни NPC (tier) из контекстов, 
    # только локальную физическую видимость.
    _tiers = {}

    # R5: Определяем успех физического действия из rules_agent
    _player_success = True  # VERBAL действия всегда "успешны" (нет броска)
    if rules_result and isinstance(rules_result, dict):
        _checks = rules_result.get("checks", [])
        if _checks:
            _first_check = _checks[0] if isinstance(_checks[0], dict) else _checks[0].to_dict() if hasattr(_checks[0], 'to_dict') else {}
            if _first_check.get("needs_roll", False):
                _result_str = _first_check.get("result", "").lower()
                _player_success = "успех" in _result_str or "крит" in _result_str
                logger.warning(f"[R5] Physical action: success={_player_success} result={_result_str}")

    _scene_ctx = SceneContext(
        distances=_distances,
        visible_npcs=_visible,
        npc_tiers=_tiers,
        player_action_text=actions[0].action if actions else "",
        player_success=_player_success,
        player_target_id=_target_id,
    )

    # Epistemic Boundary (ADR-TZ08-4): Читаем только наблюдаемый слепок (observed_state).
    # Ментальные объекты (real_state, distortion_bias) больше не генерируются ядром.
    _state_snapshots = {
        ctx["npc_id"]: ctx["observed_state"]
        for ctx in _filtered_ctxs
        if ctx.get("observed_state")
    }
    
    # ФАЗА 0: профили NPC для voice_profile, backstory, author_notes
    _npc_profiles = {
        ctx["npc_id"]: ctx["profile_l0"]
        for ctx in _filtered_ctxs
        if ctx.get("profile_l0")
    }
    # ФАЗА 4: темы NPC из TopicExtractor (Устав 3.2)
    _npc_topics = {
        ctx["npc_id"]: ctx["topic"]
        for ctx in _filtered_ctxs
        if ctx.get("topic")
    }

    # Epistemic Boundary: affective_load скрыт от DM-агента.
    
    # ADR-131: Извлекаем coherence из avatar state (если доступен)
    _avatar_coherence = 1.0  # дефолт — ясный ум
    _player_state = shared_context.player_state or {}
    if isinstance(_player_state, dict):
        for _pname, _pdata in _player_state.items():
            if isinstance(_pdata, dict):
                _coh = _pdata.get("cognitive_coherence")
                if _coh is not None:
                    try:
                        _avatar_coherence = float(_coh)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
                break  # берём первого игрока
    
    # Строим SceneOutcome → DMFrame (с психологической проекцией + ADR-131 трёхосевая модель)
    _scene = _builder.build(
        _decisions, _scene_ctx,
        state_snapshots=_state_snapshots,
        distortion_biases={},
        npc_profiles=_npc_profiles,
        topics=_npc_topics,
        npc_affective_loads={},
        avatar_coherence=_avatar_coherence,
    )

    # Диагностика ProjectionLayer + DecisionHub
    for actor in _scene.actors:
        if actor.psychological:
            p = actor.psychological
            logger.warning(f"[PROJECTION] {actor.npc_id}: {p.regime.value} (int={p.intensity}, stab={p.stability})")
    # Дельты от DecisionHub
    # Epistemic Boundary: Внутренние дельты (stress/trust) скрыты от DM. 
    # DM судит по проявлениям (manifestations), а не по скрытым математическим сдвигам.

    # B.3/B.4: Обновляем SceneContinuity из дельт
    _cont = shared_context.scene_continuity or SceneContinuity()
    # Epistemic Boundary: Внутренние дельты (stress/trust) скрыты от DM. 
    # DM судит по проявлениям (manifestations), а не по скрытым математическим сдвигам.
    _cont.update_tension(0.0)
    _cont.update_emotional_vector({
        "trust": 0.0,
        "tension": 0.0,
        "confusion": 0.3 if len(_decisions) > 2 else 0.0,  # много NPC = хаос
    })
    # Флаги ключевых событий
    _event_type = shared_context.action_type or ""
    if "insult" in _event_type:
        _cont.add_flag("insult_occurred")
        _cont.add_event(f"Игрок оскорбил {_target_id or 'NPC'}")
    if "threaten" in _event_type:
        _cont.add_flag("threat_made")
        _cont.add_event(f"Игрок угрожал {_target_id or 'NPC'}")
    if "attack" in _event_type:
        _cont.add_flag("combat_started")
        _cont.add_event("Началась драка")

    # ФАЗА 3.4: Proactive decisions → SceneContinuity (DM видит проактивные действия)
    _tick_result = shared_context.world_tick_result
    if _tick_result and _tick_result.decisions:
        for _pd in _tick_result.decisions:
            _intent_labels = {
                "block_path": "преградил(а) дорогу",
                "ambush": "пытается устроить засаду",
                "seek_ally": "отправился(ась) искать союзника",
                "offer_job": "предлагает работу",
                "request_service": "просит об услуге",
                "spread_rumor": "распространяет слух",
                "call_for_help": "зовёт на помощь",
                "change_role": "меняет роль",
            }
            _label = _intent_labels.get(_pd.intent.value, _pd.intent.value)
            _target_str = f" → {_pd.intent_target}" if _pd.intent_target else ""
            _cont.add_event(f"{_pd.npc_id}: {_label}{_target_str}")
            _cont.add_flag(f"proactive_{_pd.intent.value}_{_pd.npc_id}")
        logger.warning(f"[WORLD_TICK→CONTINUITY] {len(_tick_result.decisions)} proactive → DM context")

    # ШАГ 0.5: MicroEvents → SceneContinuity флаги/события
    for ctx in _filtered_ctxs:
        for me in ctx.get("micro_events", []):
            _name = ctx.get("observed_state", {}).get("name") or me.npc_id
            if me.event_type.value == "object_dropped":
                _cont.add_flag(f"{_name}_dropped_object")
                _cont.add_event(f"{_name} уронил(а) предмет")
            elif me.event_type.value == "interaction_disrupted":
                _cont.add_flag(f"{_name}_disrupted")
                _cont.add_event(f"Действие {_name} прервано")
            elif me.event_type.value == "grip_tightened":
                _cont.add_flag(f"{_name}_grip_tightened")
                # Без add_event — слишком мелкое для нарратива

    # ШАГ D: Social Propagation → SceneContinuity (факты для DM)
    for _pr in shared_context.social_propagation or []:
        _cont.add_event(_pr.continuity_note)

    # ФАЗА 3.1: Spatial Events → SceneContinuity
    for _sp_ev in shared_context.spatial_events or []:
        _sp_name = _sp_ev.npc_id
        if _sp_ev.event_type == "proximity_close":
            _cont.add_event(f"Игрок подошёл к {_sp_name}")
            _cont.add_flag(f"proximity_close_{_sp_name}")
        elif _sp_ev.event_type == "proximity_leave":
            _cont.add_event(f"Игрок отошёл от {_sp_name}")
            _cont.add_flag(f"proximity_leave_{_sp_name}")

    _dm_frame = _builder.build_dm_frame(_scene)

    # Конвертируем DMFrame в формат совместимый с dm_agent
    npc_result = {
        "npc_reactions": [],       # Пусто — DM генерирует сам
        "npc_actions": [],         # Пусто — DM генерирует сам
        "dm_frame": _dm_frame,     # КЛЮЧ: DM использует этот путь
    }

    # B.3/B.4: Передаём SceneContinuity в контекст для DM prompt
    shared_context.scene_continuity = _cont

    # Epistemic Boundary: Ментальные объекты NPC скрыты от DM-агента. 
    # DM описывает только то, что физически проявлено в player_perception.

    logger.warning(f"[R3_DIRECT] {len(_decisions)} decisions → DMFrame (focus={len(_dm_frame.focus_npcs)}, bg={len(_dm_frame.background_npcs)})")

    return npc_result
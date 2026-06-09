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

    Мутирует shared_context (scene_continuity, npc_recalled_memory, npc_suppressed_secrets).
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
    _distances = _scene_state.get("player_distances", {})
    _visible = {
        npc_id for npc_id, is_visible
        in _scene_state.get("line_of_sight", {}).items()
        if is_visible
    }
    _tiers = {ctx["npc_id"]: ctx.get("tier", "minor") for ctx in _filtered_ctxs}

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

    # Собираем снапшоты для ProjectionLayer (реальное состояние + искажения)
    _state_snapshots = {
        ctx["npc_id"]: ctx["real_state"]
        for ctx in _filtered_ctxs
        if ctx.get("real_state")
    }
    _distortion_biases = {
        ctx["npc_id"]: ctx["distortion_bias"]
        for ctx in _filtered_ctxs
        if ctx.get("distortion_bias")
    }
    # ФАЗА 0: профили NPC для voice_profile, backstory, author_notes
    _npc_profiles = {
        ctx["npc_id"]: ctx["profile_l0"]
        for ctx in _filtered_ctxs
        if ctx.get("profile_l0")
    }
    # ФАЗА 4: темы NPC из TopicExtractor (Устав 3.2)
    _npc_topics = {
        ctx["npc_id"]: ctx["verbalization_ctx"].topic
        for ctx in _filtered_ctxs
        if ctx.get("verbalization_ctx") and ctx["verbalization_ctx"].topic
    }

    # ADR-131: Извлекаем affective_load из NPC state для трёхосевой модели
    _npc_affective_loads = {}
    for _nid, _state in _state_snapshots.items():
        if isinstance(_state, dict):
            _load = _state.get("affective_load")
            if _load is not None:
                try:
                    _npc_affective_loads[_nid] = float(_load)
                except (TypeError, ValueError):
                    pass
    
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
                    except (TypeError, ValueError):
                        pass
                break  # берём первого игрока
    
    # Строим SceneOutcome → DMFrame (с психологической проекцией + ADR-131 трёхосевая модель)
    _scene = _builder.build(
        _decisions, _scene_ctx,
        state_snapshots=_state_snapshots,
        distortion_biases=_distortion_biases,
        npc_profiles=_npc_profiles,
        topics=_npc_topics,
        npc_affective_loads=_npc_affective_loads,
        avatar_coherence=_avatar_coherence,
    )

    # Диагностика ProjectionLayer + DecisionHub
    for actor in _scene.actors:
        if actor.psychological:
            p = actor.psychological
            logger.warning(f"[PROJECTION] {actor.npc_id}: {p.regime.value} (int={p.intensity}, stab={p.stability})")
    # Дельты от DecisionHub
    for d in _decisions:
        dl = LegacyStateDeltaAdapter.collapse(d.deltas)
        logger.warning(f"[DELTA] {d.npc_id}: intent={d.intent.value} stress_d={dl.stress_delta} trust_d={dl.trust_delta} fear_d={dl.fear_delta}")

    # B.3/B.4: Обновляем SceneContinuity из дельт
    _cont = shared_context.scene_continuity or SceneContinuity()
    _total_stress_d = sum(LegacyStateDeltaAdapter.collapse(d.deltas).stress_delta for d in _decisions)
    _total_trust_d = sum(LegacyStateDeltaAdapter.collapse(d.deltas).trust_delta for d in _decisions)
    _cont.update_tension(_total_stress_d / 100.0)  # нормализация в 0..1
    _cont.update_emotional_vector({
        "trust": _total_trust_d / 50.0,   # нормализация
        "tension": _total_stress_d / 50.0,
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
            _npc_name = ctx.get("verbalization_ctx")
            _name = _npc_name.npc_name if _npc_name else me.npc_id
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

    # Этап 4.1: Собираем recalled_facts из npc_contexts для DM промпта
    _recalled_for_dm = []
    for _nctx in shared_context.npc_contexts or []:
        _vc = _nctx.get("verbalization_ctx")
        if _vc and _vc.recalled_facts:
            _recalled_for_dm.append({
                "npc_name": _vc.npc_name,
                "facts": _vc.recalled_facts,
            })
    shared_context.npc_recalled_memory = _recalled_for_dm
    # Этап 5.5: suppressed secrets для DM
    _suppressed_for_dm = []
    for _nctx in shared_context.npc_contexts or []:
        _vc = _nctx.get("verbalization_ctx")
        if _vc and _vc.suppressed_secrets:
            _suppressed_for_dm.append({
                "npc_name": _vc.npc_name,
                "count": len(_vc.suppressed_secrets),
            })
    shared_context.npc_suppressed_secrets = _suppressed_for_dm
    # Этап 10: накопленные черты NPC для вербализации
    _identity_for_dm = []
    for _nctx in shared_context.npc_contexts or []:
        _vc = _nctx.get("verbalization_ctx")
        _traits = _nctx.get("identity_traits", {})
        if _vc and _traits:
            _identity_for_dm.append({
                "npc_name": _vc.npc_name,
                "traits": _traits,
            })
    shared_context.npc_identity_traits = _identity_for_dm

    logger.warning(f"[R3_DIRECT] {len(_decisions)} decisions → DMFrame (focus={len(_dm_frame.focus_npcs)}, bg={len(_dm_frame.background_npcs)})")

    return npc_result
# path: backend/app/services/game_loop/turn_pipeline.py
"""
TurnPipeline — владелец фазовой машины player-turn (DEGOD Phase3-3A.3).

Отвечает на вопрос: «Как выполняется player turn?»
Фазы: init-context → avatar-load(DEATH-GATE) → scene-lock → DM+intent → NPC-orchestration → finalize(Rules/Avatar/R3).
Получает зависимости явными контрактами (DmPhaseDeps/NpcOrchDeps-фабрики — GameLoop) и DI-ссылками.
Не владеет: _background_tasks/_current_tick (GameLoop; доступ через провайдеры),
коммит результата (фасад), campaign lifecycle (HOLD).

Назначение: владелец фазовой машины player-turn (DEGOD Phase3-3A.3). Отвечает на вопрос «как выполняется player turn».
Зависимости: game_loop.pipeline_state, dm_phase, npc_orchestration, tick_context, phase_1_input, scene_init
Основные сущности: TurnPipeline, R3_DIRECT_MODE
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from typing import Optional

from app.core.config import settings
from app.models.schemas import ChatTurnRequest, ChatTurnResponse
from app.services.game_loop.agent_runner import run_agent_safe
from app.services.game_loop.dm_phase import run_dm_phase
from app.services.game_loop.npc_orchestration import run_npc_orchestration
from app.services.game_loop.phase_1_input import (
    publish_classified_player_event,
    resolve_player_intent,
)
from app.services.game_loop.pipeline_state import _PipelineState
from app.services.game_loop.scene_init import init_scene_state
from app.services.game_loop.tick_context import _TickContext
from app.services.state.context_builder import build_context
from app.services.tick_orchestrator import TickPlayerResultDTO

logger = logging.getLogger(__name__)

R3_DIRECT_MODE: bool = True


class TurnPipeline:
    """Фазовая машина player-turn. Один вопрос: как выполняется ход игрока."""

    def __init__(
        self,
        *,
        memory_manager,
        rel_store,
        scene_manager,
        avatar_service,
        dm_orchestrator,
        svc,
        mvp_controller,
        intent_compressor,
        tick_orch,
        character_service,
        world_scheduler,
        get_current_tick,
        get_life_engine,
        set_current_tick,
        spawn_world_tick_task,
        build_dm_phase_deps,
        build_npc_orch_deps,
    ) -> None:
        # Имена атрибутов = прежние self-имена => тела методов переезжают 1-в-1
        self.memory_manager = memory_manager
        self._rel_store = rel_store
        self.scene_manager = scene_manager
        self.avatar_service = avatar_service
        self.dm_orchestrator = dm_orchestrator
        self._svc = svc
        self.mvp_controller = mvp_controller
        self._intent_compressor = intent_compressor
        self._tick_orch = tick_orch
        self.character_service = character_service
        self.world_scheduler = world_scheduler
        self.get_current_tick = get_current_tick
        self._get_life_engine = get_life_engine
        self._set_current_tick = set_current_tick
        self._spawn_world_tick_task = spawn_world_tick_task
        self._build_dm_phase_deps = build_dm_phase_deps
        self._build_npc_orch_deps = build_npc_orch_deps

    # ── B-провайдеры (GameLoop-owned) ──────────────────────────────────────

    def _sync_shared_context_with_scene(
        self, scene_state: dict, shared_context: Any
    ) -> None:
        """Синхронизирует shared_context с заблокированным scene_state."""
        shared_context.scene_state = scene_state

        from app.services.spatial.spatial_query_service import SpatialQueryService

        shared_context.spatial_query = SpatialQueryService(
            npc_positions=scene_state.get("npc_positions", {}),
            scene_state=scene_state,
        )

        if hasattr(shared_context, "current_tick"):
            shared_context.current_tick = scene_state.get("tick", 0) + 1
        self._set_current_tick(scene_state.get("tick", 0) + 1)

    async def _finalize_pipeline_and_build_dm_frame(
        self,
        shared_context: Any,
        _ctx: Any,
        campaign_id: str,
        actions: list,
        _player_result: TickPlayerResultDTO,
    ) -> tuple[dict, dict]:
        """ФАЗА 7 (Rules) + ФАЗЫ 8-10 (R3 Frame) + Avatar Sync."""
        _state_observed_facts = getattr(_player_result, "observed_facts", [])  # noqa: ENIGMA002
        logger.debug(
            f"[DEBUG_GAME_LOOP] _state_observed_facts count={len(_state_observed_facts)}"
        )

        from app.services.events.event_types import EventType
        from app.services.events.rules_subscriber import RulesSubscriber

        _action_type = shared_context.action_type or "player_interacts"
        _rules_action_type = self.dm_orchestrator._router.get_rules_action_type(
            _action_type
        )

        _rules_event = type(
            "Event",
            (),
            {
                "type": "player_attacks"
                if "attack" in _rules_action_type.lower()
                else "player_interacts",
                "payload": {"target_id": shared_context.player_target_id},
                "source": actions[0].player_name if actions else "player",
                "id": f"rules_{shared_context.current_tick}",
            },
        )()

        _rules_snapshot = {
            "all_npcs_raw": _ctx.all_npcs_raw or [],
            "tick_number": shared_context.current_tick or 0,
            "campaign_id": campaign_id,
            "relationship_store": self._rel_store,
            "raw_input": actions[0].action if actions else "",
        }

        _rules_sub = RulesSubscriber()
        _rules_delta = _rules_sub.handle(_rules_event, _rules_snapshot)

        rules_result = {"checks": _rules_delta.checks} if _rules_delta else {}
        logger.warning(
            f"[RULES] action_type={_action_type} → {_rules_action_type} (synchronous reducer)"
        )

        _player_name = actions[0].player_name if actions else ""
        _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

        import copy

        _avatar_state_before = copy.deepcopy(_avatar_state) if _avatar_state else None  # noqa: ENIGMA001

        # Stage 0 Task 0.8: SSOT Economic. Прямая мутация аватара запрещена.
        # Дельта денег применяется через StateApplicator.apply_batch вместе с остальными NPC.
        if _rules_delta and _rules_delta.money_delta != 0.0:
            from app.models.delta_payloads import EconomicPayload
            from app.models.state_delta import DeltaDomain, StateDeltas

            _eco_delta = StateDeltas(
                npc_id="player",
                domain=DeltaDomain.ECONOMY,
                payload=EconomicPayload(money_delta=_rules_delta.money_delta)
            )
            _state_applicator = self._svc.get_state_applicator(campaign_id)
            _player_dict = next((n for n in _ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
            if _player_dict and _state_applicator:
                _state_applicator.apply_batch([_eco_delta], _ctx.all_npcs_raw, campaign_id)
                logger.info(f"[TRADE_FIX] Applied money_delta={_rules_delta.money_delta} to avatar via StateApplicator.")

        from dataclasses import asdict, is_dataclass

        if is_dataclass(_avatar_state) and not isinstance(_avatar_state, type):
            _avatar_dict = asdict(_avatar_state)
            _avatar_dict["npc_id"] = "player"
            _avatar_dict["id"] = "player"
            if hasattr(_ctx, "all_npcs_raw") and _ctx.all_npcs_raw is not None:
                _ctx.all_npcs_raw = [
                    n for n in _ctx.all_npcs_raw if n.get("npc_id") != "player"
                ]
                _ctx.all_npcs_raw.append(_avatar_dict)

        shared_context.npc_contexts = getattr(_player_result, "npc_contexts", []) or []  # noqa: ENIGMA002
        try:
            from app.services.scene.r3_direct_builder import build_r3_dm_frame

            npc_result = (
                build_r3_dm_frame(shared_context, actions, rules_result)
                if R3_DIRECT_MODE
                else {}
            )

            logger.debug(
                f"[TRAV_CHECK_P1_5] after_finalize_return: id={id(shared_context.scene_state)} traversals={list(shared_context.scene_state.get('active_traversals', {}).keys()) if shared_context.scene_state else 'NONE'}"
            )

            _updated_avatar_dict = next(
                (
                    n
                    for n in getattr(_ctx, "all_npcs_raw", [])  # noqa: ENIGMA002
                    if n.get("npc_id") == "player"
                ),
                None,
            )
            from app.models.npc_state import NPCState
            if _updated_avatar_dict and isinstance(_avatar_state, NPCState):
                # S208 (P0-B): GameLoop — оркестратор, не писатель NPCState.
                # Каноническая граница мутации — AvatarStateApplicator.
                from app.services.avatar_state_applicator import AvatarStateApplicator

                AvatarStateApplicator.apply_pipeline_result(
                    _avatar_state, _updated_avatar_dict
                )

            if (
                _avatar_state
                and _avatar_state_before
                and _avatar_state != _avatar_state_before
            ):
                self.avatar_service.save_state(campaign_id, _avatar_state)
                _avatar_hp = getattr(_avatar_state, "effective_hp", getattr(_avatar_state, "hp", 0))
                logger.warning(
                    f"[AVATAR] STATE APPLIED: pain={_avatar_state.body_state.get('pain', 0.0):.1f} shock={_avatar_state.body_state.get('shock_impulse', 0.0):.2f} money={_avatar_state.body_state.get('money', 0.0):.1f} hp={_avatar_hp}"
                )

            _engine = self._get_life_engine()
            if (
                _engine
                and hasattr(_ctx, "all_npcs_raw")
                and _ctx.all_npcs_raw is not None
            ):
                _engine.update_cache(campaign_id, _ctx.all_npcs_raw)

        except Exception as _fin_err:
            logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
            # H-34 FIX: Не маскируем ошибку пустым npc_result, пробрасываем исключение (ADR-O-308)
            raise

        try:
            from app.models.npc_state import EmotionTag
            from app.services.game_loop.phase_6_avatar import (
                update_avatar_from_npc_intents,
            )

            update_avatar_from_npc_intents(
                self.avatar_service,
                campaign_id,
                _player_name,
                shared_context.npc_contexts or [],
                EmotionTag,
            )
        except Exception as _av_err:
            logger.warning(f"[AVATAR] update error: {_av_err}")

        return rules_result, npc_result

    async def _execute_dm_and_intent_resolution(
        self,
        actions: list,
        shared_context: Any,
        scene_state: dict,
        _ctx: Any,
        campaign_id: str,
        location: str,
    ) -> tuple[Any, Any]:
        """ФАЗА 1-3: Запуск DM-фазы и резолв интента игрока."""
        # H-32 FIX: Загружаем профиль игрока из avatar_service, а не используем None
        _player_name = shared_context.player_name or "player"
        _match = self.avatar_service.load_state(campaign_id, _player_name)
        try:
            dm_result = run_dm_phase(
                self._build_dm_phase_deps(),
                actions,
                shared_context,
                scene_state,
                _ctx,
                campaign_id,
                location,
            )
            logger.warning(
                f"[DEBUG DM] is_valid={getattr(dm_result, 'is_valid', None)}, scene_context={getattr(dm_result, 'scene_context', None)}, error={getattr(dm_result, 'error', None)}"
            )

            import dataclasses as _dc
            # Порядок условий по контракту typeshed: is_dataclass сужает тип к
            # DataclassInstance | type[...], затем isinstance исключает класс —
            # asdict получает чистый DataclassInstance.
            if _match and _dc.is_dataclass(_match) and not isinstance(_match, type):
                _player_data_dict = _dc.asdict(_match)
            elif _match and hasattr(_match, "model_dump"):
                _player_data_dict = _match.model_dump()
            else:
                _player_data_dict = None
            _raw_action = actions[0].action if actions else ""

            # S200: Получаем сессию диалога игрока с целевым NPC для контекстного резолва
            _target_npc = shared_context.player_target_id or "player"
            _dialogue_session = None
            if self.memory_manager and _target_npc != "player":
                try:
                    _dialogue_session = self.memory_manager.get_dialogue_session(
                        campaign_id=campaign_id,
                        npc_id=_target_npc,
                        partner_id="player"
                    )
                except Exception as _ds_err:
                    logger.warning(f"[S200] Failed to get dialogue session for {_target_npc}: {_ds_err}")

            _semantic_field = await self._intent_compressor.compress(
                raw_text=_raw_action,
                scene_context=scene_state,
                dialogue_session=_dialogue_session
            )

            # S201/S202: Публикуем SOCIAL_ACTION в EventBus для наблюдателей
            _action_val = _semantic_field.action.value if _semantic_field.action else "UNCERTAIN"
            if _action_val in ("ATTACK", "THREATEN", "DIALOGUE", "STEAL", "GIVE"):
                from app.domain.events import EventDTO
                from app.services.events.event_bus import get_event_bus
                from app.services.events.event_types import EventType

                _prop = None
                if _semantic_field.proposition:
                    _prop = {
                        "subject_id": _semantic_field.proposition.subject_id,
                        "predicate": _semantic_field.proposition.predicate.value,
                        "object_id": _semantic_field.proposition.object_id,
                        "polarity": _semantic_field.proposition.polarity
                    }

                _payload = {
                    "action": _action_val,
                    "actor": _semantic_field.actor or "player",
                    "target": _semantic_field.target or shared_context.player_target_id or "",
                    "speech_act": _semantic_field.speech_act.value if _semantic_field.speech_act else "assert",
                    "proposition": _prop,
                    "physical_force": _semantic_field.physical_force,
                    "emotional_charge": _semantic_field.emotional_charge,
                    "social_pressure": _semantic_field.social_pressure,
                    "tick": shared_context.current_tick
                }

                _event = EventDTO.create_social_action(
                    source=_semantic_field.actor or "player",
                    payload=_payload,
                    visibility="public",
                    radius=10.0
                )
                _bus = get_event_bus()
                _bus.publish(_event)

            _resolution = resolve_player_intent(
                raw_action=_raw_action,
                action_type=shared_context.action_type or "player_interacts",
                target=shared_context.player_target_id or "",
                player_dict=_player_data_dict,
                scene_context=scene_state,
                semantic_field=_semantic_field,
            )
            shared_context.intent_resolution = _resolution

            # ADR-O-330: Player MOVE action creates MacroMovementGoal for MovementEngine
            # Если игрок пишет "подойти к [NPC]", мы должны найти узел NPC и двигаться к нему.
            _sem_action_val = _semantic_field.action_type.value if _semantic_field else ""
            if _sem_action_val == "MOVE" and shared_context.player_target_id:
                _target_id = shared_context.player_target_id
                _target_pos = scene_state.get("npc_positions", {}).get(_target_id, {}).get("position", "")
                if _target_pos:
                    from app.domain.movement import MacroMovementGoal
                    _player_goal = MacroMovementGoal(
                        actor_id="player",
                        target_node_id=_target_pos,
                        location_id=location,
                        reason="player_action:approach",
                        priority=1.0
                    )
                    if not hasattr(_ctx, "movement_intents") or _ctx.movement_intents is None:
                        _ctx.movement_intents = []
                    _ctx.movement_intents.append(_player_goal)
                    logger.warning(f"[PLAYER_MOVE] Injected MacroMovementGoal for player -> {_target_pos}")

            if self.mvp_controller:
                # S199: Уничтожен раздвоенный semantic authority.
                # MvpTavernController теперь получает PlayerAction через bridge из расширенного IntentSemanticField.
                from app.services.player_cognition.legacy_bridge import intent_to_player_action
                _action = intent_to_player_action(
                    intent=_semantic_field,
                    tick=shared_context.current_tick,
                    truth_state=self.mvp_controller.truth_state
                )
                self.mvp_controller.action_compiler.process_action(_action)

            if _ctx.hub_event and _resolution and _resolution.original_intent:
                _params = _resolution.original_intent.parameters
                logger.debug(
                    f"[ARCHAE-PAYLOAD] params={_params} sa={getattr(_params, 'semantic_action', 'NO_SA') if _params else 'NO_PARAMS'}"
                )
                if _params:
                    _sa = getattr(_params, "semantic_action", None)  # noqa: ENIGMA002
                    _tid = getattr(_params, "target_id", None)  # noqa: ENIGMA002
                    _tref = getattr(_params, "target_reference", None)  # noqa: ENIGMA002
                    _sem_payload = {}
                    if _sa:
                        _sem_payload["semantic_action"] = _sa
                    if _tid:
                        _sem_payload["target_id"] = _tid
                    if _tref:
                        _sem_payload["target_reference"] = _tref.lower()
                    if _sem_payload:
                        import dataclasses

                        _ctx.hub_event = dataclasses.replace(
                            _ctx.hub_event, payload=_sem_payload
                        )
                        logger.warning(
                            f"[PAYLOAD_INJECT] hub_event.payload={_sem_payload} id={id(_ctx.hub_event)} event_type={_ctx.hub_event.event_type}"
                        )
        except Exception as e:
            logger.error(f"[DM_INTENT_PHASE] Error: {e}", exc_info=True)
            raise

        return dm_result, _resolution

    def _prepare_and_lock_scene(
        self,
        campaign_id: str,
        location: str,
        shared_context: Any,
        campaign_state: Any,
        player_position: tuple[float, float] | None,
    ) -> dict:
        """Блокирует scene_state на время тика, гарантируя единственный объект."""
        from app.services.game_loop.scene_init import ensure_scene_initialized

        _prepped_scene = ensure_scene_initialized(self, campaign_id)
        _loc_id = _prepped_scene.get("location_id", "") if _prepped_scene else location
        if not _loc_id:
            _loc_id = location

        scene_state = self.scene_manager.lock_for_tick(campaign_id, _loc_id)
        if scene_state is None:
            scene_state = init_scene_state(
                self,
                campaign_id,
                _loc_id,
                shared_context,
                campaign_state,
                player_position=player_position,
            )
            # BUG-CORE-008 FIX: ADR-SCENE-LOCK — _tick_scenes это Dict[str, dict].
            self.scene_manager.adopt_scene_for_tick(campaign_id, _loc_id, scene_state)
        else:
            from app.services.game_loop.scene_init import (
                _sync_game_time,
                _update_player_position,
            )

            _update_player_position(scene_state, player_position)
            _sync_game_time(scene_state, shared_context)

        return scene_state

    async def _load_player_avatar(
        self, actions: list, campaign_id: str, location: str, shared_context: Any
    ) -> Optional[ChatTurnResponse]:
        """Загружает аватар игрока. Если игрок мёртв, возвращает ответ смерти."""
        _player_name = actions[0].player_name if actions else ""
        try:
            _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

            # P0: ACTION ELIGIBILITY GATE — мёртвый игрок не может действовать (ADR-127, Rule 59)
            _player_life = (
                _avatar_state.body_state.get("life_status", "ALIVE")
                if _avatar_state and _avatar_state.body_state
                else "ALIVE"
            )
            if _player_life == "DEAD":
                logger.warning(
                    f"[DEATH_GATE] Player '{_player_name}' is DEAD. DM narrates death."
                )
                from app.services.game_loop.phase_6_avatar import avatar_to_prompt

                shared_context.player_state = {
                    _player_name: avatar_to_prompt(_avatar_state)
                }
                _bs = (
                    _avatar_state.body_state
                    if _avatar_state and _avatar_state.body_state
                    else {}
                )
                _death_avatar_dict = {
                    "physical_state": "dead",
                    "mental_state": "broken",
                    "perceptual_stability": 0.0,
                    "cognitive_coherence": 0.0,
                    "sensory_noise": 1.0,
                    "motor_disruption": 1.0,
                    "perceptual_latency": 1.0,
                    "reality_reconciliation_rate": 0.0,
                    "blood_visibility": min(
                        1.0, float(_bs.get("blood_loss", 0.0)) * 1.5
                    ),
                    "breathing_profile": "none",
                    "posture_state": "collapsed",
                    "will_resistance": 0.0,
                    "embodied_vector": None,
                    "life_status": "DEAD",
                }
                _death_ws = {"avatar_state": _death_avatar_dict}
                try:
                    _engine = self._get_life_engine()
                    _cached = _engine.get_npc_states(campaign_id) if _engine else None
                    if _cached:
                        _death_ws["npc_positions"] = {
                            str(n.get("npc_id") or n.get("id") or f"npc_{i}"): n
                            for i, n in enumerate(_cached)
                            if isinstance(n, dict)
                        }
                except Exception as e:
                    logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
                _death_dm_response = "Тьма поглощает тебя. Твоё тело безжизненно, а сознание растворяется в абсолютной тишине."
                try:
                    _death_result = await run_agent_safe(
                        "dm",
                        self.dm_agent,
                        (location, actions, {}, {}, {}, False, shared_context),
                        {},
                    )
                    if isinstance(_death_result, dict) and _death_result.get(
                        "dm_response"
                    ):
                        _death_dm_response = _death_result["dm_response"]
                except Exception as _dg_err:
                    logger.warning(
                        f"[DEATH_GATE] DM narration failed: {_dg_err}, using fallback"
                    )
                return ChatTurnResponse(
                    dm_response=_death_dm_response,
                    npc_reactions=[],
                    world_changes=[],
                    world_snapshot=_death_ws,
                    npc_positions=None,
                    will_conflict_data=None,
                    journal_entry_id="",
                    traces=[],
                )

            _sheets = self.character_service.list_characters(campaign_id)
            _match = next((s for s in _sheets if s.name == _player_name), None)
            if (
                _match
                and self.avatar_service.load_avatar(campaign_id, _player_name) is None
            ):
                self.avatar_service.migrate_from_characters_json(campaign_id, _match)
                _avatar_state = self.avatar_service.load_state(
                    campaign_id, _player_name
                )
            from app.services.game_loop.phase_6_avatar import avatar_to_prompt

            shared_context.player_state = {
                _player_name: avatar_to_prompt(_avatar_state)
            }

            # ТЗ Presentation v2.0: Инициализация BodyTopology игрока
            from app.services.body.body_topology_service import BodyTopologyService

            _sheet_str = getattr(_match, "stats", {}) if _match else {}  # noqa: ENIGMA002
            _str_score = _sheet_str.get("STR", 10) if isinstance(_sheet_str, dict) else 10

            _persistence = self.scene_manager._persistence  # noqa: ENIGMA002
            _topo_data = _persistence.load_scene(campaign_id) if _persistence else None
            if not _topo_data or not _topo_data.get("player_body_topology"):
                _topo = BodyTopologyService.create_topology("player", strength_score=_str_score)
                _old_inv = _topo_data.get("player_inventory_snapshot", {}) if _topo_data else {}
                if _old_inv:
                    _start_slot = _topo.hands.get("right_hand")
                    if _start_slot:
                        for item_id, qty in _old_inv.items():
                            for _ in range(qty if isinstance(qty, int) else 1):
                                from app.domain.body import Item
                                BodyTopologyService.add_item(_topo, "backpack_main", Item(item_id=item_id, name=item_id))
                _tmp_scene = self.scene_manager.lock_for_tick(campaign_id, location)
                if _tmp_scene:
                    _tmp_scene["player_body_topology"] = BodyTopologyService.serialize(_topo)
                    self.scene_manager.unlock_tick(campaign_id)
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        return None

    def _init_pipeline_context(
        self, actions: list, campaign_id: str, world_id: str, location: str
    ) -> tuple[Any, dict]:
        """Инициализирует shared_context и запускает фоновый world tick."""
        # 0. World tick — асинхронный фон, не блокирует ответ игроку
        world_tick_meta = {"triggered": False, "events": []}
        _task = asyncio.create_task(
            asyncio.to_thread(
                self.world_scheduler.maybe_tick,
                world_id,
                settings.world_tick_minutes,
            )
        )
        # H-35 FIX: Предотвращаем GC задачи и логируем исключения
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = set()
        self._background_tasks.add(_task)

        def _on_task_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception():
                logger.error(f"[GAME_LOOP] Background task maybe_tick failed: {t.exception()}", exc_info=t.exception())

        _task.add_done_callback(_on_task_done)

        # 1. Базовый shared_context
        _raw_mem = self.memory_manager.read_campaign_history(campaign_id, limit=3)
        if _raw_mem:
            logger.warning(
                f"[RECENT_MEM] {len(_raw_mem)} entries, dm_fields={[bool(e.get('dm')) for e in _raw_mem]}"
            )
        shared_context = build_context(
            campaign_id=campaign_id,
            world_id=world_id,
            location=location,
            player=actions[0].player_name if actions else "",
            scene_state={},
            python_engines={},
            recent_memory=[e["dm"] for e in _raw_mem if e.get("dm")],
            reaction_order=[],
            relationship_store=getattr(self, "_rel_store", None), # Phase 8.2
        )
        return shared_context, world_tick_meta

    async def execute(
        self,
        actions: list,
        campaign_id: str,
        world_id: str,
        location: str,
        campaign_state=None,
        is_session_start: bool = False,
        player_position: tuple[float, float] | None = None,
    ) -> _PipelineState:
        """Фазовый пайплайн: DM → NPC → Perception → Social → Rules → Finalize → Commit.

        Каждый блок — отдельный модуль в game_loop/. Подробнее: dm_phase, npc_orchestration.
        """
        # N-02 FIX: time.monotonic() для корректного start_ms во время replay.
        start_ms = time.monotonic() * 1000
        _ctx = _TickContext(mvp_controller=self.mvp_controller)

        shared_context, world_tick_meta = self._init_pipeline_context(
            actions, campaign_id, world_id, location
        )

        # 2. Загрузка аватара игрока
        _death_response = await self._load_player_avatar(
            actions, campaign_id, location, shared_context
        )
        if _death_response is not None:
            return _death_response

        scene_state = self._prepare_and_lock_scene(
            campaign_id, location, shared_context, campaign_state, player_position
        )

        self._sync_shared_context_with_scene(scene_state, shared_context)

        dm_result, _resolution = await self._execute_dm_and_intent_resolution(
            actions, shared_context, scene_state, _ctx, campaign_id, location
        )

        try:
            # ADR-091 FIX: Публикация ПОСЛЕ intent_resolution (иначе _semantic_action=None)
            if dm_result.is_valid:
                publish_classified_player_event(
                    shared_context,
                    location,
                    campaign_id,
                    actions[0].action if actions else "",
                )

            # ФАЗА 3-6: NPC оркестрация → TickPlayerResultDTO (Устав §3)
            _player_result: TickPlayerResultDTO = TickPlayerResultDTO()

            logger.debug(
                f"[ARCHAE-PRE-ORCH] dm_valid={dm_result.is_valid} has_scene_ctx={dm_result.scene_context is not None} hub_event={_ctx.hub_event is not None}"
            )
            if dm_result.is_valid and dm_result.scene_context:
                _player_result = run_npc_orchestration(
                    self._build_npc_orch_deps(),
                    actions,
                    shared_context,
                    scene_state,
                    _ctx,
                    campaign_id,
                    location,
                    is_session_start,
                    tick_orchestrator=self._tick_orch,
                )

            python_engines_result = {
                "dm_result": dm_result,
                "npc_contexts": _player_result.npc_contexts,
            }
        except Exception as e:
            logger.error(f"[GAME_LOOP] DM/NPC phase error: {e}", exc_info=True)
            # H-33 FIX: Не маскируем ошибку пустым DTO, пробрасываем исключение (ADR-O-308)
            raise

        rules_result, npc_result = await self._finalize_pipeline_and_build_dm_frame(
            shared_context, _ctx, campaign_id, actions, _player_result
        )

        _state_observed_facts = getattr(_player_result, "observed_facts", [])  # noqa: ENIGMA002
        return _PipelineState(
            shared_context=shared_context,
            classification_results=[],
            world_tick_meta=world_tick_meta,
            rules_result=rules_result,
            npc_result=npc_result,
            python_engines_result=python_engines_result,
            start_ms=start_ms,
            observed_facts=_state_observed_facts,
        )



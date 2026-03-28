# backend/app/services/action/python_engines.py
"""
PythonEngines — вынесенный полностью _run_python_engines из orchestrator.py
(Шаг 3 рефакторинга по плану)

Отвечает ровно за одно:
- Запуск всех Python-движков ОДНОГО хода (CombatMath + SandboxHandler + LifeEngine + NPC Psychology + S.0 target extraction)
- Python считает → LLM только рассказывает результат
- Единственный источник правды — SceneState
"""

import logging
from typing import Dict, List
from app.services.npc.psyche_engine import apply_stress, get_behavior_hint, recover_stress

from app.models.schemas import ChatTurnRequest
from app.services.action_classifier import ActionType
from app.services.game.sandbox_handler import process_sandbox_action
from app.services.game.combat_math import (
    attack_roll,
    damage_roll,
    build_combat_context,
    ability_modifier,
)
from app.services.npc.reaction_priority import get_reaction_order
from app.services.npc.npc_cognition import (
    process_player_action,
    build_npc_prompt,
    get_inner_thought,
)
from app.services.npc.psyche_engine import get_behavior_hint
from app.services.npc.threat_assessor import (
    assess_threat,
    get_threat_category,
    apply_threat_to_npc,
)
from app.services.npc.perception_engine import (
    assess_status,
    get_status_label,
    get_social_permissions,
)

logger = logging.getLogger(__name__)

# Типы действий, при которых запускается SandboxHandler
_SANDBOX_TYPES = {
    ActionType.SANDBOX_PHYSICAL,
    ActionType.SANDBOX_SOCIAL,
    ActionType.SANDBOX_MILD,
    ActionType.ROMANCE,
    ActionType.CAPTURE,
    ActionType.FLEE,
    ActionType.LIFE_CHOICE,
    ActionType.UNKNOWN,
}


class PythonEngines:
    def __init__(
        self,
        scene_manager,
        life_engine,
        target_extractor,
        character_service,
        layered_memory,
        load_npcs_func,
        save_npcs_func,
        get_npcs_in_location_func,
        get_character_dict_func,
    ):
        """
        Все зависимости передаются из GameOrchestrator.
        Никаких глобальных состояний внутри.
        """
        self.scene_manager = scene_manager
        self.life_engine = life_engine
        self.target_extractor = target_extractor
        self.character_service = character_service
        self.layered_memory = layered_memory

        # NPC-кэш функции (bound methods из orchestrator)
        self._load_npcs = load_npcs_func
        self._save_npcs = save_npcs_func
        self._get_npcs_in_location = get_npcs_in_location_func
        self._get_character_dict = get_character_dict_func

    async def run(
        self,
        req: ChatTurnRequest,
        classification_results: List[dict],
        shared_context: dict,
    ) -> dict:
        """
        Полностью вынесенная логика _run_python_engines.
        После выполнения shared_context мутируется (scene_state, reaction_order, player_target и т.д.).
        Возвращает engines_result, который кладётся в shared_context["python_engines"].
        """
        engines_result: Dict[str, dict] = {}

        for action_item, cls in zip(req.actions, classification_results):
            player_name = action_item.player_name
            action_text = cls["text_preview"]
            act_type_str = cls["type"]

            try:
                act_type = ActionType(act_type_str)
            except ValueError:
                act_type = ActionType.UNKNOWN

            char_dict = self._get_character_dict(req.campaign_id, player_name)

            player_result: dict = {
                "player": player_name,
                "action_type": act_type_str,
                "combat": None,
                "sandbox": None,
            }

            # ─────────────────────────────────────────────────────────────────
            # COMBAT MATH
            # ─────────────────────────────────────────────────────────────────
            if act_type == ActionType.COMBAT:
                try:
                    attacker = {
                        "name": player_name,
                        "level": char_dict.get("level", 1),
                        "strength": char_dict.get("strength", 10),
                        "dexterity": char_dict.get("dexterity", 10),
                        "proficiencies": char_dict.get("proficiencies", []),
                        "equipped_weapon": char_dict.get("equipped_weapon", {
                            "name": "кулак", "damage": "1d4", "type": "melee"
                        }),
                        "conditions": char_dict.get("conditions", []),
                    }
                    npcs_here = self._get_npcs_in_location(req.location)
                    target = npcs_here[0] if npcs_here else {
                        "name": "противник",
                        "ac": 12,
                        "hp": 20,
                        "max_hp": 20,
                    }

                    atk = attack_roll(attacker, target)
                    dmg: dict = {}
                    if atk.hit:
                        weapon_dice = char_dict.get("equipped_weapon", {}).get("damage", "1d4")
                        str_mod = ability_modifier(char_dict.get("strength", 10))
                        dmg = damage_roll(weapon_dice, str_mod, critical=atk.critical)

                    combat_ctx = build_combat_context(
                        attack=atk,
                        target=target,
                        damage=dmg,
                        attacker_name=player_name,
                    )
                    player_result["combat"] = combat_ctx

                    logger.info(
                        f"[PYTHON_ENGINES] COMBAT: {player_name} → "
                        f"roll={atk.roll} hit={atk.hit} crit={atk.critical} "
                        f"dmg={dmg.get('total', 0)}"
                    )
                except Exception as e:
                    logger.error(f"[PYTHON_ENGINES] CombatMath error для '{player_name}': {e}")

            # ─────────────────────────────────────────────────────────────────
            # SANDBOX HANDLER
            # ─────────────────────────────────────────────────────────────────
            elif act_type in _SANDBOX_TYPES:
                try:
                    full_action = getattr(
                        action_item, "action",
                        getattr(action_item, "description", action_text)
                    )

                    sandbox_result = process_sandbox_action(
                        player=char_dict,
                        action_desc=full_action,
                        target=None,
                        enemies=None,
                        location_type=req.location,
                        gold=char_dict.get("gold", 0),
                        scene_state=shared_context.get("scene_state"),
                    )
                    player_result["sandbox"] = sandbox_result.to_dict()

                    scene_changes = getattr(sandbox_result, "scene_changes", [])
                    if scene_changes and shared_context.get("scene_state") is not None:
                        self.scene_manager.apply_changes(
                            req.campaign_id,
                            scene_changes,
                            shared_context["scene_state"],
                        )

                        try:
                            npcs_for_reaction = self._get_npcs_in_location(req.location)
                            reaction_order = get_reaction_order(
                                npcs=npcs_for_reaction,
                                scene_state=shared_context["scene_state"],
                                scene_changes=scene_changes,
                            )
                            shared_context["reaction_order"] = reaction_order

                            if reaction_order:
                                first = reaction_order[0]
                                shared_context["forced_first_speaker"] = first["npc_id"]
                                logger.info(
                                    f"[S.4.2] ReactionPriority: "
                                    f"{[r['npc_name'] + '=' + str(r['score']) for r in reaction_order]}"
                                )
                            else:
                                shared_context["forced_first_speaker"] = None
                        except Exception as e:
                            logger.error(f"[S.4.2] ReactionPriority error: {e}")
                            shared_context["forced_first_speaker"] = None

                    logger.info(
                        f"[PYTHON_ENGINES] SANDBOX: {player_name} → "
                        f"type={sandbox_result.action_type.value} "
                        f"success={sandbox_result.success}"
                    )
                except Exception as e:
                    logger.error(f"[PYTHON_ENGINES] SandboxHandler error для '{player_name}': {e}")

            engines_result[player_name] = player_result

        # ── LifeEngine тик ────────────────────────────────────────────────
        try:
            scene_state_for_life = shared_context.get("scene_state")
            life_changes = self.life_engine.tick(req.campaign_id, scene_state_for_life)
            
            if life_changes and scene_state_for_life is not None:
                applied = self.scene_manager.apply_changes(
                    req.campaign_id,
                    life_changes,
                    scene_state_for_life,
                )
                if applied:
                    self.life_engine.save_npcs(req.campaign_id)
                    # Кэш-инвалидация больше не нужна — всё работает через GameLoop
                    logger.info(
                        f"[PYTHON_ENGINES] LifeEngine: {len(life_changes)} изменений, "
                        f"применено: {applied}"
                    )
                else:
                    logger.warning(
                        f"[PYTHON_ENGINES] LifeEngine: изменения не были применены "
                        f"({len(life_changes)} изменений)"
                    )
        except Exception as e:
            logger.error(f"[PYTHON_ENGINES] LifeEngine error: {e}")

        # ── NPC Psychology блок ───────────────────────────────────────────
        action_type = classification_results[0]["type"] if classification_results else "EXPLORE"

        try:
            recent_entries = self.layered_memory.read_campaign_memory(
                req.campaign_id, limit=2
            )
            recent_session = []
            for entry in recent_entries:
                for action in entry.get("actions", []):
                    recent_session.append(
                        f"{action.get('player_name', '?')}: {action.get('action', '?')}"
                    )
                dm_text = entry.get("dm", "")
                if dm_text:
                    recent_session.append(f"[DM]: {dm_text[:120]}")
            shared_context["recent_session"] = recent_session
        except Exception as e:
            logger.warning(f"[PYTHON_ENGINES] Не удалось загрузить recent_session: {e}")
            shared_context["recent_session"] = []

        player_data = {}
        if req.actions:
            player_name_0 = req.actions[0].player_name
            chars = self.character_service.list_characters(req.campaign_id)
            player_data = next(
                (c.model_dump() for c in chars if c.name == player_name_0), {}
            )

        npcs_in_location = self._get_npcs_in_location(req.location)
        npc_contexts = []

        for npc in npcs_in_location:
            player_markers = player_data.get("visible_markers", [])
            threat_score = assess_threat(
                player_markers, action_type, player_data.get("reputation", {})
            )
            threat_cat = get_threat_category(threat_score)
            apply_threat_to_npc(npc, threat_score, threat_cat)

            status_score = assess_status(player_markers)
            status_label = get_status_label(status_score)
            permissions = get_social_permissions(player_markers, npc)

            action_deltas = process_player_action(npc, action_type, player_data, threat_score)
            behavior_hint = get_behavior_hint(npc)

            npc_system_prompt = build_npc_prompt(
                npc, player_data, shared_context,
                behavior_hint=behavior_hint,
                perceived_status=status_label,
                threat_category=threat_cat,
            )
            inner_thought = get_inner_thought(npc, shared_context)

            npc_contexts.append({
                "npc_id": npc["id"],
                "npc_name": npc["name"],
                "name_forms": npc.get("name_forms", []),
                "tier": npc.get("tier", "minor"),
                "gender": npc.get("gender", ""),
                "description": npc.get("description", ""),
                "threat_score": threat_score,
                "threat_category": threat_cat,
                "perceived_status": status_label,
                "behavior_hint": behavior_hint,
                "system_prompt": npc_system_prompt,
                "inner_thought": inner_thought,
                "permissions": permissions,
                "action_deltas": action_deltas,
            })

        # 3B.3: decay стресса каждый ход (безопасная среда = -5, сон = -15)
        for npc in npcs_in_location:
            recover_stress(npc, ticks_safe=1)
            
        # Сохраняем обновлённые состояния NPC
        if npcs_in_location:
            all_npcs = self._load_npcs()
            for updated_npc in npcs_in_location:
                for i, n in enumerate(all_npcs):
                    if n["id"] == updated_npc["id"]:
                        all_npcs[i] = updated_npc
                        break
            self._save_npcs(all_npcs)

        engines_result["npc_contexts"] = npc_contexts

        # ── S.0: player target extraction ─────────────────────────────────
        try:
            scene_state_for_target = shared_context.get("scene_state")
            if scene_state_for_target is not None and req.actions:
                first_action_text = getattr(
                    req.actions[0], "action",
                    getattr(req.actions[0], "description", "")
                )
                (
                    target_npc_id,
                    target_npc_name,
                    target_object,
                    player_position,
                    player_distances,
                ) = self.target_extractor.extract(
                    first_action_text,
                    npc_contexts,
                    scene_state_for_target,
                )

                logger.info(
                    f"[S.0 DEBUG] action={first_action_text[:40]!r} "
                    f"→ target_npc={target_npc_name!r} "
                    f"prev_target={scene_state_for_target.get('player_target_npc')!r}"
                )

                self.scene_manager.update_player_target(
                    req.campaign_id,
                    scene_state_for_target,
                    target_npc_id=target_npc_id,
                    target_npc_name=target_npc_name,
                    target_object_id=target_object,
                    player_position=player_position,
                    player_distances=player_distances,
                )
                shared_context["scene_state"] = scene_state_for_target
                shared_context["player_target_npc"] = target_npc_id
                shared_context["player_target_name"] = target_npc_name

                logger.info(
                    f"[SCENE S.0] target_npc={target_npc_name!r} "
                    f"target_obj={target_object!r} pos={player_position!r}"
                )
        except Exception as e:
            logger.error(f"[SCENE S.0] player_target_extractor error: {e}")

        return engines_result
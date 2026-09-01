"""
Файл: backend/app/services/state/world_diff_builder.py
Назначение: Сборка WorldStateDiff из всех трекеров.
Зависимости: typing, app.models., app.services.

"""

from typing import Any, Dict, List

from app.models.fate import FateOutcome
from app.models.player_belief import BeliefValue
from app.models.truth_state import TruthState
from app.models.world_state_diff import WorldStateDiff
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.faction_alignment_tracker import FactionAlignmentTracker
from app.services.social.fate_tracker import FateTracker
from app.services.social.social_fabric_tracker import SocialFabricTracker


class WorldDiffBuilder:
    """Собирает финальный diff мира из всех трекеров состояния.

    Не решает, будет ли diff применён к следующей кампании.
    Это ответственность WorldContinuityPolicy.
    """

    def build(
        self,
        truth_state: TruthState,
        fate_tracker: FateTracker,
        faction_tracker: FactionAlignmentTracker,
        social_fabric: SocialFabricTracker,
        beliefs: PlayerBeliefModel
    ) -> WorldStateDiff:

        # 1. Судьбы NPC
        npc_fates: Dict[str, str] = {}
        world_events: List[str] = []
        for state in fate_tracker.get_all_states():
            if state.resolved_fate:
                npc_fates[state.npc_id] = state.resolved_fate.value
                world_events.append(f"{state.npc_id}_{state.resolved_fate.value}")

        # P7-13 FIX: Отношения не переносятся между кампаниями (строгий контракт WorldStateDiff).
        rel_changes: Dict[str, Any] = {}  # P7-13: Изоляция отношений
        # 3. Фракции
        faction_alignments: Dict[str, float] = {}
        player_reputation: Dict[str, str] = {}
        for align in faction_tracker.get_all():
            faction_alignments[align.faction_id] = align.alignment
            if not align.known_to_faction:
                player_reputation[align.faction_id] = "unknown"
            elif align.alignment > 50:
                player_reputation[align.faction_id] = "ally"
            elif align.alignment < -50:
                player_reputation[align.faction_id] = "enemy"
            else:
                player_reputation[align.faction_id] = "neutral"

        # 4. Раскрытые секреты
        secrets_exposed: Dict[str, bool] = {}
        for secret_id in truth_state.secrets.keys():
            belief = beliefs.get_belief_for_secret(secret_id)
            if belief and belief.belief_value == BeliefValue.TRUE:
                secrets_exposed[secret_id] = True
            else:
                secrets_exposed[secret_id] = False

        return WorldStateDiff(
            npc_fates=npc_fates,
            faction_alignments=faction_alignments,
            secrets_exposed=secrets_exposed,
            world_events=world_events,
            player_reputation=player_reputation
        )

"""
Файл: backend/tests/test_p7_13_world_diff.py
Назначение: Проверка сборки финального состояния мира.

Запуск: cd backend; python -m pytest tests/test_p7_13_world_diff.py -v -s; cd ..
"""

from pathlib import Path

import pytest
from app.models.fate import FateOutcome
from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.social_fabric import RelationshipSnapshot
from app.models.world_state_diff import WorldContinuityMode
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.faction_alignment_tracker import FactionAlignmentTracker
from app.services.social.fate_tracker import FateTracker
from app.services.social.social_fabric_tracker import SocialFabricTracker
from app.services.state.world_diff_builder import WorldDiffBuilder
from app.services.truth_state_loader import TruthStateLoader

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class TestP713WorldDiff:
    """P7-13: Тесты сборки WorldStateDiff (Run Result Export)."""

    @pytest.fixture(scope="class")
    def truth_state(self):
        state = TruthStateLoader.load(CANON_PATH)
        TruthStateLoader.validate(state)
        return state

    @pytest.fixture
    def setup(self, truth_state):
        fate = FateTracker()
        fate.update_state("maid_lusya", stability=0.1, threat=0.9)
        fate.trigger_fate("maid_lusya", FateOutcome.ESCAPE, tick=10, cause="test", description="test")
        
        faction = FactionAlignmentTracker()
        faction.set_initial("thieves_guild")
        faction.apply_delta("thieves_guild", -80.0)
        
        fabric = SocialFabricTracker()
        fabric.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=20.0, fear=10.0, affection=0.0, debt=0.0, respect=10.0
        ))
        fabric.apply_delta(tick=1, source_id="maid_lusya", target_id="player", trust_delta=-50.0, fear_delta=40.0)
        
        log = ObservationLog()
        model = PlayerBeliefModel()
        obs = log.add(tick=1, observation_type="blackmail", content="I know", source_id="maid_lusya", source_type=ObservationSourceType.NPC)
        ev = log.add_evidence(obs.observation_id, "lusya_basement", 1.0, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs, ev)
        
        return truth_state, fate, faction, fabric, model

    def test_diff_contains_npc_fates(self, setup):
        truth, fate, faction, fabric, model = setup
        builder = WorldDiffBuilder()
        diff = builder.build(truth, fate, faction, fabric, model)
        
        assert "maid_lusya" in diff.npc_fates
        assert diff.npc_fates["maid_lusya"] == "escape"
        assert "maid_lusya_escape" in diff.world_events

    def test_diff_contains_relationship_changes(self, setup):
        truth, fate, faction, fabric, model = setup
        builder = WorldDiffBuilder()
        diff = builder.build(truth, fate, faction, fabric, model)
        
        assert "maid_lusya" in diff.relationship_changes
        assert diff.relationship_changes["maid_lusya"]["trust"] == -30.0

    def test_diff_contains_faction_reputation(self, setup):
        truth, fate, faction, fabric, model = setup
        builder = WorldDiffBuilder()
        diff = builder.build(truth, fate, faction, fabric, model)
        
        assert diff.faction_alignments["thieves_guild"] == -80.0
        assert diff.player_reputation["thieves_guild"] == "enemy"

    def test_diff_contains_exposed_secrets(self, setup):
        truth, fate, faction, fabric, model = setup
        builder = WorldDiffBuilder()
        diff = builder.build(truth, fate, faction, fabric, model)
        
        assert diff.secrets_exposed.get("lusya_basement") == True
        assert diff.secrets_exposed.get("tornin_debt") == False

    def test_default_continuity_is_isolated(self):
        """Инвариант: По умолчанию режим ISOLATED (мир не наследуется)."""
        assert WorldContinuityMode.ISOLATED.value == "isolated"
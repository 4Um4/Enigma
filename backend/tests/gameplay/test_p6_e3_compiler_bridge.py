# path: /project/backend/tests/gameplay/test_p6_e3_compiler_bridge.py
"""
Файл: backend/tests/gameplay/test_p6_e3_compiler_bridge.py
Назначение: P6/E3 — T6: A/A-паритет discovery структурных action-путей
    (BLACKMAIL / DIALOGUE) компилятора последствий ЧЕРЕЗ DiscoveryBridge.
    Фаза 1 (characterization, ДО миграции): 2/2 GREEN — golden захвачен
    (протокол S255: S2-11/S2-12). Фаза 2 (эта версия): bridge-инъекция;
    golden-ассерты НЕ ИЗМЕНЕНЫ; добавлены ассерты P6-владения.
Зависимости: app.domain.player_epistemics, app.models.player_action,
    app.models.player_epistemic_state, app.services.player_cognition.*,
    app.services.social.social_fabric_tracker, app.services.truth_state_loader
Запуск: python -m pytest backend/tests/gameplay/test_p6_e3_compiler_bridge.py -v
"""

from pathlib import Path

from app.domain.player_epistemics import IDENTIFIED, SurfaceKind
from app.models.player_action import ActionType, PlayerAction
from app.models.player_epistemic_state import PlayerEpistemicState
from app.services.player_cognition.action_consequence_compiler import (
    ActionConsequenceCompiler,
)
from app.services.player_cognition.discovery_bridge import DiscoveryBridge
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.social_fabric_tracker import SocialFabricTracker
from app.services.truth_state_loader import TruthStateLoader

BASE_DIR = Path(__file__).resolve().parents[3]  # корень репозитория
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"


def _fixtures():
    truth = TruthStateLoader.load(CANON_PATH)
    assert truth is not None, "canon не загрузился"
    assert "lusya_basement" in truth.secrets, "canon без lusya_basement"
    state = PlayerEpistemicState()
    bridge = DiscoveryBridge(state, truth)
    log = ObservationLog()
    model = PlayerBeliefModel()
    fabric = SocialFabricTracker()
    compiler = ActionConsequenceCompiler(
        log, model, fabric, truth_state=truth, discovery_bridge=bridge
    )
    return compiler, log, truth, state


def test_t6_blackmail_discovery_via_bridge():
    """BLACKMAIL: golden-паритет (ассерты фазы 1 неизменны) + P6-владение."""
    compiler, log, truth, state = _fixtures()
    compiler.process_action(
        PlayerAction(
            action_id="t6_blackmail",
            tick=1,
            actor_id="player",
            action_type=ActionType.BLACKMAIL,
            target_id="maid_lusya",
            secret_id="lusya_basement",
            description="Я знаю про подвал",
        )
    )
    # ── golden (фаза 1): A/A — исход тот же, путь через Bridge ──
    assert truth.discovered_secrets == {"lusya_basement"}
    links = log.get_evidence_for_secret("lusya_basement")
    assert len(links) == 1
    assert links[0].evidence_strength == 1.0
    # ── P6-владение (фаза 2): уровень/observation в PlayerEpistemicState ──
    assert state.level("lusya_basement") == IDENTIFIED
    assert len(state.observations) == 1
    assert state.observations[0].surface_kind == SurfaceKind.DM_NARRATIVE
    assert state.observations[0].source_id == "maid_lusya"


def test_t6_dialogue_discovery_via_bridge():
    """DIALOGUE с secret_id: golden-паритет + P6-владение (контур 2)."""
    compiler, log, truth, state = _fixtures()
    compiler.process_action(
        PlayerAction(
            action_id="t6_dialogue",
            tick=2,
            actor_id="player",
            action_type=ActionType.DIALOGUE,
            target_id="maid_lusya",
            secret_id="lusya_basement",
            description="Разговор про подвал",
        )
    )
    assert truth.discovered_secrets == {"lusya_basement"}
    links = log.get_evidence_for_secret("lusya_basement")
    assert len(links) == 1
    assert links[0].evidence_strength == 0.5
    assert state.level("lusya_basement") == IDENTIFIED
    assert len(state.observations) == 1

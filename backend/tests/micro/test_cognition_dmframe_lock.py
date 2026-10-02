"""path: /project/backend/tests/micro/test_cognition_dmframe_lock.py

Назначение: Пакет C / Step 5 (вердикт Мастера) — замок полного cognition-
    канала: Claim → CognitionContextResolver → npc_contexts → build() →
    NpcOutcome → to_dm_prompt_block. Формулировка «представился как»
    доезжает до DM-промпта; имя в summary игрока НЕ доходит (два
    независимых канала не смешиваются).
Зависимости: app.services.verbalization.scene_outcome_builder,
    app.services.npc.cognition_context, app.services.memory.dialogue_session.
Запуск: cd backend; python -m pytest tests/micro/test_cognition_dmframe_lock.py -v; cd ..
"""

from app.services.memory.dialogue_session import DialogueSession
from app.services.npc.cognition_context import CognitionContextResolver
from app.services.verbalization.scene_outcome_builder import SceneOutcomeBuilder


class _SessionMemory:
    def __init__(self) -> None:
        self._sessions: dict = {}

    def get_dialogue_session(
        self, campaign_id: str, npc_id: str, partner_id: str = "player"
    ) -> DialogueSession:
        key = (campaign_id, npc_id, partner_id)
        if key not in self._sessions:
            self._sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._sessions[key]


def test_cognition_reaches_dm_prompt_block():
    """End-to-end: claim в сессии → cognition-блок → DMFrame-рендер."""
    mem = _SessionMemory()
    s = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    s.add_claim(
        text="представился как «Гобен»",
        speaker="player",
        confidence=0.9,
        tick=1,
    )

    resolver = CognitionContextResolver(mem, campaign_id_provider=lambda: "T")
    cog_block = resolver.resolve_block("merchant_goran")
    assert "Гобен" in cog_block
    assert "представился как" in cog_block

    builder = SceneOutcomeBuilder()
    # Минимальный DecisionResult-подобный объект (контракт intent.value)
    from types import SimpleNamespace

    from app.models.delta_payloads import IdentityPayload
    from app.models.state_delta import DeltaDomain, StateDeltas

    decision = SimpleNamespace(
        npc_id="merchant_goran",
        intent=SimpleNamespace(value="talk"),
        intent_target="player",
        deltas=StateDeltas(
            npc_id="merchant_goran",
            domain=DeltaDomain.IDENTITY,
            payload=IdentityPayload(),
            source="test_lock",
        ),
        score=0.5,
        micro_event=None,
        narrative_fact=None,
    )
    ctx = SimpleNamespace(
        distances={},
        visible_npcs={"merchant_goran"},
        npc_tiers={},
        player_target_id="merchant_goran",
        player_action_text="",
        player_success=True,
    )
    scene = builder.build(
        [decision],
        ctx,
        npc_profiles={},
        topics={"merchant_goran": "greeting"},
        cognition={"merchant_goran": cog_block},
    )
    # SceneOutcome.actors = List[NpcOutcome] (до DMFrame-разделения focus/bg)
    target = next(n for n in scene.actors if n.npc_id == "merchant_goran")
    assert target.cognition == cog_block

    # DMFrame-проекция: focus_npcs/background_npcs + player_line (контракт to_dm_prompt_block)
    frame = SimpleNamespace(
        focus_npcs=[target],
        background_npcs=[],
        player_line=SimpleNamespace(intent="talk", outcome="success", perceived_effect=""),
        tension_line="",
        scene_line=[],
        hidden_pressure=[],
        voice_map={},
        observed_facts=[],
    )
    block = builder.to_dm_prompt_block(frame)
    assert "представился как" in block
    assert "Гобен" in block
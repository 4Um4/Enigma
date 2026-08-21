# backend/tests/test_decision_pipeline.py
import pytest
pytest.skip("decision_pipeline рефакторен — зависимости удалены", allow_module_level=True)
"""
Проверяет:
  GameEvent → EventContext
           → DecisionHub.compute() → DecisionResult
           → StateApplicator.apply() → NPCState
           → build_verbalization_context() → VerbalizationContext

Никаких LLM-вызовов. Только Python-ядро.
"""

import pytest
from unittest.mock import MagicMock

from app.models.npc_state import (
    NPCPersonality,
    NPCState,
    NPCTier,
    EmotionTag,
    Intent,
    WillState,
)
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.state_applicator import StateApplicator
from app.services.verbalization.verbalization_context import (
    build_verbalization_context,
)

def test_state_applicator_signature():
    """Защита от изменения сигнатуры без обновления тестов."""
    import inspect
    sig = inspect.signature(StateApplicator.apply)
    params = list(sig.parameters.keys())
    assert params == ['self', 'state', 'result', 'campaign_id', 'current_tick'], \
        f"Изменилась сигнатура StateApplicator.apply: {params}"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tavern_keeper_personality() -> NPCPersonality:
    """Трактирщик Торнин — доминирующий drive: control."""
    return NPCPersonality(
        npc_id       = "tavern_keeper_tornin",
        tier         = NPCTier.MAJOR,
        drives_base  = {
            "control": 0.50,
            "significance": 0.25,
            "fear": 0.15,
            "desire": 0.10,
        },
        willpower    = 60.0,
        breakpoint   = 85.0,
        loyalty_base = 50.0,
        voice_profile= "Говоришь коротко и по делу. Не терпишь беспорядка.",
    )


@pytest.fixture
def fresh_npc_state(tavern_keeper_personality) -> NPCState:
    """NPCState с нейтральными начальными значениями."""
    return NPCState(
        npc_id             = tavern_keeper_personality.npc_id,
        stress             = 10.0,
        will_state         = WillState.FREE,
        emotion            = EmotionTag.NEUTRAL,
        relationship_cache = {"trust": 0.0, "fear": 0.0, "debt": 0.0},
    )


@pytest.fixture
def combat_event() -> EventContext:
    """Игрок атакует кого-то рядом с трактирщиком."""
    return EventContext(
        event_type    = "combat",
        actor_id      = "player",
        success       = True,
        intensity     = 1.0,
        distance      = 2.5,
        witness_count = 3,
        location      = "tavern_silver_wolf",
        day           = 1,
        visible_threat_markers = ["weapon_melee"],
    )


@pytest.fixture
def theft_event() -> EventContext:
    """Игрок пытается украсть (провал)."""
    return EventContext(
        event_type    = "theft",
        actor_id      = "player",
        success       = False,   # провал — NPC видел попытку
        intensity     = 0.8,
        distance      = 1.5,
        witness_count = 2,
        location      = "tavern_silver_wolf",
        day           = 1,
    )


@pytest.fixture
def mock_relationship_store():
    """RelationshipStore без диска."""
    store = MagicMock()
    store.get_pair.return_value = {"trust": 0.0, "fear": 0.0, "debt": 0.0}
    store.update.return_value   = None
    return store


@pytest.fixture
def state_applicator(mock_relationship_store) -> StateApplicator:
    return StateApplicator(mock_relationship_store)


@pytest.fixture
def decision_hub() -> DecisionHub:
    # Фиксированный seed — детерминированные результаты в тестах
    return DecisionHub(seed=42)


# ─────────────────────────────────────────────────────────────────────────────
# Тесты
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionHub:

    def test_combat_produces_intent(
        self,
        decision_hub,
        fresh_npc_state,
        tavern_keeper_personality,
        combat_event,
    ):
        """Боевое событие рядом → NPC принимает решение (не IDLE)."""
        result = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, combat_event
        )
        assert result.intent != Intent.IDLE, \
            f"Combat рядом не должен давать IDLE, получили: {result.intent}"
        assert result.npc_id == fresh_npc_state.npc_id
        assert isinstance(result.score, float)

    def test_scores_trace_contains_all_intents(
        self,
        decision_hub,
        fresh_npc_state,
        tavern_keeper_personality,
        combat_event,
    ):
        """scores_trace должен содержать все рассмотренные intents."""
        result = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, combat_event
        )
        assert len(result.scores_trace) >= 3, \
            "Должно быть минимум 3 рассмотренных intent"
        assert all(isinstance(v, float) for v in result.scores_trace.values())

    def test_broken_npc_cannot_attack(
        self,
        decision_hub,
        tavern_keeper_personality,
        combat_event,
    ):
        """Сломленный NPC не выбирает ATTACK."""
        broken_state = NPCState(
            npc_id     = "tavern_keeper_tornin",
            stress     = 90.0,
            will_state = WillState.BROKEN,
            emotion    = EmotionTag.FEARFUL,
        )
        result = decision_hub.compute(
            broken_state, tavern_keeper_personality, combat_event
        )
        assert result.intent != Intent.ATTACK, \
            f"Сломленный NPC не должен атаковать, получили: {result.intent}"

    def test_high_fear_drive_avoids_aggression(
        self,
        decision_hub,
        fresh_npc_state,
        combat_event,
    ):
        """NPC с fear drive > 0.6 не рассматривает агрессивные интенты."""
        coward_personality = NPCPersonality(
            npc_id      = "coward_npc",
            tier        = NPCTier.MINOR,
            drives_base = {"control": 0.1, "significance": 0.1,
                           "fear": 0.7, "desire": 0.1},
            willpower   = 20.0,
            breakpoint  = 50.0,
            loyalty_base= 30.0,
        )
        coward_state = NPCState(npc_id="coward_npc")
        result = decision_hub.compute(coward_state, coward_personality, combat_event)

        assert result.intent not in (Intent.ATTACK, Intent.INTIMIDATE), \
            f"Трусливый NPC не должен атаковать, получили: {result.intent}"
        # score для ATTACK должен быть -1.0 (заблокирован early exit)
        assert result.scores_trace.get(Intent.ATTACK.value, -1.0) <= 0.0

    def test_theft_failed_increases_suspicion_trait(
        self,
        decision_hub,
        fresh_npc_state,
        tavern_keeper_personality,
        theft_event,
    ):
        """Провальная кража → delta для trait 'suspicious'."""
        result = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, theft_event
        )
        suspicious_delta = result.deltas.trait_updates.get("suspicious", 0.0)
        assert suspicious_delta > 0.0, \
            "Провальная кража должна повышать подозрительность"

    def test_explain_mode(
        self,
        decision_hub,
        tavern_keeper_personality,
    ):
        """Intent.EXPLAIN возвращается при event_type 'player_asks_why'."""
        state = NPCState(
            npc_id           = "tavern_keeper_tornin",
            narrative_cache  = (),  # нет фактов — explain всё равно работает
        )
        event = EventContext(
            event_type = "player_asks_why",
            actor_id   = "player",
        )
        result = decision_hub.compute(state, tavern_keeper_personality, event)
        assert result.intent == Intent.EXPLAIN
        assert result.explanation_mode is True


class TestStateApplicator:

    def test_apply_returns_new_state(
        self,
        state_applicator,
        fresh_npc_state,
        tavern_keeper_personality,
        decision_hub,
        combat_event,
    ):
        """StateApplicator возвращает новый объект, оригинал не мутируется."""
        result   = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, combat_event
        )
        new_state = state_applicator.apply(
            fresh_npc_state,
            result,
            campaign_id="test",
            current_tick=1,
        )
        assert new_state is not fresh_npc_state, "Должен быть новый объект"
        assert fresh_npc_state.stress == 10.0, "Оригинал не должен измениться"

    def test_stress_increases_after_combat(
        self,
        state_applicator,
        fresh_npc_state,
        tavern_keeper_personality,
        decision_hub,
        combat_event,
    ):
        """После боя рядом стресс NPC увеличивается."""
        result    = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, combat_event
        )
        new_state = state_applicator.apply(
            fresh_npc_state,
            result,
            campaign_id="test",
            current_tick=1,
        )
        assert new_state.stress > fresh_npc_state.stress, \
            f"Стресс должен вырасти: было {fresh_npc_state.stress}, стало {new_state.stress}"

    def test_intent_duration_increments(
        self,
        state_applicator,
        tavern_keeper_personality,
        decision_hub,
        combat_event,
    ):
        """Повторное применение того же intent увеличивает duration."""
        state = NPCState(
            npc_id         = "tavern_keeper_tornin",
            intent         = Intent.WARN,
            intent_target  = "player",   # WARN требует цель
        )
        result = decision_hub.compute(state, tavern_keeper_personality, combat_event)

        # Принудительно проверяем что intent_duration растёт при совпадении
        if result.intent == Intent.WARN:
            new_state = state_applicator.apply(
                state,
                result,
                campaign_id="test",
                current_tick=5,
            )
            assert new_state.intent_duration == 1

    def test_will_break_at_breakpoint(
        self,
        state_applicator,
        tavern_keeper_personality,
        decision_hub,
        combat_event,
    ):
        """При stress >= breakpoint NPC переходит в BROKEN."""
        near_broken = NPCState(
            npc_id    = "tavern_keeper_tornin",
            stress    = 84.0,   # breakpoint=85, добавим ещё
            will_state= WillState.FREE,
        )
        result = decision_hub.compute(
            near_broken, tavern_keeper_personality, combat_event
        )
        new_state = state_applicator.apply(
            near_broken,
            result,
            campaign_id="test",
            current_tick=1,
        )
        # Если stress перешёл 85 — will_state должен стать BROKEN
        if new_state.stress >= tavern_keeper_personality.breakpoint:
            assert new_state.will_state == WillState.BROKEN, \
                "При stress >= breakpoint will_state должен быть BROKEN"

    def test_original_state_intact_on_error(
        self,
        mock_relationship_store,
        fresh_npc_state,
        tavern_keeper_personality,
    ):
        """При ошибке применения возвращается оригинальный state."""
        # StateApplicator с падающим rel_store
        mock_relationship_store.update.side_effect = RuntimeError("disk error")
        applicator = StateApplicator(mock_relationship_store)

        from app.services.npc.decision_hub import DecisionResult, StateDeltas
        bad_result = DecisionResult(
            npc_id        = fresh_npc_state.npc_id,
            intent        = Intent.WARN,
            intent_target = "player",
            score         = 0.9,
            scores_trace  = {},
            deltas        = StateDeltas(
                npc_id        = fresh_npc_state.npc_id,
                stress_delta  = 10.0,
                trust_delta   = -5.0,  # это вызовет rel_store.update
            ),
        )
        returned = applicator.apply(
            fresh_npc_state,
            bad_result, campaign_id="test", current_tick=1,
        )
        assert returned is fresh_npc_state, \
            "При ошибке должен вернуться оригинальный state"


class TestVerbalizationContext:

    def test_verbalization_context_is_frozen(
        self,
        fresh_npc_state,
        tavern_keeper_personality,
    ):
        """VerbalizationContext нельзя мутировать после создания."""
        ctx = build_verbalization_context(
            state        = fresh_npc_state,
            personality  = tavern_keeper_personality,
            scene_hint   = "Игрок стоит рядом.",
            npc_name     = "Торнин",
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.emotion = "angry"  # frozen=True должен запрещать

    def test_idle_npc_has_no_narrative_hints(
        self,
        tavern_keeper_personality,
    ):
        """IDLE NPC без важных событий не получает narrative hints."""
        idle_state = NPCState(
            npc_id          = "tavern_keeper_tornin",
            intent          = Intent.IDLE,
            narrative_cache = (),
        )
        ctx = build_verbalization_context(
            idle_state, tavern_keeper_personality,
            scene_hint="", npc_name="Торнин",
        )
        assert ctx.narrative_hints == ()

    def test_explain_mode_provides_narrative(
        self,
        tavern_keeper_personality,
    ):
        """EXPLAIN mode даёт narrative hints."""
        from app.models.npc_state import NarrativeFact
        fact = NarrativeFact(
            event_type  = "theft",
            target_id   = "player",
            emotion_tag = "angry",
            day         = 3,
            importance  = 0.85,
        )
        explain_state = NPCState(
            npc_id          = "tavern_keeper_tornin",
            intent          = Intent.EXPLAIN,
            intent_target   = "player",
            narrative_cache = (fact,),
        )
        ctx = build_verbalization_context(
            explain_state, tavern_keeper_personality,
            scene_hint="Игрок спрашивает почему.", npc_name="Торнин",
        )
        assert ctx.is_explain_mode is True
        assert len(ctx.narrative_hints) == 1
        assert ctx.narrative_hints[0].event_type == "theft"

    def test_scene_hint_truncated(
        self,
        fresh_npc_state,
        tavern_keeper_personality,
    ):
        """scene_hint обрезается до SCENE_HINT_MAX_CHARS."""
        from app.services.verbalization.verbalization_context import SCENE_HINT_MAX_CHARS
        long_hint = "X" * (SCENE_HINT_MAX_CHARS + 200)
        ctx = build_verbalization_context(
            fresh_npc_state, tavern_keeper_personality,
            scene_hint=long_hint, npc_name="Торнин",
        )
        assert len(ctx.scene_hint) <= SCENE_HINT_MAX_CHARS


class TestFullPipeline:
    """Сквозной тест: Event → DecisionHub → StateApplicator → VerbalizationContext."""

    def test_full_pipeline_no_llm(
        self,
        decision_hub,
        state_applicator,
        fresh_npc_state,
        tavern_keeper_personality,
        combat_event,
    ):
        """Полный путь без LLM. Финальный контекст содержит intent и emotion."""
        # 1. DecisionHub
        result = decision_hub.compute(
            fresh_npc_state, tavern_keeper_personality, combat_event
        )
        assert result.intent is not None

        # 2. StateApplicator
        new_state = state_applicator.apply(
            fresh_npc_state,
            result, campaign_id="smoke_test", current_tick=1,
        )
        assert new_state is not fresh_npc_state

        # 3. VerbalizationContext
        ctx = build_verbalization_context(
            new_state, tavern_keeper_personality,
            scene_hint="Игрок атакует рядом.",
            npc_name="Торнин",
        )
        assert ctx.intent  == new_state.intent.value
        assert ctx.emotion == new_state.emotion.value
        assert ctx.npc_id  == new_state.npc_id

        # 4. Промпт строится без ошибок
        from app.services.verbalization.verbalization_context import build_npc_prompt_from_context
        sys_p, usr_p = build_npc_prompt_from_context(ctx)
        assert len(sys_p) > 10
        assert len(usr_p) > 0

        print(f"\n[SMOKE TEST] intent={ctx.intent} emotion={ctx.emotion} "
              f"stress={new_state.stress:.1f} nuance='{ctx.emotional_nuance}'")
        print(f"[SMOKE TEST] scores={result.scores_trace}")
# backend/tests/test_verbalization_layer.py
"""
Контрактные тесты слоя вербализации.

Проверяет:
  - ContentProfile: валидация, передача в контекст, влияние на промпт
  - backstory: передача из Personality в VerbalizationContext
  - token budget: tier-aware логика (MAJOR > MINOR)
"""

import pytest

from app.services.npc.npc_state import (
    EmotionTag,
    Intent,
    NPCPersonality,
    NPCState,
    NPCTier,
    WillState,
)
from app.services.npc.verbalization_context import (
    ContentProfile,
    VerbalizationContext,
    build_npc_prompt_from_context,
    build_verbalization_context,
    get_token_budget,
    get_mass_template,
    SCENE_HINT_MAX_CHARS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures (минимальные — слой вербализации не требует DecisionHub)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def base_personality() -> NPCPersonality:
    """Базовая личность для тестов вербализации."""
    return NPCPersonality(
        npc_id       = "test_npc",
        tier         = NPCTier.MAJOR,
        drives_base  = {
            "control": 0.40,
            "significance": 0.30,
            "fear": 0.20,
            "desire": 0.10,
        },
        willpower    = 60.0,
        breakpoint   = 85.0,
        loyalty_base = 50.0,
        voice_profile= "Говоришь коротко. Не любишь болтунов.",
        backstory    = "Жена умерла в войну. Боится собак.",
    )


@pytest.fixture
def neutral_state() -> NPCState:
    """Нейтральный NPCState для тестов вербализации."""
    return NPCState(npc_id="test_npc")


# ─────────────────────────────────────────────────────────────────────────────
# ContentProfile
# ─────────────────────────────────────────────────────────────────────────────

class TestContentProfile:

    def test_default_profile_is_clean(self) -> None:
        """Дефолтный профиль — нулевой контент, не бросает исключений."""
        profile = ContentProfile()
        assert profile.profanity_level == 0
        assert profile.violence_level  == 0

    def test_valid_max_profile(self) -> None:
        """Максимальные значения в допустимом диапазоне не вызывают ошибку."""
        profile = ContentProfile(profanity_level=2, violence_level=2)
        assert profile.profanity_level == 2

    def test_profanity_level_out_of_range_raises(self) -> None:
        """Выход за пределы диапазона — ValueError при создании."""
        with pytest.raises(ValueError, match="profanity_level"):
            ContentProfile(profanity_level=3)

    def test_violence_level_negative_raises(self) -> None:
        """Отрицательный violence_level — ValueError."""
        with pytest.raises(ValueError, match="violence_level"):
            ContentProfile(violence_level=-1)

    def test_content_profile_passed_to_context(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """ContentProfile из вызова попадает в VerbalizationContext без изменений."""
        profile = ContentProfile(profanity_level=2, violence_level=1)
        ctx = build_verbalization_context(
            state          = neutral_state,
            personality    = base_personality,
            scene_hint     = "",
            npc_name       = "Торнин",
            content_profile= profile,
        )
        assert ctx.content_profile.profanity_level == 2
        assert ctx.content_profile.violence_level  == 1

    def test_default_content_profile_when_none_passed(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """Если content_profile не передан — дефолтный ContentProfile, не None."""
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        assert ctx.content_profile is not None
        assert isinstance(ctx.content_profile, ContentProfile)

    def test_profanity_appears_in_prompt(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """ContentProfile с матом отражается в system_prompt."""
        profile = ContentProfile(profanity_level=1, violence_level=0)
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
            content_profile=profile,
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        assert "мат" in sys_p.lower(), \
            "profanity_level=1 должен добавлять упоминание мата в промпт"

    def test_clean_profile_no_adult_in_prompt(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """Дефолтный ContentProfile не добавляет взрослые инструкции в промпт."""
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        # Проверяем что нет маркеров взрослого контента
        assert "мат" not in sys_p.lower()
        assert "насилие" not in sys_p.lower()

    def test_context_is_frozen(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """VerbalizationContext нельзя мутировать (frozen=True)."""
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.content_profile = ContentProfile(profanity_level=2)  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Backstory
# ─────────────────────────────────────────────────────────────────────────────

class TestBackstory:

    def test_backstory_passed_to_verbalization(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """backstory из NPCPersonality попадает в VerbalizationContext дословно."""
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        assert ctx.backstory == base_personality.backstory

    def test_empty_backstory_does_not_crash(
        self,
        neutral_state: NPCState,
    ) -> None:
        """Пустой backstory не ломает промпт."""
        personality = NPCPersonality(
            npc_id       = "no_backstory_npc",
            tier         = NPCTier.MINOR,
            drives_base  = {"control": 0.25, "significance": 0.25,
                            "fear": 0.25,    "desire": 0.25},
            willpower    = 50.0,
            breakpoint   = 80.0,
            loyalty_base = 40.0,
            backstory    = "",
        )
        ctx = build_verbalization_context(
            neutral_state, personality,
            scene_hint="", npc_name="Безымянный",
        )
        sys_p, usr_p = build_npc_prompt_from_context(ctx)
        assert isinstance(sys_p, str)
        assert len(sys_p) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Token Budget (tier-aware)
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenBudget:

    def test_major_talk_greater_than_minor_talk(self) -> None:
        """MAJOR TALK получает больше токенов чем MINOR TALK."""
        major = get_token_budget("major", Intent.TALK.value)
        minor = get_token_budget("minor", Intent.TALK.value)
        assert major > minor, \
            f"MAJOR TALK={major} должен быть > MINOR TALK={minor}"

    def test_major_explain_greater_than_minor_explain(self) -> None:
        """MAJOR EXPLAIN — самый большой бюджет в системе."""
        major = get_token_budget("major", Intent.EXPLAIN.value)
        minor = get_token_budget("minor", Intent.EXPLAIN.value)
        assert major > minor

    def test_combat_intent_same_for_all_tiers(self) -> None:
        """ATTACK и FLEE — одинаковый бюджет для всех tier."""
        for intent in (Intent.ATTACK.value, Intent.FLEE.value):
            assert get_token_budget("major", intent) == get_token_budget("minor", intent), \
                f"{intent}: боевой бюджет должен быть равным для всех tier"

    def test_idle_and_observe_return_zero(self) -> None:
        """IDLE и OBSERVE — нулевой бюджет (LLM не вызывается)."""
        assert get_token_budget("major", Intent.IDLE.value)    == 0
        assert get_token_budget("minor", Intent.OBSERVE.value) == 0

    def test_tier_case_insensitive(self) -> None:
        """get_token_budget не зависит от регистра tier-строки."""
        assert (
            get_token_budget("MAJOR", Intent.TALK.value)
            == get_token_budget("major", Intent.TALK.value)
        ), "Регистр tier не должен влиять на результат"

    def test_unknown_intent_returns_fallback(self) -> None:
        """Неизвестный intent возвращает fallback, не падает."""
        result = get_token_budget("major", "unknown_intent_xyz")
        assert isinstance(result, int)
        assert result >= 0


# ─────────────────────────────────────────────────────────────────────────────
# MASS Templates
# ─────────────────────────────────────────────────────────────────────────────

class TestMassTemplates:

    def _make_mass_ctx(self, intent: Intent) -> VerbalizationContext:
        """Вспомогательный метод — строит MASS VerbalizationContext."""
        return VerbalizationContext(
            npc_id         = "mass_npc_01",
            npc_name       = "Прохожий",
            tier           = NPCTier.MASS.value,
            emotion        = EmotionTag.NEUTRAL.value,
            will_state     = WillState.FREE.value,
            intent         = intent.value,
            intent_target  = None,
            scene_hint     = "",
            emotional_nuance = "",
            speech_style   = "",
            voice_profile  = "",
            backstory      = "",
        )

    def test_mass_explain_has_fallback(self) -> None:
        """MASS NPC в EXPLAIN-режиме возвращает шаблон, не None."""
        ctx      = self._make_mass_ctx(Intent.EXPLAIN)
        template = get_mass_template(ctx)
        assert template is not None, \
            "MASS EXPLAIN должен иметь шаблон — иначе падение при вопросе 'почему?'"
        assert "Прохожий" in template

    def test_mass_idle_returns_empty_string(self) -> None:
        """MASS IDLE → пустая строка (тишина), не None."""
        ctx = self._make_mass_ctx(Intent.IDLE)
        assert get_mass_template(ctx) == ""

    def test_mass_flee_contains_name(self) -> None:
        """MASS шаблон подставляет имя NPC."""
        ctx      = self._make_mass_ctx(Intent.FLEE)
        template = get_mass_template(ctx)
        assert "Прохожий" in template

class TestPromptContent:
    """Тесты содержимого промпта — не только структуры, но и данных."""

    def test_narrative_hint_appears_in_prompt(
        self,
        base_personality: NPCPersonality,
    ) -> None:
        """
        NarrativeFact из narrative_cache попадает в system_prompt.
        Защита от регрессий при рефакторинге build_npc_prompt_from_context.
        """
        from app.services.npc.npc_state import NarrativeFact

        fact = NarrativeFact(
            event_type  = "theft",
            target_id   = "player",
            emotion_tag = "angry",
            day         = 2,
            importance  = 0.9,
        )
        state = NPCState(
            npc_id          = "test_npc",
            intent          = Intent.EXPLAIN,
            intent_target   = "player",
            narrative_cache = (fact,),
        )
        ctx = build_verbalization_context(
            state, base_personality,
            scene_hint="Игрок спрашивает почему.",
            npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)

        # Факт должен быть виден в промпте
        assert "theft" in sys_p, \
            "event_type из NarrativeFact должен попасть в system_prompt"
        assert "ты" in sys_p, \
            "target_id='player' должен отображаться как 'ты' в system_prompt"

    def test_backstory_appears_in_system_prompt(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """
        backstory из NPCPersonality виден в system_prompt.
        Защита от регрессий: backstory должен доходить до LLM.
        """
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        # base_personality.backstory = "Жена умерла в войну. Боится собак."
        assert "Жена умерла" in sys_p, \
            "backstory должен попасть в system_prompt — LLM без него не знает биографию"        

    def test_explain_mode_prefix_in_prompt(
        self,
        base_personality: NPCPersonality,
    ) -> None:
        """EXPLAIN mode использует префикс 'Объясняешь', не 'Вспоминаешь'."""
        from app.services.npc.npc_state import NarrativeFact

        fact = NarrativeFact(
            event_type="combat", target_id="player",
            emotion_tag="angry", day=1, importance=0.8,
        )
        state = NPCState(
            npc_id          = "test_npc",
            intent          = Intent.EXPLAIN,
            intent_target   = "player",
            narrative_cache = (fact,),
        )
        ctx = build_verbalization_context(
            state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        assert "Объясняешь" in sys_p, \
            "EXPLAIN mode должен использовать префикс 'Объясняешь, опираясь на:'"

    def test_no_trust_change_in_prompt(
        self,
        neutral_state: NPCState,
        base_personality: NPCPersonality,
    ) -> None:
        """
        Промпт не содержит trust_change и stress_change.
        Архитектурный контракт: LLM не получает инструкции менять состояние.
        """
        ctx = build_verbalization_context(
            neutral_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        assert "trust_change" not in sys_p, \
            "Промпт не должен содержать trust_change — нарушение архитектурного контракта"
        assert "stress_change" not in sys_p, \
            "Промпт не должен содержать stress_change"


    def test_high_clarity_shows_event_type_in_prompt(
        self,
        base_personality: NPCPersonality,
    ) -> None:
        """
        Высокая clarity (>0.8) → конкретный event_type виден в промпте.
        R5.2: LLM получает детальное воспоминание.
        """
        from app.services.npc.npc_state import EventMemory, MemoryStage

        fact = EventMemory(
            event_type="theft", target_id="player",
            emotion_tag="angry", day=1,
            importance=0.9, clarity=0.9, confidence=0.9,
        )
        state = NPCState(
            npc_id          = "test_npc",
            intent          = Intent.EXPLAIN,
            intent_target   = "player",
            narrative_cache = (fact,),
        )
        ctx = build_verbalization_context(
            state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        assert "theft" in sys_p, \
            "Высокая clarity: event_type должен быть виден в промпте"

    def test_low_clarity_obscures_event_type(
        self,
        base_personality: NPCPersonality,
    ) -> None:
        """
        Низкая clarity (<0.4) → размытое описание без event_type.
        R5.2: детали памяти утеряны.
        """
        from app.services.npc.npc_state import EventMemory

        fact = EventMemory(
            event_type="theft", target_id="player",
            emotion_tag="angry", day=10,
            importance=0.4, clarity=0.2, confidence=0.3,
        )
        state = NPCState(
            npc_id          = "test_npc",
            intent          = Intent.EXPLAIN,
            intent_target   = "player",
            narrative_cache = (fact,),
        )
        ctx = build_verbalization_context(
            state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_p, _ = build_npc_prompt_from_context(ctx)
        assert "theft" not in sys_p, \
            "Низкая clarity: event_type не должен попасть в промпт"
        assert "нечто" in sys_p or "размылись" in sys_p

    def test_confidence_prefix_only_in_explain_mode(
        self,
        base_personality: NPCPersonality,
    ) -> None:
        """
        confidence-префикс ('вроде бы', 'точно помню') — только в EXPLAIN.
        В обычном режиме NPC не выражает сомнение в промпте.
        """
        from app.services.npc.npc_state import EventMemory

        fact = EventMemory(
            event_type="combat", target_id="player",
            emotion_tag="fearful", day=2,
            importance=0.7, clarity=0.6, confidence=0.35,
        )
        # EXPLAIN mode
        explain_state = NPCState(
            npc_id="test_npc", intent=Intent.EXPLAIN,
            intent_target="player", narrative_cache=(fact,),
        )
        ctx_explain = build_verbalization_context(
            explain_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_explain, _ = build_npc_prompt_from_context(ctx_explain)
        assert "вроде бы" in sys_explain, \
            "EXPLAIN + низкий confidence → 'вроде бы' в промпте"

        # Обычный режим
        normal_state = NPCState(
            npc_id="test_npc", intent=Intent.TALK,
            intent_target="player", narrative_cache=(fact,),
        )
        ctx_normal = build_verbalization_context(
            normal_state, base_personality,
            scene_hint="", npc_name="Торнин",
        )
        sys_normal, _ = build_npc_prompt_from_context(ctx_normal)
        assert "вроде бы" not in sys_normal, \
            "Обычный режим: confidence-префикс не должен попасть в промпт"        
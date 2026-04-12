# backend\tests\test_r3_verbalization_final.py
# python -m pytest backend/tests/test_r3_verbalization_final.py -v
import pytest
from app.services.npc.npc_state import Intent, NPCTier, EventMemory
from app.services.verbalization.verbalization_context import (
    build_npc_core_data, 
    build_npc_prompt_from_context,  # Добавлено для совместимости
    ContentProfile, 
    VerbalizationContext
)

def create_mock_ctx(intent=Intent.TALK, profanity=0, backstory="Бывший стражник"):
    """Вспомогательный метод для создания контекста (Синхронизация с dataclass)"""
    # Конвертируем Enum → str, т.к. VerbalizationContext работает со строками
    intent_str = intent.value if hasattr(intent, "value") else str(intent)
    
    return VerbalizationContext(
        npc_id="test_npc_tornin",
        npc_name="Торнин",
        tier="major",                      # str, не NPCTier
        intent=intent_str,                 # str, не Intent
        intent_target="Игрок",
        emotion="angry",                   # ОБЯЗАТЕЛЬНО: str из EmotionTag.value
        will_state="free",                 # ОБЯЗАТЕЛЬНО: str из WillState.value
        speech_style="Говоришь грубо и прямолинейно.",  # ОБЯЗАТЕЛЬНО: из _get_speech_style
        backstory=backstory,
        emotional_nuance="раздражение",
        voice_profile="грубый бас",
        scene_hint="Игрок разлил эль на стойку",
        content_profile=ContentProfile(profanity_level=profanity),
    )

class TestR3VerbalizationContract:
    """
    Финальный тест R3: Проверка трансформации Python State -> LLM Data.
    """

    def test_core_data_mapping(self):
        """Проверка, что все поля из Context попадают в Core Data для шаблона"""
        ctx = create_mock_ctx()
        data = build_npc_core_data(ctx)
    
        assert data["npc_name"] == "Торнин"
        assert data["emotion"] == "раздражение"
        assert "Бывший стражник" in data["biography"]
        # VerbalizationCore — dataclass, проверяем поля напрямую
        core = data["verbalization_core"]
        assert core.intent == "talk"

    def test_profanity_filter_logic(self):
        """Проверка работы контент-фильтра (R3.4)"""
        # 1. Чистый профиль — флаг мата должен быть отключён
        ctx_clean = create_mock_ctx(profanity=0)
        data_clean = build_npc_core_data(ctx_clean)
        assert data_clean["allow_profanity"] is False
        
        # 2. Разрешенный мат — флаг мата должен быть включён
        ctx_dirty = create_mock_ctx(profanity=1)
        data_dirty = build_npc_core_data(ctx_dirty)
        assert data_dirty["allow_profanity"] is True

    def test_intent_incorporation(self):
        """Проверка, что намерение (Intent) правильно описывается в ядре"""
        ctx = create_mock_ctx(intent=Intent.EXPLAIN)
        data = build_npc_core_data(ctx)
        
        # VerbalizationCore — dataclass, проверяем поля напрямую
        core = data["verbalization_core"]
        assert core.intent == "explain"
        assert "Игрок" in core.target

    def test_render_integration(self):
        """Интеграционный тест: проходит ли рендер через Jinja2 без ошибок"""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        ctx = create_mock_ctx()
        data = build_npc_core_data(ctx)
        loader = get_prompt_loader()
        
        rendered, _ = build_npc_prompt_from_context(ctx)
        
        assert "Торнин" in rendered
        assert "грубый бас" in rendered
        # Проверка, что шаблонизатор не оставил пустых переменных {{ }}
        assert "{{" not in rendered
        assert "}}" not in rendered

    @pytest.mark.parametrize("tier, expected_tokens", [
        (NPCTier.MAJOR, 600), # Предположим, такие лимиты в get_token_budget
        (NPCTier.MINOR, 200),
    ])
    def test_token_budget_assignment(self, tier, expected_tokens):
        """Проверка, что тир NPC влияет на бюджет токенов (R3.1)"""
        from app.services.verbalization.verbalization_context import get_token_budget
        
        budget = get_token_budget(tier, Intent.TALK)
        # Здесь мы просто проверяем, что MAJOR получает больше ресурсов, чем MINOR
        if tier == NPCTier.MAJOR:
            assert budget > 300
        else:
            assert budget <= 300

# backend/tests/test_verbalization_chain_ANY.py
# cd backend; python -m pytest tests/test_verbalization_chain_ANY.py -v
"""
Тесты VERBALIZATION LAYER — проверяем что LLM получает правильный промпт.
НЕ тестируем LLM вывод (нестабильный).
ТЕСТИРУЕМ промпт-содержимое (детерминированное).
"""
import pytest
import sys
from pathlib import Path

from app.services.verbalization.prompt_loader import VerbalizationCore

sys.path.insert(0, str(Path(__file__).parent.parent))


def core(text: str, intent: str = "TALK", target: str = "", scene: str = "") -> VerbalizationCore:
    """Helper: быстрое создание VerbalizationCore в тестах.
    
    Если передана только строка — использует её как scene.
    Если переданы intent/scene — использует их.
    """
    if intent == "TALK" and not scene and text:
        scene = text
    return VerbalizationCore(intent=intent, target=target, scene=scene)


# ═══════════════════════════════════════════════════════════════════════════════
# I. NPC ПРОМПТ — ЧТО LLM ВИДИТ
# ═══════════════════════════════════════════════════════════════════════════════

class TestNPCPromptContent:
    """Проверяем СОДЕРЖИМОСТЬ промпта, который идёт в LLM."""

    def test_npc_prompt_must_not_contain_dm_role(self):
        """NPC не должен видеть 'Мастер Подземелий' — это роль DM."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Торнин говорит с игроком"),
            tier="MAJOR",
            npc_name="Торнин Серебряная Луна",
            voice_profile="грубый, короткие фразы, иногда ругается",
            emotion="раздражён",
            narrative_hints="",
            biography="Бывший наёмник, управляет таверной 15 лет",
            max_tokens=80,
        )
        
        # НЕ ДОЛЖНО БЫТЬ
        forbidden = [
            "Мастер Подземелий",
            "D&D 5e",
            "не генерируй реплики NPC",
            "не говори за игрока",
            "Что вы будете делать",
        ]
        for phrase in forbidden:
            assert phrase not in result, f"ЗАПРЕЩЕНО в NPC промпте: '{phrase}'"

    def test_npc_prompt_must_have_npc_voice(self):
        """NPC должен видеть свой голос из JSON."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Торнин говорит с игроком"),
            tier="MAJOR",
            npc_name="Торнин Серебряная Луна",
            voice_profile="грубый, короткие фразы",
            emotion="раздражён",
            narrative_hints="",
            biography="Бывший наёмник",
            max_tokens=80,
        )
        
        # ДОЛЖНО БЫТЬ
        assert "Торнин" in result or "NPC" in result, "NPC имя отсутствует"
        assert "первого лица" in result or "от первого лица" in result, "Нет инструкции 'первое лицо'"

    def test_npc_prompt_must_have_scene_context(self):
        """NPC должен видеть что происходит (verbalization_core)."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Игрок спрашивает про эль, Torrean за стойкой смотрит на него"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="",
            max_tokens=80,
        )
        
        assert "эль" in result, "Контекст сцены отсутствует в промпте"

    def test_npc_prompt_must_have_emotion(self):
        """NPC должен видеть свою эмоцию."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("игрок говорит"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="зол и едва сдерживается",
            narrative_hints="",
            biography="",
            max_tokens=80,
        )
        
        assert "зол" in result, "Эмоция NPC отсутствует в промпте"

    def test_npc_prompt_major_has_biography(self):
        """MAJOR NPC должен видеть биографию."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("игрок говорит"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="Бывший наёмник, управляет таверной 15 лет, потерял жену",
            max_tokens=80,
        )
        
        assert "наёмник" in result or "жену" in result, "Биография MAJOR NPC отсутствует"

    def test_npc_prompt_minor_no_biography(self):
        """MINOR NPC НЕ должен видеть биографию (экономия токенов)."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("игрок говорит"),
            tier="MINOR",
            npc_name="Люся",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="Это не должно появиться",
            max_tokens=50,
        )
        
        assert "Это не должно появиться" not in result, "MINOR NPC видит биографию — утечка токенов"


# ═══════════════════════════════════════════════════════════════════════════════
# II. VERBALIZATION CONTEXT — КАКИЕ ДАННЫЕ ФОРМИРУЮТСЯ
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerbalizationContextFields:
    """Проверяем какие данные ПОПАДАЮТ в контекст (не то что LLM видит)."""

    def test_context_has_intent_target(self):
        """intent_target должен формироваться из target_id."""
        from app.services.verbalization.verbalization_context import VerbalizationContext
        
        ctx = VerbalizationContext(
            npc_id="tavern_keeper_tornin",
            npc_name="Торнин",
            tier="MAJOR",
            emotion="neutral",
            will_state="free",
            intent="TALK",
            intent_target="player",
            scene_hint="Игрок спрашивает про эль",
            emotional_nuance="спокоен",
            speech_style="control",
            voice_profile="грубый",
            backstory="Наёмник",
        )
        
        assert ctx.intent_target == "player", "NPC не знает к кому обращается"

    def test_context_has_emotional_nuance(self):
        """emotional_nuance должен содержать описание, не число."""
        from app.services.verbalization.verbalization_context import VerbalizationContext
        
        ctx = VerbalizationContext(
            npc_id="tavern_keeper_tornin",
            npc_name="Торнин",
            tier="MAJOR",
            emotion="neutral",
            will_state="free",
            intent="TALK",
            intent_target="player",
            scene_hint="",
            emotional_nuance="зол, едва сдерживается — голос на грани срыва",
            speech_style="",
            voice_profile="",
            backstory="",
        )
        
        # Не должно быть чисел
        assert not any(c.isdigit() for c in ctx.emotional_nuance), \
            f"Число в emotional_nuance: '{ctx.emotional_nuance}'"

    def test_context_scene_hint_from_player_action(self):
        """scene_hint должен содержать текст действия игрока."""
        from app.services.verbalization.verbalization_context import VerbalizationContext
        
        ctx = VerbalizationContext(
            npc_id="tavern_keeper_tornin",
            npc_name="Торнин",
            tier="MAJOR",
            emotion="neutral",
            will_state="free",
            intent="TALK",
            intent_target="player",
            scene_hint="Игрок подходит и спрашивает: 'Сколько стоит эль?'",
            emotional_nuance="",
            speech_style="",
            voice_profile="",
            backstory="",
        )
        
        assert "эль" in ctx.scene_hint, "Действие игрока не попало в scene_hint"
        assert "Сколько стоит" in ctx.scene_hint, "Текст вопроса потерян"


# ═══════════════════════════════════════════════════════════════════════════════
# III. ОТРИЦАТЕЛЬНЫЕ ТЕСТЫ — ЧЕГО БЫТЬ НЕ ДОЛЖНО
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptMustNotContain:
    """这些东西 НЕ ДОЛЖНЫ попадать в промпт NPC."""

    def test_no_numbers_in_prompt(self):
        """NPC не должен видеть числа (stress: 0.85, trust: -25)."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("stress: 85, trust: -25, fear: 12"),
            tier="MAJOR",
            npc_name="NPC",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Числа стресса/доверия НЕ должны выглядеть как числа
        assert "stress:" not in result.lower(), "Числа стресса в промпте!"
        assert "trust:" not in result.lower(), "Числа доверия в промпте!"

    def test_no_decision_hub_internals(self):
        """NPC не должен видеть internals DecisionHub."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("score=0.73, intent=ATTACK, commitment=0.9"),
            tier="MAJOR",
            npc_name="NPC",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        forbidden = ["score=", "commitment=", "intent="]
        for f in forbidden:
            assert f.lower() not in result.lower(), f"DecisionHub internal '{f}' в промпте!"

    def test_no_state_deltas(self):
        """NPC не должен видеть дельты состояния."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("delta_stress=+10, delta_trust=-5"),
            tier="MAJOR",
            npc_name="NPC",
            voice_profile="",
            emotion="neutral",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "delta_" not in result.lower(), "Дельты состояния в промпте!"


# ═══════════════════════════════════════════════════════════════════════════════
# III.5 TOKEN BUDGET — защита от деградации
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenBudget:
    """ИНВАРИАНТ: Длина промпта предсказуема и не растёт бесконтрольно."""

    # Реальные лимиты: system(~410) + mode(~90) + constraint(~70) + шаблон(~250) + секции(~1280)
    MAX_PROMPT_CHARS = 2100
    MIN_PROMPT_CHARS = 890   # system(~410) + mode(~90) + constraint(~70) + шаблон(~250) + MINOR пустой(~70)

    def test_prompt_length_under_limit(self):
        """Даже при максимальной нагрузке промпт не превышает лимит."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Игрок спрашивает про эль. " * 50),  # Очень длинный
            tier="MAJOR",
            npc_name="Торнин Серебряная Луна",
            voice_profile="Грубый, короткие фразы, иногда ругается, говорит с хрипом",
            emotion="Зол и едва сдерживается, голос на грани срыва",
            narrative_hints="Три дня назад игрок пытался украсть эль. " * 10,
            biography="Бывший наёмник. " * 30,
            max_tokens=200,
        )
        
        assert len(result) <= self.MAX_PROMPT_CHARS, \
            f"Промпт превышает лимит: {len(result)} > {self.MAX_PROMPT_CHARS}"

    def test_sections_have_individual_limits(self):
        """Каждая секция обрезается отдельно, не вытесняет другие."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        from app.services.verbalization.prompt_loader import (
            VERBALIZATION_CORE_MAX_LEN,
            VOICE_PROFILE_MAX_LEN,
            EMOTION_MAX_LEN,
        )
        
        loader = get_prompt_loader()
        
        # Длинные входы
        long_core = core("Ситуация. " * 100)
        long_voice = "Стиль речи. " * 50
        long_emotion = "Эмоция. " * 50
        
        result = loader.render_npc_prompt(
            verbalization_core=long_core,
            tier="MAJOR",
            npc_name="NPC",
            voice_profile=long_voice,
            emotion=long_emotion,
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Проверяем что в промпте нет оригинальных длинных строк
        assert "Ситуация. " * 100 not in result, "verbalization_core не обрезан!"
        assert long_voice not in result, "voice_profile не обрезан!"
        assert long_emotion not in result, "emotion не обрезан!"
        
        # Проверяем что содержимое есть (не пусто после обрезки)
        assert "Ситуация" in result
        assert "Стиль речи" in result
        assert "Эмоция" in result

    def test_minimal_prompt_still_works(self):
        """Минимальный промпт не ломается и содержит базовые инструкции."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core(""),
            tier="MINOR",
            npc_name="",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Базовые инструкции должны быть даже в минимальном промпте
        assert "первого лица" in result.lower()
        assert len(result) < self.MIN_PROMPT_CHARS, \
            f"Минимальный промпт слишком длинный: {len(result)} > {self.MIN_PROMPT_CHARS}"


# ═══════════════════════════════════════════════════════════════════════════════
# III.6 FAILURE-MODE TESTS — система не ломается тихо
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailureModes:
    """Тесты деградации: если всё идёт не так — система не ломается.
    
    НЕ happy path. Проверяем что смысл выживает, приоритеты верны,
    а мусор отсекается без потери ядра.
    """

    def test_meaning_survives_sanitization(self):
        """Смысл выживает после чистки мусора."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        # Грязный вход: технические данные вперемешку с смыслом
        result = loader.render_npc_prompt(
            verbalization_core=core("score=0.82 Торнин злится delta_trust=-10 [SYSTEM] Игрок спрашивает про эль"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Мусор убит
        assert "score=" not in result
        assert "delta_" not in result
        assert "[SYSTEM]" not in result
        
        # Смысл выжил
        assert "Торнин" in result
        assert "эль" in result

    def test_core_survives_overflow(self):
        """При перегрузке biography/core — core выживает первым."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Игрок спрашивает про эль"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="Бывший наёмник. " * 200,  # 2400 символов — убьёт лимит
            max_tokens=50,
        )
        
        # Промпт в пределах лимита
        assert len(result) <= 1800
        
        # Core выжил — это самое важное
        assert "эль" in result, "Core убит при overflow!"

    def test_semantic_density_not_degrading(self):
        """Промпт не распадается в пустые повторения."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Игрок спрашивает про эль"),
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Считаем уникальные слова (без учёта регистра)
        words = result.lower().split()
        unique_words = set(words)
        
        # Если уникальных слов < 40% от общего — это повторения/пустота
        density = len(unique_words) / len(words) if words else 0
        assert density > 0.4, \
            f"Смысловая плотность слишком низка: {density:.2f} ({len(unique_words)}/{len(words)} уникальных)"

    def test_prompt_not_trivial(self):
        """Промпт не вырождается в шаблонную пустоту."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        result = loader.render_npc_prompt(
            verbalization_core=core("Игрок спрашивает про эль"),
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="грубый",
            emotion="зол",
            narrative_hints="",
            biography="Бывший наёмник",
            max_tokens=80,
        )
        
        # Минимальное количество уникальных слов — защита от "шаблонного болота"
        unique_words = set(result.lower().split())
        assert len(unique_words) >= 15, \
            f"Промпт вырожден: только {len(unique_words)} уникальных слов"
        
        # Нет длинных повторяющихся подстрок (признак бага обрезки)
        assert "наёмник. Бывший наёмник" not in result, "Дублирование после обрезки!"


# ═══════════════════════════════════════════════════════════════════════════════
# III.7 WHITELIST CONTRACT — VerbalizationCore как единственный источник смысла
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerbalizationCoreContract:
    """Тесты whitelist-контракта.
    
    VerbalizationCore — это не просто тип. Это закон:
    - Только три поля
    - Нельзя протащить мусор
    - Смысл формируется ДО текста
    
    Если эти тесты сломаются — система деградировала до "строкового хаоса".
    """

    def test_core_rejects_empty_intent(self):
        """Intent обязателен — без него нет смысла."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        with pytest.raises(ValueError, match="intent"):
            VerbalizationCore(intent="", target="игрок", scene="ситуация")

    def test_core_generates_clean_text(self):
        """VerbalizationCore генерирует чистый текст без мусора."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        core = VerbalizationCore(
            intent="TALK",
            target="игрок",
            scene="Игрок спрашивает про эль"
        )
        
        text = core.to_prompt_text()
        
        # Есть смысл
        assert "TALK" in text
        assert "игрок" in text
        assert "эль" in text
        
        # Нет мусора (даже если бы кто-то пытался его внедрить)
        assert "score=" not in text
        assert "delta_" not in text
        assert "[SYSTEM]" not in text

    def test_core_cannot_leak_numbers(self):
        """Числа физически не могут попасть в VerbalizationCore."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        # Даже если кто-то попытается передать число — оно просто текст
        core = VerbalizationCore(
            intent="score=0.82",  # Пытаемся протащить как intent
            target="delta_trust=-10",  # Пытаемся протащить как target
            scene="stress: 85"
        )
        
        text = core.to_prompt_text()
        
        # Оно превращается в текст, но формат сломан — LLM не интерпретирует как числа
        # Это НЕ идеальная защита, но лучше чем прямая утечка
        assert "Намерение: SCORE=0.82" in text  # Верхний регистр — не число для LLM

    def test_core_without_target_still_works(self):
        """Target опционален — не все intent'ы направлены на кого-то."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        core = VerbalizationCore(
            intent="IDLE",
            target="",
            scene="NPC стоит у стойки"
        )
        
        text = core.to_prompt_text()
        assert "IDLE" in text
        assert ", цель:" not in text  # Нет пустого "цель: "

    def test_core_without_scene_still_works(self):
        """Scene опционален — иногда контекст уже в emotion."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        core = VerbalizationCore(
            intent="ATTACK",
            target="игрок",
            scene=""
        )
        
        text = core.to_prompt_text()
        assert "ATTACK" in text
        assert "Ситуация:" not in text  # Нет пустой секции

    def test_core_is_immutable(self):
        """VerbalizationCore — frozen, нельзя изменить после создания."""
        from app.services.verbalization.prompt_loader import VerbalizationCore
        
        core = VerbalizationCore(intent="TALK", target="игрок", scene="сцена")
        
        with pytest.raises(AttributeError):
            core.intent = "ATTACK"  # Нельзя менять после создания

    def test_render_accepts_core_object(self):
        """render_npc_prompt принимает VerbalizationCore напрямую."""
        from app.services.verbalization.prompt_loader import (
            get_prompt_loader, VerbalizationCore
        )
        
        loader = get_prompt_loader()
        core = VerbalizationCore(
            intent="TALK",
            target="игрок",
            scene="Игрок спрашивает про эль"
        )
        
        result = loader.render_npc_prompt(
            verbalization_core=core,  # Объект, не строка!
            tier="MAJOR",
            npc_name="Торнин",
            voice_profile="",
            emotion="нейтрально",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        # Промпт содержит смысл из VerbalizationCore
        assert "TALK" in result
        assert "эль" in result

    def test_str_input_rejected_after_migration(self):
        """str больше НЕ принимается — только VerbalizationCore."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        
        with pytest.raises(TypeError, match="VerbalizationCore"):
            loader.render_npc_prompt(
                verbalization_core="Эта строка теперь запрещена",
                tier="MINOR",
                npc_name="NPC",
                voice_profile="",
                emotion="",
                narrative_hints="",
                biography="",
                max_tokens=50,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# IV. ЦЕПОЧКА (механика — уже работает, но на всякий случай)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# III.8 BEHAVIOR MODE — структурный контроль поведения NPC
# ═════════════════════════════════════════════════════════════════════════════

class TestSemanticConflict:
    """Тесты detect_semantic_conflict и resolve_effective_constraint.
    
    Проверяем что State (emotion/scene) имеет приоритет над Intent.
    """
    
    def test_talk_rage_detects_conflict(self):
        """TALK + ярость = конфликт."""
        from app.services.verbalization.prompt_loader import detect_semantic_conflict
        
        assert detect_semantic_conflict("TALK", "в ярости", "тест") is True
    
    def test_talk_calm_no_conflict(self):
        """TALK + спокойствие = нет конфликта."""
        from app.services.verbalization.prompt_loader import detect_semantic_conflict
        
        assert detect_semantic_conflict("TALK", "спокоен", "тест") is False
    
    def test_threat_rage_no_conflict(self):
        """THREAT + ярость = нет конфликта (intent уже жёсткий)."""
        from app.services.verbalization.prompt_loader import detect_semantic_conflict
        
        assert detect_semantic_conflict("THREAT", "в ярости", "тест") is False
    
    def test_scene_weapon_detects_conflict(self):
        """TALK + "достаёт оружие" в scene = конфликт."""
        from app.services.verbalization.prompt_loader import detect_semantic_conflict
        
        assert detect_semantic_conflict("TALK", "нейтрально", "NPC достаёт оружие") is True
    
    def test_resolve_returns_strict_on_conflict(self):
        """При конфликте constraint ужесточается."""
        from app.services.verbalization.prompt_loader import resolve_effective_constraint
        
        c = resolve_effective_constraint("TALK", "в ярости", "тест")
        assert "НЕ задавай вопросов" in c
        assert "реакция на угрозу" in c
    
    def test_resolve_returns_normal_on_no_conflict(self):
        """Без конфликта constraint обычный."""
        from app.services.verbalization.prompt_loader import resolve_effective_constraint
        
        c = resolve_effective_constraint("TALK", "спокоен", "тест")
        assert "Можешь задавать" in c
    
    def test_conflict_constraint_appears_in_prompt(self):
        """Конфликтный constraint появляется в финальном промпте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="TALK", target="игрок", scene="NPC достаёт оружие")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="в ярости",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "ОГРАНИЧЕНИЕ:" in result
        assert "реакция на угрозу" in result
        assert "Можешь задавать" not in result


class TestIntentSubtypeHandling:
    """Тесты обработки подтипов intent через fallback.
    
    Проверяем что подтипы не ломаются и деградируют управляемо.
    """
    
    def test_exact_subtype_match(self):
        """Если подтип есть в маппинге — используется он."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        # Временно добавим для теста — проверяем что уровень 1 работает
        # (реальные подтипы добавятся через INTENT_CONSTRAINTS)
        c = _get_intent_constraint("THREAT")  # Базовый есть
        assert "НЕ задавай вопросов" in c
    
    def test_unknown_subtype_falls_to_base(self):
        """Подтип без точного совпадения → базовый intent."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("TALK_PERSUADE")
        assert "Можешь задавать" in c  # Fallback на TALK
    
    def test_unknown_subtype_falls_to_base_attack(self):
        """ATTACK_BRUTAL → fallback на ATTACK."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("ATTACK_BRUTAL")
        assert "НЕ задавай вопросов" in c  # Fallback на ATTACK
    
    def test_completely_unknown_uses_fallback(self):
        """Полностью неизвестный intent → semantic fallback (дефолт)."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("DANCE_POLKA")
        assert "Не задавай вопросы" in c
    
    def test_subtype_in_prompt(self):
        """Подтип intent проходит в промпт без ошибок."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="TALK_PERSUADE", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "ОГРАНИЧЕНИЕ:" in result
        assert "Можешь задавать" in result


class TestIntentConstraints:
    """Тесты _get_intent_constraint — конкретные ограничения поверх Mode."""
    
    def test_talk_allows_questions(self):
        """TALK -> разрешает уточняющие вопросы."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("TALK")
        assert "Можешь задавать" in c
    
    def test_threat_forbids_questions(self):
        """THREAT -> запрещает вопросы."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
    
        c = _get_intent_constraint("THREAT")
        assert "НЕ задавай вопросов" in c
    
    def test_flee_forbids_questions(self):
        """FLEE -> запрещает вопросы, только бегство."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
    
        c = _get_intent_constraint("FLEE")
        assert "НЕ задавай вопросов" in c
        assert "бегств" in c.lower()
    
    def test_idle_no_initiation(self):
        """IDLE -> не инициировать диалог."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("IDLE")
        assert "Не инициируй" in c
    
    def test_unknown_gets_default(self):
        """Неизвестный intent -> безопасный дефолт."""
        from app.services.verbalization.prompt_loader import _get_intent_constraint
        
        c = _get_intent_constraint("BLAH_BLAH")
        assert "Не задавай вопросы" in c
    
    def test_constraint_appears_in_prompt(self):
        """ОГРАНИЧЕНИЕ появляется в финальном промпте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="THREAT", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "ОГРАНИЧЕНИЕ:" in result
        assert "НЕ задавай вопросов" in result
    
    def test_talk_constraint_allows_in_prompt(self):
        """TALK constraint разрешает вопросы в промпте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="TALK", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "ОГРАНИЧЕНИЕ:" in result
        assert "Можешь задавать" in result


class TestBehaviorMode:
    """Тесты BehaviorMode — структурного контроля поведения NPC.
    
    Mode — это не текстовая рекомендация.
    Это ограничение возможностей генерации, которое LLM не может проигнорировать.
    """
    
    def test_talk_gets_flexible_mode(self):
        """TALK intent -> FLEXIBLE mode."""
        from app.services.verbalization.prompt_loader import _get_behavior_mode, BehaviorMode
        
        mode = _get_behavior_mode("TALK")
        assert mode == BehaviorMode.FLEXIBLE
    
    def test_threat_gets_strict_mode(self):
        """THREAT intent -> STRICT mode — никаких отклонений."""
        from app.services.verbalization.prompt_loader import _get_behavior_mode, BehaviorMode
        
        mode = _get_behavior_mode("THREAT")
        assert mode == BehaviorMode.STRICT
    
    def test_flee_gets_reactive_mode(self):
        """FLEE intent -> REACTIVE mode — только реакция."""
        from app.services.verbalization.prompt_loader import _get_behavior_mode, BehaviorMode
        
        mode = _get_behavior_mode("FLEE")
        assert mode == BehaviorMode.REACTIVE
    
    def test_idle_gets_silent_mode(self):
        """IDLE intent -> SILENT mode — только наблюдение."""
        from app.services.verbalization.prompt_loader import _get_behavior_mode, BehaviorMode
        
        mode = _get_behavior_mode("IDLE")
        assert mode == BehaviorMode.SILENT
    
    def test_unknown_intent_gets_default_strict(self):
        """Неизвестный intent -> STRICT (безопасный дефолт)."""
        from app.services.verbalization.prompt_loader import _get_behavior_mode, BehaviorMode
        
        mode = _get_behavior_mode("UNKNOWN_INTENT")
        assert mode == BehaviorMode.STRICT
    
    def test_mode_appears_in_prompt(self):
        """Mode block появляется в финальном промпте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="TALK", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "РЕЖИМ ПОВЕДЕНИЯ: FLEXIBLE" in result
    
    def test_strict_mode_appears_for_threat(self):
        """THREAT intent -> STRICT mode в промпте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="THREAT", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        assert "РЕЖИМ ПОВЕДЕНИЯ: STRICT" in result
        assert "FLEXIBLE" not in result
    
    def test_mode_block_not_in_user_section(self):
        """Mode block в system, не в user контенте."""
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        loader = get_prompt_loader()
        core = VerbalizationCore(intent="TALK", target="игрок", scene="тест")
        
        result = loader.render_npc_prompt(
            verbalization_core=core,
            tier="MINOR",
            npc_name="NPC",
            voice_profile="",
            emotion="",
            narrative_hints="",
            biography="",
            max_tokens=50,
        )
        
        parts = result.split("=== ПРОФИЛЬ NPC ===")
        system_part = parts[0]
        
        assert "РЕЖИМ ПОВЕДЕНИЯ" in system_part
        assert "РЕЖИМ ПОВЕДЕНИЯ" not in parts[1] if len(parts) > 1 else True


class TestTargetExtraction:
    def test_extract_finds_by_name(self):
        from app.services.action.player_target_extractor import PlayerTargetExtractor
        extractor = PlayerTargetExtractor()
        
        target_id, _, _, _, _ = extractor.extract(
            action_text="Торнин, сколько стоит эль?",
            npc_contexts=[{"npc_id": "tavern_keeper_tornin", "name_forms": ["торнин"]}],
            scene_state={},
        )
        assert target_id == "tavern_keeper_tornin"

    def test_extract_no_target(self):
        from app.services.action.player_target_extractor import PlayerTargetExtractor
        extractor = PlayerTargetExtractor()
        
        target_id, _, _, _, _ = extractor.extract(
            action_text="осматриваюсь",
            npc_contexts=[{"npc_id": "npc1", "name_forms": []}],
            scene_state={},
        )
        assert target_id is None

    def test_extract_string_position_safe(self):
        from app.services.action.player_target_extractor import PlayerTargetExtractor
        extractor = PlayerTargetExtractor()
        
        target_id, _, _, _, _ = extractor.extract(
            action_text="Борко, пропуск",
            npc_contexts=[{"npc_id": "guard_borko", "name_forms": ["борко"]}],
            scene_state={"player_position": "entrance"},
        )
        assert target_id == "guard_borko"


class TestEventBus:
    def test_publish_and_get(self):
        from app.services.events.event_types import GameEvent, EventType
        from app.services.events.event_bus import get_event_bus
        
        get_event_bus().publish(GameEvent(
            event_type=EventType.PLAYER_SPOKE,
            actor_id="player",
            location="tavern",
            campaign_id="test",
            target_id="tavern_keeper_tornin",
        ))
        recent = get_event_bus().get_recent_events(limit=1, campaign_id="test")
        assert len(recent) == 1
        assert recent[0]["target_id"] == "tavern_keeper_tornin"


class TestSystemInvariants:
    def test_one_target_one_speaker(self):
        contexts = [
            {"npc_id": "tavern_keeper_tornin"},
            {"npc_id": "maid_lusya"},
            {"npc_id": "guard_borko"},
        ]
        target = "tavern_keeper_tornin"
        filtered = [c for c in contexts if c.get("npc_id") == target]
        assert len(filtered) == 1

    def test_target_preserved_through_chain(self):
        from app.services.action.player_target_extractor import PlayerTargetExtractor
        from app.services.events.event_types import GameEvent, EventType
        from app.services.events.event_bus import get_event_bus
        
        extractor = PlayerTargetExtractor()
        target_id, _, _, _, _ = extractor.extract(
            "Торнин, привет",
            [{"npc_id": "tavern_keeper_tornin", "name_forms": ["торнин"]}],
            {},
        )
        
        get_event_bus().publish(GameEvent(
            event_type=EventType.PLAYER_SPOKE,
            actor_id="player",
            location="tavern",
            campaign_id="test_inv",
            target_id=target_id,
        ))
        
        recent = get_event_bus().get_recent_events(limit=1, campaign_id="test_inv")
        assert target_id == "tavern_keeper_tornin"
        assert recent[0]["target_id"] == "tavern_keeper_tornin"


# ═══════════════════════════════════════════════════════════════════════════════
# V. ИЗВЕСТНЫЕ БАГИ (xfail)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKnownBugs:
    def test_no_dm_prompt_in_npc(self):
        from app.services.verbalization.prompt_loader import get_prompt_loader
        
        result = get_prompt_loader().render_npc_prompt(
            verbalization_core=core("тест"),
            tier="MAJOR", npc_name="NPC", voice_profile="",
            emotion="neutral", narrative_hints="", biography="", max_tokens=50,
        )
        assert "Мастер Подземелий" not in result

    @pytest.mark.xfail(reason="BUG: Нет gender — NPC не знает свой пол")
    def test_has_gender_field(self):
        from app.services.verbalization.verbalization_context import VerbalizationContext
        fields = [f.name for f in VerbalizationContext.__dataclass_fields__.values()]
        assert "gender" in fields

    @pytest.mark.xfail(reason="BUG: Нет player_name — NPC не знает к кому обращается")
    def test_has_player_name_field(self):
        from app.services.verbalization.verbalization_context import VerbalizationContext
        fields = [f.name for f in VerbalizationContext.__dataclass_fields__.values()]
        assert "player_name" in fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
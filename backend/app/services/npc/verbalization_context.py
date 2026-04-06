# backend/app/services/npc/verbalization_context.py
"""
R3.1/R3.2 — VerbalizationContext: единственное что LLM получает об NPC.

Принципы:
  - Python генерирует ВСЮ фактуру (эмоция, нюанс, факты)
  - LLM только оживляет текстом — не принимает решений
  - scene_hint — факт из Python-данных, не текст игрока
  - emotional_nuance — сгенерировано из чисел NPCState
  - 1 narrative fact всегда (если важное), 2 только при EXPLAIN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple, Union

from app.services.npc.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    NPCPersonality,
    NPCState,
    WillState,
    EventMemory,      
    MemoryStage,      
)


SCENE_HINT_MAX_CHARS: int = 500   # ~125 токенов


@dataclass(frozen=True)
class ContentProfile:
    """
    Профиль разрешённого контента для вербализации NPC.
    Используется вместо простого adult_content: bool.
    sexual контент намеренно НЕ включаем — во избежание нежелательных генераций.
    """
    profanity_level: int = 0   # 0 = чистая речь, 1 = лёгкий мат, 2 = жёсткий мат
    violence_level:  int = 0   # 0 = нет, 1 = упоминание, 2 = детальное описание
    # sexual_level Идея разделить секс и физиологию  откладываем до после R4

    def __post_init__(self) -> None:
        # Защита от невалидных конфигов кампании на этапе загрузки
        if not (0 <= self.profanity_level <= 2):
            raise ValueError(f"profanity_level должен быть 0–2, получено: {self.profanity_level}")
        if not (0 <= self.violence_level <= 2):
            raise ValueError(f"violence_level должен быть 0–2, получено: {self.violence_level}")

@dataclass(frozen=True)    
class VerbalizationContext:
    """
    То что LLM получает для генерации речи NPC.
    Вся фактура сгенерирована Python из чисел.

    LLM НЕ получает: числа, историю, working_memory как текст, reasoning.
    LLM получает: кто, каким голосом, в каком состоянии, что хочет сделать.
    """
    npc_id:    str
    npc_name:  str
    tier:      str     # NPCTier.value — для tier-aware verbalization

    # Состояние — только качественные описания
    emotion:    str
    will_state: str
    intent:     str
    intent_target: Optional[str]

    # Python-сгенерированная фактура
    scene_hint:        str   # что произошло — факт из данных
    emotional_nuance:  str   # как именно NPC переживает эмоцию
    speech_style:      str   # стиль речи из dominant drive
    voice_profile:     str   # постоянный голос персонажа из JSON
    backstory:         str   # короткая биография / ключевые факты из жизни

    # Контент
    # Профиль разрешённого контента — заменяет примитивный adult_content: bool
    content_profile: ContentProfile = field(default_factory=ContentProfile)

    # Narrative — 1 всегда (если важное), 2 при EXPLAIN
    narrative_hints: Tuple[NarrativeFact, ...] = field(default_factory=tuple)
    is_explain_mode: bool = False


# Описания will_state — единый источник для промпта
_WILL_STATE_NUANCE: dict[str, str] = {
    WillState.BROKEN.value:    "полностью сломлен — подчиняется из страха, голос дрожит",
    WillState.COERCED.value:   "внешне подчиняется, внутри затаил злость",
    WillState.DECEPTIVE.value: "притворяется, ждёт момента для предательства",
    WillState.LOYAL.value:     "искренне предан, готов помочь",
    # FREE — не добавляем: отсутствие описания = норма
}

def generate_emotional_nuance(state: NPCState) -> str:
    """
    Python генерирует полное описание состояния NPC из чисел.
    Включает эмоцию, трейты и will_state — единая строка для LLM.
    Объединение устраняет дублирование will_text в промпте.
    """
    parts = []
    stress = state.stress
    traits = state.active_traits

    if state.emotion == EmotionTag.ANGRY:
        if stress > 70:
            parts.append("зол, едва сдерживается — голос на грани срыва")
        elif stress < 30:
            parts.append("зол холодно и расчётливо")
        else:
            parts.append("раздражён")

    elif state.emotion == EmotionTag.FEARFUL:
        if stress > 70:
            parts.append("напуган до дрожи, оглядывается")
        else:
            parts.append("настороженный, готов к бегству")

    elif state.emotion == EmotionTag.GRATEFUL:
        if traits.get("suspicious", 0) > 0.4:
            parts.append("благодарен, но всё ещё подозревает подвох")
        else:
            parts.append("искренне благодарен")

    elif state.emotion == EmotionTag.SUSPICIOUS:
        parts.append("подозревает подвох в каждом слове")

    elif state.emotion == EmotionTag.NEUTRAL:
        if stress > 60:
            parts.append("внешне спокоен, внутри напряжён")

    # Трейты (overlay — добавляются к основной эмоции)
    if traits.get("suspicious", 0) > 0.6 and state.emotion != EmotionTag.SUSPICIOUS:
        parts.append("недоверчиво прищуривается")

    if traits.get("grateful", 0) > 0.5 and state.emotion != EmotionTag.GRATEFUL:
        parts.append("помнит добро, которое ты сделал")

    # Will state — интегрирован сюда, чтобы не дублироваться в промпте
    will_nuance = _WILL_STATE_NUANCE.get(state.will_state.value)
    if will_nuance:
        parts.append(will_nuance)

    return ", ".join(parts) if parts else ""


def _select_narrative_hint(
    state:   NPCState,
    is_explain: bool,
) -> Tuple[NarrativeFact, ...]:
    """
    Выбирает релевантные факты для LLM.
    При EXPLAIN: top-2 по importance.
    Всегда: 1 факт если importance > 0.6 И релевантен текущему intent.
    """
    if not state.narrative_cache:
        return ()

    if is_explain:
        return state.get_top_narrative_facts(n=2)

    # Один самый важный факт — если он действительно важный
    top = state.get_top_narrative_facts(n=1)
    if top and top[0].importance >= 0.6:
        return top

    return ()


def build_verbalization_context(
    state:           NPCState,
    personality:     NPCPersonality,
    scene_hint:      str,
    npc_name:        str,
    content_profile: Optional[ContentProfile] = None,
) -> VerbalizationContext:
    # Дефолтный профиль — чистая речь, нет насилия
    if content_profile is None:
        content_profile = ContentProfile()
    """
    Строит VerbalizationContext из NPCState.
    Вся фактура генерируется здесь — LLM получает готовый текст.
    """
    is_explain = state.intent == Intent.EXPLAIN
    nuance     = generate_emotional_nuance(state)
    hints      = _select_narrative_hint(state, is_explain)
    hint       = scene_hint[:SCENE_HINT_MAX_CHARS].strip()

    return VerbalizationContext(
        npc_id           = state.npc_id,
        npc_name         = npc_name,
        tier             = personality.tier.value,
        emotion          = state.emotion.value,
        will_state       = state.will_state.value,
        intent           = state.intent.value if state.intent else Intent.IDLE.value,
        intent_target    = state.intent_target,
        scene_hint       = hint,
        emotional_nuance = nuance,
        speech_style     = _get_speech_style(personality),
        voice_profile    = personality.voice_profile,
        backstory        = personality.backstory,
        content_profile  = content_profile,
        narrative_hints  = hints,
        is_explain_mode  = is_explain,
    )

# Максимальная дистанция для LLM-вербализации — решение lazy verbalization
VERBALIZATION_RADIUS: float = 10.0


def should_verbalize(
    npc_id:      str,
    scene_state: dict,
    intent:      str,
) -> bool:
    """
    R3.2 — Lazy verbalization.
    LLM вызывается только если NPC достаточно близко к игроку.
    IDLE и OBSERVE не требуют LLM вне зависимости от дистанции.

    Исключения (слышно дальше):
      - WARN, ATTACK, FLEE — до 15 м
    """
    if intent in (Intent.IDLE.value, Intent.OBSERVE.value):
        return False

    distance = float(
        scene_state.get("player_distances", {}).get(npc_id, 999.0)
    )

    # Крик / атака / побег — слышно дальше
    if intent in (Intent.WARN.value, Intent.ATTACK.value, Intent.FLEE.value):
        return distance <= 15.0

    return distance <= VERBALIZATION_RADIUS


# ─────────────────────────────────────────────────────────────────────────────
# Динамический токен-бюджет (tier-aware)
# MAJOR говорит развёрнуто, MINOR — короче и проще
# ─────────────────────────────────────────────────────────────────────────────
_TOKEN_BUDGET: dict[tuple[str, str], int] = {
    # MAJOR — полноценный голос персонажа
    ("major", Intent.EXPLAIN.value):    700,
    ("major", Intent.TALK.value):       450,
    ("major", Intent.HELP.value):       350,
    ("major", Intent.WARN.value):       250,
    ("major", Intent.INTIMIDATE.value): 200,
    ("major", Intent.TRADE.value):      280,
    ("major", Intent.REPORT.value):     220,

    # MINOR — умеренная детализация
    ("minor", Intent.EXPLAIN.value):    300,
    ("minor", Intent.TALK.value):       180,
    ("minor", Intent.HELP.value):       160,
    ("minor", Intent.WARN.value):       140,
    ("minor", Intent.INTIMIDATE.value): 120,
    ("minor", Intent.TRADE.value):      140,
    ("minor", Intent.REPORT.value):     100,

    # Боевые и специальные intent — коротко для всех tier
    Intent.ATTACK.value:                 80,
    Intent.FLEE.value:                   60,
    Intent.OBSERVE.value:                 0,
    Intent.IDLE.value:                    0,
}


def get_token_budget(tier: str, intent: str) -> int:
    """
    Возвращает максимальное количество токенов в зависимости от tier и intent.
    MAJOR получает значительно больше токенов, чем MINOR.
    """
    # Боевые и специальные intent (работают одинаково для всех tier)
    if intent in (Intent.ATTACK.value, Intent.FLEE.value,
                  Intent.OBSERVE.value, Intent.IDLE.value):
        return _TOKEN_BUDGET.get(intent, 80)

    # Tier-aware бюджет
    key = (tier.lower(), intent)
    return _TOKEN_BUDGET.get(key, 150)   # разумный fallback


# Шаблоны для MASS NPC — без LLM (остаются без изменений)
_MASS_TEMPLATES: dict = {
    Intent.FLEE.value:       "{name} в панике бросается прочь.",
    Intent.ATTACK.value:     "{name} с криком бросается в атаку.",
    Intent.WARN.value:       "{name} что-то кричит и указывает в твою сторону.",
    # EXPLAIN для MASS — без LLM, просто сбивчивый ответ
    Intent.EXPLAIN.value:    "{name} бормочет что-то невнятное, не в силах объяснить.",
    Intent.OBSERVE.value:    "",
    Intent.IDLE.value:       "",
}


def get_mass_template(ctx: VerbalizationContext) -> Optional[str]:
    """Шаблонная реплика для MASS NPC — не тратим токены LLM."""
    template = _MASS_TEMPLATES.get(ctx.intent)
    if template is None:
        return None
    if template == "":
        return ""
    return template.format(name=ctx.npc_name)


def _verbalize_memory(fact: Union[NarrativeFact, "EventMemory"]) -> str:
    """
    R5.2 — Унифицированная вербализация NarrativeFact и EventMemory.
    Для stage=ABSTRACT + низкий confidence событие сильно размывается.
    Это исправляет тест test_abstract_memory_obscures_event.
    """
    # Поддержка legacy NarrativeFact и нового EventMemory
    event_type = getattr(fact, "event_type", None)
    target_id  = getattr(fact, "target_id", "player")
    clarity    = getattr(fact, "clarity", 1.0)
    confidence = getattr(fact, "confidence", 1.0)
    stage      = getattr(fact, "stage", None)

    readable = "ты" if target_id == "player" else str(target_id)
    days_ago = f"{getattr(fact, 'day', 0)} дней назад" if getattr(fact, 'day', 0) > 0 else "недавно"

    # === КРИТИЧНАЯ ЧАСТЬ ДЛЯ ТЕСТА ===
    # ABSTRACT стадия = сильное затуманивание, даже если clarity высокая
    if stage == MemoryStage.ABSTRACT or clarity < 0.25:
        if confidence < 0.45:
            return f"вроде бы что-то неприятное с {readable} ({days_ago})"
        else:
            return f"что-то связанное с {readable} ({days_ago})"

    # Обычная логика для конкретных воспоминаний
    if clarity > 0.8 and confidence > 0.6:
        mem_text = f"{event_type} ({readable})"
    elif clarity > 0.4:
        mem_text = f"что-то связанное с {readable}"
    else:
        mem_text = "нечто неприятное, детали размылись"

    return f"{mem_text} ({days_ago})"


def _confidence_prefix(confidence: float) -> str:
    """
    R5.2 — confidence определяет уверенность NPC при объяснении.
    NPC с низким confidence "сомневается" — как человек со старой памятью.
    """
    if confidence >= 0.8:
        return "точно помню"
    elif confidence >= 0.5:
        return "по-моему"
    else:
        return "вроде бы"


def build_npc_prompt_from_context(ctx: VerbalizationContext) -> tuple[str, str]:
    """
    Строит (system_prompt, user_prompt) из VerbalizationContext.
    Python сгенерировал ВСЮ фактуру — LLM только оживляет.
    will_state интегрирован в emotional_nuance — отдельный блок убран.
    """
    intent_instructions = {
        Intent.TALK.value:       "Хочешь поговорить.",
        Intent.WARN.value:       "Предупреждаешь об угрозе.",
        Intent.INTIMIDATE.value: "Запугиваешь. Давишь.",
        Intent.FLEE.value:       "Хочешь уйти. Ищешь выход.",
        Intent.ATTACK.value:     "Настроен враждебно. Готов к конфликту.",
        Intent.HELP.value:       "Хочешь помочь.",
        Intent.REPORT.value:     "Думаешь донести властям.",
        Intent.TRADE.value:      "Открыт к сделке.",
        Intent.OBSERVE.value:    "Молча наблюдаешь. Не вмешиваешься.",
        Intent.EXPLAIN.value:    "Объясняешь свои действия честно.",
        Intent.IDLE.value:       "",
    }

    target_text = f" (в отношении: {ctx.intent_target})" if ctx.intent_target else ""
    intent_text = intent_instructions.get(ctx.intent, "")

    # Narrative hints — факты из памяти NPC (R5.2)
    narrative_text = ""
    if ctx.narrative_hints:
        facts = []
        for fact in ctx.narrative_hints:
            mem_text   = _verbalize_memory(fact)
            confidence = getattr(fact, "confidence", 1.0)

            # R5.2: префикс уверенности показываем всегда для высокого confidence,
            # но "вроде бы" — только при низкой уверенности И в explain_mode
            conf_word = ""
            if confidence >= 0.8:
                conf_word = "точно помню: "
            elif ctx.is_explain_mode and confidence < 0.7:
                conf_word = _confidence_prefix(confidence) + ": "

            facts.append(f"— {conf_word}{mem_text}")

        prefix = "Вспоминаешь:" if not ctx.is_explain_mode else "Объясняешь, опираясь на:"
        narrative_text = prefix + "\n" + "\n".join(facts)

    # Контентные ограничения из ContentProfile — не примитивный bool
    adult_parts = []
    if ctx.content_profile.profanity_level >= 1:
        adult_parts.append(
            "мат разрешён"
            if ctx.content_profile.profanity_level == 1
            else "жёсткий мат разрешён"
        )
    if ctx.content_profile.violence_level >= 1:
        adult_parts.append(
            "упоминание насилия разрешено"
            if ctx.content_profile.violence_level == 1
            else "детальное насилие разрешено"
        )
    adult_text = (", ".join(adult_parts)).capitalize() + "." if adult_parts else ""

    system_prompt = "\n".join(filter(None, [
        f"Ты — {ctx.npc_name}.",
        ctx.voice_profile,
        # backstory — ключевые факты биографии, формируют контекст голоса
        f"Из твоей жизни: {ctx.backstory}" if ctx.backstory else "",
        ctx.speech_style,
        f"Сейчас: {ctx.emotional_nuance}" if ctx.emotional_nuance else "",
        f"{intent_text}{target_text}",
        narrative_text,
        adult_text,
        "",
        "Говори от первого лица. Живо, конкретно, в характере.",
        # LLM возвращает только речь и действие — состояние меняет Python
        'Затем отдельно JSON: {"speech": "...", "action": "..."}',
    ]))

    user_prompt = ctx.scene_hint if ctx.scene_hint else "Что происходит?"

    return system_prompt, user_prompt


def _get_speech_style(personality: NPCPersonality) -> str:
    drives   = personality.drives_base
    dominant = max(drives, key=drives.get) if drives else "desire"
    styles = {
        "control":      "Говоришь структурированно, ставишь условия, не терпишь хаоса.",
        "significance": "Упоминаешь своё положение. Обижаешься на неуважение.",
        "fear":         "Осторожен. Задаёшь вопросы. Говоришь тихо или торопливо.",
        "desire":       "Энергичен. Открыт к выгоде. Торгуешься. Любопытен.",
    }
    return styles.get(dominant, "")
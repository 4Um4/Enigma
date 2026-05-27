"""
Единственное место, где числа превращаются в слова для LLM.

ИНВАРИАНТЫ:
1. На выходе — только человекочитаемые строки, никаких цифр.
2. Если дизайнер поменяет шкалу — меняем только здесь.
3. can_speak/can_move выводятся из posture + conditions, не хранятся.

Файл: backend/app/services/verbalization/state_interpreter.py
Назначение: Единственный мост между числовым состоянием NPC и человекочитаемым описанием для LLM. LLM никогда не видит сырые цифры.
Зависимости: typing, backend.app.models.npc_state (Intent, EmotionTag, WillState, NPCState), backend.app.models.physical (Condition)
Основные сущности: UrgencyLevel, PhysicalState, NPCStateDescription, StateInterpreter
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum

from app.models.npc_state import NPCState, Intent
from app.models.physical import Condition


# ── Уровни для описания ──────────────────────────────────────────────

class UrgencyLevel(str, Enum):
    """Эмоциональное напряжение — вывод из stress (0-100). Базовые формы (женский род)."""
    CALM = "спокоен"
    ALERTED = "напряжён"
    SCARED = "напуган"
    PANIC = "в панике"
    BROKEN = "в шоке, не контролирует себя"


class PhysicalState(str, Enum):
    """Физическое состояние — вывод из hp_ratio. Базовые формы (мужской род)."""
    UNHARMED = "не ранен"
    SCRATCHED = "лёгкая рана"
    WOUNDED = "ранен"
    CRITICAL = "тяжело ранен"
    INCAPACITATED = "без сознания"


# ── Маппинги ─────────────────────────────────────────────────────────

# Пороги стресса адаптированы под шкалу 0-100
_STRESS_THRESHOLDS: List[tuple[float, UrgencyLevel]] = [
    (80.0, UrgencyLevel.BROKEN),
    (60.0, UrgencyLevel.PANIC),
    (40.0, UrgencyLevel.SCARED),
    (20.0, UrgencyLevel.ALERTED),
]

# Описание всех 17 intent-ов на русском — публично для SceneOutcomeBuilder
# Формы гендерно-нейтральны (глаголы/наречия) — НЕ применять _apply_gender
INTENT_DESCRIPTIONS: dict[str, str] = {
    "idle": "стоит спокойно",
    "talk": "повёрнут к игроку",
    "warn": "напряжён",
    "intimidate": "подался вперёд",
    "flee": "озирается к выходу",
    "attack": "в боевой стойке",
    "help": "подходит ближе",
    "report": "тянется к страже",
    "trade": "достаёт что-то из кармана",
    "observe": "внимательно смотрит",
    "explain": "поднял руку",
    "block_path": "преграждает путь",
    "ambush": "застыл в тени",
    "seek_ally": "озирается по сторонам",
    "offer_job": "смотрит прямо",
    "request_service": "склонил голову",
    "spread_rumor": "шепчется с соседом",
    "call_for_help": "готов крикнуть",
    "change_role": "меняется в лице",
    "approach": "подходит ближе",
}

# Маппинг EmotionTag → русский для промпта. Базовые формы (мужской род).
# Гендерные окончания применяются через _apply_gender() в месте использования.
EMOTION_DESCRIPTIONS: dict[str, str] = {
    "neutral": "",
    "angry": "злится",
    "fearful": "напуган",
    "happy": "радуется",
    "suspicious": "подозревает",
    "grateful": "благодарен",
    "disgusted": "испытывает отвращение",
    "sad": "грустит",
}

# Condition types, которые блокируют речь
_SPEECH_BLOCKING_CONDITIONS = {"stunned", "confused", "silenced"}

# Condition types, которые блокируют движение
_MOVEMENT_BLOCKING_CONDITIONS = {"stunned", "paralyzed", "frozen"}

# Condition types, которые замедляют (при высоком severity)
_SLOWING_CONDITIONS = {"slowed", "bleeding", "burning", "poisoned"}

# Маппинг condition type → русское описание. Базовые формы (мужской род, глаголы).
# Окончания подставляются через _apply_gender().
_CONDITION_DESCRIPTIONS_BASE: dict[str, str] = {
    "bleeding": "истекает кровью",
    "stunned": "оглушён",
    "prone": "лежит на земле",
    "burning": "горит",
    "slowed": "замедлен",
    "poisoned": "отравлен",
    "confused": "в замешательстве",
    "silenced": "не может говорить",
    "paralyzed": "парализован",
    "frozen": "заморожен",
}

# ── pymorphy3 для гендерных окончаний ──────────────────────────────────
import pymorphy3

_morph = pymorphy3.MorphAnalyzer()

# Кэш для избежания повторного парсинга одинаковых слов
_gender_cache: dict[tuple[str, str], str] = {}

def _apply_gender(word: str, gender: str) -> str:
    """
    Адаптирует слово к роду через pymorphy3. Базовая форма — мужской.
    gender: "male"/"мужской", "female"/"женский", прочее = мужской по умолчанию
    
    Для составных фраз ("тяжело ранен") обрабатывает последнее слово.
    """
    if gender not in ("female", "женский"):
        return word
    
    cache_key = (word, gender)
    if cache_key in _gender_cache:
        return _gender_cache[cache_key]
    
    # Составные фразы — берем последнее значимое слово
    parts = word.split()
    if len(parts) > 1:
        # "не ранен" → "не" + "ранена", "тяжело ранен" → "тяжело" + "ранена"
        last_word = parts[-1]
        result = _inflect_to_feminine(last_word)
        if result != last_word:
            parts[-1] = result
            final = " ".join(parts)
        else:
            final = word
    else:
        final = _inflect_to_feminine(word)
    
    _gender_cache[cache_key] = final
    return final


# Словарь кратких форм — pymorphy3 не умеет inflect краткие причастия правильно
# (даёт "напуганная" вместо "напугана")
_SHORT_FORM_FEMALE: dict[str, str] = {
    # Краткие причастия
    "напуган": "напугана",
    "ранен": "ранена",
    "оглушён": "оглушена",
    "оглушен": "оглушена",
    "замедлен": "замедлена",
    "отравлен": "отравлена",
    "парализован": "парализована",
    "заморожен": "заморожена",
    # Краткие прилагательные
    "спокоен": "спокойна",
    "напряжён": "напряжена",
    "напряжен": "напряжена",
    "растроган": "растрогана",
    "смущён": "смущена",
    "смущен": "смущена",
    "удивлён": "удивлена",
    "удивлен": "удивлена",
    "встревожен": "встревожена",
    "обеспокоен": "обеспокоена",
}

def _inflect_to_feminine(word: str) -> str:
    """
    Склоняет одно слово к женскому роду.
    Сначала проверяет словарь кратких форм, затем pymorphy3.
    """
    # Словарь кратких форм — приоритет
    if word in _SHORT_FORM_FEMALE:
        return _SHORT_FORM_FEMALE[word]
    
    # Для остальных — pymorphy3
    parsed = _morph.parse(word)
    if not parsed:
        return word
    
    variant = parsed[0]
    if variant.tag.gender == "femn":
        return word
    
    try:
        inflected = variant.inflect({"femn", "nomn"})
        if inflected:
            return inflected.word
    except Exception:
        pass
    
    return word


@dataclass(frozen=True)
class NPCStateDescription:
    """
    Человекочитаемое состояние NPC. Ни одной цифры.
    Это единственное, что видит LLM о состоянии NPC.
    """
    name: str
    intent: str              # "пытается убежать"
    emotional_state: str     # "в панике"
    physical_state: str      # "лёгкая рана"
    posture: str             # "стоит" / "шатается" / "лежит"
    conditions: List[str]    # ["кровоточит", "оглушена"]
    can_speak: bool
    can_move: bool
    gender: str = "male"     # для внешнего использования


class StateInterpreter:
    """
    Переводит NPCState в NPCStateDescription.
    Изолирует LLM от системных данных.
    """

    def interpret(self, state: NPCState) -> NPCStateDescription:
        """Основной метод: NPCState → человекочитаемое описание."""
        hp_ratio = state.hp / state.max_hp if state.max_hp > 0 else 1.0
        gender = getattr(state, "gender", "male")
        # GAP5 FIX: Читаем живую физиологию, а не только RPG-абстракцию HP
        body_state = getattr(state, 'body_state', {}) or {}

        return NPCStateDescription(
            name=state.npc_id,
            intent=self._intent_to_word(state.intent),
            emotional_state=_apply_gender(self._stress_to_word(state.stress), gender),
            physical_state=_apply_gender(self._physical_state_to_word(hp_ratio, body_state), gender),
            posture=self._posture_to_word(state.posture),
            conditions=self._conditions_to_list(state.conditions, gender),
            can_speak=self.derive_can_speak(state.posture, state.conditions),
            can_move=self.derive_can_move(state.posture, state.conditions, state.hp),
            gender=gender,
        )

    def _stress_to_word(self, stress: float) -> str:
        """Стресс 0-100 → человекочитаемое состояние."""
        for threshold, level in _STRESS_THRESHOLDS:
            if stress >= threshold:
                return level.value
        return UrgencyLevel.CALM.value

    def _hp_to_word(self, ratio: float) -> str:
        """HP ratio 0-1 → описание раны (legacy fallback)."""
        if ratio <= 0.0:
            return PhysicalState.INCAPACITATED.value
        if ratio < 0.25:
            return PhysicalState.CRITICAL.value
        if ratio < 0.5:
            return PhysicalState.WOUNDED.value
        if ratio < 0.9:
            return PhysicalState.SCRATCHED.value
        return PhysicalState.UNHARMED.value

    def _physical_state_to_word(self, hp_ratio: float, body_state: dict) -> str:
        """GAP5 FIX: Физиология говорит правду. Боль и шок перекрывают RPG-абстракцию HP.
        NPC с 80% HP, но с агонизирующей болью (pain: 0.9) больше не "слегка ранен".
        """
        pain = body_state.get("pain", 0.0)
        shock = body_state.get("shock_impulse", 0.0)
        blood_loss = body_state.get("blood_loss", 0.0)

        # Шок доминирует: NPC в нокауте или на грани
        if shock > 0.8:
            return PhysicalState.INCAPACITATED.value
        # Экстремальная боль или кровопотеря = критическое состояние
        if pain > 0.9 or blood_loss > 0.7:
            return PhysicalState.CRITICAL.value
        # Сильная боль или средний шок = серьезное ранение
        if pain > 0.6 or shock > 0.5:
            return PhysicalState.WOUNDED.value
        # Кровотечение или ноющая боль = легкое ранение
        if blood_loss > 0.3 or pain > 0.3:
            return PhysicalState.SCRATCHED.value

        # Фоллбэк на HP, если физиология не дает сигналов
        return self._hp_to_word(hp_ratio)

    def _intent_to_word(self, intent: Optional[Intent]) -> str:
        """Intent enum → описание на русском."""
        if intent is None:
            return INTENT_DESCRIPTIONS["idle"]
        key = intent.value if hasattr(intent, "value") else str(intent).lower()
        return INTENT_DESCRIPTIONS.get(key, INTENT_DESCRIPTIONS["observe"])

    def _posture_to_word(self, posture: str) -> str:
        """posture поле → описание."""
        mapping = {
            "standing": "стоит",
            "staggered": "шатается",
            "prone": "лежит",
        }
        return mapping.get(posture, "стоит")

    def _conditions_to_list(self, conditions: Dict[str, Condition], gender: str = "male") -> List[str]:
        """
        Словарь Condition → список русских описаний.
        Только значимые (severity > 0.3). С гендерными окончаниями.
        """
        result: List[str] = []
        for cond in conditions.values():
            if cond.severity > 0.3:
                desc = _CONDITION_DESCRIPTIONS_BASE.get(cond.type)
                if desc:
                    result.append(_apply_gender(desc, gender))
        return result

    def derive_can_speak(self, posture: str, conditions: Dict[str, Condition]) -> bool:
        """Выводит возможность говорить из posture + conditions."""
        if posture == "prone":
            return False
        for cond in conditions.values():
            if cond.type in _SPEECH_BLOCKING_CONDITIONS and cond.severity > 0.3:
                return False
            # confused при высокой severity — говорит невнятно
            if cond.type == "confused" and cond.severity > 0.7:
                return False
        return True

    def derive_can_move(self, posture: str, conditions: Dict[str, Condition], hp: int) -> bool:
        """Выводит возможность двигаться из posture + conditions + hp."""
        if hp <= 0:
            return False
        if posture == "prone":
            return False
        for cond in conditions.values():
            if cond.type in _MOVEMENT_BLOCKING_CONDITIONS and cond.severity > 0.3:
                return False
            # замедляющие условия при экстремальном severity блокируют движение
            if cond.type in _SLOWING_CONDITIONS and cond.severity > 0.8:
                return False
        return True
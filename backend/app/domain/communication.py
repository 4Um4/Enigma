# backend/app/domain/communication.py
# Назначение: Доменные объекты коммуникации NPC. Уровень exposure, адресация, тема.
# Зависимости: typing.Literal
# Основные сущности: ExposureLevel, CommunicationIntent

from dataclasses import dataclass
from typing import Literal, Optional

from app.domain.epistemology import Proposition

# Р-А (Player Dialogue, GC-DIALOGUE-01 prep): сентинел само-разговора NPC.
# Значение target_id для экстернализованного бормотания без агента-адресата.
# ОНТОЛОГИЯ: слышимая речь (журнал игрока при dist<8, LISTEN-дельты,
# claim-подслушивание), но НЕ агент — нет STM, рёбер отношений, L1-записей
# (guard в NpcDialogueSubscriber). Не путать с _EXPOSURE_DEFAULT_RADIUS
# "private" (radius=0, внутренняя когниция — уровень SpeechExposure, Р-В).
# Потребители: task_scheduler (fallback-цель), post_decision (STM-контракт),
# npc_dialogue_subscriber (agent-guard).
SELF_TALK_SENTINEL = "soliloquy"

# ADR-O-311: Exposure Default Contract — радиус выводится из semantic.
_EXPOSURE_DEFAULT_RADIUS: dict[str, float] = {
    "secret": 1.5,  # собеседник рядом
    "whisper": 3.0,  # группа вплотную
    "normal": 5.0,  # обычная речь в комнате
    "shout": 15.0,  # публичное событие, бой
    "private": 0.0,  # внутренняя речь / солилоквий (не слышим)
}


@dataclass(frozen=True)
class ExposureLevel:
    """Семантический + физический уровень доступности речи.

    physical_radius выводится из semantic если не задан явно (None).
    Прямая передача radius допускается только для override (test/sandbox).
    """

    semantic: Literal["secret", "whisper", "normal", "shout", "private"]
    physical_radius: Optional[float] = None  # None = derive from semantic

    def to_dict(self) -> dict:
        """Э6: JSON-сериализация (§12 WARA). physical_radius — явно
        (не None, т.к. __post_init__ уже вычислил его)."""
        return {
            "semantic": self.semantic,
            "physical_radius": self.physical_radius,
        }

    @staticmethod
    def from_dict(d: dict) -> "ExposureLevel":
        return ExposureLevel(
            semantic=d["semantic"],
            physical_radius=d.get("physical_radius"),
        )

    def __post_init__(self) -> None:
        if self.physical_radius is None:
            object.__setattr__(
                self,
                "physical_radius",
                _EXPOSURE_DEFAULT_RADIUS.get(self.semantic, 5.0),
            )

    @classmethod
    def from_semantic(
        cls, semantic: Literal["secret", "whisper", "normal", "shout", "private"]
    ) -> "ExposureLevel":
        """Единственный легальный способ создать ExposureLevel в прод-коде."""
        if semantic not in _EXPOSURE_DEFAULT_RADIUS:
            raise ValueError(
                f"Unknown exposure semantic: {semantic!r}. "
                f"Allowed: {list(_EXPOSURE_DEFAULT_RADIUS)}"
            )
        return cls(semantic=semantic)


@dataclass(frozen=True)
class DialogueRequest:
    """Доменный запрос на генерацию диалога.
    Execution Framework не знает про LLM, он знает только что нужно поговорить на эту тему."""

    topic: str
    target_id: str
    exposure: ExposureLevel
    intent_type: str = "talk"
    emotional_state: str = "нейтрально"
    # T-04: Строка с историей взаимодействий (npc_npc_context), сформированная в post_decision.
    npc_npc_context: str = ""
    # BUG-DL-04: ID нити диалога для пер-парной изоляции памяти.
    thread_id: str = ""
    # V8-DLG-10 FIX: Готовый промпт от VerbalizationContext, собранный в post_decision
    prepared_prompt: str = ""
    # S197: Эпистемический мост. Если реплика несёт утверждение (claim), оно передаётся сюда.
    proposition: Optional[dict] = None


@dataclass(frozen=True)
class CommunicationIntent:
    """Единый источник истины для всей цепочки ответа NPC.

    Создаётся DecisionHub ПОСЛЕ TopicExtractor.
    Не допускается создание с пустым topic.
    """

    speaker: str  # npc_id
    audience: str  # 'player' | npc_id | 'all'
    topic: str  # 'торговля_мечом', 'угроза_бандитов' — из TopicExtractor
    intent_type: str  # 'диалог', 'приказ', 'ложь', 'вопрос'
    emotional_state: str  # 'злость', 'страх', 'любопытство'
    exposure_level: ExposureLevel
    semantic_action: Optional[str] = (
        None  # GAP8 FIX: Тип социального акта (MOVE, THREATEN, PERSUADE, GIVE)
    )
    target_id: Optional[str] = (
        None  # GAP8 FIX: ID цели директивы (для NPC-to-NPC Social Physics)
    )
    thread_id: str = ""  # BUG-DL-04: ID нити диалога
    priority: float = 0.5  # H-28 FIX: DRF overlay для модуляции приоритета реплик
    # S197: Causal Provenance. Утверждение, породившее этот Intent.
    # Пробрасывается из EpistemicContext через DecisionHub в DialogueRequest.
    proposition: Optional[Proposition] = None

    def to_dict(self) -> dict:
        """Э6 (Н-40): JSON-сериализация для scene_state-персистентности
        (_pending_intents → scene_state). Все поля — примитивы или
        сериализуемые доменные объекты (§12 WARA)."""
        return {
            "speaker": self.speaker,
            "audience": self.audience,
            "topic": self.topic,
            "intent_type": self.intent_type,
            "emotional_state": self.emotional_state,
            "exposure_level": self.exposure_level.to_dict(),
            "semantic_action": self.semantic_action,
            "target_id": self.target_id,
            "thread_id": self.thread_id,
            "priority": self.priority,
            "proposition": (
                self.proposition.to_dict() if self.proposition else None
            ),
        }

    @staticmethod
    def from_dict(d: dict) -> "CommunicationIntent":
        from app.domain.epistemology import Proposition

        _exp = ExposureLevel.from_dict(d["exposure_level"])
        _prop = Proposition.from_dict(d["proposition"]) if d.get("proposition") else None
        return CommunicationIntent(
            speaker=d["speaker"],
            audience=d["audience"],
            topic=d["topic"],
            intent_type=d["intent_type"],
            emotional_state=d["emotional_state"],
            exposure_level=_exp,
            semantic_action=d.get("semantic_action"),
            target_id=d.get("target_id"),
            thread_id=d.get("thread_id", ""),
            priority=d.get("priority", 0.5),
            proposition=_prop,
        )

    def __post_init__(self) -> None:
        # Устав 7.2: пустой topic = LLM плывёт по ассоциациям
        if not self.topic or not self.topic.strip():
            raise ValueError(
                f"CommunicationIntent.topic не может быть пустым (speaker={self.speaker!r})"
            )

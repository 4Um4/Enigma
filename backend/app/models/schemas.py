"""
Назначение этого модуля — определение схем данных для API и внутреннего использования.
Здесь описаны Pydantic-модели для валидации и сериализации данных, которые проходят через API и между компонентами системы.
Схемы включают в себя:
1. Запросы и ответы для API-эндпоинтов (например, ChatTurnRequest, CharacterUpsertRequest).
2. Внутренние модели для представления состояния игры (например, CharacterSheet, NPCState, WorldEvent).
3. Модели для управления сессиями игроков (например, PlayerSession, HeartbeatRequest).
4. Модели для представления состояния кампании и мира (например, CampaignState, PlayerInfo, WorldFact).
Эти модели обеспечивают строгую типизацию и валидацию данных, что помогает предотвратить ошибки и обеспечить согласованность данных в системе. Они используются как в API-эндпоинтах, так и во внутренних сервисах для обмена данными между компонентами.

- Разнести модели по нескольким файлам для лучшей организации (например, api_models.py, game_models.py, session_models.py).
- Добавить комментарии и описания к каждому полю для улучшения документации.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelProvider(str, Enum):
    ollama = "ollama"
    lm_studio = "lm_studio"
    llama_cpp = "llama_cpp"
    koboldcpp = "koboldcpp"
    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"
    mistral = "mistral"
    openai_compatible = "openai_compatible"


class ModelSelection(BaseModel):
    """Model selection configuration."""

    model_config = {"protected_namespaces": ()}

    provider: ModelProvider
    model_name: str
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None


class PlayerAction(BaseModel):
    player_name: str
    action: str
    dice_result: Optional[int] = Field(default=None, ge=1, le=20)


class ChatTurnRequest(BaseModel):
    world_id: str
    campaign_id: str
    location: str
    model: Optional[ModelSelection] = None  # оркестратор сам управляет моделями
    actions: List[PlayerAction]
    # Позиция игрока от фронтенда — применяется в init_scene_state, сохраняется атомарно в commit_tick
    player_position: Optional[tuple[float, float]] = None
    # S82: Мировые координаты — spatial oracle input. Backend вычисляет actual_chunk независимо.
    world_position: Optional[tuple[float, float]] = None


class AgentTrace(BaseModel):
    agent: str
    output: Dict[str, Any]


class ChatTurnResponse(BaseModel):
    dm_response: str
    npc_reactions: List[str]
    world_changes: List[str]
    journal_entry_id: str
    traces: List[AgentTrace]
    # TASK 1: Force Merge — передаём world_snapshot на фронтенд (ADR-0014)
    world_snapshot: Optional[Dict[str, Any]] = None
    npc_positions: Optional[Dict[str, Any]] = None
    # Спринт 26: Артефакты Конфликта Воли (Embodied Perception Interface)
    will_conflict_data: Optional[Dict[str, Any]] = None
    # Sprint P9: Факты, донесённые до игрока (для UI и отладки)
    observed_facts: List[Any] = []


# ADR-030: Avatar Creation Vector — Вектор Начальных Условий Гибридной Сущности
class CharacterSheet(BaseModel):
    name: str
    # ADR-030: Вектор Начальных Условий (Hybrid Consciousness)
    archetype: str = "Drifter"  # Laborer, Soldier, Merchant, Drifter, Noble
    temperament: str = "Stoic"  # Fearful, Stoic, Impulsive, Calculating
    body_profile: Dict[str, Any] = Field(default_factory=dict)  # max_hp, abilities
    psyche: Dict[str, Any] = Field(default_factory=dict)  # fear, impulsivity, willpower
    # Legacy поля (для совместимости со старыми загрузчиками)
    race: str = ""
    class_name: str = ""
    level: int = 1
    stats: Dict[str, int] = Field(default_factory=dict)
    skills: Dict[str, int] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    spells: List[str] = Field(default_factory=list)
    portrait: Optional[str] = None
    backstory: Optional[str] = None
    hp: int = 10
    max_hp: int = 10
    ac: int = 10
    effects: List[str] = Field(default_factory=list)
    importance: Optional[str] = Field(
        default=None, description="major or mass for NPC importance"
    )


class NPCState(BaseModel):
    name: str
    motivation: str
    goals: List[str]
    memory: List[str] = Field(default_factory=list)
    faction: Optional[str] = None
    location: Optional[str] = None


class WorldEvent(BaseModel):
    timestamp: datetime
    title: str
    details: str
    visibility: str = "hidden"


class CampaignLoadRequest(BaseModel):
    campaign_id: str
    world_id: str


class CampaignLoadResponse(BaseModel):
    campaign_id: str
    world_id: str
    status: str
    loaded_files: List[str]


class SessionInterfaceState(BaseModel):
    campaign_id: str
    world_id: str
    players: List[str] = Field(default_factory=list)
    session_log: List[str] = Field(default_factory=list)
    dice_input_required: bool = False
    scene_state: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReadinessCheck(BaseModel):
    area: str
    status: str
    details: str


class ReadinessReport(BaseModel):
    score_percent: float
    summary: str
    checks: List[ReadinessCheck]
    next_steps: List[str]


class CharacterUpsertRequest(BaseModel):
    campaign_id: str
    character: CharacterSheet


class CharacterListResponse(BaseModel):
    campaign_id: str
    characters: List[CharacterSheet]


class WorldTickResponse(BaseModel):
    world_id: str
    triggered: bool
    reason: str
    events: List[str]


class KnowledgeIngestResponse(BaseModel):
    kind: str
    filename: str
    extracted_chars: int
    entry_id: str
    notes: str


class CombatParticipant(BaseModel):
    name: str
    initiative: int
    hp: int = 1
    ac: int = 10


class CombatStartRequest(BaseModel):
    campaign_id: str
    combat_id: str
    participants: List[CombatParticipant]


class CombatActionRequest(BaseModel):
    campaign_id: str
    combat_id: str
    attacker: str
    target: str
    d20_roll: int = Field(ge=1, le=20)
    attack_bonus: int = 0
    target_ac: int = Field(ge=1)
    damage: int = Field(ge=0)


class CombatStateResponse(BaseModel):
    campaign_id: str
    combat_id: str
    round: int
    turn_index: int
    order: List[Dict[str, Any]]
    participants: List[Dict[str, Any]]
    log: List[str]


# === Campaign State Models (RAG-ready) ===


class PlayerInfo(BaseModel):
    """Информация об игроке/персонаже."""

    name: str
    race: str = ""
    class_name: str = ""
    level: int = 1
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


class WorldFact(BaseModel):
    """Факт о мире с метаданными для RAG."""

    id: str
    text: str
    category: str = "lore"  # location, npc, quest, lore
    tags: List[str] = Field(default_factory=list)
    source: str = ""
    created_at: str = ""


class SessionSummary(BaseModel):
    """Краткое описание сессии."""

    id: str
    date: str
    summary: str
    location: str = ""
    key_events: List[str] = Field(default_factory=list)
    created_at: str = ""


class CampaignState(BaseModel):
    """Состояние кампании - "тёплый" слой между каноном и сессией."""

    campaign_id: str
    campaign_name: str = ""
    players: List[PlayerInfo] = Field(default_factory=list)
    world_facts: List[WorldFact] = Field(default_factory=list)
    session_summaries: List[SessionSummary] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlayerSession(BaseModel):
    """Сессия игрока для отслеживания активности."""

    campaign_id: str
    player_name: str
    active: bool = True
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    session_id: str = ""

    def is_active(self, timeout_seconds: int = 120) -> bool:
        """
        Проверить, активна ли сессия (timestamp < timeout).
        По умолчанию 120 секунд - синхронизировано с player_session_service.ttl_seconds.
        """
        if not self.active:
            return False
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        # Защита от race condition: отрицательный elapsed из-за синхронизации часов
        # считаем как активную сессию
        if elapsed < 0:
            return True
        return elapsed < timeout_seconds


class HeartbeatRequest(BaseModel):
    """Запрос на обновление heartbeat."""

    campaign_id: str
    player_name: str

    # Поддержка старых клиентов с другими названиями полей
    player: Optional[str] = Field(None, alias="player")
    campaign: Optional[str] = Field(None, alias="campaign")

    model_config = {"populate_by_name": True}

    def __init__(self, **data: Any) -> None:
        # Если пришли старые поля - преобразуем
        if "player" in data and data["player"]:
            data["player_name"] = data.pop("player")
        if "campaign" in data and data["campaign"]:
            data["campaign_id"] = data.pop("campaign")
        super().__init__(**data)


class HeartbeatResponse(BaseModel):
    """Ответ на heartbeat."""

    active: bool
    player_name: str
    message: str


class PlayerSelectRequest(BaseModel):
    """Запрос на выбор персонажа."""

    campaign_id: str
    player: str


class PlayerSelectResponse(BaseModel):
    """Ответ на выбор персонажа."""

    status: str
    player: str


class PlayerSessionResponse(BaseModel):
    """Ответ на получение сессии."""

    player: Optional[str] = None
    active: bool = False

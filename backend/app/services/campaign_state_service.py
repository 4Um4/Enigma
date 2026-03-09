"""
Campaign State Service - "тёплый" слой между каноном мира и сессией.
Интерфейс спроектирован для легкой миграции на SQLite.

Storage: data/campaigns/{campaign_id}/campaign_state.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.models.schemas import CampaignState, PlayerInfo, WorldFact, SessionSummary


class CampaignStateService:
    """
    Сервис для управления состоянием кампании.
    Предоставляет абстрактный интерфейс для работы с данными кампании.
    """
    
    def __init__(self, root: str = "data/campaigns") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
    
    def _campaign_dir(self, campaign_id: str) -> Path:
        """Получить директорию кампании."""
        campaign_dir = self.root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        return campaign_dir
    
    def _state_file(self, campaign_id: str) -> Path:
        """Получить путь к файлу состояния кампании."""
        return self._campaign_dir(campaign_id) / "campaign_state.json"
    
    def _now_iso(self) -> str:
        """Получить текущее время в ISO формате."""
        return datetime.now(timezone.utc).isoformat()
    
    # === Core Methods ===
    
    def get_campaign_state(self, campaign_id: str) -> CampaignState:
        """
        Загрузить полное состояние кампании.
        Если файл не существует - создает новое пустое состояние.
        """
        path = self._state_file(campaign_id)
        
        if not path.exists():
            # Создаем новое состояние
            state = CampaignState(campaign_id=campaign_id)
            self._save_to_file(path, state)
            return state
        
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CampaignState.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            # Если файл поврежден - создаем новый
            state = CampaignState(campaign_id=campaign_id)
            self._save_to_file(path, state)
            return state
    
    def _save_to_file(self, path: Path, state: CampaignState) -> None:
        """Сохранить состояние в файл."""
        path.write_text(
            json.dumps(state.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    def save(self, campaign_id: str) -> None:
        """Сохранить текущее состояние (использует кэш в памяти)."""
        state = self.get_campaign_state(campaign_id)
        self._save_to_file(self._state_file(campaign_id), state)
    
    # === Campaign Info ===
    
    def update_campaign_name(self, campaign_id: str, name: str) -> CampaignState:
        """Обновить название кампании."""
        state = self.get_campaign_state(campaign_id)
        state.campaign_name = name
        self._save_to_file(self._state_file(campaign_id), state)
        return state
    
    # === Players ===
    
    def add_player(
        self,
        campaign_id: str,
        name: str,
        race: str = "",
        class_name: str = "",
        level: int = 1,
        notes: str = ""
    ) -> PlayerInfo:
        """Добавить или обновить игрока."""
        state = self.get_campaign_state(campaign_id)
        
        now = self._now_iso()
        
        # Ищем существующего игрока
        existing = None
        for p in state.players:
            if p.name.lower() == name.lower():
                existing = p
                break
        
        if existing:
            # Обновляем
            existing.race = race or existing.race
            existing.class_name = class_name or existing.class_name
            existing.level = level or existing.level
            existing.notes = notes or existing.notes
            existing.updated_at = now
            player = existing
        else:
            # Создаем нового
            player = PlayerInfo(
                name=name,
                race=race,
                class_name=class_name,
                level=level,
                notes=notes,
                created_at=now,
                updated_at=now
            )
            state.players.append(player)
        
        self._save_to_file(self._state_file(campaign_id), state)
        return player
    
    def get_players(self, campaign_id: str) -> list[PlayerInfo]:
        """Получить список всех игроков."""
        state = self.get_campaign_state(campaign_id)
        return state.players
    
    def get_player(self, campaign_id: str, name: str) -> Optional[PlayerInfo]:
        """Получить информацию о конкретном игроке."""
        state = self.get_campaign_state(campaign_id)
        for p in state.players:
            if p.name.lower() == name.lower():
                return p
        return None
    
    # === World Facts (RAG-enabled) ===
    
    def add_world_fact(
        self,
        campaign_id: str,
        text: str,
        category: str = "lore",
        tags: Optional[list[str]] = None,
        source: str = ""
    ) -> WorldFact:
        """Добавить факт о мире с метаданными для RAG."""
        state = self.get_campaign_state(campaign_id)
        
        # Генерируем ID
        fact_id = f"fact_{uuid4().hex[:8]}"
        
        fact = WorldFact(
            id=fact_id,
            text=text,
            category=category,
            tags=tags or [],
            source=source,
            created_at=self._now_iso()
        )
        
        state.world_facts.append(fact)
        self._save_to_file(self._state_file(campaign_id), state)
        return fact
    
    def get_world_facts(
        self,
        campaign_id: str,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None
    ) -> list[WorldFact]:
        """Получить факты о мире с возможностью фильтрации."""
        state = self.get_campaign_state(campaign_id)
        facts = state.world_facts
        
        # Фильтр по категории
        if category:
            facts = [f for f in facts if f.category == category]
        
        # Фильтр по тегам
        if tags:
            facts = [f for f in facts if any(t in f.tags for t in tags)]
        
        return facts
    
    def get_all_categories(self, campaign_id: str) -> list[str]:
        """Получить список всех категорий фактов."""
        state = self.get_campaign_state(campaign_id)
        return list(set(f.category for f in state.world_facts))
    
    # === Session Summaries ===
    
    def add_session_summary(
        self,
        campaign_id: str,
        summary: str,
        date: Optional[str] = None,
        location: str = "",
        key_events: Optional[list[str]] = None
    ) -> SessionSummary:
        """Добавить краткое описание сессии."""
        state = self.get_campaign_state(campaign_id)
        
        session_id = f"session_{uuid4().hex[:8]}"
        now = self._now_iso()
        
        session = SessionSummary(
            id=session_id,
            date=date or now[:10],  # YYYY-MM-DD
            summary=summary,
            location=location,
            key_events=key_events or [],
            created_at=now
        )
        
        state.session_summaries.append(session)
        self._save_to_file(self._state_file(campaign_id), state)
        return session
    
    def get_session_summaries(
        self,
        campaign_id: str,
        limit: int = 10
    ) -> list[SessionSummary]:
        """Получить последние описания сессий."""
        state = self.get_campaign_state(campaign_id)
        sessions = sorted(
            state.session_summaries,
            key=lambda s: s.created_at,
            reverse=True
        )
        return sessions[:limit]
    
    # === Utility Methods ===
    
    def get_summary(self, campaign_id: str) -> dict[str, Any]:
        """Получить краткую сводку о кампании (для CLI)."""
        state = self.get_campaign_state(campaign_id)
        return {
            "campaign_id": campaign_id,
            "campaign_name": state.campaign_name or "(без названия)",
            "players_count": len(state.players),
            "facts_count": len(state.world_facts),
            "sessions_count": len(state.session_summaries),
            "categories": self.get_all_categories(campaign_id)
        }
    
    def auto_detect_category(self, text: str) -> str:
        """
        Автоматически определить категорию факта по тексту.
        Простая эвристика для MVP.
        """
        text_lower = text.lower()
        
        # Квесты
        if any(word in text_lower for word in ["квест", "задание", "миссия", "цель"]):
            return "quest"
        
        # Локации
        if any(word in text_lower for word in ["таверна", "город", "деревня", "замок", "пещера", "подземелье", "лес", "горы"]):
            return "location"
        
        # NPC
        if any(word in text_lower for word in ["торговец", "хозяин", "старик", "женщина", "мужчина", "NPC", "персонаж"]):
            return "npc"
        
        # По умолчанию - lore
        return "lore"


# === Singleton Instance ===
_service: Optional[CampaignStateService] = None


def get_campaign_state_service() -> CampaignStateService:
    """Получить экземпляр сервиса (singleton)."""
    global _service
    if _service is None:
        _service = CampaignStateService()
    return _service


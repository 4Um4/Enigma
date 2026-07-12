import json
import logging
from pathlib import Path
from typing import Optional

from app.models.schemas import CharacterSheet
from app.models.character import CharacterProfile

logger = logging.getLogger(__name__)


class CharacterService:
    """
    Persist player characters per campaign as local JSON.

    Два типа данных:
    - CharacterSheet (characters.json) — D&D механика: HP, AC, спеллы
    - CharacterProfile (character_profiles.json) — психология: ценности, integrity
    """

    def __init__(self, root: str = "saves") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _characters_path(self, campaign_id: str) -> Path:
        campaign_dir = self.root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        return campaign_dir / "characters.json"

    def _profiles_path(self, campaign_id: str) -> Path:
        campaign_dir = self.root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        return campaign_dir / "character_profiles.json"

    def list_characters(self, campaign_id: str) -> list[CharacterSheet]:
        path = self._characters_path(campaign_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return [CharacterSheet.model_validate(item) for item in payload]

    def upsert_character(
        self, campaign_id: str, sheet: CharacterSheet
    ) -> CharacterSheet:
        items = self.list_characters(campaign_id)
        updated: list[CharacterSheet] = []
        replaced = False
        for item in items:
            if item.name == sheet.name:
                updated.append(sheet)
                replaced = True
            else:
                updated.append(item)
        if not replaced:
            updated.append(sheet)

        path = self._characters_path(campaign_id)
        path.write_text(
            json.dumps(
                [item.model_dump() for item in updated], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        return sheet

    # =========================================================================
    # CHARACTER PROFILE (психология) — отдельный от D&D-листа
    # =========================================================================

    def list_profiles(self, campaign_id: str) -> list[CharacterProfile]:
        """Загружает все психологические профили кампании."""
        path = self._profiles_path(campaign_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return [CharacterProfile.from_dict(item) for item in payload]

    def get_profile(
        self, campaign_id: str, character_name: str
    ) -> Optional[CharacterProfile]:
        """
        Получает профиль персонажа по имени.
        character_name = CharacterSheet.name (ключ связки).
        Returns None если профиль не найден (персонаж без профиля = аватар).
        """
        profiles = self.list_profiles(campaign_id)
        for p in profiles:
            if p.character_id == character_name:
                return p
        return None

    def upsert_profile(
        self, campaign_id: str, profile: CharacterProfile
    ) -> CharacterProfile:
        """Создаёт или обновляет психологический профиль."""
        items = self.list_profiles(campaign_id)
        updated: list[CharacterProfile] = []
        replaced = False
        for item in items:
            if item.character_id == profile.character_id:
                updated.append(profile)
                replaced = True
            else:
                updated.append(item)
        if not replaced:
            updated.append(profile)

        path = self._profiles_path(campaign_id)
        path.write_text(
            json.dumps(
                [item.to_dict() for item in updated], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        return profile

    def get_or_create_profile(
        self, campaign_id: str, character_name: str
    ) -> CharacterProfile:
        """
        Получает профиль или создаёт дефолтный (пустой аватар).
        Используется для безопасного доступа — никогда не возвращает None.
        """
        existing = self.get_profile(campaign_id, character_name)
        if existing:
            return existing

        # Дефолтный профиль — аватар без ценностей
        default = CharacterProfile(character_id=character_name)
        return self.upsert_profile(campaign_id, default)

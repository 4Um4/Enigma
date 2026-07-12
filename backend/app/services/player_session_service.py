"""
Сервис для управления сессиями игроков (heartbeat).
"""

import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)

from datetime import datetime
from typing import Dict, Optional

from app.core.config import settings
from app.models.schemas import PlayerSession


class PlayerSessionService:
    """
    Сервис для отслеживания активности игроков через heartbeat.
    Хранит активные сессии в памяти и на диске (sessions/{campaign_id}.json).

    Single Source of Truth - backend хранит состояние сессий.
    """

    def __init__(self):
        # Словарь: {campaign_id: PlayerSession}
        # Только ОДИН активный игрок на кампанию!
        self._sessions: Dict[str, PlayerSession] = {}
        # TTL для сессий в секундах (сессия считается активной если heartbeat был < TTL секунд назад)
        # Увеличено с 10 до 120 секунд для стабильной работы (ранее вызывало 412 Precondition Failed)
        self.ttl_seconds = 120

        # Директория для хранения сессий на диске
        self._sessions_dir = self._get_sessions_dir()

        # Загружаем сессии с диска при старте
        self._load_sessions_from_disk()

    def _get_sessions_dir(self) -> str:
        """Получить путь к директории сессий."""
        # ADR-O-146: Сессии живут внутри saves/ (runtime world), не data/ (static world)
        # saves/<campaign_id>/session.json — единая точка runtime состояния
        sessions_dir = os.path.join(settings.saves_dir)

        # Создаем директорию если не существует
        if not os.path.exists(sessions_dir):
            os.makedirs(sessions_dir, exist_ok=True)

        return sessions_dir

    def _get_session_file_path(self, campaign_id: str) -> str:
        """Получить путь к файлу сессии кампании."""
        safe_id = campaign_id.replace("/", "_").replace("\\", "_")
        return os.path.join(self._sessions_dir, f"{safe_id}.json")

    def _save_session_to_disk(self, campaign_id: str, session: PlayerSession) -> None:
        """Сохранить сессию на диск."""
        try:
            filepath = self._get_session_file_path(campaign_id)
            data = {
                "campaign_id": session.campaign_id,
                "player_name": session.player_name,
                "active": session.active,
                "last_heartbeat": session.last_heartbeat.isoformat(),
                "session_id": session.session_id,
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"[SESSION_SAVED] Campaign: {campaign_id}, File: {filepath}")
        except Exception as e:
            logger.debug(f"[SESSION_SAVE_ERROR] Campaign: {campaign_id}, Error: {e}")

    def _load_sessions_from_disk(self) -> None:
        """Загрузить сессии с диска при старте."""
        if not os.path.exists(self._sessions_dir):
            return

        try:
            for filename in os.listdir(self._sessions_dir):
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(self._sessions_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Создаем сессию из данных
                    session = PlayerSession(
                        campaign_id=data["campaign_id"],
                        player_name=data["player_name"],
                        active=data.get("active", False),
                        last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]),
                        session_id=data["session_id"],
                    )

                    campaign_id = data["campaign_id"]
                    self._sessions[campaign_id] = session
                    logger.info(
                        f"[SESSION_LOADED] Campaign: {campaign_id}, Player: {session.player_name}"
                    )
                except Exception as e:
                    logger.debug(f"[SESSION_LOAD_ERROR] File: {filename}, Error: {e}")
        except Exception as e:
            logger.debug(f"[SESSION_DIR_ERROR] Error: {e}")

    def _delete_session_from_disk(self, campaign_id: str) -> None:
        """Удалить сессию с диска."""
        try:
            filepath = self._get_session_file_path(campaign_id)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.debug(f"[SESSION_DELETED] Campaign: {campaign_id}")
        except Exception as e:
            logger.debug(f"[SESSION_DELETE_ERROR] Campaign: {campaign_id}, Error: {e}")

    def select_player(self, campaign_id: str, player_name: str) -> PlayerSession:
        """
        Выбрать персонажа и создать новую сессию.
        Атомарная операция - удаляет все существующие сессии для кампании.
        """
        # Удаляем старую сессию (если была)
        if campaign_id in self._sessions:
            old_session = self._sessions[campaign_id]
            logger.debug(
                f"[PLAYER_SESSION_REPLACED] Campaign: {campaign_id}, Old player: {old_session.player_name}"
            )
            # Сброс session_flag делается через game_loop.reset_session_flag() в routes.py

        # Создаем новую сессию
        session = PlayerSession(
            campaign_id=campaign_id,
            player_name=player_name,
            active=True,
            last_heartbeat=datetime.now(),
            session_id=str(uuid.uuid4()),
        )
        self._sessions[campaign_id] = session

        logger.debug(f"[PLAYER_SELECT] Campaign: {campaign_id}, Player: {player_name}")
        logger.debug(f"[PLAYER_SESSION_CREATED] Session ID: {session.session_id}")

        # Форсируем обновление timestamp сразу после создания сессии
        # Это предотвращает 412 при первом action до первого heartbeat
        session.last_heartbeat = datetime.now()

        # Сохраняем на диск
        self._save_session_to_disk(campaign_id, session)

        return session

    def get_session(self, campaign_id: str) -> Optional[PlayerSession]:
        """Получить текущую сессию для кампании."""
        return self._sessions.get(campaign_id)

    def heartbeat(self, campaign_id: str, player_name: str) -> PlayerSession:
        """
        Обновить или создать сессию игрока.
        Возвращает текущее состояние сессии.
        """
        # Проверяем, что игрок соответствует текущей сессии
        if campaign_id in self._sessions:
            existing = self._sessions[campaign_id]
            if existing.player_name != player_name:
                # Игрок пытается обновить чужую сессию
                logger.debug(
                    f"[PLAYER_HEARTBEAT] игнорирован - неверный игрок: {player_name}, ожидается: {existing.player_name}"
                )
                return existing

            # Обновляем существующую сессию
            existing.last_heartbeat = datetime.now()
            existing.active = True
            logger.debug(
                f"[PLAYER_HEARTBEIT] Campaign: {campaign_id}, Player: {player_name}"
            )
            return existing
        else:
            # Сессия не существует, создаем новую (для обратной совместимости)
            session = PlayerSession(
                campaign_id=campaign_id,
                player_name=player_name,
                active=True,
                last_heartbeat=datetime.now(),
                session_id=str(uuid.uuid4()),
            )
            self._sessions[campaign_id] = session
            logger.debug(
                f"[PLAYER_SESSION_CREATED] Campaign: {campaign_id}, Player: {player_name} (from heartbeat)"
            )
            return session

    def is_player_active(self, campaign_id: str, player_name: str = None) -> bool:
        """
        Проверить, активен ли игрок.
        Игрок считается активным если:
        1. Сессия существует для кампании
        2. active = True
        3. last_heartbeat < ttl_seconds назад
        4. (опционально) имя игрока совпадает
        """
        if campaign_id not in self._sessions:
            return False

        session = self._sessions[campaign_id]

        # Если указано имя игрока, проверяем совпадение
        if player_name and session.player_name != player_name:
            return False

        return session.is_active(self.ttl_seconds)

    def get_all_active_players(self, campaign_id: str) -> list[str]:
        """Получить список активных игроков для кампании."""
        if campaign_id in self._sessions and self.is_player_active(campaign_id):
            return [self._sessions[campaign_id].player_name]
        return []

    def deactivate_player(self, campaign_id: str) -> bool:
        """Деактивировать сессию игрока для кампании."""
        if campaign_id in self._sessions:
            self._sessions[campaign_id].active = False
            player_name = self._sessions[campaign_id].player_name
            logger.debug(
                f"[PLAYER_DEACTIVATED] Campaign: {campaign_id}, Player: {player_name}"
            )
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """
        Очистить истекшие сессии.
        Возвращает количество удаленных сессий.
        """
        expired_keys = []

        for campaign_id, session in self._sessions.items():
            if not session.is_active(self.ttl_seconds):
                expired_keys.append(campaign_id)
                logger.debug(
                    f"[PLAYER_SESSION_EXPIRED] Campaign: {campaign_id}, Player: {session.player_name}"
                )

        for campaign_id in expired_keys:
            del self._sessions[campaign_id]

        return len(expired_keys)


# Глобальный экземпляр сервиса
player_session_service = PlayerSessionService()

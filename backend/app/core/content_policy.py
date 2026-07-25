# backend/app/core/content_policy.py
"""
Фундамент системы управления контентом (Content Policy Fundament).
Определяет глобальную политику контента (ContentPolicy) и её загрузку из user_settings.yaml.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

class ContentLevel(IntEnum):
    """Уровень разрешённого контента по одной оси."""
    OFF = 0          # Полный запрет
    MODERATE = 1     # Лёгкие формы, намёки, эвфемизмы
    EXPLICIT = 2     # Полный контент без ограничений

@dataclass(frozen=True)
class ContentPolicy:
    """Глобальная политика контента. Один экземпляр на игру."""
    profanity_level: ContentLevel = ContentLevel.OFF
    sexual_content_level: ContentLevel = ContentLevel.OFF
    violence_level: ContentLevel = ContentLevel.MODERATE
    taboo_practices_level: ContentLevel = ContentLevel.OFF

    @classmethod
    def preset_off(cls) -> "ContentPolicy":
        return cls(
            profanity_level=ContentLevel.OFF,
            sexual_content_level=ContentLevel.OFF,
            violence_level=ContentLevel.OFF,
            taboo_practices_level=ContentLevel.OFF,
        )

    @classmethod
    def preset_moderate(cls) -> "ContentPolicy":
        return cls(
            profanity_level=ContentLevel.MODERATE,
            sexual_content_level=ContentLevel.MODERATE,
            violence_level=ContentLevel.MODERATE,
            taboo_practices_level=ContentLevel.OFF,
        )

    @classmethod
    def preset_explicit(cls) -> "ContentPolicy":
        return cls(
            profanity_level=ContentLevel.EXPLICIT,
            sexual_content_level=ContentLevel.EXPLICIT,
            violence_level=ContentLevel.EXPLICIT,
            taboo_practices_level=ContentLevel.EXPLICIT,
        )

    @property
    def hardcore_mode(self) -> bool:
        """Deprecated alias для обратной совместимости. True, если хотя бы одна ось = EXPLICIT."""
        return any(
            level == ContentLevel.EXPLICIT
            for level in [
                self.profanity_level,
                self.sexual_content_level,
                self.violence_level,
                self.taboo_practices_level,
            ]
        )

def _content_to_dict(policy: ContentPolicy, reason: str = "user_action") -> Dict[str, Any]:
    return {
        "preset": None, # При ручном изменении сбрасываем пресет
        "individual": {
            "profanity_level": int(policy.profanity_level),
            "sexual_content_level": int(policy.sexual_content_level),
            "violence_level": int(policy.violence_level),
            "taboo_practices_level": int(policy.taboo_practices_level),
        },
        "last_changed_tick": 0, # Обновляется при вызове из UI
        "last_changed_reason": reason
    }

def _content_from_dict(data: Dict[str, Any]) -> ContentPolicy:
    preset = data.get("preset")
    if preset:
        if preset == "off":
            return ContentPolicy.preset_off()
        if preset == "moderate":
            return ContentPolicy.preset_moderate()
        if preset == "explicit":
            return ContentPolicy.preset_explicit()

    individual = data.get("individual", {})
    return ContentPolicy(
        profanity_level=ContentLevel(individual.get("profanity_level", 0)),
        sexual_content_level=ContentLevel(individual.get("sexual_content_level", 0)),
        violence_level=ContentLevel(individual.get("violence_level", 1)),
        taboo_practices_level=ContentLevel(individual.get("taboo_practices_level", 0)),
    )

def load_content_policy(settings: Any) -> ContentPolicy:
    """Загружает ContentPolicy из user_settings.yaml."""
    path: Path = getattr(settings, "user_settings_path", Path("config/user_settings.yaml"))

    if not path.exists():
        logger.info("[CONTENT_POLICY] user_settings.yaml not found. Migrating from hardcore_mode.")
        if getattr(settings, "hardcore_mode", True):
            policy = ContentPolicy.preset_explicit()
        else:
            policy = ContentPolicy.preset_off()
        _save_content_section(path, policy, reason="migration")
        return policy

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.error(f"[CONTENT_POLICY] Failed to read {path}: {e}. Fallback to explicit.")
        return ContentPolicy.preset_explicit()

    content_section = data.get("content")

    if content_section is None:
        logger.info("[CONTENT_POLICY] 'content' section missing. Migrating from hardcore_mode.")
        if getattr(settings, "hardcore_mode", True):
            policy = ContentPolicy.preset_explicit()
        else:
            policy = ContentPolicy.preset_off()
        data["content"] = _content_to_dict(policy, reason="migration")
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return policy

    return _content_from_dict(content_section)

def _save_content_section(path: Path, policy: ContentPolicy, reason: str = "user_action") -> None:
    """Сохраняет секцию content в user_settings.yaml."""
    if not path.exists():
        data = {}
    else:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}

    data["content"] = _content_to_dict(policy, reason)
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

def save_content_policy(settings: Any, preset_name: str) -> ContentPolicy:
    """Сохраняет выбранный пресет в user_settings.yaml и перезагружает кэш."""
    path: Path = getattr(settings, "user_settings_path", Path("config/user_settings.yaml"))

    if preset_name == "off":
        policy = ContentPolicy.preset_off()
    elif preset_name == "moderate":
        policy = ContentPolicy.preset_moderate()
    elif preset_name == "explicit":
        policy = ContentPolicy.preset_explicit()
    else:
        logger.warning(f"[CONTENT_POLICY] Unknown preset '{preset_name}'. Fallback to explicit.")
        policy = ContentPolicy.preset_explicit()

    if not path.exists():
        data = {}
    else:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}

    data["content"] = {
        "preset": preset_name,
        "individual": {
            "profanity_level": int(policy.profanity_level),
            "sexual_content_level": int(policy.sexual_content_level),
            "violence_level": int(policy.violence_level),
            "taboo_practices_level": int(policy.taboo_practices_level),
        },
        "last_changed_tick": 0,
        "last_changed_reason": "user_action"
    }
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    # Принудительно перезагружаем кэш в настройках
    return settings.reload_content_policy()

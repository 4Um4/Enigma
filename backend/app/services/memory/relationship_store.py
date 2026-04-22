# backend/app/services/memory/relationship_store.py
"""
R1.4 — Relationship Memory.
Хранит отношения между NPC и игроком в JSON на диске.
Python обновляет после каждого хода. LLM получает готовые числа.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

RELATIONSHIP_KEYS = ("trust", "fear", "debt", "respect")


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class RelationshipStore:
    def __init__(self, data_dir: str = "data") -> None:
        self._root = Path(data_dir)
        # Кэш в RAM — исключает повторные чтения диска за один тик.
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _path(self, campaign_id: str) -> Path:
        folder = self._root / f"campaign_{campaign_id}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "npc_relationships.json"

    def _load(self, campaign_id: str) -> Dict[str, Any]:
        # Возвращаем кэш если он уже загружен — диск не трогаем.
        if campaign_id in self._cache:
            return self._cache[campaign_id]
        path = self._path(campaign_id)
        if not path.exists():
            self._cache[campaign_id] = {}
            return self._cache[campaign_id]
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            self._cache[campaign_id] = data
            return data
        except Exception as e:
            logger.error(f"[RELATIONSHIPS] Ошибка чтения {path}: {e}")
            self._cache[campaign_id] = {}
            return self._cache[campaign_id]

    def _save(self, campaign_id: str, data: Dict[str, Any]) -> None:
        # Обновляем кэш синхронно с диском.
        self._cache[campaign_id] = data
        path = self._path(campaign_id)
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[RELATIONSHIPS] Ошибка записи {path}: {e}")

    def update(
        self,
        campaign_id: str,
        source: str,
        target: str,
        delta: Dict[str, float],
    ) -> None:
        """
        Обновляет отношение source→target на delta.
        Пример: update("c1", "player", "tornin", {"trust": +10, "fear": -5})
        """
        data = self._load(campaign_id)
        key = f"{source}→{target}"
        current = data.get(key, {})
        for attr, change in delta.items():
            if attr not in RELATIONSHIP_KEYS:
                continue
            current_val = float(current.get(attr, 0))
            # Saturation: изменения теряют эффект при приближении к пределу.
            # trust=90 → новый +10 даёт только +1 (10% от полного изменения).
            headroom = (100.0 - abs(current_val)) / 100.0
            effective_change = float(change) * headroom
            current[attr] = _clamp(current_val + effective_change)
        data[key] = current
        self._save(campaign_id, data)

    def get(self, campaign_id: str, source: str) -> Dict[str, Any]:
        """Возвращает все отношения от source."""
        data = self._load(campaign_id)
        return {
            k: v for k, v in data.items()
            if k.startswith(f"{source}→")
        }

    def get_all(self, campaign_id: str) -> Dict[str, Any]:
        """Возвращает весь граф отношений кампании."""
        return self._load(campaign_id)

    def get_all_for_source(
        self,
        campaign_id: str,
        source: str,
    ) -> Dict[str, Dict[str, float]]:
        """
        Возвращает {target_id: {trust, fear, debt, respect}} для всех target.
        Decision Hub вызывает один раз за тик — не по одной паре.
        """
        if not source:
            return {}
        data = self._load(campaign_id)
        prefix = f"{source}→"
        return {
            key.split("→")[1]: {
                attr: float(data[key].get(attr, 0.0))
                for attr in RELATIONSHIP_KEYS
            }
            for key in data
            if key.startswith(prefix)
        }

    def reset_campaign(self, campaign_id: str) -> int:
        """Сбрасывает все отношения для кампании. Для миграции после бага #7."""
        path = self._path(campaign_id)
        if not path.exists():
            return 0
        data = self._load(campaign_id)
        count = len(data)
        if count == 0:
            return 0
        # Сохраняем пустой словарь
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if not data else "{}", encoding="utf-8")
        logger.warning(f"[RELATIONSHIPS] Сброшено {count} записей для {campaign_id} (миграция бага #7)")
        return count

    def get_pair(
        self,
        campaign_id: str,
        source: str,
        target: str,
    ) -> Dict[str, float]:
        """Возвращает отношение source→target как числовой словарь.
        Используется Decision Hub для получения весов формулы score().
        Если пара не существует — возвращает нули (нейтральные отношения).
        """
        if not source or not target:
            return {attr: 0.0 for attr in RELATIONSHIP_KEYS}
        data = self._load(campaign_id)
        key  = f"{source}→{target}"
        raw  = data.get(key, {})
        # Нормализация: хранится -100..100, DecisionHub ожидает -1.0..1.0.
        # Saturation встроена через _clamp при записи — здесь только масштаб.
        return {
            attr: round(float(raw.get(attr, 0.0)) / 100.0, 4)
            for attr in RELATIONSHIP_KEYS
        }


# backend/app/services/npc/expectation_store.py
"""
Назначение: Персистентное хранилище ожиданий NPC (EMA). Обновляется строго через StateApplicator.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: Expectation, ExpectationStore
"""


import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass, asdict
import sqlite3
import json

_logger = logging.getLogger(__name__)

@dataclass
class Expectation:
    source_id: str
    expected_reward: float = 0.0
    expected_threat: float = 0.0
    confidence: float = 0.1  # Базовая неуверенность

class ExpectationStore:
    """S-93: Pure projection store for Free Energy Principle.
    Хранит EMA ожиданий наград/угроз от источников (игрока).
    """
    _LEARNING_RATE = 0.3  # Alpha для EMA

    def __init__(self, db_path: str = "memory.db"):
        self._db_path = db_path
        self._cache: Dict[Tuple[str, str], Expectation] = {}
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS npc_expectations (
                    npc_id TEXT,
                    source_id TEXT,
                    expected_reward REAL,
                    expected_threat REAL,
                    confidence REAL,
                    PRIMARY KEY (npc_id, source_id)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            _logger.error(f"[EXPECTATION_STORE] DB init failed: {e}")

    def get_expectation(self, npc_id: str, source_id: str) -> Expectation:
        key = (npc_id, source_id)
        if key in self._cache:
            return self._cache[key]
        
        # Fallback to DB
        try:
            conn = sqlite3.connect(self._db_path)
            cur = conn.cursor()
            cur.execute("SELECT expected_reward, expected_threat, confidence FROM npc_expectations WHERE npc_id=? AND source_id=?", (npc_id, source_id))
            row = cur.fetchone()
            conn.close()
            if row:
                exp = Expectation(source_id=source_id, expected_reward=row[0], expected_threat=row[1], confidence=row[2])
                self._cache[key] = exp
                return exp
        except Exception:
            pass
        
        # Default
        exp = Expectation(source_id=source_id)
        self._cache[key] = exp
        return exp

    def decay(self, dt_game_seconds: float) -> None:
        """S-93: Затухание ожиданий. Вызывается в Phase 0.5."""
        if dt_game_seconds <= 0: return
        _decay_rate = 0.01  # 1% в секунду
        _factor = math.exp(-_decay_rate * dt_game_seconds)
        
        for key, exp in self._cache.items():
            exp.expected_reward *= _factor
            exp.expected_threat *= _factor
            exp.confidence *= _factor

    def update_expectation(self, npc_id: str, source_id: str, actual_reward: float, actual_threat: float):
        key = (npc_id, source_id)
        exp = self.get_expectation(npc_id, source_id)
        
        # EMA Update
        exp.expected_reward = (1 - self._LEARNING_RATE) * exp.expected_reward + self._LEARNING_RATE * actual_reward
        exp.expected_threat = (1 - self._LEARNING_RATE) * exp.expected_threat + self._LEARNING_RATE * actual_threat
        
        # Confidence grows with observations
        exp.confidence = min(1.0, exp.confidence + 0.05)
        
        self._cache[key] = exp
        
        # Persist
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT OR REPLACE INTO npc_expectations (npc_id, source_id, expected_reward, expected_threat, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (npc_id, source_id, exp.expected_reward, exp.expected_threat, exp.confidence))
            conn.commit()
            conn.close()
        except Exception as e:
            _logger.error(f"[EXPECTATION_STORE] Failed to persist: {e}")
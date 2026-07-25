"""
path: backend/app/services/npc/crystallized_belief_store.py
Назначение: Хранилище кристаллизованных убеждений NPC (L2.5) с SQLite-персистентностью.
Зависимости: backend/app/domain/identity_events.py, app.services.memory.sqlite_store
Основные сущности: CrystallizedBeliefStore
"""

import logging
from typing import Any, Dict, List, Optional

from app.domain.identity_events import CrystallizedBelief

_logger = logging.getLogger(__name__)


class CrystallizedBeliefStore:
    """
    Хранилище убеждений, кристаллизованных BeliefCrystallizationEngine.

    ADR-O-305: Разделено от BeliefState (R7/R8), чтобы избежать DOUBLE TRUTH.
    DEEP-013: Добавлена SQLite-персистентность. Убеждения переживают рестарт.
    """

    def __init__(self, store: Optional[Any] = None, campaign_id: str = ""):
        self._store = store
        self._campaign_id = campaign_id
        self._beliefs: Dict[str, List[CrystallizedBelief]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy load из SQLite при первом обращении."""
        if self._loaded or self._store is None:
            return

        if not self._campaign_id:
            self._loaded = True
            return

        try:
            # Создаём таблицу, если её нет
            self._store.execute("""
                CREATE TABLE IF NOT EXISTS crystallized_beliefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    npc_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    trait TEXT NOT NULL,
                    weight REAL NOT NULL,
                    last_updated_tick INTEGER NOT NULL
                )
            """)
            self._store.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_belief_unique
                ON crystallized_beliefs(campaign_id, npc_id, source_id, trait)
            """)

            rows = self._store.query(
                "SELECT npc_id, source_id, trait, weight, last_updated_tick "
                "FROM crystallized_beliefs "
                "WHERE campaign_id = ?",
                (self._campaign_id,),
            )
            for row in rows:
                npc_id = row["npc_id"]
                if npc_id not in self._beliefs:
                    self._beliefs[npc_id] = []
                self._beliefs[npc_id].append(
                    CrystallizedBelief(
                        source_id=row["source_id"],
                        trait=row["trait"],
                        weight=row["weight"],
                        last_updated_tick=row["last_updated_tick"],
                    )
                )
        except Exception as e:
            _logger.error(f"[BELIEF_STORE] Failed to load from SQLite: {e}", exc_info=True)
        finally:
            self._loaded = True

    def get_beliefs(self, npc_id: str) -> List[CrystallizedBelief]:
        """Чтение убеждений NPC для передачи в резолвер."""
        self._ensure_loaded()
        return self._beliefs.get(npc_id, [])

    def query_all(self, npc_id: str) -> List[CrystallizedBelief]:
        """SHI-FIX: Alias for get_beliefs for causal_validation test."""
        return self.get_beliefs(npc_id)

    def update_beliefs(self, npc_id: str, beliefs: List[CrystallizedBelief]) -> None:
        """Запись обновлённых убеждений после работы BeliefCrystallizationEngine."""
        self._ensure_loaded()
        self._beliefs[npc_id] = beliefs

        if self._store is not None and self._campaign_id:
            try:
                # Удаляем старые убеждения этого NPC
                self._store.execute(
                    "DELETE FROM crystallized_beliefs WHERE campaign_id = ? AND npc_id = ?",
                    (self._campaign_id, npc_id),
                )
                # Вставляем новые
                for b in beliefs:
                    self._store.execute(
                        "INSERT INTO crystallized_beliefs "
                        "(campaign_id, npc_id, source_id, trait, weight, last_updated_tick) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            self._campaign_id,
                            npc_id,
                            b.source_id,
                            b.trait,
                            b.weight,
                            b.last_updated_tick,
                        ),
                    )
            except Exception as e:
                _logger.error(f"[BELIEF_STORE] Failed to save beliefs for {npc_id}: {e}", exc_info=True)

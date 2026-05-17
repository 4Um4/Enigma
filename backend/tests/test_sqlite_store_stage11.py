"""Этап 11 — Тесты SqliteMemoryStore.

path: backend/tests/test_sqlite_store_stage11.py
Назначение: Тесты SqliteMemoryStore — append/recent, save/load EventMemory, batch atomic, rollback при ошибке
Зависимости: pytest, app.services.memory.sqlite_store.SqliteMemoryStore, tempfile
Основные сущности: TestSqliteStoreBasic, TestSqliteEventMemory, TestSqliteBatch

Покрывает:
- append / recent (совместимость с JsonMemoryStore)
- save_event_memory / load_event_memories (структурированное API)
- save_event_memories_batch (atomic commit — Закон 4.2.1)
- rollback при ошибке в batch
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from app.services.memory.sqlite_store import SqliteMemoryStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Изолированная БД для каждого теста."""
    return tmp_path / "test_memory.db"


@pytest.fixture
def store(db_path: Path) -> SqliteMemoryStore:
    """Свежий store с инициализированной схемой."""
    s = SqliteMemoryStore(db_path)
    yield s
    s.close()


# ── Совместимость с JsonMemoryStore ────────────────────────────────────


class TestSqliteStoreBasic:
    """append / recent — drop-in замена JsonMemoryStore."""

    def test_append_returns_id(self, store: SqliteMemoryStore) -> None:
        doc_id = store.append("test_coll", {"key": "value"})
        assert isinstance(doc_id, str)
        assert len(doc_id) > 0

    def test_append_stores_payload(self, store: SqliteMemoryStore) -> None:
        payload = {"action": "talk", "npc": "lusya"}
        store.append("events", payload)
        recent = store.recent("events", limit=1)
        assert len(recent) == 1
        # recent() возвращает payload + id и timestamp из entries
        assert recent[0]["action"] == "talk"
        assert recent[0]["npc"] == "lusya"

    def test_recent_returns_latest_first(self, store: SqliteMemoryStore) -> None:
        for i in range(5):
            store.append("nums", {"n": i})
        recent = store.recent("nums", limit=3)
        assert len(recent) == 3
        # Последние записанные — первые в результате (DESC по timestamp)
        assert recent[0]["n"] == 4
        assert recent[2]["n"] == 2

    def test_recent_empty_collection(self, store: SqliteMemoryStore) -> None:
        assert store.recent("nonexistent", limit=10) == []

    def test_multiple_collections_isolated(self, store: SqliteMemoryStore) -> None:
        store.append("coll_a", {"x": 1})
        store.append("coll_b", {"x": 2})
        assert len(store.recent("coll_a")) == 1
        assert len(store.recent("coll_b")) == 1


# ── Структурированное API: EventMemory ─────────────────────────────────


class TestSqliteEventMemory:
    """save_event_memory / load_event_memories — чтение и запись EventMemory."""

    def _sample_memory(self, npc_id: str = "maid_lusya", **overrides: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "npc_id": npc_id,
            "event_type": "player_interacts",
            "target_id": "player",
            "emotion_tag": "neutral",
            "summary": "Игрок поздоровался",
            "day": 5,
            "importance": 0.6,
            "accessibility": 1.0,
            "clarity": 0.9,
            "confidence": 0.8,
            "decay_rate": 0.05,
            "stage": "FRESH",
            "sequence_id": 0,
            "tags": ("player_interacts", "neutral"),
            "is_secret": False,
            "known_by": (),
            "hidden_from": (),
            "fulfilled": False,
            "contract_ref": "",
            "is_compressed": False,
            "compressed_from": (),
        }
        base.update(overrides)
        return base

    def test_save_and_load_single(self, store: SqliteMemoryStore) -> None:
        mem = self._sample_memory()
        store.save_event_memory("mem_001", "camp_1", mem)
        loaded = store.load_event_memories("camp_1", "maid_lusya")
        assert len(loaded) == 1
        assert loaded[0]["summary"] == "Игрок поздоровался"
        assert loaded[0]["importance"] == 0.6

    def test_load_returns_tuples_not_lists(self, store: SqliteMemoryStore) -> None:
        """tags, known_by, hidden_from должны быть tuple — как в EventMemory."""
        mem = self._sample_memory(
            tags=("a", "b"),
            known_by=("npc_1",),
            hidden_from=("player",),
        )
        store.save_event_memory("mem_002", "camp_1", mem)
        loaded = store.load_event_memories("camp_1", "maid_lusya")
        assert isinstance(loaded[0]["tags"], tuple)
        assert isinstance(loaded[0]["known_by"], tuple)
        assert isinstance(loaded[0]["hidden_from"], tuple)

    def test_load_filters_by_campaign_and_npc(self, store: SqliteMemoryStore) -> None:
        store.save_event_memory("m1", "camp_1", self._sample_memory(npc_id="npc_a"))
        store.save_event_memory("m2", "camp_1", self._sample_memory(npc_id="npc_b"))
        store.save_event_memory("m3", "camp_2", self._sample_memory(npc_id="npc_a"))

        assert len(store.load_event_memories("camp_1", "npc_a")) == 1
        assert len(store.load_event_memories("camp_1", "npc_b")) == 1
        assert len(store.load_event_memories("camp_2", "npc_a")) == 1

    def test_load_ordered_by_importance_desc(self, store: SqliteMemoryStore) -> None:
        store.save_event_memory("m1", "c1", self._sample_memory(importance=0.3))
        store.save_event_memory("m2", "c1", self._sample_memory(importance=0.9))
        store.save_event_memory("m3", "c1", self._sample_memory(importance=0.5))

        loaded = store.load_event_memories("c1", "maid_lusya")
        assert [m["importance"] for m in loaded] == [0.9, 0.5, 0.3]

    def test_secret_fields_preserved(self, store: SqliteMemoryStore) -> None:
        mem = self._sample_memory(
            is_secret=True,
            hidden_from=("player", "guard"),
            contract_ref="promise_001",
            fulfilled=False,
        )
        store.save_event_memory("m_sec", "c1", mem)
        loaded = store.load_event_memories("c1", "maid_lusya")
        assert loaded[0]["is_secret"] is True
        assert loaded[0]["hidden_from"] == ("player", "guard")
        assert loaded[0]["contract_ref"] == "promise_001"
        assert loaded[0]["fulfilled"] is False

    def test_compressed_fields_preserved(self, store: SqliteMemoryStore) -> None:
        mem = self._sample_memory(
            is_compressed=True,
            compressed_from=("evt_1", "evt_2", "evt_3"),
        )
        store.save_event_memory("m_comp", "c1", mem)
        loaded = store.load_event_memories("c1", "maid_lusya")
        assert loaded[0]["is_compressed"] is True
        assert loaded[0]["compressed_from"] == ("evt_1", "evt_2", "evt_3")

    def test_save_accepts_dataclass(self, store: SqliteMemoryStore) -> None:
        """Если передали dataclass EventMemory — сериализуется автоматически."""
        from app.models.npc_state import EventMemory

        mem_dc = EventMemory(
            event_type="player_attacks",
            target_id="maid_lusya",
            emotion_tag="angry",
            day=1,
            importance=0.9,
            summary="Игрок ударил Люсю",
            npc_id="maid_lusya",
            tags=("player_attacks", "negative"),
        )
        store.save_event_memory("dc_001", "c1", mem_dc)
        loaded = store.load_event_memories("c1", "maid_lusya")
        assert len(loaded) == 1
        assert loaded[0]["summary"] == "Игрок ударил Люсю"
        assert loaded[0]["event_type"] == "player_attacks"

    def test_load_empty_returns_empty_list(self, store: SqliteMemoryStore) -> None:
        assert store.load_event_memories("no_camp", "no_npc") == []


# ── Batch atomic commit (Закон 4.2.1) ──────────────────────────────────


class TestSqliteBatch:
    """save_event_memories_batch — всё или ничего."""

    def _make_memories(self, count: int, npc_id: str = "npc_1") -> list:
        return [
            {
                "npc_id": npc_id,
                "event_type": "test_event",
                "summary": f"Событие {i}",
                "importance": 0.5 + i * 0.1,
                "accessibility": 1.0,
                "clarity": 0.8,
                "confidence": 0.9,
                "decay_rate": 0.05,
                "stage": "FRESH",
                "sequence_id": i,
                "tags": ("test",),
                "is_secret": False,
                "known_by": (),
                "hidden_from": (),
                "fulfilled": False,
                "contract_ref": "",
                "is_compressed": False,
                "compressed_from": (),
            }
            for i in range(count)
        ]

    def test_batch_saves_all(self, store: SqliteMemoryStore) -> None:
        mems = self._make_memories(5)
        store.save_event_memories_batch("camp_1", "npc_1", mems)
        loaded = store.load_event_memories("camp_1", "npc_1")
        assert len(loaded) == 5

    def test_batch_uses_sequence_id_for_mem_id(self, store: SqliteMemoryStore) -> None:
        mems = self._make_memories(3)
        store.save_event_memories_batch("c1", "npc_1", mems)
        # Должны быть доступны по id npc_1_seq_0, npc_1_seq_1, npc_1_seq_2
        row = store._conn.execute(
            "SELECT id FROM event_memories WHERE npc_id = 'npc_1' AND campaign_id = 'c1' ORDER BY sequence_id"
        ).fetchall()
        ids = [r["id"] for r in row]
        assert ids == ["npc_1_seq_0", "npc_1_seq_1", "npc_1_seq_2"]

    def test_batch_rollback_on_bad_data(self, store: SqliteMemoryStore) -> None:
        """Если одно воспоминание невалидно — все откатываются (Закон 4.2.1)."""
        mems = self._make_memories(3)
        # Вставляем невалидные данные — None вместо dict
        mems.insert(1, None)  # type: ignore[assignment]

        store.save_event_memories_batch("c1", "npc_1", mems)
        loaded = store.load_event_memories("c1", "npc_1")
        # Роллбек — ничего не должно сохраниться
        assert len(loaded) == 0

    def test_batch_isolated_between_npcs(self, store: SqliteMemoryStore) -> None:
        store.save_event_memories_batch("c1", "npc_a", self._make_memories(2, "npc_a"))
        store.save_event_memories_batch("c1", "npc_b", self._make_memories(3, "npc_b"))
        assert len(store.load_event_memories("c1", "npc_a")) == 2
        assert len(store.load_event_memories("c1", "npc_b")) == 3

    def test_batch_overwrite_replaces(self, store: SqliteMemoryStore) -> None:
        """INSERT OR REPLACE — повторный batch с теми же sequence_id перезаписывает."""
        mems_v1 = self._make_memories(2)
        store.save_event_memories_batch("c1", "npc_1", mems_v1)

        # Обновляем summary для seq 0
        mems_v2 = self._make_memories(2)
        mems_v2[0]["summary"] = "Обновлённое событие"
        store.save_event_memories_batch("c1", "npc_1", mems_v2)

        loaded = store.load_event_memories("c1", "npc_1")
        assert len(loaded) == 2
        summaries = [m["summary"] for m in loaded]
        assert "Обновлённое событие" in summaries


# ── YAML export ────────────────────────────────────────────────────────


class TestYamlExport:
    """Этап 11.6 — дамп из SQLite в YAML (Закон 4.2.2)."""

    def _seed_memories(self, store: SqliteMemoryStore, count: int = 3) -> None:
        for i in range(count):
            store.save_event_memory(
                f"ym_{i}",
                "camp_yaml",
                {
                    "npc_id": "npc_yaml",
                    "event_type": "test",
                    "summary": f"Воспоминание {i}",
                    "importance": 0.5 + i * 0.15,
                    "accessibility": 1.0,
                    "clarity": 0.8,
                    "confidence": 0.9,
                    "decay_rate": 0.05,
                    "stage": "FRESH",
                    "sequence_id": i,
                    "tags": ("test",),
                    "is_secret": False,
                    "known_by": (),
                    "hidden_from": (),
                    "fulfilled": False,
                    "contract_ref": "",
                    "is_compressed": False,
                    "compressed_from": (),
                },
            )

    def test_export_npc_returns_yaml_string(self, store: SqliteMemoryStore) -> None:
        self._seed_memories(store)
        from app.services.memory.yaml_export import export_npc_memories_to_yaml

        result = export_npc_memories_to_yaml(store, "camp_yaml", "npc_yaml")
        assert "воспоминаний: 3" in result
        assert "Воспоминание 0" in result
        assert "важность:" in result

    def test_export_npc_writes_file(self, store: SqliteMemoryStore, tmp_path: Path) -> None:
        self._seed_memories(store)
        from app.services.memory.yaml_export import export_npc_memories_to_yaml

        out = tmp_path / "npc_yaml.yaml"
        export_npc_memories_to_yaml(store, "camp_yaml", "npc_yaml", out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "кампания: camp_yaml" in content

    def test_export_campaign_multiple_npcs(self, store: SqliteMemoryStore, tmp_path: Path) -> None:
        store.save_event_memory(
            "a1", "camp_multi",
            {"npc_id": "npc_a", "event_type": "t", "summary": "A", "importance": 0.5,
             "accessibility": 1.0, "clarity": 0.8, "confidence": 0.9, "decay_rate": 0.05,
             "stage": "FRESH", "sequence_id": 0, "tags": (), "is_secret": False,
             "known_by": (), "hidden_from": (), "fulfilled": False, "contract_ref": "",
             "is_compressed": False, "compressed_from": ()},
        )
        store.save_event_memory(
            "b1", "camp_multi",
            {"npc_id": "npc_b", "event_type": "t", "summary": "B", "importance": 0.7,
             "accessibility": 1.0, "clarity": 0.8, "confidence": 0.9, "decay_rate": 0.05,
             "stage": "FRESH", "sequence_id": 0, "tags": (), "is_secret": False,
             "known_by": (), "hidden_from": (), "fulfilled": False, "contract_ref": "",
             "is_compressed": False, "compressed_from": ()},
        )
        from app.services.memory.yaml_export import export_campaign_to_yaml

        count = export_campaign_to_yaml(store, "camp_multi", tmp_path)
        assert count == 2
        assert (tmp_path / "npc_a.yaml").exists()
        assert (tmp_path / "npc_b.yaml").exists()

    def test_export_empty_returns_empty_string(self, store: SqliteMemoryStore) -> None:
        from app.services.memory.yaml_export import export_npc_memories_to_yaml

        result = export_npc_memories_to_yaml(store, "no_camp", "no_npc")
        assert result == ""

    def test_export_secret_shows_hidden_flag(self, store: SqliteMemoryStore) -> None:
        store.save_event_memory(
            "sec1", "camp_s",
            {"npc_id": "npc_s", "event_type": "t", "summary": "Тайна",
             "importance": 0.8, "accessibility": 1.0, "clarity": 0.8, "confidence": 0.9,
             "decay_rate": 0.05, "stage": "FRESH", "sequence_id": 0,
             "tags": (), "is_secret": True, "known_by": (), "hidden_from": ("player",),
             "fulfilled": False, "contract_ref": "", "is_compressed": False, "compressed_from": ()},
        )
        from app.services.memory.yaml_export import export_npc_memories_to_yaml

        result = export_npc_memories_to_yaml(store, "camp_s", "npc_s")
        assert "секрет: true" in result
        assert "скрыто_от:" in result
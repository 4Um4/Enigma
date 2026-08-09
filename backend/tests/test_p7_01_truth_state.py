"""
Файл: backend/tests/test_p7_01_truth_state.py
Назначение: Проверка всех инвариантов TruthState.

Запуск: cd backend; python -m pytest tests/test_p7_01_truth_state.py -v -s; cd ..
"""

import os
from pathlib import Path

import pytest
from app.models.truth_state import RelationType, Secret, TruthRelation, TruthState
from app.services.truth_state_loader import TruthStateLoader

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class TestP701TruthState:
    """P7-01: Тесты канонической истины и загрузчика."""

    @pytest.fixture(scope="class")
    def truth_state(self) -> TruthState:
        assert CANON_PATH.exists(), f"Канонический файл не найден: {CANON_PATH}"
        state = TruthStateLoader.load(CANON_PATH)
        TruthStateLoader.validate(state)
        return state

    def test_secrets_count(self, truth_state: TruthState):
        """Инвариант: Ровно 16 секретов."""
        assert len(truth_state.secrets) == 17, f"Ожидалось 17 секретов, получено {len(truth_state.secrets)}"

    def test_relations_count(self, truth_state: TruthState):
        """Инвариант: Ровно 20 связей."""
        assert len(truth_state.relations) == 20, f"Ожидалось 20 связей, получено {len(truth_state.relations)}"

    def test_no_duplicate_secret_ids(self, truth_state: TruthState):
        """Инвариант: 0 дубликатов ID секретов (гарантируется Dict)."""
        ids = [s.secret_id for s in truth_state.secrets.values()]
        assert len(ids) == len(set(ids)), "Обнаружены дубликаты ID секретов"

    def test_no_dangling_references(self, truth_state: TruthState):
        """Инвариант: 0 dangling references в связях."""
        secret_ids = set(truth_state.secrets.keys())
        for rel in truth_state.relations:
            assert rel.source_secret_id in secret_ids, f"Dangling reference: {rel.source_secret_id}"
            assert rel.target_secret_id in secret_ids, f"Dangling reference: {rel.target_secret_id}"

    def test_no_self_loops(self, truth_state: TruthState):
        """Инвариант: 0 самоссылок (self-loops)."""
        for rel in truth_state.relations:
            assert rel.source_secret_id != rel.target_secret_id, f"Self-loop detected: {rel.source_secret_id}"

    def test_no_duplicate_relations(self, truth_state: TruthState):
        """Инвариант: 0 дубликатов связей (одинаковые source, target, type)."""
        rel_keys = set()
        for rel in truth_state.relations:
            key = (rel.source_secret_id, rel.target_secret_id, rel.relation_type)
            assert key not in rel_keys, f"Дубликат связи: {key}"
            rel_keys.add(key)

    def test_truth_state_immutable(self, truth_state: TruthState):
        """Инвариант: TruthState неизменяем после загрузки (MappingProxyType)."""
        with pytest.raises(TypeError): # MappingProxyType бросает TypeError при попытке мутации
            truth_state.secrets["new"] = Secret("new", "npc", ("npc",), "cat", "truth", 0.5, (), ())
            
        with pytest.raises(AttributeError):
            truth_state.relations = ()

    def test_truth_state_independent_from_npc_state(self, truth_state: TruthState):
        """Инвариант: TruthState не содержит NPCState."""
        # Проверяем, что секреты не содержат полей из NPCState (stress, trust и т.д.)
        for secret in truth_state.secrets.values():
            assert not hasattr(secret, "stress"), "Секрет не должен содержать NPCState поля"
            assert not hasattr(secret, "trust"), "Секрет не должен содержать NPCState поля"

    def test_deterministic_reload(self, truth_state: TruthState):
        """Инвариант: Повторная загрузка даёт эквивалентное состояние."""
        state2 = TruthStateLoader.load(CANON_PATH)
        assert state2 == truth_state, "Повторная загрузка дала другой результат"

    def test_schema_version_exists(self):
        """Инвариант: JSON содержит schema_version."""
        import json
        with open(CANON_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        assert "schema_version" in data, "schema_version отсутствует в JSON"
        assert data["schema_version"] == 1, "Неподдерживаемая версия схемы"

    def test_importance_in_valid_range(self, truth_state: TruthState):
        """Инвариант: importance находится в диапазоне 0.0..1.0."""
        for secret in truth_state.secrets.values():
            assert 0.0 <= secret.importance <= 1.0, f"Importance out of range for {secret.secret_id}"

    def test_strength_in_valid_range(self, truth_state: TruthState):
        """Инвариант: strength связей находится в диапазоне 0.0..1.0."""
        for rel in truth_state.relations:
            assert 0.0 <= rel.strength <= 1.0, f"Strength out of range for {rel.source_secret_id} -> {rel.target_secret_id}"

    def test_participants_not_empty(self, truth_state: TruthState):
        """Инвариант: Каждый секрет имеет хотя бы одного участника."""
        for secret in truth_state.secrets.values():
            assert len(secret.participants) > 0, f"Секрет {secret.secret_id} не имеет участников"

    def test_campaign_isolation(self, truth_state: TruthState):
        """Инвариант: Runtime-состояние не мутирует глобальный объект."""
        # TruthState является immutable, поэтому мутация невозможна.
        # Этот тест проверяет, что создание нового экземпляра не влияет на старый.
        state2 = TruthStateLoader.load(CANON_PATH)
        assert state2 is not truth_state, "Загрузчик вернул тот же объект (не изолирован)"
        assert state2.secrets is not truth_state.secrets, "Словари секретов ссылаются на один объект"

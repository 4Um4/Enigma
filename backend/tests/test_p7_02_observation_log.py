"""
Файл: backend/tests/test_p7_02_observation_log.py
Назначение: Проверка логики добавления и фильтрации наблюдений.

Запуск: cd backend; python -m pytest tests/test_p7_02_observation_log.py -v -s; cd ..
"""

import pytest
from app.models.observation import ObservationSourceType
from app.services.player_cognition.observation_log import ObservationLog


class TestP702ObservationLog:
    """P7-02: Тесты сырых наблюдений и доказательств."""

    @pytest.fixture
    def log(self) -> ObservationLog:
        return ObservationLog()

    def test_add_raw_observation(self, log: ObservationLog):
        """Сырое наблюдение добавляется без секретов и уверенности."""
        obs = log.add(
            tick=1,
            observation_type="visual_cue",
            content="Люся оглядывается на дверь подвала",
            source_id="maid_lusya",
            source_type=ObservationSourceType.NPC
        )
        
        assert obs.observation_id == 1
        assert obs.content == "Люся оглядывается на дверь подвала"
        assert not hasattr(obs, "secret_hint"), "Сырое наблюдение не должно содержать secret_hint"
        assert not hasattr(obs, "confidence"), "Сырое наблюдение не должно содержать confidence"

    def test_add_evidence_link(self, log: ObservationLog):
        """Доказательство связывает наблюдение с секретом."""
        obs = log.add(tick=1, observation_type="visual_cue", content="Оглядывается", source_id="maid_lusya", source_type=ObservationSourceType.NPC)
        ev = log.add_evidence(obs.observation_id, "lusya_basement", 0.3)
        
        assert ev.observation_id == obs.observation_id
        assert ev.secret_id == "lusya_basement"
        assert ev.evidence_strength == 0.3

    def test_filter_by_source(self, log: ObservationLog):
        """Фильтрация по источнику (NPC)."""
        log.add(tick=1, observation_type="dialogue", content="Привет", source_id="maid_lusya", source_type=ObservationSourceType.NPC)
        log.add(tick=2, observation_type="dialogue", content="Стой!", source_id="guard_borko", source_type=ObservationSourceType.NPC)
        
        lusya_obs = log.get_for_source("maid_lusya")
        assert len(lusya_obs) == 1
        assert lusya_obs[0].source_id == "maid_lusya"

    def test_filter_evidence_by_secret(self, log: ObservationLog):
        """Фильтрация доказательств по секрету."""
        obs1 = log.add(tick=1, observation_type="visual_cue", content="Оглядывается", source_id="maid_lusya", source_type=ObservationSourceType.NPC)
        obs2 = log.add(tick=2, observation_type="eavesdrop", content="Будь готова", source_id="thief_shadow", source_type=ObservationSourceType.NPC)
        
        log.add_evidence(obs1.observation_id, "lusya_basement", 0.3)
        log.add_evidence(obs2.observation_id, "lusya_shadow_orders", 0.5)
        log.add_evidence(obs1.observation_id, "lusya_basement", 0.2) # Двойное доказательство
        
        basement_ev = log.get_evidence_for_secret("lusya_basement")
        assert len(basement_ev) == 2
        assert all(e.secret_id == "lusya_basement" for e in basement_ev)

    def test_observation_validation(self, log: ObservationLog):
        """Валидация: tick >= 0, content не пустой."""
        with pytest.raises(ValueError):
            log.add(tick=-1, observation_type="x", content="valid", source_id="y", source_type=ObservationSourceType.NPC)
        with pytest.raises(ValueError):
            log.add(tick=1, observation_type="x", content="   ", source_id="y", source_type=ObservationSourceType.NPC)

    def test_evidence_validation(self, log: ObservationLog):
        """Валидация: strength в [0, 1], observation_id существует."""
        obs = log.add(tick=1, observation_type="x", content="valid", source_id="y", source_type=ObservationSourceType.NPC)
        with pytest.raises(ValueError):
            log.add_evidence(obs.observation_id, "sec", 1.5)
        with pytest.raises(ValueError):
            log.add_evidence(999, "sec", 0.5) # Несуществующий obs_id
"""
Файл: backend/tests/test_world_continuity.py
Назначение: TDD тест инварианта WorldContinuityMode (ISOLATED vs CONTINUOUS).
Запуск: cd backend; python -m pytest tests/test_world_continuity.py -v; cd ..
"""

import pytest
from app.models.world_state_diff import WorldStateDiff
from app.services.state.world_diff_applicator import WorldStateApplicator
from app.models.world_continuity import WorldContinuityMode

class TestWorldContinuity:
    """Проверка опциональности и изоляции персистентности."""

    @pytest.fixture
    def mock_diff(self) -> WorldStateDiff:
        """Diff, где Горан мёртв, а Люся сбежала."""
        return WorldStateDiff(
            npc_fates={"merchant_goran": "killed_by_guild", "maid_lusya": "escaped"},
            faction_alignments={"гильдия_воров": -100.0},
            secrets_exposed={"goran_contraband": True},
            world_events=["goran_killed", "lusya_escaped"],
            player_reputation={"гильдия_воров": "enemy"}
        )

    def test_isolated_mode_ignores_diff(self, mock_diff: WorldStateDiff):
        """В ISOLATED режиме diff не должен менять состояние NPC."""
        applicator = WorldStateApplicator(mode=WorldContinuityMode.ISOLATED)
        
        # Имитируем кэш NPC новой кампании
        npc_cache = {
            "merchant_goran": {"life_status": "ALIVE"},
            "maid_lusya": {"life_status": "ALIVE"}
        }
        
        applicator.apply(diff=mock_diff, npc_cache=npc_cache)
        
        # Проверяем, что NPC остались живы (diff проигнорирован)
        assert npc_cache["merchant_goran"]["life_status"] == "ALIVE"
        assert npc_cache["maid_lusya"]["life_status"] == "ALIVE"

    def test_continuous_mode_applies_fate(self, mock_diff: WorldStateDiff):
        """В CONTINUOUS режиме судьбы из diff должны примениться к NPC."""
        applicator = WorldStateApplicator(mode=WorldContinuityMode.CONTINUOUS)
        
        npc_cache = {
            "merchant_goran": {"life_status": "ALIVE"},
            "maid_lusya": {"life_status": "ALIVE"}
        }
        
        applicator.apply(diff=mock_diff, npc_cache=npc_cache)
        
        # Проверяем, что Горан мёртв, а Люся удалена/сбежала
        assert npc_cache["merchant_goran"]["life_status"] == "DEAD"
        assert "maid_lusya" not in npc_cache # Сбежавшие удаляются из кэша

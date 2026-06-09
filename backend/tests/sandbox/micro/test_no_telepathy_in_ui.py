"""
path: backend/tests/sandbox/micro/test_no_telepathy_in_ui.py
Назначение: Верификация Rule 11 (Нет телепатии в UI) и контракта WorldSnapshotDTO
Зависимости: app.domain.snapshot
Основные сущности: WorldSnapshotDTO, NPCPositionDTO

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_no_telepathy_in_ui.py -v --tb=short; cd ..
"""
import pytest
from app.domain.snapshot import WorldSnapshotDTO, NPCPositionDTO


class TestNoTelepathyInUI:
    """Rule 11: Передача Игроку внутренних состояний NPC (HP, fear, trust) запрещена."""

    def test_npc_position_dto_has_no_internal_stats(self):
        """ДОКАЗЫВАЕТ: DTO позиции NPC, уходящее во фронтенд, не содержит скрытых внутренних параметров."""
        # Поля, которые NPCState имеет внутри, но фронтенд НЕ ДОЛЖЕН видеть напрямую
        forbidden_keys = {"fear", "trust", "stress", "hp", "max_hp", "pain", "blood_loss", "shock_impulse", "will_state"}
        
        # Получаем все поля DTO
        dto_fields = set(NPCPositionDTO.__dataclass_fields__.keys())
        
        leaks = dto_fields.intersection(forbidden_keys)
        assert not leaks, f"Rule 11 Нарушено: NPCPositionDTO содержит внутренние поля: {leaks}"

    def test_world_snapshot_dto_has_no_internal_npc_states(self):
        """ДОКАЗЫВАЕТ: WorldSnapshotDTO не имеет полей для передачи массива внутренних состояний NPC."""
        # Поля, которые нарушали бы мембрану восприятия, если бы существовали в снимке мира
        forbidden_keys = {"all_npcs_raw", "npc_states", "npc_internal_states", "affect_states"}
        
        dto_fields = set(WorldSnapshotDTO.__dataclass_fields__.keys())
        
        leaks = dto_fields.intersection(forbidden_keys)
        assert not leaks, f"Rule 11 Нарушено: WorldSnapshotDTO содержит поля с внутренними состояниями: {leaks}"
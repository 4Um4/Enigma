"""
Файл: backend/tests/test_belief_single_writer.py
Назначение: Проверка инварианта единственного писателя в NPCState.beliefs.
Запуск: cd backend; python -m pytest tests/test_belief_single_writer.py -v; cd ..
"""

import pytest
from app.models.npc_state import NPCState
from app.errors import ArchitecturalViolationError

class TestBeliefSingleWriter:
    def test_direct_write_raises_error(self):
        """Попытка прямой записи в beliefs из произвольного модуля должна поднять ArchitecturalViolationError."""
        # Создаём валидный NPCState через конструктор (допустимо в тесте)
        state = NPCState(npc_id="test_npc")
        
        # Пытаемся написать напрямую в beliefs
        with pytest.raises(ArchitecturalViolationError) as exc_info:
            state.beliefs = {}  # noqa
            
        assert "beliefs" in str(exc_info.value)
        assert "test_belief_single_writer" in str(exc_info.value)
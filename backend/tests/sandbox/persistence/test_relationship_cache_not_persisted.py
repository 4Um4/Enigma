"""
path: backend/tests/sandbox/persistence/test_relationship_cache_not_persisted.py
Назначение: Верификация Rule 36 (relationship_cache не персистируется в legacy, ADR-121)
Зависимости: app.models.npc_state
Основные сущности: NPCState, NPCStateAdapter

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_relationship_cache_not_persisted.py -v --tb=short; cd ..
"""
import dataclasses
from app.models.npc_state import NPCState, NPCStateAdapter


def test_relationship_cache_not_persisted_in_legacy():
    """ДОКАЗЫВАЕТ: write_to_legacy НЕ записывает relationship_cache в словарь сохранения (Rule 36).
    
    ADR-121: relationship_cache — эфемерный read-кэш. SSOT = RelationshipStore.
    Персистенция кэша = DOUBLE TRUTH (расхождение с RelationshipStore при следующей загрузке).
    """
    initial_dict = {
        "npc_id": "test_npc",
        "psyche": {"stress": 0.5},
        "social_stats": {},
        "body_state": {},
    }
    
    # Создаём состояние через фабрику (§12.3)
    state = NPCStateAdapter.from_legacy(initial_dict)
    
    # Инжектим эфемерный кэш (имитация работы пайплайна текущего тика)
    state = dataclasses.replace(
        state, 
        relationship_cache={"player": {"fear": 80.0, "trust": 10.0}}
    )
    
    # Сериализуем в legacy dict
    legacy_out = {}
    NPCState.write_to_legacy(state, legacy_out)
    
    # Проверяем, что кэш НЕ попал в сериализацию
    assert "relationship_cache" not in legacy_out, \
        "Rule 36 Нарушено: relationship_cache персистируется в legacy dict (DOUBLE TRUTH риск)"
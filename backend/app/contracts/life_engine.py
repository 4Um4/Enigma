# backend/app/contracts/life_engine.py
"""
Protocol (Interface) для LifeEngine.
Определяет минимальный публичный контракт, используемый оркестратором и game_loop.
"""
from typing import Protocol, runtime_checkable, Any, List, Dict, Optional

@runtime_checkable
class LifeEngineInterface(Protocol):
    """Минимальный интерфейс LifeEngine для Dependency Injection."""
    
    @property
    def _temporal(self) -> Any:
        """Доступ к TemporalEngine."""
        ...
    
    def get_current_tick(self, campaign_id: str) -> int:
        """Возвращает текущий тик кампании."""
        ...
        
    def get_npc_states(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Возвращает список NPC для кампании."""
        ...
        
    def get_npc_observed_state(self, *args: Any, **kwargs: Any) -> Any:
        """Возвращает наблюдаемое состояние NPC."""
        ...
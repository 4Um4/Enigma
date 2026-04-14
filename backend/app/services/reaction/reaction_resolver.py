"""
ReactionResolver — фасад Reaction Layer.

path: /backend/app/services/reaction/reaction_resolver.py
Назначение: Фасад Reaction Layer — единственная точка входа для game_loop
Зависимости: reaction_rules.py, micro_event.py, decision_hub.py
Основные сущности: ReactionResolver

Позиция в pipeline (ROAD_MAP ШАГ 0.5):
    DecisionResult → ReactionResolver → MicroEvents[] → SceneContinuity
    
КРИТИЧЕСКИЙ РАЗРЫВ который закрывает:
    Без этого слоя DecisionHub говорит "NPC испуган", но:
    - ничего не падает
    - ничего не прерывается
    - ничего физически не меняется
    
    LLM запрещено создавать реальность, но Python не создавал её.
    Теперь Python создаёт.
"""
from typing import List, Optional

from app.services.npc.decision_hub import DecisionResult, EventContext
from app.services.reaction.micro_event import MicroEvent


class ReactionResolver:
    """
    Фасад Reaction Layer.
    Преобразует DecisionResult + EventContext в MicroEvents[].
    
    Чистый Python — не использует LLM.
    """
    
    def resolve(
        self,
        decision: DecisionResult,
        event: EventContext,
        composure: float = 1.0,
        hands_occupied: bool = False,
        current_activity: str = "",
    ) -> List[MicroEvent]:
        """
        Генерирует микро-события на основе решения NPC.
        
        Args:
            decision: Результат DecisionHub.compute()
            event: Контекст события из dm_scene_builder
            composure: Уровень самообладания [0..1]
                       Выводится из NPC state: 1.0 - stress/100
            hands_occupied: Заняты ли руки NPC (из LifeEngine activity)
            current_activity: Текущая активность (из LifeEngine)
            
        Returns:
            Список MicroEvent (может быть пустым — нет физической реакции)
        """
        from app.services.reaction.reaction_rules import compute_reaction_events
        
        return compute_reaction_events(
            decision=decision,
            event=event,
            composure=composure,
            hands_occupied=hands_occupied,
            current_activity=current_activity,
        )
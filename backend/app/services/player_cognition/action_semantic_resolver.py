"""
Файл: backend/app/services/player_cognition/action_semantic_resolver.py
Назначение: Извлечение PlayerAction из сырого текста игрока. MVP-эвристика по ключевым словам.
Зависимости: typing, app.models.player_action, app.models.truth_state
Основные сущности: ActionSemanticResolve
"""

from typing import Optional
from app.models.player_action import PlayerAction, ActionType
from app.models.truth_state import TruthState

class ActionSemanticResolver:
    """Маршрутизатор текста игрока в доменный PlayerAction.
    
    В MVP использует простую эвристику по ключевым словам.
    В будущем будет заменён на LLM-парсер.
    """
    
    def __init__(self, truth_state: Optional[TruthState] = None) -> None:
        self._truth = truth_state

    def resolve(
        self,
        raw_text: str,
        tick: int,
        target_id: str
    ) -> PlayerAction:
        """Парсит текст и возвращает готовый PlayerAction."""
        raw_lower = raw_text.lower()
        
        _act_type = ActionType.DIALOGUE
        if "blackmail" in raw_lower or "шантаж" in raw_lower:
            _act_type = ActionType.BLACKMAIL
        elif "help" in raw_lower or "помочь" in raw_lower:
            _act_type = ActionType.HELP
            
        _secret_id = self._extract_secret_id(raw_lower, target_id)
        
        return PlayerAction(
            action_id=f"player_act_{tick}",
            tick=tick,
            actor_id="player",
            action_type=_act_type,
            target_id=target_id,
            secret_id=_secret_id,
            description=raw_text
        )

    def _extract_secret_id(self, raw_lower: str, target_id: str) -> Optional[str]:
        """MVP-эвристика: матчит ключевые слова к секретам target_id."""
        # Если Люся
        if target_id == "maid_lusya":
            if "подвал" in raw_lower or "тайный ход" in raw_lower:
                return "lusya_basement"
            if "тень" in raw_lower and ("приказ" in raw_lower or "дело" in raw_lower):
                return "lusya_shadow_orders"
            if "орм" in raw_lower and ("спать" in raw_lower or "любовник" in raw_lower):
                return "lusya_orm_borko"
            if "борко" in raw_lower and ("люблю" in raw_lower or "влюб" in raw_lower):
                return "lusya_borko_crush"
                
        # Если Борко
        elif target_id == "guard_borko":
            if "подгляд" in raw_lower:
                return "borko_voyeur"
            if ("взятк" in raw_lower) or ("горан" in raw_lower and ("золото" in raw_lower or "платить" in raw_lower)):
                return "borko_bribe"
            if "караван" in raw_lower or "труп" in raw_lower:
                return "borko_negligence"
                
        # Если Горан
        elif target_id == "merchant_goran":
            if "шёлк" in raw_lower or "контрабанд" in raw_lower:
                return "goran_contraband"
            if "борко" in raw_lower and ("золото" in raw_lower or "платить" in raw_lower):
                return "goran_bribe"
                
        # Если Орм
        elif target_id == "blacksmith_orm":
            if "торнин" in raw_lower and ("заказ" in raw_lower or "ковал" in raw_lower):
                return "orm_tornin_order"
            if "мастер" in raw_lower and ("секрет" in raw_lower or "умер" in raw_lower):
                return "orm_craft"
                
        # Если Тень
        elif target_id == "thief_shadow":
            if "предатель" in raw_lower or "шёлк" in raw_lower:
                return "shadow_investigation"
            if "люся" in raw_lower and "подозрев" in raw_lower:
                return "shadow_suspects_lusya"
            if "убил" in raw_lower or "первый" in raw_lower and "убийство" in raw_lower:
                return "shadow_first_kill"
                
        # Если Торнин
        elif target_id == "tavern_keeper_tornin":
            if "долг" in raw_lower or ("гильдия" in raw_lower and "должен" in raw_lower):
                return "tornin_debt"
            if "подвал" in raw_lower and ("знаешь" in raw_lower or "притворя" in raw_lower):
                return "tornin_basement"
                
        return None
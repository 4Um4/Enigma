"""
SceneToDMAdapter — единый входной контракт для DM.

Принцип: DM видит ТОЛЬКО DMFrame. Никаких fallback'ов внутри DM.

path: backend/app/services/verbalization/scene_to_dm_adapter.py
Назначение: Единая точка входа для DM — конвертирует ЛЮБОЙ формат в DMFrame
Зависимости: scene_outcome_builder.py

Adapter принимает:
- SceneOutcome (новый формат от DecisionHub)
- Legacy Dict (старый формат от NPC Agent)

Всегда возвращает: DMFrame
"""

from dataclasses import dataclass, field
from typing import Dict, List, Union

from app.services.verbalization.scene_outcome_builder import (
    SceneOutcomeBuilder,
    SceneOutcome,
    DMFrame,
    NpcOutcome,
    PlayerOutcome,
    LatentSignal,
    Visibility,
    TensionOutcome,
    TensionTrend,
)


# Тип входа — либо новый, либо legacy
DMInput = Union[SceneOutcome, Dict]


@dataclass
class SceneToDMAdapter:
    """
    Адаптер — единственная точка где определяется формат входа.
    
    DM слой НЕ знает про существование legacy формата.
    Если нужно изменить конверсию — меняем ТОЛЬКО здесь.
    """
    builder: SceneOutcomeBuilder = field(default_factory=SceneOutcomeBuilder)

    def adapt(self, input_data: DMInput) -> DMFrame:
        """
        Единая точка входа. Конвертирует ЛЮБОЙ формат в DMFrame.
        
        Args:
            input_data: SceneOutcome (новый) или Dict (legacy npc_result)
            
        Returns:
            DMFrame — единый формат для DM
        """
        if isinstance(input_data, SceneOutcome):
            return self._from_scene_outcome(input_data)
        
        if isinstance(input_data, dict):
            return self._from_legacy_dict(input_data)
        
        # Неверный тип — безопасный fallback
        return self._empty_frame()

    def _from_scene_outcome(self, scene: SceneOutcome) -> DMFrame:
        """Новый формат — делегируем builder'у."""
        return self.builder.build_dm_frame(scene)

    def _from_legacy_dict(self, npc_result: Dict) -> DMFrame:
        """
        Legacy формат из NPC Agent.
        
        Формат:
        {
            "npc_reactions": ["Торнин: Ты чего тут делаешь?", ...],
            "npc_actions": ["Торнин достал топор", ...],
            "npc_state_updates": [...],
        }
        
        Ограничения legacy:
        - Нет salience → все NPC в background
        - Нет tension → "Сцена спокойная"
        - Нет скрытых сигналов
        - Имена NPC парсятся из строк (грязно, но работает)
        """
        # Извлекаем данные
        reactions: List[str] = npc_result.get("npc_reactions", [])
        actions: List[str] = npc_result.get("npc_actions", [])
        
        # Парсим NPC из реакций (формат: "Имя: текст" или просто текст)
        npc_outcomes = self._parse_legacy_reactions(reactions)
        
        # Scene changes из actions
        scene_changes = [a for a in actions if a]
        
        # Player outcome — заглушка (legacy не имеет этой информации)
        player = PlayerOutcome(
            intent="действие игрока",
            outcome="success",  # legacy не знает результат
            perceived_effect="",
        )
        
        return DMFrame(
            focus_npcs=[],  # Нет salience → нет фокуса
            background_npcs=npc_outcomes,
            player_line=player,
            tension_line="Сцена спокойная",  # Нет данных о tension
            scene_line=scene_changes,
            hidden_pressure=[],  # Нет скрытых сигналов в legacy
            voice_map={},  # Нет voice constraints в legacy
        )

    def _parse_legacy_reactions(self, reactions: List[str]) -> List[NpcOutcome]:
        """
        Парсит legacy реакции в NpcOutcome.
        
        Форматы:
        - "Торнин: Ты чего тут делаешь?" → npc_id="Торнин", intent="talk"
        - "Ты чего тут делаешь?" → npc_id="unknown", intent="talk"
        """
        outcomes: List[NpcOutcome] = []
        
        for reaction in reactions:
            if not isinstance(reaction, str) or not reaction.strip():
                continue
            
            npc_id = "unknown"
            intent = "talk"  # Legacy реакции — это всегда речь
            
            # Пробуем парсить "Имя: текст"
            if ":" in reaction:
                parts = reaction.split(":", 1)
                potential_name = parts[0].strip()
                # Если имя похоже на имя (не слишком длинное, без спецсимволов)
                if 1 < len(potential_name) < 30 and potential_name[0].isupper():
                    npc_id = potential_name
            
            outcomes.append(NpcOutcome(
                npc_id=npc_id,
                intent=intent,
                emotion=None,  # Legacy не имеет структурированных эмоций
                salience=0.0,  # Нет salience в legacy
                visibility=Visibility.DIRECT,  # Допущение: если говорил — значит виден
                visibility_confidence=1.0,
                voice_constraints={},
                latent_signals=[],
            ))
        
        return outcomes

    def _empty_frame(self) -> DMFrame:
        """Безопасный fallback при неверном типе входа."""
        return DMFrame(
            focus_npcs=[],
            background_npcs=[],
            player_line=PlayerOutcome(intent="действие", outcome="success"),
            tension_line="Сцена спокойная",
            scene_line=[],
            hidden_pressure=[],
            voice_map={},
        )
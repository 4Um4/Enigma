"""
dm_contract_builder.py — контракт для DM промпта.

Принцип: DMFrame (структура) → DMContract (текст для LLM).

ЗАЧЕМ:
- Единое место формирования промпта вместо разбросанного по _build_prompt()
- Строгий контракт = предсказуемый output
- Легко добавить/убрать блоки без изменения consumer кода

Путь: backend/app/services/verbalization/dm_contract_builder.py
Назначение: Трансформация DMFrame в жёсткий контракт для DM LLM
Зависимости: contract_base, scene_outcome_builder (DMFrame)
Основные сущности: DMContract, DMContractBuilder
"""

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from app.services.verbalization.contract_base import NarrativeContractProtocol


# ── Системный промпт (фиксированный) ──────────────────────────────────────

DM_SYSTEM_PROMPT = (
    "Ты — Мастер Подземелий D&D 5e. Опиши мир от второго лица.\n"
    "Отвечай ТОЛЬКО по-русски. НЕ ПИШИ по-китайски (中文) — это ЗАПРЕЩЕНО.\n"
    "Не говори за игроков. Не задавай вопросов.\n"
    "ЖЁСТКИЕ ПРАВИЛА:\n"
    "1. ПРОВАЛ броска = действие НЕ произошло.\n"
    "2. УСПЕХ = действие произошло, опиши результат.\n"
    "3. Используй ТОЛЬКО объекты и NPC из блоков выше.\n"
    "4. Состояние NPC из блока 'Ключевые NPC' — факт.\n"
    "5. Максимум 3 предложения."
)

# Усиленный системный промпт для hardcore режима
DM_SYSTEM_PROMPT_HARDCORE = (
    DM_SYSTEM_PROMPT
    + "\n\nТОН/РЕЖИМ: HARDCORE.\n"
    "Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.\n"
    "Не морализируй, не сглаживай и не 'перевоспитывай' игрока."
)


@dataclass(frozen=True)
class DMContract:
    """
    Конкретный контракт для DM.
    
    Immutable — после создания не меняется.
    Все блоки уже отфильтрованы (пустые не включены).
    """
    system_prompt: str
    user_prompt: str
    max_sentences: int = 3
    contract_id: str = field(default_factory=lambda: uuid4().hex[:8])
    _forbidden_tuple: tuple[str, ...] = (
        "придумывать события",
        "менять намерение NPC",
        "описывать мысли NPC",
        "повторять сказанное",
        "задавать вопросы игроку",
    )
    
    @property
    def forbidden_actions(self) -> list[str]:
        """Protocol compatibility: tuple field → list property."""
        return list(self._forbidden_tuple)


class DMContractBuilder:
    """
    Строит DMContract из компонентов.
    
    Каждый блок добавляется отдельно — можно переиспользовать builder
    для разных сценариев (combat, social, exploration).
    """
    
    def __init__(
        self,
        hardcore_mode: bool = False,
        max_sentences: int = 3,
    ) -> None:
        self._hardcore = hardcore_mode
        self._max_sentences = max_sentences
        self._blocks: list[str] = []
    
    def add_player_action(self, actions_str: str) -> "DMContractBuilder":
        """Блок 1: Действия игроков — всегда первый."""
        self._blocks.append(f"Действия игроков:\n{actions_str}")
        return self
    
    def add_dm_frame(self, frame_block: str) -> "DMContractBuilder":
        """Блок 2: NPC контент из DMFrame."""
        if frame_block and frame_block.strip():
            self._blocks.append(frame_block)
        return self
    
    def add_scene(self, scene_block: str, location: str) -> "DMContractBuilder":
        """Блок 3: Описание сцены + локация."""
        if scene_block and scene_block.strip():
            self._blocks.append(f"{scene_block}Текущая локация: {location}")
        return self
    
    def add_player_state(self, state_block: str) -> "DMContractBuilder":
        """Блок 4: Состояние игрока."""
        if state_block and state_block.strip():
            self._blocks.append(state_block)
        return self
    
    def add_rules(self, rules_str: str) -> "DMContractBuilder":
        """Блок 5: Результаты проверок."""
        if rules_str and rules_str.strip():
            self._blocks.append(f"Результаты проверок:\n{rules_str}")
        return self
    
    def add_world_changes(self, world_str: str) -> "DMContractBuilder":
        """Блок 6: Изменения мира."""
        if world_str and world_str.strip() and world_str != "Нет изменений мира":
            self._blocks.append(f"Изменения в мире:\n{world_str}")
        return self
    
    def add_continuity(self, continuity_block: str) -> "DMContractBuilder":
        """Блок 7: Фиксация состояния сцены."""
        if continuity_block and continuity_block.strip():
            self._blocks.append(continuity_block)
        return self
    
    def add_guardrail(self, guardrail: str) -> "DMContractBuilder":
        """Блок 8: Предотвращение повторов."""
        if guardrail and guardrail.strip():
            self._blocks.append(guardrail)
        return self
    
    def add_npc_stm(self, stm_block: str) -> "DMContractBuilder":
        """ФАЗА 0: Блок кратковременной памяти (текущий разговор)."""
        if stm_block and stm_block.strip():
            self._blocks.append(f"[Краткая память — текущий разговор]\n{stm_block}")
        return self
    
    def add_npc_l2_memory(self, memory_block: str) -> "DMContractBuilder":
        """ФАЗА 0: Блок важных воспоминаний (top-3 EventMemory)."""
        if memory_block and memory_block.strip():
            self._blocks.append(f"[Важные воспоминания]\n{memory_block}")
        return self
    
    def add_npc_author_notes(self, notes: str) -> "DMContractBuilder":
        """ФАЗА 0: Режиссёрская инструкция для NPC."""
        if notes and notes.strip():
            self._blocks.append(f"[Режиссёрская инструкция]\n{notes}")
        return self
    
    def add_custom_block(self, label: str, content: str) -> "DMContractBuilder":
        """Произвольный блок — для расширения без изменения класса."""
        if content and content.strip():
            self._blocks.append(f"{label}:\n{content}")
        return self
    
    def build(self, system_prompt: Optional[str] = None) -> DMContract:
        """
        Собирает финальный контракт.
        
        Args:
            system_prompt: внешний системный промпт (из файла).
                          Если None — используется дефолтный.
        
        Пустые блоки уже отфильтрованы на этапе add_*.
        """
        if system_prompt:
            system = system_prompt
        else:
            system = DM_SYSTEM_PROMPT_HARDCORE if self._hardcore else DM_SYSTEM_PROMPT
            
        # B3-FIX: forbidden-блок из контракта (single source of truth, pure render).
        blocks = list(self._blocks)
        forbidden = list(DMContract._forbidden_tuple)
        if forbidden:
            forbidden_parts = ["### КАТЕГОРИЧЕСКИЕ ЗАПРЕТЫ:"]
            for i, action in enumerate(forbidden, 1):
                forbidden_parts.append(f"{i}. НЕ {action}.")
            forbidden_parts.append("")
            forbidden_parts.append("Нарушение → ответ отклоняется.")
            blocks.append("\n".join(forbidden_parts))
            
        user = "\n\n".join(blocks)
        
        return DMContract(
            system_prompt=system,
            user_prompt=user,
            max_sentences=self._max_sentences,
        )
    
    def reset(self) -> "DMContractBuilder":
        """Сбрасывает builder для переиспользования."""
        self._blocks = []
        return self


# ── Compatibility check ──────────────────────────────────────────────────

# Protocol проверяется duck-typing в рантайме
# _dummy = DMContract(system_prompt="", user_prompt="")
# assert isinstance(_dummy, NarrativeContractProtocol)
# backend/app/models/character.py
"""
CharacterProfile — психологический профиль персонажа игрока.
Отдельная сущность от NPC (npc_profile.py) и от CharacterSheet (schemas.py — D&D-stats).

Файл: backend/app/models/character.py
Зависимости: typing, dataclasses
Основные сущности: CharacterProfile, ValueSet

Контракт:
- self_integrity ∈ [0..1] — текущая способность сопротивляться давлению мира
- values — базовые ценности (формируются при создании, меняются медленно)
- social_constraints — усвоенные нормы (могут деградировать под давлением)
- Используется CharacterFilter (Фаза 2.0.2) для расчёта сопротивления

ФАЗА 5 ПРЕДПОСЫЛКА:
- erosion_accumulator — копится от RESIST действий, влияет на self_integrity
- Когда self_integrity < 0.3 → CharacterFilter ослаблен (Identity Erosion)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional


# Стандартные ценности для справки (не constraint, а справочник)
CORE_VALUE_IDS = frozenset({
    "honour",        # честь — не предавать данный слово
    "survival",      # выживание — любая ценой остаться в живых
    "loyalty",       # верность — группе, фракции, человеку
    "freedom",       # свобода — независимость от контроля
    "compassion",    # сострадание — помощь слабым
    "justice",       # справедливость — наказание виновных
    "knowledge",     # знание — истина важнее комфорта
    "power",         # власть — контроль над другими
})


@dataclass(frozen=True)
class ValueSet:
    """
    Набор ценностей персонажа. Frozen — ценности меняются медленно,
    через отдельные события, не через каждый тик.
    
    Каждый value ∈ [0..1]:
    - 0.0 — ценность отсутствует
    - 0.5 — умеренная
    - 1.0 — абсолютная (отказ = глубокий кризис)
    """
    weights: Dict[str, float] = field(default_factory=dict)
    
    def get(self, value_id: str) -> float:
        """Безопасное получение веса ценности."""
        return self.weights.get(value_id, 0.0)
    
    def has(self, value_id: str) -> bool:
        """Проверка наличия ценности (вес > 0)."""
        return self.weights.get(value_id, 0.0) > 0.0
    
    def conflict_score(self, action_values: Dict[str, float]) -> float:
        """
        Рассчитывает конфликт между действием и ценностями персонажа.
        Возвращает ∈ [0..1]: 0 = нет конфликта, 1 = максимальный конфликт.
        
        Логика: если действие нарушает ценность → конфликт = вес_ценности * сила_нарушения
        """
        if not action_values:
            return 0.0
        
        max_conflict = 0.0
        for value_id, violation_strength in action_values.items():
            my_weight = self.get(value_id)
            if my_weight > 0 and violation_strength > 0:
                conflict = my_weight * violation_strength
                max_conflict = max(max_conflict, conflict)
        
        return min(max_conflict, 1.0)


@dataclass
class CharacterProfile:
    """
    Полный психологический профиль персонажа игрока.
    Мутирует в рантайме через CharacterFilter (RESIST действия).
    
    СВЯЗЬ С D&D-ЛИСТОМ:
    - character_id = CharacterSheet.name (ключ связки)
    - CharacterSheet = механика (HP, AC, спеллы)
    - CharacterProfile = психология (ценности, сопротивление, эрозия)
    - Хранятся раздельно: characters.json (sheet) vs character_profile.json (profile)
    
    МНОГОПОЛЬЗОВАТЕЛЬСКИЙ РЕЖИМ (hot-seat):
    - В кампании несколько персонажей, каждый со своим профилем
    - Активный персонаж определяется текущим ходом (не здесь)
    - self_integrity — личный ресурс, не общий на партию
    """
    character_id: str
    
    # ── ЯДРО СОПРОТИВЛЕНИЯ ──
    # Способность персонажа противостоять давлению мира
    # Начинается с 1.0, деградирует через erosion_accumulator
    self_integrity: float = 1.0
    
    # ── БАЗОВЫЕ ЦЕННОСТИ ──
    # Формируются при создании персонажа. Frozen — меняются только через крупные события.
    values: ValueSet = field(default_factory=ValueSet)
    
    # ── СОЦИАЛЬНЫЕ ОГРАНИЧЕНИЯ ──
    # Усвоенные нормы: "как благородный человек должен себя вести"
    # Меняются быстрее чем values, но медленнее чем self_integrity
    # ∈ [0..1] для каждого constraint
    social_constraints: Dict[str, float] = field(default_factory=dict)
    
    # ── CHARACTER→NPC TRUST (отдельный от NPC→player) ──
    # Влияет на то КАК персонаж интерпретирует действия NPC
    # Меняется через CharacterFilter, не через StateApplicator
    # npc_id → trust ∈ [-1.0, 1.0]
    npc_trust: Dict[str, float] = field(default_factory=dict)
    
    # ── ДЛЯ БУДУЩЕГО (ФАЗА 5.2) ──
    # Накопитель эрозии от RESIST-действий
    erosion_accumulator: float = 0.0
    
    # История эрозии для анализа (cap=20)
    erosion_events: List[str] = field(default_factory=list)
    
    def get_constraint(self, constraint_id: str) -> float:
        """Безопасное получение веса социального ограничения."""
        return self.social_constraints.get(constraint_id, 0.0)
    
    def get_npc_trust(self, npc_id: str) -> float:
        """Возвращает доверие персонажа к конкретному NPC. Default=0 (нейтральное)."""
        return self.npc_trust.get(npc_id, 0.0)
    
    def adjust_npc_trust(self, npc_id: str, delta: float, cap: float = 1.0) -> float:
        """
        Корректирует trust к NPC. Вызывается из CharacterFilter.
        Returns: новое значение trust.
        """
        current = self.get_npc_trust(npc_id)
        new_trust = max(-cap, min(cap, current + delta))
        self.npc_trust[npc_id] = round(new_trust, 4)
        return self.npc_trust[npc_id]
    
    def apply_erosion(self, amount: float, reason: str) -> None:
        """
        Применяет эрозию от RESIST-действия.
        Вызывается CharacterFilter после успешного сопротивления.
        
        Формула эрозии self_integrity:
        - erosion_accumulator копится
        - Когда accumulator > 1.0 → self_integrity -= 0.05
        - Cap: self_integrity ∈ [0.05, 1.0] (полная потеря = 0.05, не 0)
        """
        self.erosion_accumulator += amount
        
        # Каждые 1.0 накопленной эрозии — деградация
        while self.erosion_accumulator >= 1.0:
            self.erosion_accumulator -= 1.0
            self.self_integrity = max(0.05, self.self_integrity - 0.05)
        
        # Логируем событие
        self.erosion_events.append(reason)
        if len(self.erosion_events) > 20:
            self.erosion_events = self.erosion_events[-20:]
    
    def to_dict(self) -> Dict:
        """Сериализация для persistence."""
        return {
            "character_id": self.character_id,
            "self_integrity": self.self_integrity,
            "values": self.values.weights,
            "social_constraints": self.social_constraints,
            "npc_trust": self.npc_trust,
            "erosion_accumulator": self.erosion_accumulator,
            "erosion_events": self.erosion_events,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CharacterProfile":
        """Десериализация из persistence."""
        values_data = data.get("values", {})
        return cls(
            character_id=data.get("character_id", "unknown"),
            self_integrity=float(data.get("self_integrity", 1.0)),
            values=ValueSet(weights=values_data),
            social_constraints=data.get("social_constraints", {}),
            npc_trust=data.get("npc_trust", {}),
            erosion_accumulator=float(data.get("erosion_accumulator", 0.0)),
            erosion_events=data.get("erosion_events", []),
        )
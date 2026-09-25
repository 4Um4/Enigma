"""
path: /project/backend/app/domain/control_source.py
Назначение: Ось источника контроля актора (INV-PLAYER-AUTHORSHIP, мини-ADR F1).
    Различает «существует в мире» и «кто управляет действием»:
    Actor ≠ AutonomousDecisionAgent. Единственная точка знания о том,
    чьё решение производится autonomous decision loop; строка 'player'
    как предикат агентности живёт ЗДЕСЬ, новые строковые гарды запрещены.
    Legacy-гарды мигрируются постепенно, вне этого фикса.
Зависимости: нет (domain purity — только stdlib).
Основные сущности: ControlSource, resolve_control_source
"""
from enum import Enum


class ControlSource(Enum):
    """Источник агентности актора. Расширение (мультиплеер, звери-актёры) —
    только через реестр ниже, не через новые строковые сравнения."""
    PLAYER_INPUT = "player_input"            # решение производится player-input pipeline
    NPC_DECISION = "npc_decision"            # автономный decision loop
    SCRIPTED_SYSTEM = "scripted_system"      # системные/скриптовые механизмы
    COMBAT_CONTROLLER = "combat_controller"  # зарезервировано: пошаговый бой (будущий ADR)


_PLAYER_ACTORS = frozenset({"player"})


def resolve_control_source(actor_id: str) -> ControlSource:
    """Детерминированный резолв источника агентности."""
    if actor_id in _PLAYER_ACTORS:
        return ControlSource.PLAYER_INPUT
    return ControlSource.NPC_DECISION

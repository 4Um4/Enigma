"""
path: /project/backend/app/domain/sanity_membrane.py
Назначение: Мембрана адресации (кандидат будущий ADR «Sanity Membrane»).
    Отвечает на единственный вопрос: может ли этот NPC СЕЙЧАС адресовать
    речь этой цели. Дефолт = sanity 1.0: акторы (NPC_DECISION) и player —
    да; остальное — нет (узлы графа, объекты).
    ЛАЗЕЙКА БУДУЩЕГО (вердикт Мастера, S292): безумие/паранойя/опьянение —
    perceived_as_actor через эпистемическую мембрану; аффорданс
    can_be_addressed (W-track, говорящая дверь/кот); weighted membrane
    (addressing_sanity в личности). Всё это реализуется ВНУТРИ
    can_address без изменения callers. Пока — детерминированный дефолт.
Зависимости: domain.control_source (только stdlib + домен).
Основные сущности: can_address
"""
from app.domain.control_source import ControlSource, resolve_control_source


def can_address(npc_id: str, target_id: str) -> bool:
    """Дефолтная мембрана (sanity=1.0). Параметры (tick, personality,
    epistemics) — будущая сигнатура; расширение без ломки callers."""
    if not target_id:
        return False
    if target_id == "player":
        return True
    return resolve_control_source(target_id) is ControlSource.NPC_DECISION

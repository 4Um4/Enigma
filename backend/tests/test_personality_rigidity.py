"""
path: backend/tests/test_personality_rigidity.py
Назначение: W-IR (S208): personality_from_legacy читает psyche["identity_rigidity"]
    (ранее — всегда default 0.5, параметр некалибруем). Тест строится на реальной
    структуре config/npc/individuals/lusya.json (§12.3 — фабрика, не конструктор).
Зависимости: app.models.npc_state.personality_from_legacy.
Основные сущности: test_personality_rigidity_default / _read_from_psyche.

Запуск: cd backend; python -m pytest tests/test_personality_rigidity.py -q --tb=line; cd ..
"""
from app.models.npc_state import personality_from_legacy


def _real_lusya_dict() -> dict:
    """Реальная структура psyche (ключ identity_rigidity отсутствует —
    как во всех текущих конфигах кампании)."""
    return {
        "npc_id": "maid_lusya",
        "id": "maid_lusya",
        "tier": "major",
        "drives": {"control": 0.15, "significance": 0.2, "fear": 0.45, "desire": 0.2},
        "psyche": {"willpower": 35, "breakpoint": 55, "loyalty_true": 0},
        "voice_profile": "Говоришь тихо, короткими фразами.",
        "backstory": "Три года работает у Торнина.",
        "author_notes": "Ты не осознаёшь себя жертвой.",
    }


def test_personality_rigidity_default_preserved() -> None:
    """Без ключа в psyche — 0.5 (default dataclass): нулевой дифф для
    существующих конфигов. Регрессия-гард W-IR."""
    p = personality_from_legacy(_real_lusya_dict())
    assert p.identity_rigidity == 0.5


def test_personality_rigidity_read_from_psyche() -> None:
    """psyche["identity_rigidity"] пробрасывается в личность:
    разблокирует npc_overrides пресетов лаборатории (ADR-O-361)."""
    d = _real_lusya_dict()
    d["psyche"]["identity_rigidity"] = 0.95
    p = personality_from_legacy(d)
    assert p.identity_rigidity == 0.95
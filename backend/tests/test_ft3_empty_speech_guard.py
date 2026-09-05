"""
path: /project/backend/tests/test_ft3_empty_speech_guard.py
Назначение: Регрессия FT-3 — DM-реакции с пустым хвостом не порождают ни NPC_SPOKE,
    ни пустой ход STM-сессии (оба стока продюсера); непустая реакция проходит в оба.
    До фикса тест воспроизводит симптом «npc → player: ''» на изолированной шине.
Зависимости: app.services.memory.working_memory_tick, EventBus (clear — прецедент S194)
Основные сущности: test_empty_reaction_skipped, test_nonempty_reaction_written
"""

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.memory.working_memory_tick import write_npc_reactions_to_memory


class _MemStub:
    """Счётчик STM-записей: продюсер пишет через публичный API —
    объект реальности не нужен (§13.4, фабрика/стаб вместо конструктора мечты)."""

    def __init__(self):
        self.turns = []

    def add_dialogue_turn(self, *, campaign_id, npc_id, speaker, text, **_):
        self.turns.append((npc_id, speaker, text))


def _subscribe_recorder():
    _seen = []

    def _rec(event):
        _seen.append(event)
        return None

    bus = get_event_bus()
    bus.clear()  # изоляция шины, прецедент S194
    bus.subscribe(EventType.NPC_SPOKE, _rec)
    return _seen


def test_empty_reaction_skipped():
    """FT-3: «Имя:» и «Имя:   » — не речь; ни публикации, ни STM-хода."""
    _seen = _subscribe_recorder()
    mem = _MemStub()
    npcs = [{"npc_id": "merchant_goran", "name": "Купец Горан"}]
    write_npc_reactions_to_memory(
        mem, ["Купец Горан:", "Купец Горан:   "], npcs, "test_ft3"
    )
    assert _seen == [], "пустая реакция опубликована как NPC_SPOKE (FT-3 жив)"
    assert mem.turns == [], "пустой ход записан в STM-сессию (FT-3 жив)"


def test_nonempty_reaction_written():
    """FT-3 guard не режет легитимную речь: оба стока работают."""
    _seen = _subscribe_recorder()
    mem = _MemStub()
    npcs = [{"npc_id": "merchant_goran", "name": "Купец Горан"}]
    write_npc_reactions_to_memory(mem, ["Купец Горан: привет"], npcs, "test_ft3")
    assert len(_seen) == 1 and _seen[0].payload["content"] == "привет"
    assert mem.turns == [("merchant_goran", "Купец Горан", "привет")]
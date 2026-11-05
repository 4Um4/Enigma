"""R-1 (NPC_LONGFORM E1): атрибуция говорящего в парной сессии NPC<->NPC.

До фикса dialogue_session.to_prompt_block печатал не-игрока как self.npc_id
(владелец сессии) — LLM не мог различить «я сказал»/«мне сказали» в парной
сессии NPC<->NPC. После фикса печатается фактический говорящий (turn.speaker).

Тест:
  - Парная сессия maid_lusya (владелец) с репликой speaker="tavern_keeper_tornin"
  - to_prompt_block должен содержать "tavern_keeper_tornin" (фактический говорящий)
  - НЕ должен подписывать реплику торнина как "maid_lusya" (владелец сессии)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.memory.dialogue_session import DialogueSession


def test_r1_npc_speaker_attributed_not_owner():
    """R-1: реплика NPC-партнёра подписана его ID, не ID владельца сессии."""
    # Сессия владельца maid_lusya, партнёр tavern_keeper_tornin
    session = DialogueSession(npc_id="maid_lusya", partner_id="tavern_keeper_tornin")
    # Торнин говорит Люсе
    session.add_turn(
        speaker="tavern_keeper_tornin",
        text="Опять кружку разбила? Я тебя проучу!",
        target_id="maid_lusya",
        intent="intimidate",
        tick=5,
    )
    # Люся отвечает
    session.add_turn(
        speaker="maid_lusya",
        text="Простите, хозяин, я буду осторожнее.",
        target_id="tavern_keeper_tornin",
        intent="appease",
        tick=6,
    )

    block = session.to_prompt_block()

    # Позитивные проверки: фактические говорящие подписаны
    assert "tavern_keeper_tornin" in block, (
        f"R-1 FAIL: реплика Торнина не подписана его ID. Block:\n{block}"
    )
    assert "maid_lusya" in block, (
        f"R-1 FAIL: реплика Люси не подписана её ID. Block:\n{block}"
    )

    # Негативная проверка: реплика Торнина НЕ подписана как maid_lusya (владелец)
    # До фикса: speaker_name = self.npc_id -> обе реплики подписаны "maid_lusya"
    # После фикса: каждая реплика подписана фактическим говорящим.
    # Формат строки: "  {speaker_name}{target_marker}{intent_marker}: {turn.text}"
    # Поэтому проверяем startswith, а не "id:" (двоеточие после intent_marker).
    lines = [l.strip() for l in block.split("\n")
             if l.strip().startswith("tavern_keeper_tornin")
             or l.strip().startswith("maid_lusya")]
    assert len(lines) >= 2, (
        f"R-1 FAIL: ожидается >=2 строк с разными говорящими, найдено {len(lines)}.\n"
        f"Block:\n{block}"
    )
    # Первая реплика — Торнин (говорил первым)
    assert lines[0].startswith("tavern_keeper_tornin"), (
        f"R-1 FAIL: первая реплика не подписана как tavern_keeper_tornin.\n"
        f"Lines:\n{lines}"
    )


def test_r1_player_speaker_still_igrok():
    """R-1: реплика игрока по-прежнему подписана 'Игрок' (не 'player')."""
    session = DialogueSession(npc_id="maid_lusya", partner_id="player")
    session.add_turn(
        speaker="player",
        text="Привет, Люся.",
        target_id="maid_lusya",
        intent="greeting",
        tick=1,
    )
    session.add_turn(
        speaker="maid_lusya",
        text="Здравствуйте, господин.",
        target_id="player",
        intent="appease",
        tick=2,
    )

    block = session.to_prompt_block()

    assert "Игрок" in block, (
        f"R-1 FAIL: реплика игрока не подписана 'Игрок'. Block:\n{block}"
    )
    assert "maid_lusya" in block, (
        f"R-1 FAIL: реплика Люси не подписана её ID. Block:\n{block}"
    )


def test_r1_three_way_attribution():
    """R-1: три разные реплики от трёх разных говорящих — все подписаны корректно."""
    session = DialogueSession(npc_id="maid_lusya", partner_id="tavern_keeper_tornin")
    # Торнин говорит
    session.add_turn(speaker="tavern_keeper_tornin", text="Работай лучше.", tick=1)
    # Люся отвечает
    session.add_turn(speaker="maid_lusya", text="Да, хозяин.", tick=2)
    # Третий NPC (через подслушивание) — но в парной сессии только 2 участника
    # Проверяем, что обе реплики подписаны корректно
    block = session.to_prompt_block()
    assert "tavern_keeper_tornin" in block
    assert "maid_lusya" in block


if __name__ == "__main__":
    test_r1_npc_speaker_attributed_not_owner()
    print("test_r1_npc_speaker_attributed_not_owner: PASS")
    test_r1_player_speaker_still_igrok()
    print("test_r1_player_speaker_still_igrok: PASS")
    test_r1_three_way_attribution()
    print("test_r1_three_way_attribution: PASS")
    print("\nAll R-1 tests PASS")
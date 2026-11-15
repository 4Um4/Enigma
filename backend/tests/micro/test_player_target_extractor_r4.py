"""
Тест R4-FIX для player_target_extractor: обработка sticky-target при отсутствии NPC в сцене.
"""

import pytest
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.action.player_target_extractor import PlayerTargetExtractor


def test_sticky_target_ignored_if_not_in_scene_but_pronoun_used():
    """
    Сценарий: Игрок обращается к Торнину местоимением ("он"), но Торнина нет
    в current_npc_ids (например, из-за рассинхрона локации city_gate/tavern).
    Ожидаемое поведение: extractor ВСЁ РАВНО возвращает prev_target_id,
    чтобы DM мог обработать обращение, а не игнорировать его.
    """
    extractor = PlayerTargetExtractor()

    action_text = "он здесь?"
    scene_state = {"player_target_npc": "tavern_keeper_tornin", "player_target_npc_name": "Торнин"}
    # Торнина НЕТ в текущей сцене (только вор)
    npc_contexts = [{"npc_id": "thief_shadow", "npc_name": "Тень"}]

    # extract возвращает кортеж: (target_id, target_name, target_object, player_position, player_distances)
    target_id, target_name, obj_id, pos, dists = extractor.extract(action_text, npc_contexts, scene_state)

    # Ключевая проверка: target_id ДОЛЖЕН быть возвращен, несмотря на отсутствие в current_npc_ids
    assert target_id == "tavern_keeper_tornin", (
        f"Ожидался tavern_keeper_tornin, получен {target_id}. "
        "Sticky-target не должен игнорироваться при использовании местоимения."
    )
    assert target_name == "Торнин"


def test_sticky_target_matched_by_name_even_if_not_in_scene():
    """
    Сценарий: Игрок явно называет имя "Торнин", но его нет в current_npc_ids.
    Ожидаемое поведение: extractor распознает имя и вернет prev_target_id.
    """
    extractor = PlayerTargetExtractor()

    action_text = "Торнин, что за мост?"
    scene_state = {"player_target_npc": "tavern_keeper_tornin", "player_target_npc_name": "Торнин"}
    npc_contexts = [{"npc_id": "thief_shadow", "npc_name": "Тень"}]

    target_id, target_name, obj_id, pos, dists = extractor.extract(action_text, npc_contexts, scene_state)

    assert target_id == "tavern_keeper_tornin", (
        f"Ожидался tavern_keeper_tornin, получен {target_id}. "
        "Явное упоминание имени предыдущей цели должно срабатывать."
    )

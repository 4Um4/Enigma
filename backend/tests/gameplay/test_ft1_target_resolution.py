# path: /project/backend/tests/gameplay/test_ft1_target_resolution.py
# Назначение: FT-1 фальсификатор (S243) — адресация реплики игрока.
#   Production-путь run_turn; ассерт SSOT player_target_npc. Красный ДО
#   фикса (sticky-подмена), зелёный после.
# Зависимости: tests.gameplay.harness
# Основные сущности: test_ft1_id_addressing, test_ft1_cyrillic_control,
#   test_ft1_id_symmetry.
# Запуск: cd backend; python -m pytest tests/gameplay/test_ft1_target_resolution.py -v -s
import logging

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.ft1")

_CAMPAIGN = "Open_road"


def _target_of(harness) -> str:
    _scene = harness.get_scene_fresh() or harness.get_scene() or {}
    return _scene.get("player_target_npc", "")


def test_ft1_id_addressing():
    """FT-1 главный: id-адресация «[обращаясь к maid_lusya] привет» при
    ближайшем Торнине обязана резолвить maid_lusya (не sticky-Торнина)."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        # Ход-праймер: устанавливает sticky-цель (как в поле — Торнин)
        _h.player_action("осмотреться")
        _before = _target_of(_h)
        print(f"\n[FT1] sticky after primer: {_before}")

        _h.player_action("[обращаясь к maid_lusya] привет")
        _after = _target_of(_h)
        print(f"[FT1] id-addressing: requested=maid_lusya selected={_after}")

        assert _after == "maid_lusya", (
            f"FT1-MAIN: подмена адресата: requested=maid_lusya, "
            f"selected={_after} (sticky={_before}). Причина: name_forms-матч "
            f"слеп к npc_id + ADDRESS_LEMMA-sticky переносит прежнюю цель. "
            f"suspect: player_target_extractor.extract (:638 прямой матч)"
        )
    finally:
        _h.dispose()


def test_ft1_cyrillic_control():
    """Контроль: кириллическая адресация матчится (вне досягаемости бага)."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        _h.player_action("[обращаясь к люся] привет")
        _after = _target_of(_h)
        print(f"\n[FT1] cyrillic control: selected={_after}")
        assert _after == "maid_lusya", (
            f"FT1-CTRL: кириллический матч не сработал ({_after}) — "
            f"проверь name_forms-контексты в production-цепочке"
        )
    finally:
        _h.dispose()


def test_ft1_id_symmetry():
    """Симметрия: id-адресация к Торнину при ближайшей Люсе → Торнин."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    try:
        _h.player_action("[обращаясь к tavern_keeper_tornin] привет")
        _after = _target_of(_h)
        print(f"\n[FT1] id symmetry: requested=tavern_keeper_tornin selected={_after}")
        assert _after == "tavern_keeper_tornin", (
            f"FT1-SYM: симметричная подмена: requested=tornin, selected={_after}"
        )
    finally:
        _h.dispose()
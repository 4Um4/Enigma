"""
path: /project/backend/tests/test_player_board_service.py
Назначение: B1 gate Investigation Board store: init → load → mutate →
    atomic save → load → round-trip; monotonicity счётчиков; duplicate
    protection; M7 (старый/битый файл); изоляция эпистемики (B6-battery
    пока в зачатке — byte-compare player_beliefs вокруг полного цикла).
Зависимости: pytest, json, sys/path (корень backend в sys.path)
Основные сущности: тесты PlayerBoardService + чистых операций

Запуск: cd backend; python -m pytest tests/test_player_board_service.py -v; cd ..
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.player_board_service import (  # noqa: E402
    PlayerBoardService,
    add_card,
    create_hypothesis,
    delete_hypothesis,
    link,
    move_card,
    remove_card,
    unlink,
)


@pytest.fixture()
def svc(tmp_path):
    return PlayerBoardService(root=str(tmp_path))


CAMPAIGN = "board_test_campaign"


def test_missing_file_inits_v1(svc):
    board = svc.load_board(CAMPAIGN)
    assert board["version"] == 1
    assert board["cards"] == [] and board["links"] == []
    assert board["hypotheses"] == []
    assert board["next_card_id"] == 1 and board["next_hypothesis_id"] == 1


def test_roundtrip_full_cycle(svc):
    # Полный цикл операций ТЗ §3 → save → НОВЫЙ инстанс (холодный read) → идентично
    def _ops(b):
        hyp = create_hypothesis(b, "Горан — вор")
        c1 = add_card(b, "journal", "evt-123", pos=(10.0, 20.0))
        c2 = add_card(b, "hypothesis", hyp, pos=(100.0, 200.0))
        link(b, c1, c2, "PLAYER_SUPPORTS")
        move_card(b, c1, (15.0, 25.0))
        return (hyp, c1, c2)

    svc.mutate(CAMPAIGN, _ops)
    before = svc.load_board(CAMPAIGN)

    cold = PlayerBoardService(root=str(svc.root))
    after = cold.load_board(CAMPAIGN)
    assert before == after


def test_counter_self_repair_upward(svc, tmp_path):
    # Ручной/повреждённый JSON: declared counter < существующих id
    # → аллокация ОБЯЗАНА выдать board-card-002, не переиспользовать 001
    d = tmp_path / CAMPAIGN
    d.mkdir(parents=True)
    (d / "board_state.json").write_text(
        json.dumps({
            "version": 1, "next_card_id": 1, "next_hypothesis_id": 1,
            "cards": [{"id": "board-card-001", "ref_type": "journal",
                       "ref_id": "evt-1", "pos": [1.0, 2.0]}],
            "links": [], "hypotheses": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    new_id = svc.mutate(CAMPAIGN, lambda b: add_card(b, "journal", "evt-2"))
    assert new_id == "board-card-002"


def test_link_idempotent_unlink_noop(svc):
    def _ops(b):
        c1 = add_card(b, "journal", "evt-1")
        c2 = add_card(b, "journal", "evt-2")
        assert link(b, c1, c2, "PLAYER_SUPPORTS") == "linked"
        assert link(b, c1, c2, "PLAYER_SUPPORTS") == "noop"  # idempotent
        assert len(b["links"]) == 1
        assert unlink(b, c1, c2, "PLAYER_CONTRADICTS") == "noop"  # нет ребра
        assert unlink(b, c1, c2, "PLAYER_SUPPORTS") == "unlinked"
        assert unlink(b, c1, c2, "PLAYER_SUPPORTS") == "noop"  # повторный
    svc.mutate(CAMPAIGN, _ops)


def test_delete_hypothesis_cascade(svc):
    def _ops(b):
        hyp = create_hypothesis(b, "Гипотеза X")
        c_hyp = add_card(b, "hypothesis", hyp)
        c_j = add_card(b, "journal", "evt-9")
        link(b, c_j, c_hyp, "PLAYER_SUPPORTS")
        link(b, c_hyp, c_j, "PLAYER_CONTRADICTS")
        delete_hypothesis(b, hyp)
        # каскад: гипотеза, карточка-указатель, оба инцидентных ребра
        assert b["hypotheses"] == []
        assert b["cards"] == [c_j.__class__ and
                              next(c for c in b["cards"] if c["id"] == c_j)]
        assert b["links"] == []
    svc.mutate(CAMPAIGN, _ops)


def test_hypothesis_pointer_requires_existing_hyp(svc):
    with pytest.raises(ValueError):
        svc.mutate(CAMPAIGN, lambda b: add_card(b, "hypothesis", "hyp-999"))


def test_corrupt_json_loud_failure(svc, tmp_path):
    d = tmp_path / CAMPAIGN
    d.mkdir(parents=True)
    (d / "board_state.json").write_text("{not json", encoding="utf-8")
    # L4: тихий re-init уничтожил бы расследование молча — громкий отказ
    with pytest.raises(ValueError):
        svc.load_board(CAMPAIGN)


def test_player_beliefs_byte_identical(svc):
    # Ранний контур гейта №3: полный цикл операций доски не трогает
    # эпистемику ни байтом (полная battery — B6)
    beliefs = [
        {"agent_id": "player",
         "proposition": {"subject_id": "goran", "predicate": "STOLE"},
         "confidence": 0.9},
    ]
    before = json.dumps(beliefs, sort_keys=True, ensure_ascii=False)

    def _ops(b):
        hyp = create_hypothesis(b, "Горан — вор")
        c1 = add_card(b, "journal", "evt-1")
        c2 = add_card(b, "hypothesis", hyp)
        link(b, c1, c2, "PLAYER_SUPPORTS")
        remove_card(b, c1)
        delete_hypothesis(b, hyp)

    svc.mutate(CAMPAIGN, _ops)
    assert json.dumps(beliefs, sort_keys=True, ensure_ascii=False) == before


def test_board_state_in_reset_list() -> None:
    """Phase 4.1-R (вердикт Мастера 1): board_state.json обязан быть
    в списке runtime_files reset_campaign — новая игра = новая пустая
    доска. Замок от молчаливого выпадения строки (Continue не проходит
    этот список — доска при загрузке кампании сохраняется)."""
    from pathlib import Path
    _src = Path(__file__).resolve().parents[1] / "app" / "services" / \
        "game_loop" / "campaign_lifecycle.py"
    _text = _src.read_text(encoding="utf-8")
    assert '"board_state.json"' in _text, (
        "board_state.json выпал из reset-списка campaign_lifecycle — "
        "новая игра унаследует расследование прошлого прохождения"
    )
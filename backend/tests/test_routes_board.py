"""
path: /project/backend/tests/test_routes_board.py
Назначение: B2 gate REST Investigation Board: GET пустой доски, ADD_CARD
    (валидный + invalid ref_type → 422), MOVE (несуществующая → 422),
    REMOVE + round-trip через второй GET; traversal-защита campaign_id;
    изоляция: monkeypatched tmp-root, settings.saves_dir не тронут.
Зависимости: pytest, fastapi TestClient, monkeypatch
Основные сущности: тесты board_router

Запуск: cd backend; python -m pytest tests/test_routes_board.py -v; cd ..
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import routes_board  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CAMPAIGN = "board_rest_test"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Изоляция: подменяем корень сервиса на tmp — реальные saves/ не пишутся
    monkeypatch.setattr(
        routes_board, "player_board_service",
        routes_board.PlayerBoardService(root=str(tmp_path)),
    )
    _app = FastAPI()
    _app.include_router(routes_board.board_router, prefix="/api")
    return TestClient(_app)


def test_get_empty_board(client):
    r = client.get(f"/api/board/{CAMPAIGN}")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["cards"] == [] and body["links"] == [] and body["hypotheses"] == []


def test_add_and_move_card_roundtrip(client):
    r = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "journal", "ref_id": "evt-1",
              "pos": [10.0, 20.0]},
    )
    assert r.status_code == 200
    card_id = r.json()["card_id"]
    assert card_id == "board-card-001"

    r = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "move", "card_id": card_id, "pos": [50.0, 60.0]},
    )
    assert r.status_code == 200

    body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert body["cards"][0]["pos"] == [50.0, 60.0]
    # счётчик продвинулся детерминированно
    assert body["next_card_id"] == 2

    r = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "remove", "card_id": card_id},
    )
    assert r.status_code == 200
    assert client.get(f"/api/board/{CAMPAIGN}").json()["cards"] == []


def test_add_invalid_ref_type_422(client):
    r = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "truth", "ref_id": "x"},
    )
    assert r.status_code == 422
    # файл не мутировал (нет частичных коммитов)
    assert client.get(f"/api/board/{CAMPAIGN}").json()["cards"] == []


def test_move_nonexistent_card_422(client):
    r = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "move", "card_id": "board-card-999", "pos": [1.0, 2.0]},
    )
    assert r.status_code == 422


def test_link_unlink_roundtrip(client):
    # Подготовка: две карточки
    _ids = []
    for _ref in ("evt-1", "evt-2"):
        _r = client.post(
            f"/api/board/{CAMPAIGN}/cards",
            json={"op": "add", "ref_type": "journal", "ref_id": _ref},
        )
        _ids.append(_r.json()["card_id"])

    # LINK
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": _ids[0], "to": _ids[1],
              "kind": "PLAYER_SUPPORTS"},
    )
    assert _r.status_code == 200 and _r.json()["result"] == "linked"
    # idempotent: повтор → 'noop', дубля нет
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": _ids[0], "to": _ids[1],
              "kind": "PLAYER_SUPPORTS"},
    )
    assert _r.status_code == 200 and _r.json()["result"] == "noop"
    _body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert len(_body["links"]) == 1

    # UNLINK чужим kind: ребро живо, no-op
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "unlink", "from": _ids[0], "to": _ids[1],
              "kind": "PLAYER_CONTRADICTS"},
    )
    assert _r.status_code == 200 and _r.json()["result"] == "noop"
    assert len(client.get(f"/api/board/{CAMPAIGN}").json()["links"]) == 1

    # UNLINK точной тройкой: удаляет ровно это ребро
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "unlink", "from": _ids[0], "to": _ids[1],
              "kind": "PLAYER_SUPPORTS"},
    )
    assert _r.status_code == 200 and _r.json()["result"] == "unlinked"
    assert client.get(f"/api/board/{CAMPAIGN}").json()["links"] == []


def test_link_nonexistent_card_422(client):
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": "board-card-999", "to": "board-card-998",
              "kind": "PLAYER_SUPPORTS"},
    )
    assert _r.status_code == 422


def test_link_invalid_kind_422(client):
    # kind — user-authored relation, но множество закрыто (ТЗ §2)
    _c = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "journal", "ref_id": "evt-1"},
    ).json()["card_id"]
    _r = client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": _c, "to": _c, "kind": "IMPLIES"},
    )
    assert _r.status_code == 422


def test_hypothesis_create_edit_delete(client):
    # CREATE → детерминированный id
    _r = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "create", "text": "Горан — вор"},
    )
    assert _r.status_code == 200
    _hyp = _r.json()["hypothesis_id"]
    assert _hyp == "hyp-001"

    # EDIT text + status
    _r = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "edit", "hyp_id": _hyp, "text": "Горан украл золото",
              "status": "supports"},
    )
    assert _r.status_code == 200
    _body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert _body["hypotheses"][0]["text"] == "Горан украл золото"
    assert _body["hypotheses"][0]["status"] == "supports"

    # DELETE без гипотез-указателей
    _r = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "delete", "hyp_id": _hyp},
    )
    assert _r.status_code == 200
    _body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert _body["hypotheses"] == []
    assert _body["cards"] == [] and _body["links"] == []


def test_delete_hypothesis_cascade_via_rest(client):
    # Полный каскад через REST: гипотеза + карточка-указатель + link
    _hyp = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "create", "text": "Гипотеза X"},
    ).json()["hypothesis_id"]
    _c_hyp = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "hypothesis", "ref_id": _hyp},
    ).json()["card_id"]
    _c_j = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "journal", "ref_id": "evt-9"},
    ).json()["card_id"]
    client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": _c_j, "to": _c_hyp,
              "kind": "PLAYER_SUPPORTS"},
    )

    _r = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "delete", "hyp_id": _hyp},
    )
    assert _r.status_code == 200
    _body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert _body["hypotheses"] == []
    # выжила только journal-карточка, ребро ушло каскадом
    assert [c["id"] for c in _body["cards"]] == [_c_j]
    assert _body["links"] == []
    # счётчик гипотез монотонен после каскада (self-repair вверх)
    _hyp2 = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "create", "text": "Новая гипотеза"},
    ).json()["hypothesis_id"]
    assert _hyp2 == "hyp-002"


def test_hypothesis_validation_422(client):
    # create без text
    assert client.post(
        f"/api/board/{CAMPAIGN}/hypotheses", json={"op": "create"},
    ).status_code == 422
    # create с пустым текстом
    assert client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "create", "text": "   "},
    ).status_code == 422
    # edit несуществующей
    assert client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "edit", "hyp_id": "hyp-999", "text": "x"},
    ).status_code == 422
    # delete несуществующей
    assert client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "delete", "hyp_id": "hyp-999"},
    ).status_code == 422
    # edit/delete без hyp_id
    assert client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "edit", "text": "x"},
    ).status_code == 422
    # файл не мутировал ни одной невалидной попыткой
    assert client.get(f"/api/board/{CAMPAIGN}").json()["hypotheses"] == []


def test_campaign_traversal_blocked(client):
    # %2F не декодируется до матчинга: роут не сматчится, handler недостижим
    assert client.get("/api/board/..%2Fetc").status_code == 404
    assert client.get("/api/board/a/b").status_code == 404  # не сматчился роут
    # Валидатор _validate_campaign тестируем напрямую (слой 2 защиты)
    with pytest.raises(routes_board.HTTPException) as _e:
        routes_board._validate_campaign("../etc")
    assert _e.value.status_code == 400
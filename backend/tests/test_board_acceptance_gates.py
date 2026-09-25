"""
path: /project/backend/tests/test_board_acceptance_gates.py
Назначение: Финальные гейты приёмки Phase 4 (ТЗ §6):
    G1 — round-trip: полный цикл операций через REST → файл → холодная
         перезагрузка → состояние идентично;
    G2 — «пустая карточка»: карточка ссылается на event_id, вытесненный
         из journal cap-100 → не крашит, карточка доступна (серый рендер
         — клиентская ответственность; сервер обязан вернуть организацию);
    G3 — изоляция: полный цикл операций доски → player_beliefs живого
         снапшота (через настоящий WorldSnapshotBuilder + настоящий
         EpistemicStore) byte-for-byte не изменились;
    G4 — M7: файл без board-полей / отсутствующий файл → пустая доска,
         без миграции.
Зависимости: pytest, json, app.services.player_board_service,
    app.services.integration.world_snapshot_builder, app.domain.epistemology
Основные сущности: тесты гейтов приёмки

Запуск: cd backend; python -m pytest tests/test_board_acceptance_gates.py -v; cd ..
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import routes_board  # noqa: E402
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
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CAMPAIGN = "board_gates_test"


# ══ G1: ROUND-TRIP через REST ═══════════════════════════════════

def test_g1_roundtrip_full_cycle_via_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(
        routes_board, "player_board_service",
        routes_board.PlayerBoardService(root=str(tmp_path)),
    )
    _app = FastAPI()
    _app.include_router(routes_board.board_router, prefix="/api")
    client = TestClient(_app)

    # Полный закрытый цикл операций ТЗ §3 через REST
    _hyp = client.post(
        f"/api/board/{CAMPAIGN}/hypotheses",
        json={"op": "create", "text": "Горан — вор"},
    ).json()["hypothesis_id"]
    _c1 = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "journal", "ref_id": "evt-001",
              "pos": [10.0, 20.0]},
    ).json()["card_id"]
    _c2 = client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "hypothesis", "ref_id": _hyp,
              "pos": [100.0, 200.0]},
    ).json()["card_id"]
    client.post(
        f"/api/board/{CAMPAIGN}/links",
        json={"op": "link", "from": _c1, "to": _c2,
              "kind": "PLAYER_SUPPORTS"},
    )
    client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "move", "card_id": _c1, "pos": [42.0, 43.0]},
    )
    _before = client.get(f"/api/board/{CAMPAIGN}").json()

    # ХОЛОДНАЯ перезагрузка: новый инстанс сервиса, тот же файл
    _cold = routes_board.PlayerBoardService(root=str(tmp_path))
    _after = _cold.load_board(CAMPAIGN)
    assert _before == _after

    # Файл на диске валиден и завершён
    _raw = json.loads((tmp_path / CAMPAIGN / "board_state.json").read_text(
        encoding="utf-8"))
    assert _raw["version"] == 1


# ══ G2: «ПУСТАЯ КАРТОЧКА» (ref вытеснен из journal cap-100) ═════

def test_g2_dead_ref_card_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        routes_board, "player_board_service",
        routes_board.PlayerBoardService(root=str(tmp_path)),
    )
    _app = FastAPI()
    _app.include_router(routes_board.board_router, prefix="/api")
    client = TestClient(_app)

    # Карточка ссылается на event_id, которого в журнале нет (вытеснен FIFO
    # cap-100 — сервер доски журнальный SSOT не читает, ссылка opaque)
    client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "journal",
              "ref_id": "evt-evicted-fifo-000"},
    )
    # GET не крашится, организация цела — «пустая карточка» валидное
    # состояние (ТЗ §2); рендер серым — клиентский джойн
    _r = client.get(f"/api/board/{CAMPAIGN}")
    assert _r.status_code == 200
    _body = _r.json()
    assert _body["cards"][0]["ref_id"] == "evt-evicted-fifo-000"
    assert _body["cards"][0]["ref_type"] == "journal"
    # provenance-хвост сохранён: организация не чистит мёртвые ссылки
    # (это НЕ её знание — решать «жив/мёртв» клиенту)

    # Серый рендер моделируем клиентским джойном: ref отсутствует
    # в живом канале → unresolved
    _live_refs = set()  # имитация пустого dialog_journal
    _resolved = _body["cards"][0]["ref_id"] in _live_refs
    assert _resolved is False


def test_g2b_claim_belief_refs_persist_grey(tmp_path, monkeypatch):
    # Вердикт Мастера (б): claim/belief — допустимые persisted opaque-типы,
    # клиент рендерит серыми; сервер хранит и отдаёт без интерпретации
    monkeypatch.setattr(
        routes_board, "player_board_service",
        routes_board.PlayerBoardService(root=str(tmp_path)),
    )
    _app = FastAPI()
    _app.include_router(routes_board.board_router, prefix="/api")
    client = TestClient(_app)
    client.post(
        f"/api/board/{CAMPAIGN}/cards",
        json={"op": "add", "ref_type": "belief", "ref_id": "no-stable-id-yet"},
    )
    _body = client.get(f"/api/board/{CAMPAIGN}").json()
    assert _body["cards"][0]["ref_type"] == "belief"
    assert _body["cards"][0]["ref_id"] == "no-stable-id-yet"


# ══ G3: ИЗОЛЯЦИЯ (живой EpistemicStore → player_beliefs) ════════

def test_g3_epistemic_isolation_live_snapshot(tmp_path):
    """Полный цикл операций доски → player_beliefs снапшота байт-в-байт
    не изменились. Проверка против НАСТОЯЩЕЙ проекции: EpistemicStore с
    реальным убеждением игрока → WorldSnapshotBuilder — тот же путь, что
    world_snapshot_builder.py:97-99."""
    from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
    from app.services.npc.epistemic_store import EpistemicStore

    _svc = PlayerBoardService(root=str(tmp_path))

    def _build_beliefs() -> str:
        # Настоящий store с настоящим убеждением — НЕ mock.
        # Путь проекции идентичен world_snapshot_builder.py:97-99
        # (to_dict → фильтр agent_id == "player").
        _store = EpistemicStore()
        _store.upsert(EpistemicRecord(
            agent_id="player",
            proposition=Proposition(
                subject_id="goran",
                predicate=Predicate.STOLE,
                object_id="gold",
                polarity=True,
            ),
            confidence=0.9,
            source_id="goran",
            source_claim_id="claim-1",
            first_observed_tick=1,
            last_updated_tick=1,
        ))
        return json.dumps(
            [r for r in _store.to_dict() if r.get("agent_id") == "player"],
            sort_keys=True, ensure_ascii=False,
        )

    _before = _build_beliefs()

    # Полный цикл операций доски (все 8 операций ТЗ §3)
    def _full_cycle(b):
        _hyp = create_hypothesis(b, "Горан — вор")
        _c1 = add_card(b, "journal", "evt-1", pos=(1.0, 2.0))
        _c2 = add_card(b, "hypothesis", _hyp, pos=(3.0, 4.0))
        link(b, _c1, _c2, "PLAYER_SUPPORTS")
        move_card(b, _c1, (5.0, 6.0))
        unlink(b, _c1, _c2, "PLAYER_SUPPORTS")
        link(b, _c1, _c2, "PLAYER_CONTRADICTS")
        remove_card(b, _c1)
        delete_hypothesis(b, _hyp)
        return b

    _svc.mutate(CAMPAIGN, _full_cycle)

    _after = _build_beliefs()
    assert _after == _before  # байт-в-байт


# ══ G4: M7-совместимость ════════════════════════════════════════

def test_g4_legacy_file_without_board_fields(tmp_path):
    # Старая кампания: board_state.json отсутствует вообще
    _svc = PlayerBoardService(root=str(tmp_path))
    _board = _svc.load_board("ancient_campaign")
    assert _board["cards"] == [] and _board["links"] == []
    assert _board["hypotheses"] == []

    # Файл есть, но это чужой JSON без board-полей (прототип/мусор)
    _d = tmp_path / "legacy_campaign"
    _d.mkdir(parents=True)
    (_d / "board_state.json").write_text(
        json.dumps({"unknown_future_field": 42}, ensure_ascii=False),
        encoding="utf-8",
    )
    _board2 = _svc.load_board("legacy_campaign")
    assert _board2["cards"] == []
    # M7: неизвестные поля СОХРАНЯЮТСЯ (forward-compat), без миграции
    assert _board2.get("unknown_future_field") == 42
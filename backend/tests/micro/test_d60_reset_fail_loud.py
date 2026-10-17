"""Тесты COV-D60 / ADR-O-426 Шаг 3: fail-loud reset_campaign.

Пины: контракт ADR-O-403 (порядок 1->12, форма возврата, состав files_removed,
board_state.json удаляется / characters.json выживает); немедленное прерывание
(CampaignResetError: campaign_id/step/detail + __cause__; последующие владельцы
не зовутся); регрессия NameError (_mem_reset); passthrough классифицированных
отказов (П1-18: step-поле не лжёт).

Владельцы — SimpleNamespace с рабочими методами (ловушка D59: object() не
переживает reset). Шаг 4 подменяет атрибут МОДУЛЯ player_session_service
(from-import внутри функции читает атрибут модуля в момент вызова). Сцена без
location_id (seed-ветка шага 6 не активируется) и с player_body_topology
(шаг 6.5 скипается) — герметичность без реальных сервисов.
"""

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.game_loop.campaign_lifecycle import (
    CampaignLifecycle,
    CampaignResetError,
)

STEP_IDS = [
    "sqlite_persistence",
    "json_files",
    "relationships",
    "crystallized_beliefs",
    "player_session",
    "life_engine_npc",
    "scene_reinit",
    "current_location_seed",
    "body_topology",
    "atomic_commit",
    "memory_manager",
    "temporal_engine",
    "avatar_session",
    "npc_runtime_caches",
    "mvp_controller_init",
]

# Порядок 1->12 = контракт ADR-O-403 (13 операций: player_session = 2 вызова сервиса).
ORDER = [
    "sqlite_persistence",
    "relationships",
    "crystallized_beliefs",
    "player_session.deactivate",
    "player_session.delete_disk",
    "life_engine_npc",
    "scene_reinit",
    "atomic_commit",
    "memory_manager",
    "temporal_engine",
    "avatar_session",
    "npc_runtime_caches",
    "mvp_controller_init",
]

# Без location_id (seed-ветка шага 6 офф), с topology (шаг 6.5 офф).
SCENE = {"player_body_topology": {"serialized": "stub"}}


def _make_lifecycle(tmp_path, calls, *, scene=None, npcs=None):
    """Все владельцы — SimpleNamespace с рабочими методами; маркеры в calls."""
    scene = SCENE if scene is None else scene
    npcs = [{"npc_id": "goran"}] if npcs is None else npcs

    def sm_persistence(cid):
        calls.append("sqlite_persistence")
        return True

    def sm_reinit(cid):
        calls.append("scene_reinit")
        return scene

    def sm_commit(**kwargs):
        calls.append("atomic_commit")

    scene_manager = SimpleNamespace(
        reset_campaign_persistence=sm_persistence,
        reinit_campaign=sm_reinit,
        commit=sm_commit,
    )
    rel_store = SimpleNamespace(
        reset_campaign=lambda cid: calls.append("relationships")
    )
    tick_orch = SimpleNamespace(
        crystallized_belief_store=SimpleNamespace(
            reset_campaign=lambda cid: calls.append("crystallized_beliefs")
        )
    )

    def mm_reset(cid):
        calls.append("memory_manager")
        return {"sqlite_rows": 5}

    memory_manager = SimpleNamespace(reset_campaign_state=mm_reset)
    engine = SimpleNamespace(
        reset_campaign=lambda cid: (calls.append("life_engine_npc"), npcs)[1],
        _temporal=SimpleNamespace(
            reset_campaign=lambda cid: calls.append("temporal_engine")
        ),
        clear_runtime_caches=lambda cid: calls.append("npc_runtime_caches"),
    )
    avatar_service = SimpleNamespace(
        reset_campaign=lambda cid: (calls.append("avatar_session"), True)[1]
    )
    mvp_controller = SimpleNamespace(
        init_campaign=lambda cid: calls.append("mvp_controller_init")
    )

    lc = CampaignLifecycle(
        scene_manager=scene_manager,
        rel_store=rel_store,
        memory_manager=memory_manager,
        tick_orch=tick_orch,
        avatar_service=avatar_service,
        mvp_controller=mvp_controller,
        get_life_engine=lambda: engine,
        load_npcs=lambda: [],
        saves_dir=tmp_path / "saves",
    )
    return lc, scene_manager, engine


@pytest.fixture
def patch_session(monkeypatch):
    """Подмена singleton player_session_service (шаг 4) фейком с записью."""

    def _patch(calls):
        def deactivate(cid):
            calls.append("player_session.deactivate")
            return False

        def delete_disk(cid):
            calls.append("player_session.delete_disk")
            return None

        import app.services.player_session_service as pss

        monkeypatch.setattr(
            pss,
            "player_session_service",
            SimpleNamespace(
                deactivate_player=deactivate,
                _delete_session_from_disk=delete_disk,
            ),
        )

    return _patch


class TestHappyPath:
    def test_order_and_return(self, tmp_path, patch_session):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)
        patch_session(calls)
        result = lc.reset_campaign("d60")
        assert calls == ORDER
        assert result == {
            "reset": True,
            "campaign_id": "d60",
            "files_removed": [
                "sqlite:scene+runtime",
                "relationships",
                "sqlite:crystallized_beliefs",
                "world_tick.json",
                "player_avatar.json",
                "sqlite:memories(5)",
            ],
        }

    def test_board_state_removed_characters_survive(self, tmp_path, patch_session):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)
        patch_session(calls)
        cdir = tmp_path / "saves" / "d60"
        cdir.mkdir(parents=True)
        for name in ("npc_runtime.json", "campaign_state.json", "board_state.json"):
            (cdir / name).write_bytes(b"x")
        (cdir / "characters.json").write_bytes(b"keep")
        (cdir / "character_profiles.json").write_bytes(b"keep")
        result = lc.reset_campaign("d60")
        fr = result["files_removed"]
        assert {"npc_runtime.json", "campaign_state.json", "board_state.json"} <= set(fr)
        assert "characters.json" not in fr
        assert "character_profiles.json" not in fr
        assert not (cdir / "board_state.json").exists()
        assert not (cdir / "npc_runtime.json").exists()
        assert (cdir / "characters.json").read_bytes() == b"keep"
        assert (cdir / "character_profiles.json").exists()

    def test_mem_reset_none_guard(self, tmp_path, patch_session):
        # Гвард биндинга: reset_campaign_state -> None => секция 12-sqlite
        # пропущена (до D60 несвязанное имя давало NameError ВНЕ try).
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)
        lc.memory_manager = SimpleNamespace(
            reset_campaign_state=lambda cid: (calls.append("memory_manager"), None)[1]
        )
        patch_session(calls)
        result = lc.reset_campaign("d60")
        assert result["reset"] is True
        assert not [x for x in result["files_removed"] if str(x).startswith("sqlite:memories")]


class TestImmediateInterrupt:
    def test_sqlite_persistence(self, tmp_path):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)

        def boom(cid):
            raise RuntimeError("sqlite locked")

        sm.reset_campaign_persistence = boom
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        exc = ei.value
        assert exc.campaign_id == "d60"
        assert exc.step == "sqlite_persistence"
        assert "sqlite locked" in exc.detail
        assert isinstance(exc.__cause__, RuntimeError)
        assert calls == []  # немедленность: последующие владельцы не званы

    def test_json_files_unlink(self, tmp_path, monkeypatch):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)
        cdir = tmp_path / "saves" / "d60"
        cdir.mkdir(parents=True)
        target = cdir / "npc_runtime.json"
        target.write_bytes(b"x")

        def bad_unlink(self, *args, **kwargs):
            raise OSError("EACCES: unlink denied")

        monkeypatch.setattr(Path, "unlink", bad_unlink)
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        assert ei.value.step == "json_files"
        assert "npc_runtime.json" in ei.value.detail
        assert target.read_bytes() == b"x"  # файл не тронут
        assert calls == ["sqlite_persistence"]

    def test_atomic_commit(self, tmp_path, patch_session):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)

        def bad_commit(**kwargs):
            raise RuntimeError("commit boom")

        sm.commit = bad_commit
        patch_session(calls)
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        assert ei.value.step == "atomic_commit"
        assert calls[-1] == "scene_reinit"
        assert "memory_manager" not in calls
        assert "mvp_controller_init" not in calls

    def test_memory_manager_nameerror_regression(self, tmp_path, patch_session):
        # До D60: отказ здесь глотался, _mem_reset оставался несвязанным,
        # секция 12-sqlite давала NameError ВНЕ try (криптический краш).
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)

        def bad_mm(cid):
            raise RuntimeError("mm boom")

        lc.memory_manager = SimpleNamespace(reset_campaign_state=bad_mm)
        patch_session(calls)
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        assert type(ei.value) is CampaignResetError
        assert ei.value.step == "memory_manager"
        assert "temporal_engine" not in calls

    def test_scene_reinit(self, tmp_path, patch_session):
        calls = []
        lc, sm, engine = _make_lifecycle(tmp_path, calls)

        def bad_reinit(cid):
            raise RuntimeError("reinit boom")

        sm.reinit_campaign = bad_reinit
        patch_session(calls)
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        assert ei.value.step == "scene_reinit"
        assert isinstance(ei.value.__cause__, RuntimeError)
        assert "atomic_commit" not in calls

    def test_current_location_seed_passthrough(self, tmp_path, monkeypatch, patch_session):
        # П1-18: отказ seed уже классифицирован (current_location_seed) и
        # переупаковке в scene_reinit НЕ подлежит — step-поле не лжёт (В7).
        calls = []
        lc, sm, engine = _make_lifecycle(
            tmp_path, calls, scene={"location_id": "tavern"}, npcs=[]
        )
        import app.services.campaign_state_service as css

        def boom_factory():
            raise RuntimeError("cs boom")

        monkeypatch.setattr(css, "get_campaign_state_service", boom_factory)
        patch_session(calls)
        with pytest.raises(CampaignResetError) as ei:
            lc.reset_campaign("d60")
        assert ei.value.step == "current_location_seed"
        assert "cs boom" in ei.value.detail
        assert isinstance(ei.value.__cause__, RuntimeError)
        assert calls[-1] == "scene_reinit"  # reinit прошёл, упал именно seed


class TestMachineReadable:
    def test_fields_and_message(self):
        e = CampaignResetError("cid-1", "json_files", "unlink failed: x")
        assert (e.campaign_id, e.step, e.detail) == ("cid-1", "json_files", "unlink failed: x")
        assert str(e) == (
            "campaign_reset_failed: campaign_id='cid-1' "
            "step='json_files' detail='unlink failed: x'"
        )

    def test_hierarchy(self):
        assert CampaignResetError.__bases__ == (RuntimeError,)

    def test_all_15_step_ids_in_source(self):
        src = inspect.getsource(CampaignLifecycle.reset_campaign)
        for sid in STEP_IDS:
            assert f'"{sid}"' in src, sid

class TestRouteTranslation:
    """Патч №2 (COV-D60): честный перевод отказа в HTTPException(500, dict-detail).

    Прямой вызов обработчика с фейковым game_loop — без TestClient и старта
    приложения (Depends-дефолт перекрыт явным аргументом). Фейк поднимает
    ровно то, что поднял бы lifecycle через прозрачный фасад GameLoop.
    """

    def test_reset_error_translated(self):
        from app.api.routes import NewGameRequest, new_game
        from fastapi import HTTPException

        class BoomLoop:
            def new_game(self, **kwargs):
                raise CampaignResetError("cid-9", "atomic_commit", "commit boom")

        with pytest.raises(HTTPException) as ei:
            new_game("cid-9", NewGameRequest(), game_loop=BoomLoop())
        exc = ei.value
        assert exc.status_code == 500
        assert exc.detail == {
            "error": "campaign_reset_failed",
            "campaign_id": "cid-9",
            "step": "atomic_commit",
            "detail": "commit boom",
        }
        assert isinstance(exc.__cause__, CampaignResetError)  # чейнинг В7

    def test_happy_path_untouched(self):
        from app.api.routes import NewGameRequest, new_game

        class OkLoop:
            def new_game(self, **kwargs):
                return {"reset": True, "campaign_id": kwargs["campaign_id"], "files_removed": []}

        result = new_game("cid-9", NewGameRequest(), game_loop=OkLoop())
        assert result == {"reset": True, "campaign_id": "cid-9", "files_removed": []}

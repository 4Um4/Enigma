"""
path: backend/tests/sandbox/re_gap1_production_probe.py
Назначение: GAP-1 production proof (вердикт Мастера §7): контролируемый мир →
    production build_game_loop → player-интервенция → runtime evidence
    различающегося interpretation. Дифференциал: NPC_A trust=-60 (порог -30
    пробит → trust_bias=-0.2), NPC_B trust=+60 (ветка молчит → 0.0) —
    одинаковый остальной контекст. Изоляция temp-saves (S239-эталон);
    player-путь по прецеденту test_player_turn_headless (S115-инъекция).
    На подвижной платформе (uncommitted S313): файловое пересечение — нет
    (interpretation_engine вне зоны S313); оговорка фиксируется в отчёте.
Зависимости: tempfile, shutil, app.core.config, game_loop_builder,
    player_session_service, CharacterService, InterventionEvent
Основные сущности: main
Запуск: python backend/tests/sandbox/re_gap1_production_probe.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

CAMPAIGN = "Open_road"
PLAYER = "Tester"


def main() -> int:
    import logging

    logging.getLogger().setLevel(logging.ERROR)

    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    tmp = Path(tempfile.mkdtemp(prefix="gap1_probe_"))
    saves = tmp / "saves"
    (saves / "locations").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        _ROOT / "frontend/map_editor/campaigns/Open_road",
        saves / "Open_road",
    )
    shutil.copy2(
        _ROOT / "backend/data/locations/location_templates.json",
        saves / "locations/location_templates.json",
    )
    settings.saves_dir = str(saves)  # S239: мутация ДО build

    loop = build_game_loop(data_dir=saves)
    loop.load_campaign(CAMPAIGN, CAMPAIGN)

    from app.services.game_loop.scene_init import ensure_scene_initialized

    ensure_scene_initialized(loop, CAMPAIGN)

    # S115-прецедент: аватар через штатный API
    from app.services.player_session_service import player_session_service

    player_session_service.select_player(CAMPAIGN, PLAYER)

    from app.models.schemas import CharacterSheet
    from app.services.character_service import CharacterService
    from app.models.npc_state import BODY_STATE_HEALTHY, NPCState

    _char_svc = CharacterService(root=str(loop._saves_dir))
    _sheet = CharacterSheet(name=PLAYER, archetype="Drifter", temperament="Stoic")
    _char_svc.upsert_character(CAMPAIGN, _sheet)

    _avatar = NPCState(npc_id=PLAYER)
    _avatar.drives = {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    _avatar.psyche = {"willpower": 50, "breakpoint": 70, "loyalty_true": 0}
    _avatar.body_state = dict(BODY_STATE_HEALTHY)
    loop.avatar_service.save_state(CAMPAIGN, _avatar)

    # ── World-вход: разведённые отношения к player (легальная инъекция входа,
    #    прецедент G2 «инъекция входа легальна, beliefs/intents — нет»).
    #    Канон: npc_dict relationship_cache (loader:205), масштаб 0-100.
    #    Ось trust: A=-60 (пробивает порог -30), B=+60. Остальное — Vacuum.
    from app.services.tick_orchestrator import _get_alive_npcs  # может не существовать — см. guard ниже

    scene = loop.scene_state_manager.get_scene(CAMPAIGN) if hasattr(loop, "scene_state_manager") else None
    # Ранний guard: если API-доступа к NPC-диктам нет — падаем честно (INVALID RUN, не вердикт)
    _npcs = scene.get("npc_positions", {}) if isinstance(scene, dict) else {}
    if not _npcs:
        print("[GAP1-PROBE] FAIL-FAST: npc_positions недоступны — API-археология нужна, вердикта нет")
        return 2

    _set_trust = {"merchant_goran": -60.0, "maid_lusya": 60.0}
    _injected = []
    for _nid, _val in _set_trust.items():
        _npc_dict = next(
            (d for d in loop.all_npcs_raw if isinstance(d, dict) and d.get("id") == _nid),
            None,
        ) if hasattr(loop, "all_npcs_raw") else None
        if _npc_dict is None:
            print(f"[GAP1-PROBE] FAIL-FAST: {_nid} не найден в all_npcs_raw — вердикта нет")
            return 2
        _rc = _npc_dict.setdefault("relationship_cache", {})
        _rc["player"] = {"trust": _val, "fear": 0.0}
        _injected.append((_nid, _val))
    print(f"[GAP1-PROBE] INJECTED: {_injected}")

    # ── Одноразовый P3-зонд (временный, удалить после прогона — соблюдено):
    #    печать фактических fear/trust/bias в _compute_bias живого контура.
    import app.services.npc.interpretation_engine as _ie

    _orig_bias = _ie.InterpretationEngine._compute_bias

    def _probe_bias(self, state, actor_is_player):
        _fb, _tb = _orig_bias(self, state, actor_is_player)
        if actor_is_player:
            _rc = getattr(state, "relationship_cache", {}) or {}
            _p = _rc.get("player", {})
            print(
                f"[GAP1-PROBE][P3] npc={state.npc_id} trust_in={_p.get('trust')} "
                f"fear_in={_p.get('fear')} trust_bias={_tb.trust_bias} threat_bias={_fb.threat_bias}"
            )
        return _fb, _tb

    _ie.InterpretationEngine._compute_bias = _probe_bias  # monkey-patch наблюдателя

    # ── Player-интервенция ( actor_id='player' активирует bias-ветки)
    from app.contracts.interventions import InterventionEvent

    _intervention = InterventionEvent(
        source="player",
        payload={
            "text": "привет всем",
            "player_name": PLAYER,
            "semantic_action": "TALK",
            "target_id": "merchant_goran",
            "tick": 2,
        },
        tick=2,
    )
    loop.submit_intervention(_intervention) if hasattr(loop, "submit_intervention") else None
    if not hasattr(loop, "submit_intervention"):
        print("[GAP1-PROBE] FAIL-FAST: submit_intervention API отсутствует — вердикта нет")
        return 2

    result = loop.idle_tick(CAMPAIGN)
    print(f"[GAP1-PROBE] idle_tick status={result.get('status') if isinstance(result, dict) else 'n/a'}")

    print("[GAP1-PROBE] PROBE DONE — вердикт: см. P3-строки (trust_bias A=-0.2 vs B=0.0 при trust_in -60/+60)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
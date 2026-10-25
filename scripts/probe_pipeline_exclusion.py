import logging, os, sys, copy, math
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")

from tests.gameplay.harness import TavernGameplayHarness
from app.services.npc.npc_tick_pipeline import NpcTickPipeline
from app.services.npc.npc_loader import load_profile_from_legacy_json
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

_orig_run = NpcTickPipeline.run

def _patched_run(self, state):
    _is_player_turn = state.hub_event is not None
    _npcs_to_process = state.nearby_npcs if _is_player_turn else state.all_npcs_raw
    input_ids = [n.get("npc_id") or n.get("id") for n in (_npcs_to_process or [])]
    print(f"[ACCOUNTING] input NPC count: {len(input_ids)} ids: {input_ids}")

    processed_ids = []
    excluded_ids = []

    for npc in (_npcs_to_process or []):
        npc_id = npc.get("npc_id") or npc.get("id")
        state_l2 = load_l2_state_from_runtime_dict(dict(npc)) if npc_id else None

        if npc_id and _is_player_turn and not (state.line_of_sight.get(npc_id, False) if state.line_of_sight else False):
            excluded_ids.append((npc_id, "player_turn_no_los"))
            continue

        _npc_profile = None
        for _n in state.all_npcs_raw:
            if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
                _npc_profile = _n
                break
        if not _npc_profile:
            excluded_ids.append((npc_id, "profile_not_found"))
            continue

        _npc_dict_for_write = copy.deepcopy(dict(_npc_profile))
        try:
            profile_l0 = load_profile_from_legacy_json(_npc_dict_for_write)
        except Exception as e:
            excluded_ids.append((npc_id, f"profile_l0_error: {e}"))
            continue

        if profile_l0 is None:
            excluded_ids.append((npc_id, "profile_l0_None"))
            continue

        _effective_drives = state.effective_drives_map.get(npc_id)
        if _effective_drives is None:
            excluded_ids.append((npc_id, "effective_drives_None"))
            continue

        processed_ids.append(npc_id)

    print(f"[ACCOUNTING] processed: {processed_ids}")
    print(f"[ACCOUNTING] excluded: {excluded_ids}")

    _thief = next((n for n in (_npcs_to_process or []) if (n.get("npc_id") or n.get("id")) == "thief_shadow"), None)
    if _thief:
        print(f"[THIEF_SHADOW] Detailed diagnosis:")
        _td = copy.deepcopy(dict(_thief))
        try:
            _pl0 = load_profile_from_legacy_json(_td)
            print(f"  profile_l0: {_pl0 is not None}")
            if _pl0:
                print(f"  archetype: {getattr(_pl0, 'archetype', 'MISSING')}")
                print(f"  drives_base: {getattr(_pl0, 'drives_base', 'MISSING')}")
        except Exception as e:
            print(f"  profile_l0 error: {e}")
        _ed = state.effective_drives_map.get("thief_shadow")
        print(f"  effective_drives: {_ed}")
        _edm_keys = list(state.effective_drives_map.keys()) if hasattr(state, "effective_drives_map") else []
        print(f"  effective_drives_map keys: {_edm_keys}")

    return _orig_run(self, state)

NpcTickPipeline.run = _patched_run

h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(1)
h.dispose()

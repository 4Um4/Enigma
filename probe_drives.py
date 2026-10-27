import sys
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_h.advance_ticks(2)

# 1. inspect guard_borko через harness
_gb = _h.inspect_npc("guard_borko")
print("=== guard_borko via inspect_npc ===")
if _gb:
    print(f"  archetype={_gb.get('archetype')}")
    print(f"  drives_runtime={_gb.get('drives')}")
    print(f"  drives_base={_gb.get('drives_base', _gb.get('personality', {}).get('drives_base'))}")
    print(f"  effective_hp={_gb.get('effective_hp')}")
    print(f"  effective_max_hp={_gb.get('effective_max_hp')}")
    print(f"  perceptual_kernel={_gb.get('perceptual_kernel')}")
else:
    print("  MISSING")

# 2. NPC state из scene_state (production-path)
_scene = _h.get_scene_fresh() or {}
_ns = (_scene.get("npc_states", {}) or {}).get("guard_borko", {})
print(f"\n=== guard_borko from scene_state.npc_states ===")
print(f"  drives={_ns.get('drives')}")
print(f"  archetype={_ns.get('archetype')}")

# 3. Попробуем найти где можно seed-нуть drives
from app.services.npc.life_engine import get_life_engine
_le = get_life_engine()
_states = _le.get_npc_states("Open_road")
_gb_le = next((s for s in _states if s.get("npc_id") == "guard_borko"), None)
print(f"\n=== guard_borko from life_engine ===")
if _gb_le:
    print(f"  drives_runtime={_gb_le.get('drives_runtime')}")
    print(f"  archetype={_gb_le.get('archetype')}")
    print(f"  perceptual_kernel={_gb_le.get('perceptual_kernel')}")

# 4. NPC profile из config
from app.services.npc.npc_loader import load_npcs_merged
_npcs = load_npcs_merged(_h.game_loop._saves_dir)
_gb_profile = next((n for n in _npcs if n.get("id") == "guard_borko"), None)
if _gb_profile:
    print(f"\n=== guard_borko from config ===")
    print(f"  archetype={_gb_profile.get('archetype')}")
    print(f"  drives={_gb_profile.get('drives')}")
    print(f"  drives_base={_gb_profile.get('drives_base', _gb_profile.get('personality', {}).get('drives_base'))}")

_h.dispose()

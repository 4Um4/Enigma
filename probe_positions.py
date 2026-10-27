import sys
sys.path.insert(0, "backend")
from tests.gameplay.harness import TavernGameplayHarness
_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_h.advance_ticks(2)
_scene = _h.get_scene_fresh() or {}
_np = _scene.get("npc_positions", {}) or {}
print("NPC positions:")
for k, v in _np.items():
    print(f"  {k}: {v}")
print(f"\nplayer position: {_np.get('player', 'MISSING')}")
print(f"maid_lusya position: {_np.get('maid_lusya', 'MISSING')}")
print(f"guard_borko position: {_np.get('guard_borko', 'MISSING')}")

from app.services.events.event_bus import get_event_bus
from app.services.spatial.spatial_query_service import SpatialQueryService
_bus = get_event_bus()
_sq = getattr(_h.game_loop, "_spatial_query_service", None) or getattr(_h.game_loop._tick_orch, "_spatial_query", None)
print(f"\nspatial_query: {_sq}")
if _sq:
    print(f"  _npc_positions: {getattr(_sq, '_npc_positions', None)}")
    _d = _sq.distance("player", "maid_lusya") if hasattr(_sq, "distance") else "no distance method"
    print(f"  distance(player, maid_lusya) = {_d}")

print("\nRelationshipStore API:")
_rel = _h.game_loop.memory_manager._relationships
print(f"  type: {type(_rel).__name__}")
print(f"  methods: {[m for m in dir(_rel) if not m.startswith('__')]}")
print(f"  get_all(Open_road): {_rel.get_all('Open_road')}")

_h.dispose()

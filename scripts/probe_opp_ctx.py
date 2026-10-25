import logging, os, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from tests.gameplay.harness import TavernGameplayHarness
h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()
h.advance_ticks(2)

print("W3_G2_ENABLED:", os.environ.get("W3_G2_ENABLED", "OFF"))
print("W3_G3_ENABLED:", os.environ.get("W3_G3_ENABLED", "OFF"))

# _tick_orch — что в нём про opportunity?
_to = h.game_loop._tick_orch
_attrs = [a for a in dir(_to) if "opp" in a.lower() or "afford" in a.lower() or "weapon" in a.lower() or "steal" in a.lower()]
print("_tick_orch attrs:", _attrs)

# Проверим W3_G2 guard и affordance_facts
try:
    from app.services.world.affordance_facts import _g2_enabled
    print(f"_g2_enabled: {_g2_enabled()}")
except Exception as e:
    print(f"_g2_enabled import error: {e}")

# Читаем config — где хранятся env defaults
try:
    from app.core.config import settings
    print(f"settings.env W3_G2: {os.environ.get('W3_G2_ENABLED', '<not set>')}")
except Exception as e:
    print(f"settings import error: {e}")

# Проверить npc_tick_pipeline — где build_opportunity_context
try:
    from app.services.npc.npc_tick_pipeline import NpcTickPipeline
    _src_lines = []
    import inspect
    _src = inspect.getsource(NpcTickPipeline)
    for i, line in enumerate(_src.splitlines()):
        if "opp" in line.lower() or "afford" in line.lower() or "weapon" in line.lower() or "steal" in line.lower():
            _src_lines.append(f"  L{i}: {line.strip()}")
    print(f"npc_tick_pipeline opportunity/affordance lines ({len(_src_lines)}):")
    for l in _src_lines[:10]:
        print(l)
except Exception as e:
    print(f"npc_tick_pipeline inspect error: {e}")

h.dispose()

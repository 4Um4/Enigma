"""R4/PAT-x8 debug: проверить, вызывается ли mark_tick_aborted при exception в idle_tick."""
import sys
sys.path.insert(0, ".")
from tests.gameplay.harness import TavernGameplayHarness
from unittest.mock import patch


def main():
    h = TavernGameplayHarness(seed=42)
    h.new_game()
    gl = h.game_loop
    sm = gl.scene_manager

    # Spy на mark_tick_aborted
    orig_mark = sm.mark_tick_aborted
    def spy_mark(campaign_id):
        print(f"[DEBUG] mark_tick_aborted called: campaign_id={campaign_id}, _tick_locked={sm._tick_locked}, _tick_campaign_id={sm._tick_campaign_id}")
        result = orig_mark(campaign_id)
        print(f"[DEBUG] after mark_tick_aborted: _tick_aborted={sm._tick_aborted}")
        return result
    sm.mark_tick_aborted = spy_mark

    # Spy на unlock_tick
    orig_unlock = sm.unlock_tick
    def spy_unlock(campaign_id):
        print(f"[DEBUG] unlock_tick called: campaign_id={campaign_id}, _tick_locked={sm._tick_locked}, _tick_aborted={sm._tick_aborted}")
        return orig_unlock(campaign_id)
    sm.unlock_tick = spy_unlock

    # Spy на atomic_commit_all
    orig_ac = sm._persistence.atomic_commit_all
    def spy_ac(**kwargs):
        cid = kwargs.get("campaign_id")
        n_scenes = len(kwargs.get("all_scenes", {}))
        print(f"[DEBUG] atomic_commit_all called: campaign_id={cid}, n_scenes={n_scenes}")
        return orig_ac(**kwargs)
    sm._persistence.atomic_commit_all = spy_ac

    # Проверить, что такое _tick_orch
    print(f"[DEBUG] gl._tick_orch type: {type(gl._tick_orch).__name__}")
    print(f"[DEBUG] gl._tick_orch id: {id(gl._tick_orch)}")
    print(f"[DEBUG] has execute: {hasattr(gl._tick_orch, 'execute')}")

    # Inject exception в _tick_orch.execute
    def raising_execute(*args, **kwargs):
        print(f"[DEBUG] raising_execute called, args count={len(args)}, kwargs keys={list(kwargs.keys())[:5]}")
        raise RuntimeError("DEBUG test failure")

    with patch.object(gl._tick_orch, "execute", side_effect=raising_execute):
        try:
            gl.idle_tick(h.campaign_id)
            print("[DEBUG] idle_tick completed WITHOUT exception")
        except RuntimeError as e:
            print(f"[DEBUG] idle_tick raised RuntimeError: {e}")
        except Exception as e:
            print(f"[DEBUG] idle_tick raised {type(e).__name__}: {e}")

    print(f"[DEBUG] final state: _tick_locked={sm._tick_locked}, _tick_aborted={sm._tick_aborted}")
    h.dispose()


if __name__ == "__main__":
    main()

"""GC-01 Block 65 — Retry D2 (correct indent) + Fix D3 (MOCK all configs)."""
import sys
from pathlib import Path

ROOT = Path(".")
results = []

def ok(name, msg):
    results.append((name, "OK", msg))
    print(f"[OK]   {name}: {msg}")

def warn(name, msg):
    results.append((name, "WARN", msg))
    print(f"[WARN] {name}: {msg}")

def fail(name, msg):
    results.append((name, "FAIL", msg))
    print(f"[FAIL] {name}: {msg}")


# === D2 retry: correct indentation (20 spaces for if, 24 for append) ===
def fix_d2():
    p = ROOT / "backend/app/services/npc/npc_tick_pipeline.py"
    src = p.read_text(encoding="utf-8")
    # Exact pattern from 64c output: 20 spaces before 'if', 24 before 'append'
    candidates = [
        # Primary: 20-space indent (from 64c observation)
        (
            "                    if _movement:\n"
            "                        movement_intents.append(_movement)\n"
        ),
        # Fallback: 16-space indent
        (
            "                if _movement:\n"
            "                    movement_intents.append(_movement)\n"
        ),
        # Fallback: 24-space indent
        (
            "                        if _movement:\n"
            "                            movement_intents.append(_movement)\n"
        ),
    ]
    new_template = (
        "{indent}# D2 fix (GC-01 / ADR-O-407): player turn pauses world time —\n"
        "{indent}# no NEW traversal initiation. Existing in-flight traversals\n"
        "{indent}# may continue interpolating (ADR-O-201 E5 ghost interpolation),\n"
        "{indent}# but no new movement_intents during player_action.\n"
        "{indent}if _movement and not _is_player_turn:\n"
        "{indent}    movement_intents.append(_movement)\n"
    )
    for idx, old in enumerate(candidates):
        if old in src:
            # Detect indent from old pattern
            indent = " " * (len(old) - len(old.lstrip()))
            new = new_template.format(indent=indent)
            src = src.replace(old, new, 1)
            p.write_text(src, encoding="utf-8")
            ok("D2", f"gate added (variant {idx+1}, indent={len(indent)} spaces)")
            return
    warn("D2", f"none of {len(candidates)} indent variants matched")


# === D3 fix: set MOCK on ALL model configs, not just qwen_7b ===
def fix_d3():
    p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
    src = p.read_text(encoding="utf-8")

    # Replace the activate() method to iterate over ALL configs
    old_activate = '''            def activate(self):
                pool = _get_model_pool()
                self._cfg = pool._model_configs.get("qwen_7b")
                if self._cfg is None:
                    pytest.skip(
                        "qwen_7b not registered in pool._model_configs after h.new_game()"
                    )
                self._orig_pt = self._cfg.provider_type
                self._orig_env = settings.environment
                self._cfg.provider_type = ProviderType.MOCK
                settings.environment = "development"
                pool.unload_all()
                self._active = True

            def restore(self):
                if not self._active:
                    return
                pool = _get_model_pool()
                self._cfg.provider_type = self._orig_pt
                settings.environment = self._orig_env
                pool.unload_all()
                self._active = False
'''
    new_activate = '''            def activate(self):
                pool = _get_model_pool()
                # Set MOCK on ALL model configs — router picks capability model
                # dynamically (e.g. yandexgpt_8b for NARRATIVE, qwen_3_5_9b fallback).
                # Setting MOCK only on qwen_7b misses the actually-used models.
                self._cfgs = list(pool._model_configs.values())
                if not self._cfgs:
                    pytest.skip(
                        "no model configs registered in pool after h.new_game()"
                    )
                self._orig_pts = [c.provider_type for c in self._cfgs]
                self._orig_env = settings.environment
                for c in self._cfgs:
                    c.provider_type = ProviderType.MOCK
                settings.environment = "development"
                pool.unload_all()
                self._active = True

            def restore(self):
                if not self._active:
                    return
                pool = _get_model_pool()
                for c, orig_pt in zip(self._cfgs, self._orig_pts):
                    c.provider_type = orig_pt
                settings.environment = self._orig_env
                pool.unload_all()
                self._active = False
'''
    if old_activate in src:
        src = src.replace(old_activate, new_activate, 1)
        p.write_text(src, encoding="utf-8")
        ok("D3", "activate() now sets MOCK on ALL model configs")
    else:
        warn("D3", "activate() block not found (already patched?)")


if __name__ == "__main__":
    print("=" * 70)
    print("GC-01 Block 65 — Retry D2 + Fix D3")
    print("=" * 70)
    fix_d2()
    fix_d3()
    print()
    for name, status, msg in results:
        print(f"  [{status:4}] {name}: {msg}")
    fails = [r for r in results if r[1] == "FAIL"]
    sys.exit(0 if not fails else 1)
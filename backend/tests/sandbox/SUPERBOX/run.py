#!/usr/bin/env python
"""
Путь: backend/tests/sandbox/SUPERBOX/run.py
ENIGMA Sandbox Suite — единый ангар исследовательских инструментов.

Запуск:
  cd backend
  python -m tests.sandbox.SUPERBOX.run npc quick_debug
  python -m tests.sandbox.SUPERBOX.run drift long_horizon
  python -m tests.sandbox.SUPERBOX.run drift mass_traversal
  python -m tests.sandbox.SUPERBOX.run drift save_load_storm
  python -m tests.sandbox.SUPERBOX.run drift chunk_migration
  python -m tests.sandbox.SUPERBOX.run behavior trait_economy
  python -m tests.sandbox.SUPERBOX.run player_stress
  python -m tests.sandbox.SUPERBOX.run all

Правило: все долгоживущие исследовательские инструменты живут в SUPERBOX/.
Unit/integration тесты — в tests/sandbox/micro/, tests/sandbox/system/.
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        print(__doc__)
        return

    tool = args[0]
    mode = args[1] if len(args) > 1 else "default"

    if tool == "npc":
        from tests.sandbox.SUPERBOX.npc_sandbox import main as npc_main

        # Передаём оставшиеся аргументы
        sys.argv = [sys.argv[0]] + args[1:]
        npc_main()

    elif tool == "drift":
        from tests.sandbox.SUPERBOX.drift_laboratory import main as drift_main

        session_id = args[2] if len(args) > 2 else None
        drift_main(mode, session_id=session_id)

    elif tool == "behavior":
        from tests.sandbox.SUPERBOX.behavior_laboratory import run_trait_economy_probe

        if mode == "trait_economy":
            run_trait_economy_probe()
        else:
            print(f"Unknown behavior scenario: {mode}")

    elif tool == "player_stress":
        import asyncio

        from tests.sandbox.SUPERBOX.player_stress_test import run_player_stress_test

        success = asyncio.run(run_player_stress_test())
        sys.exit(0 if success else 1)

    elif tool == "causal":
        import asyncio

        from tests.sandbox.SUPERBOX.causal_validation import CausalValidator

        validator = CausalValidator()
        success = asyncio.run(validator.run_all())
        sys.exit(0 if success else 1)

    elif tool == "all":
        print("=== NPC Sandbox ===")
        from tests.sandbox.SUPERBOX.npc_sandbox import main as npc_main

        sys.argv = [sys.argv[0], "quick_debug"]
        npc_main()

        print("\n=== Drift Laboratory ===")
        from tests.sandbox.SUPERBOX.drift_laboratory import main as drift_main

        drift_main("long_horizon")

        print("\n=== Behavior Laboratory ===")
        from tests.sandbox.SUPERBOX.behavior_laboratory import run_trait_economy_probe

        run_trait_economy_probe()

    else:
        print(f"Неизвестный инструмент: {tool}")
        print("Доступные: npc, drift, behavior, all")
        sys.exit(1)


if __name__ == "__main__":
    main()

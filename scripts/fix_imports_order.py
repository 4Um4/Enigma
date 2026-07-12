import os

files = [
    "backend/app/models/social.py",
    "backend/app/models/thick_scene_change.py",
    "backend/app/models/world_snapshot.py",
    "backend/app/models/schemas.py",
    "backend/app/models/economy.py",
    "backend/app/models/pipeline_context.py",
    "backend/app/models/phase8.py",
    "backend/app/models/character.py",
    "backend/app/models/physical.py",
    "backend/app/services/state/persistence_port.py",
    "backend/app/services/state/sqlite_persistence_adapter.py",
    "backend/app/services/state/json_persistence_adapter.py",
    "backend/app/services/state/context_builder.py",
    "backend/app/services/simulation/world_state.py",
    "backend/app/models/will.py",
]

for f in files:
    if not os.path.exists(f):
        continue
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()

    lines = content.split("\n")

    # Ищем импорт typing, который мог встать в самую первую строку
    typing_line = ""
    typing_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_line = line
            typing_idx = i
            break

    # Если typing на самом верху (до __future__), перемещаем его
    if typing_idx == 0 and "from __future__" in content:
        # Удаляем его оттуда
        del lines[typing_idx]

        # Ищем строку __future__ и вставляем typing сразу после неё
        for i, line in enumerate(lines):
            if "from __future__ import annotations" in line:
                lines.insert(i + 1, typing_line)
                break

        with open(f, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        print(f"Fixed import order in {f}")

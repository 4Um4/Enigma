import os
import re


def process_file(filepath: str) -> bool:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    original = content

    # 1. Заменяем создание MovementIntent на MacroMovementGoal
    content = content.replace("MovementIntent(", "MacroMovementGoal(")

    # 2. Заменяем импорт MovementIntent на MacroMovementGoal
    content = content.replace("import MovementIntent", "import MacroMovementGoal")

    # 3. Заменяем npc_id=npc_id на actor_id=npc_id в конструкторах
    content = re.sub(
        r"(\bMacroMovementGoal\([^)]*?)\bnpc_id=",
        r"\1actor_id=",
        content,
        flags=re.DOTALL,
    )

    # 4. Заменяем доступ к .npc_id на .actor_id для объектов intent
    content = content.replace("intent.npc_id", "intent.actor_id")
    content = content.replace("intent_id.npc_id", "intent_id.actor_id")

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


count = 0
for root, dirs, files in os.walk("backend/app"):
    if "__pycache__" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            if process_file(filepath):
                count += 1
                print(f"Fixed: {filepath}")

print(f"Total files fixed: {count}")

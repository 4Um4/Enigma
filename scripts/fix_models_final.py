import os
import re

FILES = [
    "backend/app/models/social.py",
    "backend/app/models/thick_scene_change.py",
    "backend/app/models/world_snapshot.py",
    "backend/app/models/economy.py",
    "backend/app/models/character.py",
    "backend/app/models/phase8.py",
    "backend/app/models/schemas.py",
    "backend/app/models/npc_state.py",
]

def fix_content(content: str) -> str:
    # Фиксим заглавные Dict и List (если они без скобок)
    content = re.sub(r'(:\s*)Dict(?!\[)', r'\1Dict[str, Any]', content)
    content = re.sub(r'(->\s*)Dict(?!\[)', r'\1Dict[str, Any]', content)
    content = re.sub(r'(Optional\[)Dict(?!\])', r'\1Dict[str, Any]', content)
    
    content = re.sub(r'(:\s*)List(?!\[)', r'\1List[Any]', content)
    content = re.sub(r'(->\s*)List(?!\[)', r'\1List[Any]', content)
    content = re.sub(r'(Optional\[)List(?!\])', r'\1List[Any]', content)
    
    # Фиксим строчные dict и list (на всякий случай)
    content = re.sub(r'(:\s*)dict(?!\[)', r'\1Dict[str, Any]', content)
    content = re.sub(r'(->\s*)dict(?!\[)', r'\1Dict[str, Any]', content)
    
    return content

for f in FILES:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        new_content = fix_content(content)
        if new_content != content:
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print(f"Fixed generics: {f}")

# 1. Вырезаем мёртвый код в npc_state.py по условию
filepath = "backend/app/models/npc_state.py"
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()
new_lines = []
skip_mode = False
for line in lines:
    if "_bl = float(state.body_state.get" in line:
        skip_mode = True
    if "return state" in line and skip_mode:
        new_lines.append("        return state\n")
        skip_mode = False
        continue
    if not skip_mode:
        new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Fixed dead code in npc_state.py")

# 2. schemas.py: добавляем -> None к функции без аннотации (строка ~295)
filepath = "backend/app/models/schemas.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
# Ищем любой def без -> и добавляем -> None
content = re.sub(r'(def\s+\w+\(self\))\s*:', r'\1 -> None:', content)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed untyped def in schemas.py")
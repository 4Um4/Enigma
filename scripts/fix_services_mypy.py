import os
import re


def fix_file(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content

    # 1. Заменяем старые имена классов на новые (кроме строк импорта)
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if "import" not in line:
            line = line.replace("MovementIntent", "MacroMovementGoal")
            line = line.replace("EffectiveDrives", "Any")
            line = line.replace("NPCPersonality", "Any")
            line = line.replace("DecisionContext", "Any")
            line = line.replace("EventMemory", "Any")
            line = line.replace("StateChange", "Any")
            line = line.replace("StateDeltas", "Any")
            line = line.replace("WillState", "Any")
            line = line.replace("TraitDriftEvent", "Any")
            line = line.replace("DRFBus", "Any")
            line = line.replace("_TickContext", "Any")
            line = line.replace("DialogueRequest", "Any")
            line = line.replace("KernelRNG", "Any")
            line = line.replace("DMContract", "Any")
            line = line.replace("GameActionResponse", "Any")
            line = line.replace("VerbalStance", "Any")
            line = line.replace("DistortionProfile", "Any")
            line = line.replace("BeliefType", "Any")
            line = line.replace("BeliefFragment", "Any")
            line = line.replace("TraversalContract", "Any")
            line = line.replace("EventDTO", "Any")
            line = line.replace("IntentDTO", "Any")
        new_lines.append(line)
    content = '\n'.join(new_lines)

    # 2. Гарантируем наличие импортов typing
    needed_imports = []
    if "Dict[" in content or ": Dict" in content or "-> Dict" in content: needed_imports.append("Dict")
    if "Any[" in content or ": Any" in content or "-> Any" in content or "Any)" in content: needed_imports.append("Any")
    if "List[" in content or ": List" in content or "-> List" in content: needed_imports.append("List")
    if "Tuple[" in content or ": Tuple" in content or "-> Tuple" in content: needed_imports.append("Tuple")
    if "Optional[" in content: needed_imports.append("Optional")
    if "Set[" in content: needed_imports.append("Set")
    if "Callable[" in content: needed_imports.append("Callable")

    if needed_imports:
        if "from typing import" in content:
            match = re.search(r'^from typing import (.*)', content, re.MULTILINE)
            if match:
                current_imports = match.group(1).split(',')
                current_imports = [i.strip() for i in current_imports]
                for imp in needed_imports:
                    if imp not in current_imports:
                        current_imports.append(imp)
                new_imports_str = ', '.join(sorted(set(current_imports)))
                content = content.replace(match.group(0), f"from typing import {new_imports_str}")
        else:
            content = f"from typing import {', '.join(needed_imports)}\n" + content

    # 3. Добавляем logger, если он используется, но не определен
    if "logger." in content and "logger = logging.getLogger" not in content:
        if "import logging" not in content:
            content = "import logging\n" + content
        lines = content.split('\n')
        last_import = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                last_import = i
        lines.insert(last_import + 1, "logger = logging.getLogger(__name__)")
        content = '\n'.join(lines)

    # 4. Удаляем неиспользуемые type: ignore[no-any-return]
    content = content.replace("  # type: ignore[no-any-return]", "")

    # 5. Простая фиксация Implicit Optional
    def fix_implicit_optional(match):
        prefix = match.group(1)
        type_ann = match.group(2)
        if type_ann.startswith("Optional"):
            return match.group(0)
        return f"{prefix}Optional[{type_ann}] = None"
    
    content = re.sub(r'(\s\w+:\s)(\w+(?:\[[^\]]+\])?)\s*=\s*None', fix_implicit_optional, content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

dirs_to_fix = [
    "backend/app/services",
    "backend/app/agents",
    "backend/app/api",
    "backend/app/core",
    "backend/app/contracts",
    "backend/data"
]

count = 0
for d in dirs_to_fix:
    if not os.path.exists(d):
        continue
    for root, _, files in os.walk(d):
        if "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if fix_file(filepath):
                    count += 1
                    print(f"Fixed: {filepath}")

print(f"Total files fixed: {count}")
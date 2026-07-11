import os
import re

FILES = [
    "backend/app/models/social.py",
    "backend/app/models/thick_scene_change.py",
    "backend/app/models/world_snapshot.py",
    "backend/app/models/schemas.py",
    "backend/app/models/economy.py",
    "backend/app/models/pipeline_context.py",
    "backend/app/models/phase8.py",
]

def process_file(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    changed = False
    
    # Добавляем импорты, если их нет
    if "from typing import" not in content:
        content = "from typing import Any, Dict, List\n" + content
        changed = True
    else:
        if "Any" not in content:
            content = content.replace("from typing import", "from typing import Any,", 1)
            changed = True
        if "Dict" not in content:
            content = content.replace("from typing import", "from typing import Dict,", 1)
            changed = True
        if "List" not in content:
            content = content.replace("from typing import", "from typing import List,", 1)
            changed = True

    # Заменяем голые dict и list в аннотациях
    def repl_dict(m):
        nonlocal changed
        changed = True
        return m.group(1) + "Dict[str, Any]" + m.group(3)
        
    def repl_list(m):
        nonlocal changed
        changed = True
        return m.group(1) + "List[Any]" + m.group(3)

    # Ищем ": dict" или "-> dict" или "Optional[dict]"
    content = re.sub(r'(:\s*)dict(\b)', repl_dict, content)
    content = re.sub(r'(->\s*)dict(\b)', repl_dict, content)
    content = re.sub(r'(Optional\[)dict(\])', repl_dict, content)
    
    # Ищем ": list" или "-> list" или "Optional[list]"
    content = re.sub(r'(:\s*)list(\b)', repl_list, content)
    content = re.sub(r'(->\s*)list(\b)', repl_list, content)
    content = re.sub(r'(Optional\[)list(\])', repl_list, content)
    
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    return changed

count = 0
for f in FILES:
    if os.path.exists(f):
        if process_file(f):
            count += 1
            print(f"Fixed: {f}")

print(f"Total files fixed: {count}")
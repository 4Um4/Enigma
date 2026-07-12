import os
import re


def fix_content(content: str) -> str:
    # Добавляем импорты, если их нет
    if "from typing import" not in content:
        content = "from typing import Any, Dict, List, Optional\n" + content
    else:
        if "Any" not in content:
            content = content.replace("from typing import", "from typing import Any,", 1)
        if "Dict" not in content:
            content = content.replace("from typing import", "from typing import Dict,", 1)
        if "List" not in content:
            content = content.replace("from typing import", "from typing import List,", 1)

    # Заменяем голые dict и list в аннотациях
    content = re.sub(r'(:\s*)dict(?!\[)', r'\1Dict[str, Any]', content)
    content = re.sub(r'(->\s*)dict(?!\[)', r'\1Dict[str, Any]', content)
    content = re.sub(r'(Optional\[)dict(\])', r'\1Dict[str, Any]\2', content)
    
    content = re.sub(r'(:\s*)list(?!\[)', r'\1List[Any]', content)
    content = re.sub(r'(->\s*)list(?!\[)', r'\1List[Any]', content)
    content = re.sub(r'(Optional\[)list(\])', r'\1List[Any]\2', content)
    
    # Заменяем голые tuple
    content = re.sub(r'(:\s*)tuple(?!\[)', r'\1Tuple[Any, ...]', content)
    content = re.sub(r'(->\s*)tuple(?!\[)', r'\1Tuple[Any, ...]', content)
    
    return content

dirs_to_fix = [
    "backend/app/services/npc",
    "backend/app/services/spatial",
    "backend/app/services/social",
    "backend/app/services/reaction",
    "backend/app/services/memory",
    "backend/app/services/economy",
    "backend/app/services/events",
    "backend/app/services/verbalization",
    "backend/app/services/scene",
    "backend/app/services/temporal",
    "backend/app/services/perception",
    "backend/app/services/affective",
    "backend/app/services/offscreen",
    "backend/app/services/world",
    "backend/app/services/execution",
    "backend/app/services/integration",
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
                with open(filepath, 'r', encoding='utf-8') as f:
                    original = f.read()
                new_content = fix_content(original)
                if new_content != original:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    count += 1
                    print(f"Fixed: {filepath}")

print(f"Total files fixed: {count}")
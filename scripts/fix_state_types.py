import os
import re

FILES = [
    "backend/app/services/state/persistence_port.py",
    "backend/app/services/state/json_persistence_adapter.py",
    "backend/app/services/state/sqlite_persistence_adapter.py",
    "backend/app/services/state/context_builder.py",
    "backend/app/services/simulation/world_state.py",
    "backend/app/models/will.py",
]


def fix_content(content: str) -> str:
    # Добавляем импорты, если их нет
    if "from typing import" not in content:
        content = "from typing import Any, Dict, List, Optional\n" + content
    else:
        if "Any" not in content:
            content = content.replace(
                "from typing import", "from typing import Any,", 1
            )
        if "Dict" not in content:
            content = content.replace(
                "from typing import", "from typing import Dict,", 1
            )
        if "List" not in content:
            content = content.replace(
                "from typing import", "from typing import List,", 1
            )

    # Заменяем голые dict и list в аннотациях
    content = re.sub(r"(:\s*)dict(?!\[)", r"\1Dict[str, Any]", content)
    content = re.sub(r"(->\s*)dict(?!\[)", r"\1Dict[str, Any]", content)
    content = re.sub(r"(Optional\[)dict(\])", r"\1Dict[str, Any]\2", content)

    content = re.sub(r"(:\s*)list(?!\[)", r"\1List[Any]", content)
    content = re.sub(r"(->\s*)list(?!\[)", r"\1List[Any]", content)
    content = re.sub(r"(Optional\[)list(\])", r"\1List[Any]\2", content)

    return content


for f in FILES:
    if os.path.exists(f):
        with open(f, "r", encoding="utf-8") as file:
            content = file.read()
        new_content = fix_content(content)
        if new_content != content:
            with open(f, "w", encoding="utf-8") as file:
                file.write(new_content)
            print(f"Fixed generics: {f}")

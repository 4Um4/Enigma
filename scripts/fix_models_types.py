import os
import re

FILES = [
    "backend/app/models/physical.py",
    "backend/app/models/psychological.py",
    "backend/app/models/npc_state.py",
]

def fix_physical(content: str) -> str:
    # Добавляем Any, если нет
    if "from typing import" in content and "Any" not in content:
        content = content.replace("from typing import", "from typing import Any,")
    elif "from typing import" not in content:
        content = "from typing import Any, Dict\n" + content
        
    content = content.replace("def to_dict(self) -> Dict:", "def to_dict(self) -> Dict[str, Any]:")
    content = content.replace("def from_dict(cls, data: Dict) ->", "def from_dict(cls, data: Dict[str, Any]) ->")
    return content

def fix_psychological(content: str) -> str:
    # Добавляем Dict, Any, если нет
    if "from typing import" in content:
        if "Dict" not in content:
            content = content.replace("from typing import", "from typing import Dict,")
        if "Any" not in content:
            content = content.replace("from typing import", "from typing import Any,")
    else:
        content = "from typing import Any, Dict\n" + content
        
    content = content.replace("-> dict:", "-> Dict[str, Any]:")
    content = content.replace("d: dict", "d: Dict[str, Any]")
    return content

def fix_npc_state(content: str) -> str:
    # 1. Добавляем TYPE_CHECKING в импорты typing
    if "TYPE_CHECKING" not in content:
        content = content.replace(
            "from typing import Any, Dict, List, Optional, Set, Tuple, Union",
            "from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING, Union"
        )
        
    # 2. Добавляем импорт Condition и Wound под TYPE_CHECKING
    if 'if TYPE_CHECKING:' not in content:
        # Вставляем после импорта behavior_mask
        content = content.replace(
            "from app.models.behavior_mask import BehaviorMaskState",
            "from app.models.behavior_mask import BehaviorMaskState\n\nif TYPE_CHECKING:\n    from app.models.physical import Condition, Wound"
        )
        
    # 3. Фикс BODY_STATE_DISABLED
    content = content.replace(
        'BODY_STATE_DISABLED: dict = dict  # type: ignore[assignment] —陷阱 guard, используйте dict(BODY_STATE_DISABLED_DATA)',
        'BODY_STATE_DISABLED: Any = dict  # 陷阱 guard, используйте dict(BODY_STATE_DISABLED_DATA)'
    )
    
    # 4. Заменяем голые dict и tuple в сигнатурах методов
    content = content.replace("npc_dict: dict", "npc_dict: Dict[str, Any]")
    content = content.replace("pk_dict: dict", "pk_dict: Dict[str, Any]")
    content = content.replace("-> tuple:", "-> Tuple[Any, ...]:")
    
    return content

for filepath in FILES:
    if not os.path.exists(filepath):
        print(f"Skip (not found): {filepath}")
        continue
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if "physical.py" in filepath:
        new_content = fix_physical(content)
    elif "psychological.py" in filepath:
        new_content = fix_psychological(content)
    elif "npc_state.py" in filepath:
        new_content = fix_npc_state(content)
    else:
        continue
        
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed: {filepath}")
    else:
        print(f"No changes: {filepath}")

print("Done!")
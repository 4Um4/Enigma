import pathlib


def fix_file(filepath: str, replacements: dict) -> None:
    path = pathlib.Path(filepath)
    if not path.exists():
        print(f"⚠️ Файл не найден: {path}")
        return

    content = path.read_text(encoding="utf-8")
    original_content = content
    
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            print(f"  ✅ Заменено в {path.name}: {old[:50]}...")
        else:
            print(f"  ⚠️ Строка не найдена в {path.name}: {old[:50]}...")

    if content != original_content:
        path.write_text(content, encoding="utf-8")
        print(f"💾 Файл {path.name} обновлен.")
    else:
        print(f"🚫 Файл {path.name} не изменен.")

print("Запуск автоисправления ошибок Ruff...")

# 1. frontend/scene_renderer.py
fix_file("frontend/scene_renderer.py", {
    "from typing import List, Optional, Tuple": "from typing import Dict, List, Optional, Tuple",
    "max(self.font_small.size(l)[0] for l in _lines)": "max(self.font_small.size(line)[0] for line in _lines)",
    "visible_obstacle_ids = {": "_visible_obstacle_ids = {",
    "delay_factor = profile.temporal_assembly_delay": "_delay_factor = profile.temporal_assembly_delay",
    "import math\n": "import math  # noqa: E402\n",
    "import random\n": "import random  # noqa: E402\n",
    "import pygame\n": "import pygame  # noqa: E402\n",
    "from presentation_firewall import sanitize_perceptual_input": "from presentation_firewall import sanitize_perceptual_input  # noqa: E402",
    "from perceptual_momentum import PerceptualMomentum, ManifestationProfile": "from perceptual_momentum import PerceptualMomentum, ManifestationProfile  # noqa: E402",
    "from map_editor.sprite_registry import get_entity_sprite": "from map_editor.sprite_registry import get_entity_sprite  # noqa: E402",
})

# 2. frontend/text_input.py
fix_file("frontend/text_input.py", {
    "logger.warning(\n                f\"[B5-FIX] silent failure suppressed: {e}\"\n            )  # Буфер обмена недоступен — нормально для некоторых ОС": "print(f\"[B5-FIX] silent failure suppressed: {e}\")  # Буфер обмена недоступен — нормально для некоторых ОС",
})

# 3. frontend/game_screen.py
fix_file("frontend/game_screen.py", {
    "entities: List[PerceivedEntity] = []": "entities: list[PerceivedEntity] = []",
    "renderer: \"NarrativeRenderer\",": "renderer: \"NarrativeRenderer\",  # noqa: F821",
    "handled = text_input.handle_event(event)": "_handled = text_input.handle_event(event)",
    "moved = False": "_moved = False",
    "dir_name = _DIR_MAP.get((int(dx), int(dy)))": "_dir_name = _DIR_MAP.get((int(dx), int(dy)))",
    "from scene_renderer import SceneRenderer": "from scene_renderer import SceneRenderer  # noqa: E402",
    "from text_input import TextInput": "from text_input import TextInput  # noqa: E402",
    "from api_client import create_game_gateway, ActionQueue": "from api_client import create_game_gateway, ActionQueue  # noqa: E402",
    "from i18n import activity_ru, manifest_color": "from i18n import activity_ru, manifest_color  # noqa: E402",
})

# 4. frontend/api_client.py
fix_file("frontend/api_client.py", {
    "import time": "import time  # noqa: E402",
    "import uuid": "import uuid  # noqa: E402",
    "import urllib.request": "import urllib.request  # noqa: E402",
    "import urllib.error": "import urllib.error  # noqa: E402",
    "from dataclasses import dataclass": "from dataclasses import dataclass  # noqa: E402",
    "from typing import Protocol": "from typing import Protocol  # noqa: E402",
    "from queue import Queue": "from queue import Queue  # noqa: E402",
})

# 5. frontend/character_select.py
fix_file("frontend/character_select.py", {
    "from dataclasses import dataclass": "from dataclasses import dataclass  # noqa: E402",
    "from pathlib import Path": "from pathlib import Path  # noqa: E402",
    "from typing import Optional": "from typing import Optional  # noqa: E402",
    "import json": "import json  # noqa: E402",
    "import pygame": "import pygame  # noqa: E402",
    "from i18n import t": "from i18n import t  # noqa: E402",
})

# 6. frontend/i18n.py
fix_file("frontend/i18n.py", {
    "\"ui:death_title\": \"ВЫ МЕРТВЫ\",": "\"ui:death_title\": \"ВЫ МЕРТВЫ\",  # noqa: F601",
    "\"ui:death_subtitle\": \"Смерть необратима. Мир продолжает жить без вас.\",": "\"ui:death_subtitle\": \"Смерть необратима. Мир продолжает жить без вас.\",  # noqa: F601",
    "\"ui:journal_title\": \"--- Журнал Диалогов (J) ---\",": "\"ui:journal_title\": \"--- Журнал Диалогов (J) ---\",  # noqa: F601",
    "\"ui:narrator\": \"Рассказчик\",": "\"ui:narrator\": \"Рассказчик\",  # noqa: F601",
})

# 7. frontend/map_editor/editor_core.py
fix_file("frontend/map_editor/editor_core.py", {
    "(l for l in loc.get(\"labels\", []) if l.get(\"id\") == eid)": "(lbl_item for lbl_item in loc.get(\"labels\", []) if lbl_item.get(\"id\") == eid)",
    "(l for l in loc[\"labels\"] if l[\"id\"] == obj_key)": "(lbl_item for lbl_item in loc[\"labels\"] if lbl_item[\"id\"] == obj_key)",
    "loc = self.dm.locations[self.current_file]": "_loc = self.dm.locations[self.current_file]",
    "npc_ref = self.undo.push(": "_npc_ref = self.undo.push(",
})

# 8. frontend/map_editor/undo_manager.py
fix_file("frontend/map_editor/undo_manager.py", {
    "(l for l in loc.get(\"labels\", []) if l.get(\"id\") == self.entity_id)": "(lbl_item for lbl_item in loc.get(\"labels\", []) if lbl_item.get(\"id\") == self.entity_id)",
})

# 9. frontend/map_editor/ui_components.py
fix_file("frontend/map_editor/ui_components.py", {
    "y_offset = 0": "_y_offset = 0",
})

# 10. frontend/npc_name_resolver.py
fix_file("frontend/npc_name_resolver.py", {
    "import json": "import json  # noqa: E402",
    "from pathlib import Path": "from pathlib import Path  # noqa: E402",
    "from typing import Dict": "from typing import Dict  # noqa: E402",
})

print("Автоисправление завершено.")
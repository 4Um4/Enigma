# apply_tz6_fixes.py
import os
from pathlib import Path

ROOT = Path(__file__).parent

def patch(filepath, replacements):
    path = ROOT / filepath
    if not path.exists():
        print(f"Файл не найден: {path}")
        return
    
    content = path.read_text(encoding="utf-8")
    changed = False
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new, 1)
            print(f"  [OK] Заменено в {filepath}")
            changed = True
        else:
            print(f"  [WARN] Не найдено в {filepath}: {old[:60]}...")
            
    if changed:
        path.write_text(content, encoding="utf-8")

# 1. constants.py
const_replacements = [
    (
        'def format_world_date(total_seconds: int) -> str:\n    """Переводит абсолютные секунды симуляции в дату мира: \'Год X, День Y, HH:MM\'."""\n    if total_seconds < 0:\n        total_seconds = 0\n    \n    year = total_seconds // SECONDS_PER_YEAR + DEFAULT_START_YEAR\n    remaining_seconds = total_seconds % SECONDS_PER_YEAR\n    \n    day_of_year = remaining_seconds // SECONDS_PER_DAY + DEFAULT_START_DAY\n    seconds_in_day = remaining_seconds % SECONDS_PER_DAY\n    \n    hour = seconds_in_day // SECONDS_PER_HOUR\n    minute = (seconds_in_day % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE\n    \n    return f"Год {year}, День {day_of_year}, {hour:02d}:{minute:02d}"',
        'def format_world_date(total_seconds: int) -> str:\n    """Переводит абсолютные секунды симуляции в дату мира: \'Год X, День Y, HH:MM\'."""\n    if total_seconds < 0:\n        total_seconds = 0\n    \n    year = total_seconds // SECONDS_PER_YEAR + DEFAULT_START_YEAR\n    remaining_seconds = total_seconds % SECONDS_PER_YEAR\n    \n    day_of_year = remaining_seconds // SECONDS_PER_DAY + DEFAULT_START_DAY\n    seconds_in_day = remaining_seconds % SECONDS_PER_DAY\n    \n    hour = seconds_in_day // SECONDS_PER_HOUR\n    minute = (seconds_in_day % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE\n    \n    return f"Год {year}, День {day_of_year}, {hour:02d}:{minute:02d}"\n\n# ═══════════════════════════════════════════════════════════════════\n# UI PALETTE & FONTS (ТЗ-6 C1)\n# ═══════════════════════════════════════════════════════════════════\n\n# Базовые цвета UI\nCOLOR_TEXT_DEFAULT: tuple = (220, 220, 220)\nCOLOR_TEXT_DIM: tuple = (180, 180, 180)\nCOLOR_TEXT_MUTED: tuple = (140, 140, 140)\nCOLOR_TEXT_DARK: tuple = (80, 80, 80)\nCOLOR_TEXT_OBS_TITLE: tuple = (160, 170, 220)\nCOLOR_TEXT_OBS_LINE: tuple = (200, 200, 200)\nCOLOR_TEXT_SCALE_HIGHLIGHT: tuple = (255, 220, 100)\nCOLOR_TEXT_SYS_MSG: tuple = (180, 180, 180)\nCOLOR_DEATH_TITLE: tuple = (180, 0, 0)\nCOLOR_DEATH_SUB: tuple = (140, 140, 140)\nCOLOR_JOURNAL_TITLE: tuple = (218, 165, 32)\nCOLOR_NARRATOR: tuple = (218, 165, 32)\nCOLOR_NPC_NAME: tuple = (100, 149, 237)\nCOLOR_MANIFEST_DEFAULT: tuple = (160, 160, 160)\n\n# Палитра рендерера (scene_renderer)\nRENDER_COLORS: dict = {\n    "bg_dark": (18, 18, 23),\n    "floor_visible": (35, 35, 42),\n    "floor_dim": (25, 25, 30),\n    "wall": (100, 100, 110),\n    "wall_visible": (140, 140, 150),\n    "obstacle": (55, 55, 65),\n    "obstacle_visible": (75, 75, 85),\n    "object": (80, 100, 80),\n    "object_visible": (100, 140, 100),\n    "npc_body": (180, 140, 100),\n    "npc_focused": (220, 180, 120),\n    "player_body": (70, 170, 255),\n    "player_focused": (100, 200, 255),\n    "text_audio": (200, 180, 120),\n    "text_body": (200, 120, 120),\n    "text_environment": (140, 140, 140),\n    "fog": (12, 12, 16),\n    "attention_glow": (70, 170, 255, 40),\n}\n\n# Цвета маркеров агрессии/коммуникации на карте\nAGGRESSION_COLORS: dict = {\n    "combat": (255, 80, 80),\n    "armed": (255, 160, 60),\n    "active_aggression": (255, 50, 50),\n    "potential_aggression": (200, 120, 60),\n    "potentially_hostile": (180, 100, 80),\n    "communication": (100, 200, 100),\n    "peaceful_interaction": (80, 180, 80),\n    "friendly_action": (60, 160, 60),\n}\n\n# Константы шрифтов\nFONT_NAME_MAIN: str = "consolas"\nFONT_NAME_UI: str = "segoeui"\nFONT_SIZE_SMALL: int = 12\nFONT_SIZE_AUDIO: int = 13\nFONT_SIZE_BODY: int = 13\nFONT_SIZE_TOOLTIP: int = 14\n\n# Графический масштаб\nSCALE_PIXELS_PER_METER: int = 40'
    )
]
patch("frontend/constants.py", const_replacements)

# 2. scene_renderer.py
scene_replacements = [
    (
        'from game_types import (\n    PerceivedEntity,\n    PerceivedScene,\n)\n\n# === Пиксели на метр ===\nSCALE = 40\n\n# === Цвета рендера ===\n_COLORS = {\n    "bg_dark": (18, 18, 23),\n    "floor_visible": (35, 35, 42),\n    "floor_dim": (25, 25, 30),\n    "wall": (100, 100, 110),\n    "wall_visible": (140, 140, 150),\n    "obstacle": (55, 55, 65),\n    "obstacle_visible": (75, 75, 85),\n    "object": (80, 100, 80),\n    "object_visible": (100, 140, 100),\n    "npc_body": (180, 140, 100),\n    "npc_focused": (220, 180, 120),\n    "player_body": (70, 170, 255),\n    "player_focused": (100, 200, 255),\n    "text_audio": (200, 180, 120),\n    "text_body": (200, 120, 120),\n    "text_environment": (140, 140, 140),\n    "fog": (12, 12, 16),\n    "attention_glow": (70, 170, 255, 40),\n}',
        'from game_types import (\n    PerceivedEntity,\n    PerceivedScene,\n)\nfrom constants import (\n    RENDER_COLORS as _COLORS,\n    AGGRESSION_COLORS,\n    COLOR_TEXT_DIM, COLOR_MANIFEST_DEFAULT,\n    FONT_NAME_MAIN, FONT_NAME_UI,\n    FONT_SIZE_SMALL, FONT_SIZE_AUDIO, FONT_SIZE_BODY, FONT_SIZE_TOOLTIP,\n    SCALE_PIXELS_PER_METER as SCALE,\n)'
    ),
    (
        'self.font_small = pygame.font.SysFont("consolas", 12)\n        self.font_audio = pygame.font.SysFont("consolas", 13, italic=True)\n        self.font_body = pygame.font.SysFont("consolas", 13)',
        'self.font_small = pygame.font.SysFont(FONT_NAME_MAIN, FONT_SIZE_SMALL)\n        self.font_audio = pygame.font.SysFont(FONT_NAME_MAIN, FONT_SIZE_AUDIO, italic=True)\n        self.font_body = pygame.font.SysFont(FONT_NAME_MAIN, FONT_SIZE_BODY)'
    ),
    (
        'name_color = (255, 255, 255) if is_focused else (180, 180, 180)',
        'name_color = (255, 255, 255) if is_focused else COLOR_TEXT_DIM'
    ),
    (
        '_manif_color = _manif.get("color", (160, 160, 160))',
        '_manif_color = _manif.get("color", COLOR_MANIFEST_DEFAULT)'
    ),
    (
        '_font = pygame.font.SysFont("segoeui", 14)',
        '_font = pygame.font.SysFont(FONT_NAME_UI, FONT_SIZE_TOOLTIP)'
    ),
    (
        '"combat": (255, 80, 80),\n            "armed": (255, 160, 60),\n            "active_aggression": (255, 50, 50),\n            "potential_aggression": (200, 120, 60),\n            "potentially_hostile": (180, 100, 80),\n            "communication": (100, 200, 100),\n            "peaceful_interaction": (80, 180, 80),\n            "friendly_action": (60, 160, 60),',
        '"combat": AGGRESSION_COLORS["combat"],\n            "armed": AGGRESSION_COLORS["armed"],\n            "active_aggression": AGGRESSION_COLORS["active_aggression"],\n            "potential_aggression": AGGRESSION_COLORS["potential_aggression"],\n            "potentially_hostile": AGGRESSION_COLORS["potentially_hostile"],\n            "communication": AGGRESSION_COLORS["communication"],\n            "peaceful_interaction": AGGRESSION_COLORS["peaceful_interaction"],\n            "friendly_action": AGGRESSION_COLORS["friendly_action"],'
    )
]
patch("frontend/scene_renderer.py", scene_replacements)

# 3. game_screen.py
game_screen_replacements = [
    (
        'if system_log and "Привязка" not in system_log[-1]:',
        'if system_log and t("ui:sys_binding") not in system_log[-1]:'
    ),
    (
        'system_log.append("Привязка")',
        'system_log.append(t("ui:sys_binding"))'
    ),
    (
        'system_log.append(f"Идёшь к {clicked_npc}")',
        'system_log.append(t("ui:going_to", npc=clicked_npc))'
    ),
    (
        '(0, -1): "север", (0, 1): "юг", (-1, 0): "запад", (1, 0): "восток",\n                            (-1, -1): "северо-запад", (1, -1): "северо-восток",\n                            (-1, 1): "юго-запад", (1, 1): "юго-восток",',
        '(0, -1): t("dir:north"), (0, 1): t("dir:south"), (-1, 0): t("dir:west"), (1, 0): t("dir:east"),\n                            (-1, -1): t("dir:northwest"), (1, -1): t("dir:northeast"),\n                            (-1, 1): t("dir:southwest"), (1, 1): t("dir:southeast"),'
    ),
    (
        '"observe": "присматривается",\n                    "talk": "хочет поговорить",\n                    "warn": "хочет предупредить",\n                    "report": "хочет что-то сообщить",\n                    "trade": "хочет предложить сделку",\n                    "help": "хочет помочь",\n                    "flee": "пытается уйти",',
        '"observe": t("intent:observe"),\n                    "talk": t("intent:talk"),\n                    "warn": t("intent:warn"),\n                    "report": t("intent:report"),\n                    "trade": t("intent:trade"),\n                    "help": t("intent:help"),\n                    "flee": t("intent:flee"),'
    ),
    (
        '_readable = _intent_map.get(_ev_desc, "проявляет инициативу")',
        '_readable = _intent_map.get(_ev_desc, t("intent:default"))'
    ),
    (
        'if resp and resp != "Ничего не произошло.":',
        'if resp and resp != t("ui:nothing_happened"):'
    ),
    (
        'speaker = "Система"',
        'speaker = t("ui:sys_system")'
    ),
    (
        'if speaker in ("Мужчина", "Женщина", "???"):\n                                    recognition = RecognitionLevel.UNKNOWN_FEMALE if speaker == "Женщина" else RecognitionLevel.UNKNOWN_MALE',
        'if speaker in (t("ui:male_unknown"), t("ui:female_unknown"), t("ui:unknown_speaker")):\n                                    recognition = RecognitionLevel.UNKNOWN_FEMALE if speaker == t("ui:female_unknown") else RecognitionLevel.UNKNOWN_MALE'
    ),
    (
        '_dtxt = _dfont.render("ВЫ МЕРТВЫ", True, (180, 0, 0))',
        '_dtxt = _dfont.render(t("ui:death_title"), True, COLOR_DEATH_TITLE)'
    ),
    (
        '_subtxt = _subfont.render("Смерть необратима. Мир продолжает жить без вас.", True, (140, 140, 140))',
        '_subtxt = _subfont.render(t("ui:death_subtitle"), True, COLOR_DEATH_SUB)'
    ),
    (
        '_title_surf = _font_title.render("--- Журнал Диалогов (J) ---", True, (218, 165, 32))',
        '_title_surf = _font_title.render(t("ui:journal_title"), True, COLOR_JOURNAL_TITLE)'
    ),
    (
        '_empty_surf = _font_text.render("(Журнал пуст. Сначала поговорите с NPC)", True, (140, 140, 140))',
        '_empty_surf = _font_text.render(t("ui:journal_empty"), True, COLOR_TEXT_MUTED)'
    ),
    (
        'if _speaker == "Рассказчик": _color = (218, 165, 32)   # Золотой\n                        elif _speaker == "NPC": _color = (100, 149, 237)       # Голубой\n                        else: _color = (200, 200, 200)                         # Нейтральный',
        'if _speaker == t("ui:narrator"): _color = COLOR_NARRATOR\n                        elif _speaker == t("ui:npc_label"): _color = COLOR_NPC_NAME\n                        else: _color = COLOR_TEXT_DEFAULT'
    ),
    (
        '_text_surf = _font_text.render(_line, True, (220, 220, 220))',
        '_text_surf = _font_text.render(_line, True, COLOR_TEXT_DEFAULT)'
    ),
    (
        'scale_surf = sys_font.render(scale_str, True, (255, 220, 100)) # Желтый цвет для внимания',
        'scale_surf = sys_font.render(scale_str, True, COLOR_TEXT_SCALE_HIGHLIGHT)'
    ),
    (
        'sys_surf = sys_font.render(sys_msg, True, (180, 180, 180))',
        'sys_surf = sys_font.render(sys_msg, True, COLOR_TEXT_SYS_MSG)'
    ),
    (
        '_color = manifest_color(_first_key) if _first_key else (160, 160, 160)',
        '_color = manifest_color(_first_key) if _first_key else COLOR_MANIFEST_DEFAULT'
    ),
    (
        '_text_surf = _font.render(_text, True, (220, 220, 220))',
        '_text_surf = _font.render(_text, True, COLOR_TEXT_DEFAULT)'
    ),
    (
        '_title_s = self.renderer.font_small.render(t("ui:obs_title"), True, (160, 170, 220))',
        '_title_s = self.renderer.font_small.render(t("ui:obs_title"), True, COLOR_TEXT_OBS_TITLE)'
    ),
    (
        '_obs_s = self.renderer.font_small.render(f"  {_oline}", True, (200, 200, 200))',
        '_obs_s = self.renderer.font_small.render(f"  {_oline}", True, COLOR_TEXT_OBS_LINE)'
    ),
    (
        'f"FPS: {int(self.clock.get_fps())}", True, (80, 80, 80)',
        'f"FPS: {int(self.clock.get_fps())}", True, COLOR_TEXT_DARK'
    ),
    (
        'format_world_date(self.game_time_seconds), True, (140, 140, 140)',
        'format_world_date(self.game_time_seconds), True, COLOR_TEXT_MUTED'
    )
]
patch("frontend/game_screen.py", game_screen_replacements)

# Add imports to game_screen.py
gs_path = ROOT / "frontend" / "game_screen.py"
gs_content = gs_path.read_text(encoding="utf-8")
if "from i18n import t" not in gs_content:
    import_line = "from constants import (\n    COLOR_TEXT_DEFAULT, COLOR_TEXT_DIM, COLOR_TEXT_MUTED, COLOR_TEXT_DARK,\n    COLOR_TEXT_OBS_TITLE, COLOR_TEXT_OBS_LINE, COLOR_TEXT_SCALE_HIGHLIGHT,\n    COLOR_TEXT_SYS_MSG, COLOR_DEATH_TITLE, COLOR_DEATH_SUB, COLOR_JOURNAL_TITLE,\n    COLOR_NARRATOR, COLOR_NPC_NAME, COLOR_MANIFEST_DEFAULT\n)\nfrom i18n import t\n"
    gs_content = gs_content.replace("import pygame", "import pygame\n" + import_line, 1)
    gs_path.write_text(gs_content, encoding="utf-8")
    print("  [OK] Импорты добавлены в game_screen.py")

# 4. campaign_select.py
campaign_replacements = [
    (
        'title_surf = self.font_title.render("Выбор кампании", True, _COLORS["accent_blue"])',
        'title_surf = self.font_title.render(t("ui:campaign_select_title"), True, _COLORS["accent_blue"])'
    ),
    (
        '"Кампании не найдены. Создайте кампанию в редакторе карт.",',
        't("ui:campaign_not_found"),'
    ),
    (
        'back_surf = self.font_button.render("Назад", True, _COLORS["text"])',
        'back_surf = self.font_button.render(t("ui:btn_back"), True, _COLORS["text"])'
    ),
    (
        'play_surf = self.font_button.render("Играть", True, play_text_color)',
        'play_surf = self.font_button.render(t("ui:btn_play"), True, play_text_color)'
    )
]
patch("frontend/campaign_select.py", campaign_replacements)

cs_path = ROOT / "frontend" / "campaign_select.py"
cs_content = cs_path.read_text(encoding="utf-8")
if "from i18n import t" not in cs_content:
    cs_content = cs_content.replace("import pygame", "import pygame\nfrom i18n import t\n", 1)
    cs_path.write_text(cs_content, encoding="utf-8")
    print("  [OK] Импорты добавлены в campaign_select.py")

# 5. character_select.py
char_replacements = [
    (
        'fields = [("name", "Имя"), ("archetype", "Архетип"), ("temperament", "Темперамент")]',
        'fields = [("name", t("ui:field_name")), ("archetype", t("ui:field_archetype")), ("temperament", t("ui:field_temperament"))]'
    ),
    (
        'title_surf = self.font_title.render("Выбор персонажа", True, _COLORS["accent_blue"])',
        'title_surf = self.font_title.render(t("ui:char_select_title"), True, _COLORS["accent_blue"])'
    ),
    (
        'desc_parts.append(f"Ур.{entry.level}")',
        'desc_parts.append(f"{t(\'ui:char_level\')}{entry.level}")'
    ),
    (
        '"Персонажи не найдены.",',
        't("ui:char_not_found"),'
    ),
    (
        'create_surf = self.font_button.render("Создать персонажа", True, _COLORS["text"])',
        'create_surf = self.font_button.render(t("ui:btn_create_char"), True, _COLORS["text"])'
    ),
    (
        'back_surf = self.font_button.render("Назад", True, _COLORS["text"])',
        'back_surf = self.font_button.render(t("ui:btn_back"), True, _COLORS["text"])'
    ),
    (
        'play_surf = self.font_button.render("Выбрать", True, play_text_color)',
        'play_surf = self.font_button.render(t("ui:btn_select"), True, play_text_color)'
    ),
    (
        'title_surf = self.font_name.render("Новый персонаж", True, _COLORS["text_highlight"])',
        'title_surf = self.font_name.render(t("ui:new_char_title"), True, _COLORS["text_highlight"])'
    ),
    (
        'fields = [("name", "Имя"), ("archetype", "Архетип"), ("temperament", "Темперамент")]',
        'fields = [("name", t("ui:field_name")), ("archetype", t("ui:field_archetype")), ("temperament", t("ui:field_temperament"))]'
    ),
    (
        'create_surf = self.font_button.render("Создать", True, _COLORS["text"])',
        'create_surf = self.font_button.render(t("ui:btn_create"), True, _COLORS["text"])'
    ),
    (
        'cancel_surf = self.font_button.render("Отмена", True, _COLORS["text"])',
        'cancel_surf = self.font_button.render(t("ui:btn_cancel"), True, _COLORS["text"])'
    )
]
patch("frontend/character_select.py", char_replacements)

ch_path = ROOT / "frontend" / "character_select.py"
ch_content = ch_path.read_text(encoding="utf-8")
if "from i18n import t" not in ch_content:
    ch_content = ch_content.replace("import pygame", "import pygame\nfrom i18n import t\n", 1)
    ch_path.write_text(ch_content, encoding="utf-8")
    print("  [OK] Импорты добавлены в character_select.py")

# 6. i18n.py
i18n_replacements = [
    (
        '    "ui:scale_50x": " 50x⏩",\n}',
        '    "ui:scale_50x": " 50x⏩",\n\n    # ── UI: Экраны выбора (ТЗ-6 C2) ──\n    "ui:campaign_select_title": "Выбор кампании",\n    "ui:campaign_not_found": "Кампании не найдены. Создайте кампанию в редакторе карт.",\n    "ui:btn_back": "Назад",\n    "ui:btn_play": "Играть",\n    "ui:char_select_title": "Выбор персонажа",\n    "ui:char_not_found": "Персонажи не найдены.",\n    "ui:btn_create_char": "Создать персонажа",\n    "ui:btn_select": "Выбрать",\n    "ui:new_char_title": "Новый персонаж",\n    "ui:field_name": "Имя",\n    "ui:field_archetype": "Архетип",\n    "ui:field_temperament": "Темперамент",\n    "ui:btn_create": "Создать",\n    "ui:btn_cancel": "Отмена",\n    "ui:char_level": "Ур.",\n\n    # ── UI: Игровой экран (ТЗ-6 C2) ──\n    "ui:sys_binding": "Привязка",\n    "ui:sys_system": "Система",\n    "ui:male_unknown": "Мужчина",\n    "ui:female_unknown": "Женщина",\n    "ui:unknown_speaker": "???",\n    "ui:death_title": "ВЫ МЕРТВЫ",\n    "ui:death_subtitle": "Смерть необратима. Мир продолжает жить без вас.",\n    "ui:journal_title": "--- Журнал Диалогов (J) ---",\n    "ui:journal_empty": "(Журнал пуст. Сначала поговорите с NPC)",\n    "ui:narrator": "Рассказчик",\n    "ui:npc_label": "NPC",\n    "ui:nothing_happened": "Ничего не произошло.",\n    "ui:going_to": "Идёшь к {npc}",\n    "ui:journal_open": "Журнал открыт",\n    \n    # ── UI: Интенты NPC ──\n    "intent:observe": "присматривается",\n    "intent:talk": "хочет поговорить",\n    "intent:warn": "хочет предупредить",\n    "intent:report": "хочет что-то сообщить",\n    "intent:trade": "хочет предложить сделку",\n    "intent:help": "хочет помочь",\n    "intent:flee": "пытается уйти",\n    "intent:default": "проявляет инициативу",\n\n    # ── UI: Стороны света ──\n    "dir:north": "север",\n    "dir:south": "юг",\n    "dir:west": "запад",\n    "dir:east": "восток",\n    "dir:northwest": "северо-запад",\n    "dir:northeast": "северо-восток",\n    "dir:southwest": "юго-запад",\n    "dir:southeast": "юго-восток",\n}'
    )
]
patch("frontend/i18n.py", i18n_replacements)

# 7. map_editor/sprite_registry.py
sr_replacements = [
    (
        'from typing import Dict, Optional',
        'from typing import Dict, Optional, Tuple'
    ),
    (
        '# Глобальный экземпляр реестра\nsprite_registry = SpriteRegistry()',
        '# ═══════════════════════════════════════════════════════════════════\n# Маппинг типов сущностей (используется рендерером)\n# ═══════════════════════════════════════════════════════════════════\nENTITY_SPRITE_MAP: Dict[str, Tuple[str, int, int]] = {\n    "table": ("Deadbeat/deadbeat_b", 5, 11),\n    "chair": ("Deadbeat/deadbeat_b", 8, 17),\n    "stool": ("Deadbeat/deadbeat_b", 9, 19),\n    "bar": ("Deadbeat/deadbeat_b", 5, 11),\n    "bed": ("Deadbeat/deadbeat_b", 8, 16),\n    "bookshelf": ("Deadbeat/deadbeat_b", 7, 16),\n    "door": ("Deadbeat/deadbeat_b", 3, 9),\n    "window": ("Deadbeat/deadbeat_b", 6, 9),\n    "gap": ("Deadbeat/deadbeat_b", 3, 9),\n    "ladder": ("Deadbeat/deadbeat_b", 0, 9),\n    "hatch": ("Deadbeat/deadbeat_b", 11, 16),\n    "stairs_up": ("Deadbeat/deadbeat_b", 0, 9),\n    "stairs_down": ("Deadbeat/deadbeat_b", 0, 9),\n    "door_transition": ("Deadbeat/deadbeat_b", 3, 9),\n    "portal_magic": ("Deadbeat/deadbeat_b", 6, 2),\n    "tree": ("Deadbeat/deadbeat_b", 6, 0),\n    "spruce": ("Deadbeat/deadbeat_b", 6, 3),\n    "apple_tree": ("Deadbeat/deadbeat_b", 7, 4),\n    "palm": ("Deadbeat/deadbeat_b", 7, 7),\n    "grass": ("Deadbeat/deadbeat_b", 7, 0),\n    "rocks": ("Deadbeat/deadbeat_b", 6, 18),\n    "tent": ("Deadbeat/deadbeat_b", 8, 15),\n    "toilet": ("Deadbeat/deadbeat_b", 7, 21),\n    "cauldron": ("Deadbeat/deadbeat_b", 11, 17),\n    "campfire": ("Deadbeat/deadbeat_b", 4, 15),\n    "sign_flophouse": ("Deadbeat/deadbeat_b", 11, 4),\n    "bones": ("Deadbeat/deadbeat_b", 22, 13),\n    "heart": ("Deadbeat/deadbeat_b", 22, 12),\n    "heart_empty": ("Deadbeat/deadbeat_b", 22, 12),\n    "decoration": ("Deadbeat/deadbeat_b", 3, 9),\n    "mage": ("Deadbeat/deadbeat_b", 23, 22),\n    "warrior": ("Deadbeat/deadbeat_b", 25, 21),\n    "person": ("Deadbeat/deadbeat_b", 23, 21),\n    "thief": ("Deadbeat/deadbeat_b", 25, 22),\n    "cow": ("Deadbeat/deadbeat_b", 25, 28),\n    "knight": ("Deadbeat/deadbeat_b", 26, 21),\n}\n\n\ndef get_entity_sprite(entity_type: str) -> Optional[pygame.Surface]:\n    """Возвращает тайл для типа сущности из кэша или с диска (через глобальный реестр)."""\n    sprite_info = ENTITY_SPRITE_MAP.get(entity_type)\n    if not sprite_info:\n        return None\n    sheet_key, col, row = sprite_info\n    return sprite_registry.get(sheet_key, col, row)\n\n\n# Глобальный экземпляр реестра\nsprite_registry = SpriteRegistry()'
    )
]
patch("frontend/map_editor/sprite_registry.py", sr_replacements)

# 8. scene_renderer.py (import fix)
sr_path = ROOT / "frontend" / "scene_renderer.py"
sr_content = sr_path.read_text(encoding="utf-8")
if "from map_editor.sprite_registry import get_entity_sprite" not in sr_content:
    sr_content = sr_content.replace("from sprite_resolver import get_entity_sprite", "from map_editor.sprite_registry import get_entity_sprite", 1)
    sr_path.write_text(sr_content, encoding="utf-8")
    print("  [OK] Импорт get_entity_sprite обновлен в scene_renderer.py")

# 9. Delete sprite_resolver.py
sr_old_path = ROOT / "frontend" / "sprite_resolver.py"
if sr_old_path.exists():
    sr_old_path.unlink()
    print("  [OK] Файл frontend/sprite_resolver.py удален")

print("\nГотово! Теперь запусти smoke-тест:")
print("cd backend; python -m pytest tests/sandbox/test_tz6_ui_hardcodes_removed.py -v; cd ..")
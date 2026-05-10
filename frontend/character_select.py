"""
path: /frontend/character_select.py

Экран выбора персонажа — полностью самодостаточен, без зависимостей от app/.
Читает characters.json из папки кампании напрямую.

Назначение: Экран выбора персонажа — показывает список доступных персонажей, возвращает имя выбранного или None
Зависимости: pygame, pathlib, json (только стандартная библиотека)
Основные сущности: CharacterEntry, CharacterSelectScreen

Назначение: Экран выбора персонажа — читает characters.json из папки кампании, показывает список, возвращает имя выбранного персонажа или None
Зависимости: pygame, pathlib, json (только стандартная библиотека)
Основные сущности: CharacterEntry, CharacterSelectScreen
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json

import pygame

# Папки кампаний — приоритет saves/ (runtime), fallback campaigns/ (исходники)
_SAVES_DIR = Path(__file__).parent.parent / "saves"
_CAMPAIGNS_DIR = Path(__file__).parent / "map_editor" / "campaigns"

# Цветовая схема — из campaign_select.py (TODO: вынести в общий ui_theme.py)
_COLORS = {
    "bg_dark": (18, 18, 23),
    "bg_panel": (28, 28, 33),
    "bg_selected": (40, 55, 75),
    "bg_hover": (35, 45, 60),
    "text": (220, 220, 220),
    "text_dim": (140, 140, 140),
    "text_highlight": (255, 255, 255),
    "btn_primary": (70, 100, 130),
    "btn_primary_hover": (90, 130, 160),
    "btn_secondary": (80, 80, 90),
    "btn_secondary_hover": (100, 100, 110),
    "border": (60, 60, 70),
    "border_highlight": (100, 180, 255),
    "accent_blue": (70, 170, 255),
    "accent_yellow": (255, 200, 80),
    "hp_green": (80, 200, 120),
    "hp_red": (200, 80, 80),
}


@dataclass
class CharacterEntry:
    """Метаданные одного персонажа из characters.json"""
    name: str
    race: str
    class_name: str
    level: int
    hp: int
    max_hp: int
    ac: int


def _load_characters(campaign_id: str) -> list[CharacterEntry]:
    """Читает всех персонажей из characters.json — приоритет saves/"""
    entries: list[CharacterEntry] = []
    # Приоритет: saves/ (runtime), fallback: campaigns/ (исходники)
    char_file = _SAVES_DIR / campaign_id / "characters.json"
    if not char_file.exists():
        char_file = _CAMPAIGNS_DIR / campaign_id / "characters.json"
    if not char_file.exists():
        return entries

    try:
        with open(char_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return entries
        for item in data:
            entries.append(CharacterEntry(
                name=item.get("name", "???"),
                race=item.get("race", ""),
                class_name=item.get("class_name", ""),
                level=item.get("level", 1),
                hp=item.get("hp", 0),
                max_hp=item.get("max_hp", 0),
                ac=item.get("ac", 10),
            ))
    except Exception as e:
        print(f"[CHAR_SELECT] Ошибка парсинга персонажей: {e}")
    return entries


class CharacterSelectScreen:
    """Экран выбора персонажа — возвращает имя выбранного персонажа или None"""

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        campaign_id: str,
    ):
        self.screen = screen
        self.clock = clock
        self.campaign_id = campaign_id
        self._result: Optional[str] = None  # имя персонажа или None (назад)

        # Шрифты
        self.font_title = pygame.font.SysFont("consolas", 32, bold=True)
        self.font_name = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_desc = pygame.font.SysFont("consolas", 14)
        self.font_button = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 13)
        self.font_stats = pygame.font.SysFont("consolas", 13, bold=True)

        # Данные
        self._characters = _load_characters(campaign_id)
        self._selected_index: int = -1
        # Двойной клик
        self._last_click_time: float = 0.0
        self._last_click_pos: tuple[int, int] = (0, 0)

        # Размеры списка
        self._item_height = 70
        self._list_padding = 12
        self._list_rect = pygame.Rect(0, 0, 0, 0)

        # Кнопки
        self._btn_back_rect = pygame.Rect(0, 0, 0, 0)
        self._btn_play_rect = pygame.Rect(0, 0, 0, 0)
        self._btn_create_rect = pygame.Rect(0, 0, 0, 0)

        # Диалог создания персонажа: Вектор начальных условий (ADR-0017)
        self._dialog_active = False
        self._dialog_inputs = {"name": "", "archetype": "Drifter", "temperament": "Stoic"}
        self._dialog_focus = "name"
        # Выбор из предопределенных векторов
        self._archetypes = ["Laborer", "Soldier", "Merchant", "Drifter", "Noble"]
        self._temperaments = ["Fearful", "Stoic", "Impulsive", "Calculating"]
        self._archetype_idx = 3  # Drifter по умолчанию
        self._temperament_idx = 1  # Stoic по умолчанию

        self._layout()

    def _layout(self) -> None:
        """Пересчитывает позиции элементов при изменении размера окна"""
        w, h = self.screen.get_size()

        # Заголовок — сверху с отступом
        self._title_y = 40

        # Область списка
        list_top = 90
        list_bottom = h - 70
        self._list_rect = pygame.Rect(
            w // 2 - 320, list_top,
            640, max(0, list_bottom - list_top)
        )

        # Кнопки — под списком
        btn_y = h - 55
        self._btn_create_rect = pygame.Rect(w // 2 - 80, btn_y, 160, 40)
        self._btn_back_rect = pygame.Rect(w // 2 - 290, btn_y, 130, 40)
        self._btn_play_rect = pygame.Rect(w // 2 + 160, btn_y, 130, 40)

    def run(self) -> Optional[str]:
        """Запускает цикл экрана, возвращает имя персонажа или None"""
        self._result = None
        self._selected_index = 0 if self._characters else -1

        while self._result is None:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )
                    self._layout()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    import time
                    now = time.time()
                    dx = abs(event.pos[0] - self._last_click_pos[0])
                    dy = abs(event.pos[1] - self._last_click_pos[1])
                    is_double = (now - self._last_click_time < 0.4) and (dx < 5 and dy < 5)
                    self._last_click_time = now
                    self._last_click_pos = event.pos

                    self._handle_click(event.pos)

                    # Двойной клик по списку = войти
                    if not self._dialog_active and is_double and 0 <= self._selected_index < len(self._characters):
                        if self._list_rect.collidepoint(event.pos):
                            self._result = self._characters[self._selected_index].name
                elif event.type == pygame.KEYDOWN:
                    if self._dialog_active:
                        self._handle_dialog_key(event)
                    elif event.key == pygame.K_ESCAPE:
                        return None
                    elif event.key == pygame.K_UP:
                        if self._selected_index > 0:
                            self._selected_index -= 1
                    elif event.key == pygame.K_DOWN:
                        if self._selected_index < len(self._characters) - 1:
                            self._selected_index += 1
                    elif event.key == pygame.K_RETURN:
                        if 0 <= self._selected_index < len(self._characters):
                            self._result = self._characters[self._selected_index].name

            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

        return self._result

    def _handle_click(self, pos: tuple[int, int]) -> None:
        """Обрабатывает клик по списку и кнопкам"""
        # Диалог создания — обработка своих кнопок
        if self._dialog_active:
            self._handle_dialog_click(pos)
            return

        # Кнопка «Назад»
        if self._btn_back_rect.collidepoint(pos):
            self._result = None
            return

        # Кнопка «Играть»
        if self._btn_play_rect.collidepoint(pos) and 0 <= self._selected_index < len(self._characters):
            self._result = self._characters[self._selected_index].name
            return

        # Кнопка «Создать персонажа»
        if self._btn_create_rect.collidepoint(pos):
            self._dialog_active = True
            self._dialog_inputs = {"name": ""}
            self._dialog_focus = "name"
            return

        # Список персонажей
        if self._list_rect.collidepoint(pos):
            relative_y = pos[1] - self._list_rect.top
            index = relative_y // self._item_height
            if 0 <= index < len(self._characters):
                self._selected_index = index

    def _handle_dialog_key(self, event: pygame.event.Event) -> None:
        """Обработка ввода текста и выбора вектора в диалоге создания (ADR-030)"""
        if event.key == pygame.K_ESCAPE:
            self._dialog_active = False
            return
        if event.key == pygame.K_RETURN:
            self._create_character()
            return
        if event.key == pygame.K_TAB:
            fields = ["name", "archetype", "temperament"]
            idx = fields.index(self._dialog_focus)
            self._dialog_focus = fields[(idx + 1) % len(fields)]
            return
            
        # Навигация по векторам стрелками (Архетип и Темперамент)
        if self._dialog_focus == "archetype":
            if event.key == pygame.K_RIGHT:
                self._archetype_idx = (self._archetype_idx + 1) % len(self._archetypes)
            elif event.key == pygame.K_LEFT:
                self._archetype_idx = (self._archetype_idx - 1) % len(self._archetypes)
            return
        if self._dialog_focus == "temperament":
            if event.key == pygame.K_RIGHT:
                self._temperament_idx = (self._temperament_idx + 1) % len(self._temperaments)
            elif event.key == pygame.K_LEFT:
                self._temperament_idx = (self._temperament_idx - 1) % len(self._temperaments)
            return

        # Ввод текста только для имени
        if event.key == pygame.K_BACKSPACE:
            self._dialog_inputs["name"] = self._dialog_inputs["name"][:-1]
            return
        if event.unicode and event.unicode.isprintable() and len(self._dialog_inputs["name"]) < 30:
            self._dialog_inputs["name"] += event.unicode

    def _handle_dialog_click(self, pos: tuple[int, int]) -> None:
        """Обработка кликов в диалоге создания персонажа"""
        w, h = self.screen.get_size()
        # Поля ввода — вычисляем позиции как в _draw_dialog
        fields = [("name", "Имя"), ("archetype", "Архетип"), ("temperament", "Темперамент")]
        field_y_start = h // 2 - 60
        for i, (key, label) in enumerate(fields):
            field_rect = pygame.Rect(w // 2 - 150, field_y_start + i * 50, 300, 32)
            if field_rect.collidepoint(pos):
                self._dialog_focus = key
                return

        # Кнопка «Создать»
        create_btn = pygame.Rect(w // 2 - 140, field_y_start + len(fields) * 50 + 10, 130, 36)
        if create_btn.collidepoint(pos):
            self._create_character()
            return

        # Кнопка «Отмена»
        cancel_btn = pygame.Rect(w // 2 + 10, field_y_start + len(fields) * 50 + 10, 130, 36)
        if cancel_btn.collidepoint(pos):
            self._dialog_active = False
            return

    def _create_character(self) -> None:
        """Сохраняет нового персонажа в saves/ и обновляет список"""
        name = self._dialog_inputs["name"].strip()
        if not name:
            return

        # Формируем Вектор Начальных Условий (ADR-0017)
        archetype = self._archetypes[self._archetype_idx]
        temperament = self._temperaments[self._temperament_idx]

        # Маппинг Темперамента в Психику (drives_base)
        psyche_map = {
            "Fearful": {"fear": 0.8, "impulsivity": 0.3, "willpower": 0.4},
            "Stoic": {"fear": 0.3, "impulsivity": 0.2, "willpower": 0.8},
            "Impulsive": {"fear": 0.4, "impulsivity": 0.9, "willpower": 0.5},
            "Calculating": {"fear": 0.2, "impulsivity": 0.1, "willpower": 0.7},
        }

        # Маппинг Архетипа в Физиологию (body_profile)
        body_map = {
            "Laborer": {"max_hp": 120, "strength": 14, "dexterity": 10},
            "Soldier": {"max_hp": 130, "strength": 15, "dexterity": 12},
            "Merchant": {"max_hp": 90, "strength": 8, "dexterity": 10},
            "Drifter": {"max_hp": 100, "strength": 10, "dexterity": 14},
            "Noble": {"max_hp": 80, "strength": 8, "dexterity": 8},
        }

        new_char = {
            "name": name,
            "npc_id": "player",  # Гибридная сущность в симуляции
            "archetype": archetype,
            "temperament": temperament,
            "body_profile": body_map.get(archetype, body_map["Drifter"]),
            "psyche": psyche_map.get(temperament, psyche_map["Stoic"]),
            # Legacy поля для совместимости со старыми загрузчиками (будут удалены)
            "race": "Human",
            "class_name": archetype,
            "level": 1,
            "stats": {"str": body_map.get(archetype, {}).get("strength", 10), 
                      "dex": body_map.get(archetype, {}).get("dexterity", 10), 
                      "con": 10, "int": 10, "wis": 10, "cha": 10},
            "hp": body_map.get(archetype, {}).get("max_hp", 100),
            "max_hp": body_map.get(archetype, {}).get("max_hp", 100),
        }

        # Читаем существующих или создаём пустой список
        char_file = _SAVES_DIR / self.campaign_id / "characters.json"
        char_file.parent.mkdir(parents=True, exist_ok=True)
        if char_file.exists():
            try:
                with open(char_file, "r", encoding="utf-8") as f:
                    chars = json.load(f)
            except Exception:
                chars = []
        else:
            chars = []
        chars.append(new_char)

        with open(char_file, "w", encoding="utf-8") as f:
            json.dump(chars, f, ensure_ascii=False, indent=2)

        # Обновляем список и закрываем диалог
        self._characters = _load_characters(self.campaign_id)
        self._dialog_active = False
        if self._characters:
            self._selected_index = len(self._characters) - 1

    def _draw(self) -> None:
        """Отрисовка экрана"""
        self.screen.fill(_COLORS["bg_dark"])
        w, _ = self.screen.get_size()

        # Заголовок
        title_surf = self.font_title.render("Выбор персонажа", True, _COLORS["accent_blue"])
        self.screen.blit(title_surf, (w // 2 - title_surf.get_width() // 2, self._title_y))

        # Область списка — фон
        if self._characters:
            pygame.draw.rect(
                self.screen, _COLORS["bg_panel"], self._list_rect, border_radius=8
            )
            pygame.draw.rect(
                self.screen, _COLORS["border"], self._list_rect, 1, border_radius=8
            )

            # Обрезаем отрисовку элементов по области списка
            clip = self.screen.get_clip()
            self.screen.set_clip(self._list_rect)

            for i, entry in enumerate(self._characters):
                item_rect = pygame.Rect(
                    self._list_rect.x + self._list_padding,
                    self._list_rect.y + i * self._item_height + 4,
                    self._list_rect.width - self._list_padding * 2,
                    self._item_height - 8,
                )

                # Фон элемента
                is_hovered = item_rect.collidepoint(pygame.mouse.get_pos())
                if i == self._selected_index:
                    bg = _COLORS["bg_selected"]
                    border = _COLORS["border_highlight"]
                elif is_hovered:
                    bg = _COLORS["bg_hover"]
                    border = None
                else:
                    bg = None
                    border = None

                if bg:
                    pygame.draw.rect(self.screen, bg, item_rect, border_radius=6)
                if border:
                    pygame.draw.rect(self.screen, border, item_rect, 1, border_radius=6)

                # Имя персонажа
                name_color = _COLORS["text_highlight"] if i == self._selected_index else _COLORS["text"]
                name_surf = self.font_name.render(entry.name, True, name_color)
                self.screen.blit(name_surf, (item_rect.x + 10, item_rect.y + 8))

                # Раса / Класс / Уровень
                desc_parts = []
                if entry.race:
                    desc_parts.append(entry.race)
                if entry.class_name:
                    desc_parts.append(entry.class_name)
                if entry.level:
                    desc_parts.append(f"Ур.{entry.level}")
                desc_text = " | ".join(desc_parts) if desc_parts else ""
                desc_surf = self.font_desc.render(desc_text, True, _COLORS["text_dim"])
                self.screen.blit(desc_surf, (item_rect.x + 10, item_rect.y + 30))

                # HP и AC — справа
                hp_color = _COLORS["hp_green"] if entry.hp > entry.max_hp * 0.3 else _COLORS["hp_red"]
                hp_text = f"HP {entry.hp}/{entry.max_hp}"
                hp_surf = self.font_stats.render(hp_text, True, hp_color)
                self.screen.blit(
                    hp_surf,
                    (item_rect.right - hp_surf.get_width() - 10, item_rect.y + 10),
                )

                ac_text = f"AC {entry.ac}"
                ac_surf = self.font_small.render(ac_text, True, _COLORS["text_dim"])
                self.screen.blit(
                    ac_surf,
                    (item_rect.right - ac_surf.get_width() - 10, item_rect.y + 30),
                )

            self.screen.set_clip(clip)
        else:
            # Нет персонажей
            empty_surf = self.font_desc.render(
                "Персонажи не найдены.",
                True, _COLORS["text_dim"],
            )
            self.screen.blit(
                empty_surf,
                (
                    w // 2 - empty_surf.get_width() // 2,
                    self._list_rect.y + 30,
                ),
            )

        # Кнопка «Создать персонажа»
        create_hovered = self._btn_create_rect.collidepoint(pygame.mouse.get_pos())
        create_color = _COLORS["btn_primary_hover"] if create_hovered else _COLORS["btn_primary"]
        pygame.draw.rect(self.screen, create_color, self._btn_create_rect, border_radius=6)
        create_surf = self.font_button.render("Создать персонажа", True, _COLORS["text"])
        self.screen.blit(create_surf, create_surf.get_rect(center=self._btn_create_rect.center))

        # Кнопка «Назад»
        back_hovered = self._btn_back_rect.collidepoint(pygame.mouse.get_pos())
        back_color = _COLORS["btn_secondary_hover"] if back_hovered else _COLORS["btn_secondary"]
        pygame.draw.rect(self.screen, back_color, self._btn_back_rect, border_radius=6)
        back_surf = self.font_button.render("Назад", True, _COLORS["text"])
        self.screen.blit(back_surf, back_surf.get_rect(center=self._btn_back_rect.center))

        # Кнопка «Выбрать»
        can_play = 0 <= self._selected_index < len(self._characters)
        play_hovered = self._btn_play_rect.collidepoint(pygame.mouse.get_pos()) and can_play
        if can_play:
            play_color = _COLORS["btn_primary_hover"] if play_hovered else _COLORS["btn_primary"]
            play_text_color = _COLORS["text_highlight"]
        else:
            play_color = _COLORS["btn_secondary"]
            play_text_color = _COLORS["text_dim"]
        pygame.draw.rect(self.screen, play_color, self._btn_play_rect, border_radius=6)
        play_surf = self.font_button.render("Выбрать", True, play_text_color)
        self.screen.blit(play_surf, play_surf.get_rect(center=self._btn_play_rect.center))

        # Диалог создания персонажа
        if self._dialog_active:
            self._draw_dialog()

    def _draw_dialog(self) -> None:
        """Отрисовка диалога создания персонажа"""
        w, h = self.screen.get_size()
        # Затемнение фона
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        # Панель диалога
        panel_w, panel_h = 360, 280
        panel_rect = pygame.Rect(w // 2 - panel_w // 2, h // 2 - panel_h // 2, panel_w, panel_h)
        pygame.draw.rect(self.screen, _COLORS["bg_panel"], panel_rect, border_radius=8)
        pygame.draw.rect(self.screen, _COLORS["border"], panel_rect, 1, border_radius=8)

        # Заголовок
        title_surf = self.font_name.render("Новый персонаж", True, _COLORS["text_highlight"])
        self.screen.blit(title_surf, (panel_rect.x + 20, panel_rect.y + 15))

        # Поля ввода
        fields = [("name", "Имя"), ("archetype", "Архетип"), ("temperament", "Темперамент")]
        field_y_start = panel_rect.y + 55
        for i, (key, label) in enumerate(fields):
            label_surf = self.font_desc.render(label, True, _COLORS["text_dim"])
            self.screen.blit(label_surf, (panel_rect.x + 20, field_y_start + i * 50))

            field_rect = pygame.Rect(panel_rect.x + 20, field_y_start + i * 50 + 16, panel_w - 40, 28)
            border_color = _COLORS["border_highlight"] if self._dialog_focus == key else _COLORS["border"]
            pygame.draw.rect(self.screen, _COLORS["bg_dark"], field_rect, border_radius=4)
            pygame.draw.rect(self.screen, border_color, field_rect, 1, border_radius=4)

            # Рендер содержимого поля в зависимости от типа (ADR-030)
            if key == "name":
                text = self._dialog_inputs["name"]
                if text:
                    text_surf = self.font_desc.render(text, True, _COLORS["text"])
                    self.screen.blit(text_surf, (field_rect.x + 6, field_rect.y + 6))
                elif self._dialog_focus == key:
                    # Курсор
                    cursor_surf = self.font_desc.render("|", True, _COLORS["accent_blue"])
                    self.screen.blit(cursor_surf, (field_rect.x + 6, field_rect.y + 6))
            elif key == "archetype":
                val = self._archetypes[self._archetype_idx]
                text_surf = self.font_desc.render(f"<  {val}  >", True, _COLORS["accent_blue"])
                self.screen.blit(text_surf, text_surf.get_rect(center=field_rect.center))
            elif key == "temperament":
                val = self._temperaments[self._temperament_idx]
                text_surf = self.font_desc.render(f"<  {val}  >", True, _COLORS["accent_blue"])
                self.screen.blit(text_surf, text_surf.get_rect(center=field_rect.center))

        # Кнопки
        btn_y = field_y_start + len(fields) * 50 + 10
        create_btn = pygame.Rect(panel_rect.x + 20, btn_y, 140, 36)
        cancel_btn = pygame.Rect(panel_rect.x + panel_w - 160, btn_y, 140, 36)

        create_hovered = create_btn.collidepoint(pygame.mouse.get_pos())
        create_color = _COLORS["btn_primary_hover"] if create_hovered else _COLORS["btn_primary"]
        pygame.draw.rect(self.screen, create_color, create_btn, border_radius=6)
        create_surf = self.font_button.render("Создать", True, _COLORS["text"])
        self.screen.blit(create_surf, create_surf.get_rect(center=create_btn.center))

        cancel_hovered = cancel_btn.collidepoint(pygame.mouse.get_pos())
        cancel_color = _COLORS["btn_secondary_hover"] if cancel_hovered else _COLORS["btn_secondary"]
        pygame.draw.rect(self.screen, cancel_color, cancel_btn, border_radius=6)
        cancel_surf = self.font_button.render("Отмена", True, _COLORS["text"])
        self.screen.blit(cancel_surf, cancel_surf.get_rect(center=cancel_btn.center))
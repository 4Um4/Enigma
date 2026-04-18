"""
backend/text_input.py
Кастомный виджет ввода текста для pygame.

Поддерживает:
- Кириллицу (через TEXTINPUT / TEXTEDITING события)
- Историю команд (↑/↓)
- Буфер обмена (Ctrl+C / Ctrl+V)
- Курсор, выделение, автоскролл длинного текста

path: /backend/text_input.py
Назначение: Виджет ввода текста с кириллицей, историей, буфером
Зависимости: pygame, typing
Основные сущности: TextInput

Назначение: Кастомный виджет ввода текста для pygame — кириллица, история, буфер обмена
Зависимости: pygame, typing
Основные сущности: TextInput
"""
from typing import Optional

import pygame


class TextInput:
    """Однострочное текстовое поле с кириллицей, историей и буфером."""

    # Максимальная длина ввода
    MAX_LENGTH: int = 500
    # Максимальный размер истории
    MAX_HISTORY: int = 100

    def __init__(
        self,
        rect: pygame.Rect,
        font: pygame.font.Font,
        colors: Optional[dict[str, tuple[int, int, int]]] = None,
        pass_through_keys: Optional[set[int]] = None,
    ) -> None:
        self.rect = rect
        self.font = font

        # Цвета
        _default_colors = {
            "bg": (25, 25, 30),
            "border": (70, 70, 80),
            "border_active": (100, 180, 255),
            "text": (220, 220, 220),
            "cursor": (200, 200, 200),
            "selection": (60, 90, 130),
        }
        self.colors = colors or _default_colors

        # Клавиши, которые всегда проходят сквозь виджет (WASD для движения)
        self._pass_through: set[int] = pass_through_keys or set()

        # Состояние текста
        self._text: str = ""
        self._cursor_pos: int = 0  # позиция курсора в строке
        self._selection_start: Optional[int] = None  # начало выделения или None

        # История команд
        self._history: list[str] = []
        self._history_index: int = -1  # -1 = текущий (несохранённый) ввод
        self._history_saved: str = ""  # сохранённый текущий ввод при навигации

        # Фокус
        self._focused: bool = False

        # IME (Input Method Editor) для составных символов (китайский, etc.)
        self._ime_text: str = ""

        # Вертикальное смещение для автоскролла длинного текста
        self._scroll_offset: int = 0

    # ── Публичный API ──────────────────────────────────────────────────

    @property
    def focused(self) -> bool:
        return self._focused

    @focused.setter
    def focused(self, value: bool) -> None:
        self._focused = value

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value[:self.MAX_LENGTH]
        self._cursor_pos = len(self._text)
        self._selection_start = None

    @property
    def empty(self) -> bool:
        return len(self._text) == 0

    def clear(self) -> str:
        """Очищает поле, возвращает предыдущий текст."""
        prev = self._text
        self._text = ""
        self._cursor_pos = 0
        self._selection_start = None
        self._scroll_offset = 0
        return prev

    def push_history(self, text: str) -> None:
        """Добавляет текст в историю команд (вызывать после отправки)."""
        if not text.strip():
            return
        # Не дублируем последний элемент
        if self._history and self._history[-1] == text:
            return
        self._history.append(text)
        if len(self._history) > self.MAX_HISTORY:
            self._history.pop(0)
        self._history_index = -1
        self._history_saved = ""

    def set_focused(self, focused: bool) -> None:
        """Устанавливает фокус (совместимость)."""
        self._focused = focused

    # ── Обработка событий ──────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Обрабатывает событие pygame. Возвращает True если событие обработано.
        """
        # Клик по полю ввода всегда забирает фокус (даже если был сброшен через Tab)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._focused = True
                self._move_cursor_to_click(event.pos[0])
                return True
            elif self._focused:
                self._focused = False
                return False

        if not self._focused:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key in self._pass_through:
                return False  # движение — проходит к movement handler
            return self._handle_keydown(event)

        # TEXTINPUT — итоговый введённый текст (после IME)
        if event.type == pygame.TEXTINPUT:
            self._insert_text(event.text)
            return True

        # TEXTEDITING — промежуточное состояние IME (составные символы)
        if event.type == pygame.TEXTEDITING:
            self._ime_text = event.text
            return True

        return False

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        """Обработка нажатий клавиш."""
        mods = pygame.key.get_mods()

        # Ctrl/Cmd комбинации
        ctrl = mods & (pygame.KMOD_CTRL | pygame.KMOD_META)

        if ctrl:
            if event.key == pygame.K_a:
                # Выделить всё
                self._selection_start = 0
                self._cursor_pos = len(self._text)
                return True
            elif event.key == pygame.K_c:
                # Копировать
                self._copy_to_clipboard()
                return True
            elif event.key == pygame.K_v:
                # Вставить
                self._paste_from_clipboard()
                return True
            elif event.key == pygame.K_x:
                # Вырезать
                self._copy_to_clipboard()
                self._delete_selection()
                return True
            elif event.key == pygame.K_z:
                # Отмена — упрощённо: очистить
                if self._selection_start is not None:
                    self._delete_selection()
                return True
            return False

        # Навигация по истории
        if event.key == pygame.K_UP:
            return self._history_prev()
        if event.key == pygame.K_DOWN:
            return self._history_next()

        # Движение курсора
        if event.key == pygame.K_LEFT:
            if mods & pygame.KMOD_SHIFT:
                self._extend_selection_left()
            else:
                self._selection_start = None
                self._cursor_pos = max(0, self._cursor_pos - 1)
            self._update_scroll()
            return True

        if event.key == pygame.K_RIGHT:
            if mods & pygame.KMOD_SHIFT:
                self._extend_selection_right()
            else:
                self._selection_start = None
                self._cursor_pos = min(len(self._text), self._cursor_pos + 1)
            self._update_scroll()
            return True

        if event.key == pygame.K_HOME:
            if mods & pygame.KMOD_SHIFT:
                if self._selection_start is None:
                    self._selection_start = self._cursor_pos
                self._cursor_pos = 0
            else:
                self._cursor_pos = 0
                self._selection_start = None
            self._update_scroll()
            return True

        if event.key == pygame.K_END:
            if mods & pygame.KMOD_SHIFT:
                if self._selection_start is None:
                    self._selection_start = self._cursor_pos
                self._cursor_pos = len(self._text)
            else:
                self._cursor_pos = len(self._text)
                self._selection_start = None
            self._update_scroll()
            return True

        # Удаление
        if event.key == pygame.K_BACKSPACE:
            if self._selection_start is not None:
                self._delete_selection()
            elif self._cursor_pos > 0:
                self._cursor_pos -= 1
                self._text = self._text[:self._cursor_pos] + self._text[self._cursor_pos + 1:]
            self._update_scroll()
            return True

        if event.key == pygame.K_DELETE:
            if self._selection_start is not None:
                self._delete_selection()
            elif self._cursor_pos < len(self._text):
                self._text = self._text[:self._cursor_pos] + self._text[self._cursor_pos + 1:]
            self._update_scroll()
            return True

        # Enter — не обрабатываем здесь (внешний код решает что делать)
        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            return False

        # Escape — сбросить фокус
        if event.key == pygame.K_ESCAPE:
            self._focused = False
            return True

        # Прочие клавиши — не обрабатываем (TEXTINPUT придёт отдельно)
        return False

    # ── Внутренние методы ──────────────────────────────────────────────

    def _insert_text(self, text: str) -> None:
        """Вставляет текст в позицию курсора."""
        if self._selection_start is not None:
            self._delete_selection()
        if len(self._text) + len(text) > self.MAX_LENGTH:
            text = text[:self.MAX_LENGTH - len(self._text)]
        self._text = self._text[:self._cursor_pos] + text + self._text[self._cursor_pos:]
        self._cursor_pos += len(text)
        self._selection_start = None
        self._update_scroll()

    def _delete_selection(self) -> None:
        """Удаляет выделенный текст."""
        if self._selection_start is None:
            return
        start = min(self._selection_start, self._cursor_pos)
        end = max(self._selection_start, self._cursor_pos)
        self._text = self._text[:start] + self._text[end:]
        self._cursor_pos = start
        self._selection_start = None
        self._update_scroll()

    def _extend_selection_left(self) -> None:
        """Расширяет выделение влево."""
        if self._cursor_pos > 0:
            if self._selection_start is None:
                self._selection_start = self._cursor_pos
            self._cursor_pos -= 1

    def _extend_selection_right(self) -> None:
        """Расширяет выделение вправо."""
        if self._cursor_pos < len(self._text):
            if self._selection_start is None:
                self._selection_start = self._cursor_pos
            self._cursor_pos += 1

    def _move_cursor_to_click(self, click_x: int) -> None:
        """Перемещает курсор в позицию клика."""
        inner_x = click_x - self.rect.x - 6  # отступ от края
        # Приближённая ширина символа (моноширинный шрифт)
        char_w = self.font.size("A")[0]
        if char_w <= 0:
            return
        clicked_pos = (inner_x + self._scroll_offset) // char_w
        self._cursor_pos = max(0, min(len(self._text), int(clicked_pos)))
        self._selection_start = None
        self._update_scroll()

    def _update_scroll(self) -> None:
        """Обновляет горизонтальное смещение для автоскролла."""
        char_w = self.font.size("A")[0]
        if char_w <= 0:
            return
        visible_chars = (self.rect.width - 12) // char_w  # 6px отступ с каждой стороны
        if visible_chars <= 0:
            self._scroll_offset = self._cursor_pos
            return
        if self._cursor_pos < self._scroll_offset:
            self._scroll_offset = self._cursor_pos
        elif self._cursor_pos >= self._scroll_offset + visible_chars:
            self._scroll_offset = self._cursor_pos - visible_chars + 1

    # ── История ────────────────────────────────────────────────────────

    def _history_prev(self) -> bool:
        """Перемещение вверх по истории."""
        if not self._history:
            return False
        if self._history_index == -1:
            # Сохраняем текущий ввод
            self._history_saved = self._text
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return True  # Уже в начале
        self._text = self._history[self._history_index]
        self._cursor_pos = len(self._text)
        self._selection_start = None
        self._update_scroll()
        return True

    def _history_next(self) -> bool:
        """Перемещение вниз по истории."""
        if self._history_index == -1:
            return False
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._text = self._history[self._history_index]
        else:
            # Возвращаем сохранённый ввод
            self._history_index = -1
            self._text = self._history_saved
        self._cursor_pos = len(self._text)
        self._selection_start = None
        self._update_scroll()
        return True

    # ── Буфер обмена ───────────────────────────────────────────────────

    def _copy_to_clipboard(self) -> None:
        """Копирует выделенный текст в буфер обмена."""
        if self._selection_start is None:
            return
        start = min(self._selection_start, self._cursor_pos)
        end = max(self._selection_start, self._cursor_pos)
        selected = self._text[start:end]
        try:
            pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, selected.encode("utf-8"))
        except Exception:
            pass  # Буфер обмена недоступен

    def _paste_from_clipboard(self) -> None:
        """Вставляет текст из буфера обмена."""
        try:
            pygame.scrap.init()
            raw = pygame.scrap.get(pygame.SCRAP_TEXT)
            if raw:
                text = raw.decode("utf-8", errors="ignore").rstrip("\x00")
                self._insert_text(text)
        except Exception:
            pass  # Буфер обмена недоступен

    # ── Отрисовка ──────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        """Отрисовывает текстовое поле на поверхности."""
        # Фон
        pygame.draw.rect(surface, self.colors["bg"], self.rect, border_radius=6)

        # Рамка
        border_color = self.colors["border_active"] if self._focused else self.colors["border"]
        pygame.draw.rect(surface, border_color, self.rect, 1, border_radius=6)

        # Область текста с отступом
        text_area = pygame.Rect(
            self.rect.x + 6, self.rect.y + 4,
            self.rect.width - 12, self.rect.height - 8,
        )

        # Вычисляем видимый фрагмент текста
        char_w = self.font.size("A")[0]
        visible_chars = text_area.width // char_w if char_w > 0 else 0
        start_char = self._scroll_offset
        end_char = start_char + visible_chars + 1
        visible_text = self._text[start_char:end_char]

        # Рисуем выделение
        if self._selection_start is not None:
            sel_start = min(self._selection_start, self._cursor_pos) - start_char
            sel_end = max(self._selection_start, self._cursor_pos) - start_char
            sel_start = max(0, sel_start)
            sel_end = min(len(visible_text), sel_end)
            if sel_end > sel_start:
                sel_rect = pygame.Rect(
                    text_area.x + sel_start * char_w,
                    text_area.y,
                    (sel_end - sel_start) * char_w,
                    text_area.height,
                )
                pygame.draw.rect(surface, self.colors["selection"], sel_rect)

        # Рисуем текст
        text_surf = self.font.render(visible_text, True, self.colors["text"])
        surface.blit(text_surf, text_area.topleft)

        # Рисуем IME текст (если есть)
        if self._ime_text:
            ime_surf = self.font.render(self._ime_text, True, (180, 180, 180))
            surface.blit(ime_surf, (text_area.x + len(visible_text) * char_w, text_area.y))

        # Рисуем курсор (мигает только при фокусе)
        if self._focused:
            cursor_x = text_area.x + (self._cursor_pos - start_char) * char_w
            cursor_rect = pygame.Rect(cursor_x, text_area.y + 2, 2, text_area.height - 4)
            pygame.draw.rect(surface, self.colors["cursor"], cursor_rect)
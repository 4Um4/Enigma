"""
path: /frontend/narrative_renderer.py
Назначение: Cinematic Layer — рендеринг сценических событий (NarrativeBeat) вместо плоского чата.
Соблюдение Устава §10: Импрессионизм, контраст 0.45-0.6, Micro AO.
Зависимости: pygame, frontend.narrative_beat
Основные сущности: NarrativeRenderer

Контракт:
- Чистая функция: не мутирует состояние игры, только рендерит переданные NarrativeBeat.
- Рендерит имя говорящего с учетом уровня распознавания (известный, мужчина, женщина, странное лицо).
- Рендерит текст с учетом DeliveryType (обычный, шепот, крик) и Certainty (добавляет рваный текст при низкой уверенности).
- Рендерит активный beat с эффектом внимания (глоу) и дрожью для крика.
- Рендерит ввод игрока в отдельном стиле "Черновик разума", расширяющемся по мере печати.

TODO:
- В будущем можно добавить анимацию появления/исчезновения beat'ов, а также более сложные эффекты для разных DeliveryType (например, шепот может иметь легкую размытость, а крик — более агрессивную рамку и сильную дрожь). Но на начальном этапе достаточно базового рендеринга с учетом основных параметров, чтобы обеспечить выразительность сценических событий и соблюдение визуального стиля Устава §10. Это позволит нам быстро интегрировать NarrativeBeat в игру и начать создавать насыщенные диалоговые сцены, не отвлекаясь на сложные визуальные эффекты, которые можно будет добавить позже. Важно, что рендерер остается чистой функцией, которая не зависит от глобального состояния и не мутирует данные, а просто принимает NarrativeBeat и рисует их на переданной поверхности, что обеспечивает предсказуемость и легкость тестирования.
- Рендеринг имени с учетом уровня распознавания позволяет усилить атмосферу неопределенности и постепенного узнавания персонажей, что является важной частью нарративного опыта. Это также добавляет глубину взаимодействия с NPC, так как игрок будет видеть, как его персонаж воспринимает других, что может влиять на его решения и эмоции в игре. Визуальное оформление в стиле Устава §10 с контрастными цветами и эффектами поможет создать уникальную атмосферу и подчеркнуть важность каждого сказанного слова, делая диалоговые сцены более запоминающимися и эмоционально насыщенными.
"""

import pygame
import random
from typing import List
from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel, BeatLifetime


class NarrativeRenderer:
    # Палитра Устава §10 (высокий контраст, низкая насыщенность)
    COLOR_BG_NPC = (18, 18, 22, 220)
    COLOR_BG_PLAYER = (15, 25, 40, 220)
    COLOR_BORDER_NPC = (220, 160, 40)  # Теплый оранж (Таверна)
    COLOR_BORDER_PLAYER = (80, 160, 255)  # Холодный синий (Игрок)
    COLOR_TEXT = (210, 210, 210)
    COLOR_NAME_KNOWN = (255, 255, 255)
    COLOR_NAME_UNKNOWN = (150, 140, 130)  # Приглушенный

    def __init__(self, font_normal: pygame.font.Font, font_bold: pygame.font.Font):
        self.font_normal = font_normal
        self.font_bold = font_bold
        # Заготовка маски шума для дизеринга (Bayer 8x8 упрощенный для текста)
        self._dither_mask = self._generate_dither_mask(200, 50)

    def _generate_dither_mask(self, w: int, h: int) -> pygame.Surface:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            for y in range(h):
                if random.random() < 0.4:
                    mask.set_at((x, y), (0, 0, 0, 120))
        return mask

    def _wrap_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> List[str]:
        """Перенос слов, сохраняя пробелы и явные переносы строки (\n)"""
        if not text:
            return [""]

        paragraphs = text.split("\n")
        lines = []

        for para in paragraphs:
            if not para:
                lines.append("")  # Сохраняем пустые строки от Shift+Enter
                continue

            import re

            parts = re.split(r"(\s+)", para)
            current_line = ""

            for part in parts:
                if not part:
                    continue

                test_line = current_line + part
                if font.size(test_line)[0] <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                        current_line = part.lstrip(" ")
                    else:
                        # Слово длиннее самой строки — всё равно пишем
                        current_line = part.lstrip(" ")

            if current_line:
                lines.append(current_line)

        return lines if lines else [""]

    def draw_beat(
        self,
        surface: pygame.Surface,
        beat: NarrativeBeat,
        x: int,
        y: int,
        max_width: int,
    ) -> int:
        """Рисует пузырь реплики. Возвращает полную высоту пузыря."""
        is_player = beat.is_player
        pad = 12

        # Выбор стиля по DeliveryType (Experiential Architecture: шрифт не мельчим!)
        font = self.font_normal
        border_color = self.COLOR_BORDER_PLAYER if is_player else self.COLOR_BORDER_NPC
        text_color = self.COLOR_TEXT
        bg_color = self.COLOR_BG_PLAYER if is_player else self.COLOR_BG_NPC

        if beat.delivery == DeliveryType.SHOUT:
            border_color = (255, 50, 50)  # Агрессивная красная рамка
            text_color = (255, 255, 255)  # Максимальный контраст для крика
        elif beat.delivery == DeliveryType.WHISPER:
            border_color = (100, 100, 100)  # Приглушенная рамка
            text_color = (170, 170, 170)  # Мягкий серый (читаемый, но тихий)
        elif beat.delivery == DeliveryType.INTERNAL:
            border_color = (80, 120, 180)  # Холодная синяя рамка (мысли)
            text_color = (190, 200, 230)  # Приглушенный голубоватый текст
            bg_color = (15, 15, 30, 200)  # Чуть более темный фон для мыслей

        # Certainty Layer (Пункт 2 Мастера тай) — эмуляция дрожи/пропуска
        display_text = beat.text
        if beat.certainty < 0.5:
            # Рваный текст
            display_text = "".join(
                c if random.random() < beat.certainty + 0.3 else " " for c in beat.text
            )

        # Обработка имени (ТЗ 1 + Пункт 3 Мастера тай)
        speaker_name = beat.speaker
        name_color = self.COLOR_NAME_KNOWN
        if not is_player:
            if beat.recognition == RecognitionLevel.UNKNOWN_MALE:
                speaker_name = "Мужчина"
                name_color = self.COLOR_NAME_UNKNOWN
            elif beat.recognition == RecognitionLevel.UNKNOWN_FEMALE:
                speaker_name = "Женщина"
                name_color = self.COLOR_NAME_UNKNOWN
            elif beat.recognition == RecognitionLevel.STRANGE_FACE:
                speaker_name = "Знакомый..."
                name_color = self.COLOR_NAME_UNKNOWN

        # Рендер текста с переносом строк
        lines = self._wrap_text(display_text, font, max_width - pad * 2)
        line_height = font.get_linesize()
        text_height = len(lines) * line_height

        # Размеры пузыря
        bubble_height = text_height + pad * 2
        name_height = self.font_bold.get_linesize() + 6

        total_height = name_height + bubble_height

        # Сдвиг для тряски (SHOUT)
        offset_x, offset_y = 0, 0
        if beat.delivery == DeliveryType.SHOUT and beat.is_active:
            offset_x = random.randint(-1, 1)
            offset_y = random.randint(-1, 1)

        # Пузырь
        bubble_rect = pygame.Rect(
            x + offset_x, y + name_height + offset_y, max_width, bubble_height
        )
        bubble_surf = pygame.Surface(
            (bubble_rect.width, bubble_rect.height), pygame.SRCALPHA
        )
        pygame.draw.rect(bubble_surf, bg_color, bubble_surf.get_rect(), border_radius=4)

        # Рамка: толще для крика (3), тоньше для шепота/мыслей (1), стандарт (2)
        border_width = (
            3
            if beat.delivery == DeliveryType.SHOUT
            else 1
            if beat.delivery in (DeliveryType.WHISPER, DeliveryType.INTERNAL)
            else 2
        )
        pygame.draw.rect(
            bubble_surf,
            border_color,
            bubble_surf.get_rect(),
            border_width,
            border_radius=4,
        )

        # Текст внутри пузыря
        for i, line in enumerate(lines):
            # Приоритет 3: Визуальные стили для DeliveryType
            if beat.delivery == DeliveryType.WHISPER:
                # Легкий серый ореол (тень)
                shadow_surf = font.render(line, True, (80, 80, 80))
                bubble_surf.blit(shadow_surf, (pad + 1, pad + i * line_height + 1))
                # Полупрозрачный текст (alpha = 200)
                line_surf = font.render(line, True, text_color)
                line_surf.set_alpha(200)
            else:
                line_surf = font.render(line, True, text_color)
            bubble_surf.blit(line_surf, (pad, pad + i * line_height))

        surface.blit(bubble_surf, bubble_rect.topleft)

        # Плашка имени (над пузырем)
        name_surf = self.font_bold.render(speaker_name, True, name_color)
        name_bg_rect = pygame.Rect(
            x + offset_x, y + offset_y, name_surf.get_width() + 12, name_height
        )

        name_bg_surf = pygame.Surface(
            (name_bg_rect.width, name_bg_rect.height), pygame.SRCALPHA
        )
        pygame.draw.rect(
            name_bg_surf, (*border_color, 180), name_bg_surf.get_rect(), border_radius=2
        )

        name_bg_surf.blit(name_surf, (6, 3))

        # Дизеринг для неизвестных (Устав §10 + Пункт 3 Мастера тай)
        if beat.recognition in (
            RecognitionLevel.UNKNOWN_MALE,
            RecognitionLevel.UNKNOWN_FEMALE,
            RecognitionLevel.STRANGE_FACE,
        ):
            # Накладываем маску шума на имя
            name_bg_surf.blit(
                self._dither_mask, (0, 0), special_flags=pygame.BLEND_RGBA_SUB
            )

        # Применяем альфа-канал к плашке имени (растворение)
        if beat.alpha < 255.0:
            fade_overlay = pygame.Surface(name_bg_surf.get_size(), pygame.SRCALPHA)
            fade_overlay.fill((255, 255, 255, int(beat.alpha)))
            name_bg_surf.blit(
                fade_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT
            )

        surface.blit(name_bg_surf, name_bg_rect.topleft)

        # Маска внимания (Устав §10) — аддитивный свет для активного пузыря
        if beat.is_active and beat.lifetime != BeatLifetime.TRANSIENT:
            glow_surf = pygame.Surface(
                (bubble_rect.width + 40, bubble_rect.height + 40), pygame.SRCALPHA
            )
            pygame.draw.ellipse(
                glow_surf,
                (border_color[0], border_color[1], border_color[2], 30),
                glow_surf.get_rect(),
            )
            surface.blit(
                glow_surf,
                (bubble_rect.x - 20, bubble_rect.y - 20),
                special_flags=pygame.BLEND_ADD,
            )

        return total_height

    def draw_input_bubble(
        self,
        surface: pygame.Surface,
        player_name: str,
        text: str,
        cursor_pos: int,
        x: int,
        y: int,
        max_width: int,
    ) -> int:
        """Рисует пузырь ввода игрока (Persona 5 Style: расширяющийся, с хвостиком)"""
        pad = 14
        accent_width = 6  # Ширина акцентной полосы справа

        # Текст для отображения (если пусто — подсказка)
        display_text = text if text else "Введите текст..."
        text_color = (220, 220, 220) if text else (90, 90, 100)

        # Вычисляем размер текста с учетом переноса
        lines = self._wrap_text(
            display_text, self.font_normal, max_width - pad * 2 - accent_width
        )
        line_height = self.font_normal.get_linesize()
        text_height = len(lines) * line_height

        bubble_height = text_height + pad * 2
        name_height = self.font_bold.get_linesize() + 8
        total_height = name_height + bubble_height

        # --- 1. Рисуем плашку имени (со стрелкой-вырезом) ---
        name_surf = self.font_bold.render(player_name, True, self.COLOR_NAME_KNOWN)
        name_bg_width = name_surf.get_width() + 20
        name_bg_surf = pygame.Surface((name_bg_width, name_height), pygame.SRCALPHA)

        # Фон плашки
        pygame.draw.rect(
            name_bg_surf,
            (*self.COLOR_BORDER_PLAYER, 200),
            (0, 0, name_bg_width, name_height - 6),
            border_radius=4,
        )
        # Стрелка-вырез снизу плашки
        pygame.draw.polygon(
            name_bg_surf,
            (*self.COLOR_BORDER_PLAYER, 200),
            [
                (name_bg_width - 25, name_height - 6),
                (name_bg_width - 15, name_height + 2),
                (name_bg_width - 35, name_height - 6),
            ],
        )
        name_bg_surf.blit(name_surf, (10, 4))
        surface.blit(name_bg_surf, (x, y))

        # --- 2. Рисуем пузырь ---
        bubble_rect = pygame.Rect(x, y + name_height, max_width, bubble_height)
        bubble_surf = pygame.Surface(
            (bubble_rect.width, bubble_rect.height), pygame.SRCALPHA
        )

        # Фон пузыря (темный, полупрозрачный)
        pygame.draw.rect(
            bubble_surf,
            self.COLOR_BG_PLAYER,
            (0, 0, bubble_rect.width, bubble_rect.height),
            border_radius=6,
        )

        # Акцентная полоса справа (стиль Persona)
        pygame.draw.rect(
            bubble_surf,
            self.COLOR_BORDER_PLAYER,
            (bubble_rect.width - accent_width, 0, accent_width, bubble_rect.height),
            border_top_right_radius=6,
            border_bottom_right_radius=6,
        )

        # Рамка пузыря
        pygame.draw.rect(
            bubble_surf,
            (*self.COLOR_BORDER_PLAYER, 160),
            (0, 0, bubble_rect.width, bubble_rect.height),
            2,
            border_radius=6,
        )

        # Хвостик пузыря (треугольник справа снизу)
        tail_size = 12
        tail_x_start = bubble_rect.width - accent_width - tail_size * 2
        tail_y = bubble_rect.height - 2
        pygame.draw.polygon(
            bubble_surf,
            (*self.COLOR_BG_PLAYER[:3], 255),
            [
                (tail_x_start, tail_y),
                (bubble_rect.width - accent_width, tail_y),
                (bubble_rect.width - accent_width, tail_y - tail_size),
            ],
        )

        # --- 3. Рендер текста внутри пузыря ---
        for i, line in enumerate(lines):
            line_surf = self.font_normal.render(line, True, text_color)
            bubble_surf.blit(line_surf, (pad, pad + i * line_height))

        # --- 4. Курсор (учитывает многострочность и мигает) ---
        if text and cursor_pos <= len(text):
            text_before_cursor = text[:cursor_pos]
            cursor_lines = self._wrap_text(
                text_before_cursor, self.font_normal, max_width - pad * 2 - accent_width
            )
            cy = pad + (len(cursor_lines) - 1) * line_height
            last_line = cursor_lines[-1]
            cx = pad + self.font_normal.size(last_line)[0]

            # Мигание курсора
            is_cursor_visible = (pygame.time.get_ticks() % 1000) < 600
            if is_cursor_visible:
                pygame.draw.rect(bubble_surf, (200, 200, 255), (cx, cy, 2, line_height))

        # Ввод игрока всегда непрозрачен (нет объекта beat для fade)
        surface.blit(bubble_surf, bubble_rect.topleft)
        return total_height

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
from typing import List, Tuple
from narrative_beat import NarrativeBeat, DeliveryType, RecognitionLevel, BeatLifetime

class NarrativeRenderer:
    # Палитра Устава §10 (высокий контраст, низкая насыщенность)
    COLOR_BG_NPC = (18, 18, 22, 220)
    COLOR_BG_PLAYER = (15, 25, 40, 220)
    COLOR_BORDER_NPC = (220, 160, 40)  # Теплый оранж (Таверна)
    COLOR_BORDER_PLAYER = (80, 160, 255) # Холодный синий (Игрок)
    COLOR_TEXT = (210, 210, 210)
    COLOR_NAME_KNOWN = (255, 255, 255)
    COLOR_NAME_UNKNOWN = (150, 140, 130) # Приглушенный

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

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        """Перенос слов без обрезания смысла"""
        words = text.split(' ')
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line: lines.append(current_line)
                current_line = word
        if current_line: lines.append(current_line)
        return lines if lines else [""]

    def draw_beat(self, surface: pygame.Surface, beat: NarrativeBeat, x: int, y: int, max_width: int) -> int:
        """Рисует пузырь реплики. Возвращает полную высоту пузыря."""
        is_player = beat.is_player
        pad = 12

        # Выбор шрифта по DeliveryType (Пункт 1 Мастера тай)
        font = self.font_normal
        if beat.delivery == DeliveryType.SHOUT:
            # В идеале тут другой шрифт, пока просто изменяем цвет/рамку
            border_color = (255, 50, 50)
        elif beat.delivery == DeliveryType.WHISPER:
            border_color = (100, 100, 100)
        else:
            border_color = self.COLOR_BORDER_PLAYER if is_player else self.COLOR_BORDER_NPC

        bg_color = self.COLOR_BG_PLAYER if is_player else self.COLOR_BG_NPC

        # Certainty Layer (Пункт 2 Мастера тай) — эмуляция дрожи/пропуска
        display_text = beat.text
        if beat.certainty < 0.5:
            # Рваный текст
            display_text = "".join(c if random.random() < beat.certainty + 0.3 else ' ' for c in beat.text)

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
            offset_x = random.randint(-2, 2)
            offset_y = random.randint(-2, 2)

        # Пузырь
        bubble_rect = pygame.Rect(x + offset_x, y + name_height + offset_y, max_width, bubble_height)
        bubble_surf = pygame.Surface((bubble_rect.width, bubble_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(bubble_surf, bg_color, bubble_surf.get_rect(), border_radius=4)
        pygame.draw.rect(bubble_surf, border_color, bubble_surf.get_rect(), 2, border_radius=4)

        # Текст внутри пузыря
        for i, line in enumerate(lines):
            line_surf = font.render(line, True, self.COLOR_TEXT)
            bubble_surf.blit(line_surf, (pad, pad + i * line_height))

        surface.blit(bubble_surf, bubble_rect.topleft)

        # Плашка имени (над пузырем)
        name_surf = self.font_bold.render(speaker_name, True, name_color)
        name_bg_rect = pygame.Rect(x + offset_x, y + offset_y, name_surf.get_width() + 12, name_height)
        
        name_bg_surf = pygame.Surface((name_bg_rect.width, name_bg_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(name_bg_surf, (*border_color, 180), name_bg_surf.get_rect(), border_radius=2)
        
        name_bg_surf.blit(name_surf, (6, 3))

        # Дизеринг для неизвестных (Устав §10 + Пункт 3 Мастера тай)
        if beat.recognition in (RecognitionLevel.UNKNOWN_MALE, RecognitionLevel.UNKNOWN_FEMALE, RecognitionLevel.STRANGE_FACE):
            # Накладываем маску шума на имя
            name_bg_surf.blit(self._dither_mask, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        surface.blit(name_bg_surf, name_bg_rect.topleft)

        # Маска внимания (Устав §10) — аддитивный свет для активного пузыря
        if beat.is_active and beat.lifetime != BeatLifetime.TRANSIENT:
            glow_surf = pygame.Surface((bubble_rect.width + 40, bubble_rect.height + 40), pygame.SRCALPHA)
            pygame.draw.ellipse(glow_surf, (border_color[0], border_color[1], border_color[2], 30), glow_surf.get_rect())
            surface.blit(glow_surf, (bubble_rect.x - 20, bubble_rect.y - 20), special_flags=pygame.BLEND_ADD)

        return total_height

    def draw_input_bubble(self, surface: pygame.Surface, player_name: str, text: str, cursor_pos: int, x: int, y: int, max_width: int) -> int:
        """Рисует пузырь ввода игрока (ТЗ 3) — расширяющийся по мере печати"""
        if not text and cursor_pos == 0:
            # Пустой минимальный пузырь
            text = "..."
        
        pad = 12
        lines = self._wrap_text(text, self.font_normal, max_width - pad * 2)
        line_height = self.font_normal.get_linesize()
        text_height = len(lines) * line_height
        
        bubble_height = text_height + pad * 2
        name_height = self.font_bold.get_linesize() + 6
        total_height = name_height + bubble_height

        # Рамка и фон (Стиль "Черновик разума")
        bubble_rect = pygame.Rect(x, y + name_height, max_width, bubble_height)
        bubble_surf = pygame.Surface((bubble_rect.width, bubble_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(bubble_surf, self.COLOR_BG_PLAYER, bubble_surf.get_rect(), border_radius=4)
        pygame.draw.rect(bubble_surf, self.COLOR_BORDER_PLAYER, bubble_surf.get_rect(), 2, border_radius=4)

        # Текст
        for i, line in enumerate(lines):
            line_surf = self.font_normal.render(line, True, self.COLOR_TEXT)
            bubble_surf.blit(line_surf, (pad, pad + i * line_height))

        # Курсор
        if cursor_pos <= len(text):
            # Вычисляем позицию курсора с учетом многострочности
            text_before_cursor = text[:cursor_pos]
            cursor_lines = self._wrap_text(text_before_cursor, self.font_normal, max_width - pad * 2)
            cy = pad + (len(cursor_lines) - 1) * line_height
            cx = pad + self.font_normal.size(cursor_lines[-1])[0]
            pygame.draw.rect(bubble_surf, (200, 200, 255), (cx, cy, 2, line_height))

        surface.blit(bubble_surf, bubble_rect.topleft)

        # Имя игрока
        name_surf = self.font_bold.render(player_name, True, self.COLOR_NAME_KNOWN)
        name_bg_rect = pygame.Rect(x, y, name_surf.get_width() + 12, name_height)
        name_bg_surf = pygame.Surface((name_bg_rect.width, name_bg_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(name_bg_surf, (*self.COLOR_BORDER_PLAYER, 180), name_bg_surf.get_rect(), border_radius=2)
        name_bg_surf.blit(name_surf, (6, 3))
        surface.blit(name_bg_surf, name_bg_rect.topleft)

        return total_height
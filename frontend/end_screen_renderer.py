# -*- coding: utf-8 -*-
"""
path: /frontend/end_screen_renderer.py
Назначение: Рендер финального экрана миниигры "Таверна Серебряный Волк".
Зависимости: pygame, frontend.constants, frontend.i18n
Основные сущности: EndScreenRenderer
"""

import pygame
from constants import (
    COLOR_TEXT_DEFAULT, COLOR_TEXT_DIM, COLOR_TEXT_MUTED,
    COLOR_JOURNAL_TITLE, COLOR_DEATH_TITLE
)
from i18n import t

class EndScreenRenderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font_title = pygame.font.Font(None, 64)
        self.font_header = pygame.font.Font(None, 36)
        self.font_body = pygame.font.Font(None, 24)
        
    def render(self, data: dict) -> bool:
        """Отрисовывает финальный экран. Возвращает True если нужно выйти в меню."""
        # Затенение фона
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((10, 10, 15, 230))
        self.screen.blit(overlay, (0, 0))
        
        w, h = self.screen.get_size()
        y = 50
        
        # Заголовок
        title = self.font_title.render(t("ui:end_screen_title"), True, COLOR_JOURNAL_TITLE)
        self.screen.blit(title, (w // 2 - title.get_width() // 2, y))
        y += 80
        
        # Оценка
        score = data.get("score", 0)
        score_color = (100, 255, 100) if score >= 50 else COLOR_DEATH_TITLE
        score_txt = self.font_header.render(f"{t('ui:end_screen_score')}: {score} / 100", True, score_color)
        self.screen.blit(score_txt, (w // 2 - score_txt.get_width() // 2, y))
        y += 50
        
        # Статистика по секретам
        stats = [
            f"{t('ui:end_screen_secrets_found')}: {data.get('secrets_identified', 0)} / {data.get('secrets_total', 16)}",
            f"{t('ui:end_screen_wrong_guesses')}: {data.get('secrets_misidentified', 0)}",
            f"{t('ui:end_screen_missed')}: {data.get('secrets_missed', 0)}"
        ]
        
        for line in stats:
            surf = self.font_body.render(line, True, COLOR_TEXT_DEFAULT)
            self.screen.blit(surf, (w // 2 - 150, y))
            y += 30
            
        y += 20
        
        # Методы
        methods = data.get("methods_used", {})
        if methods:
            m_header = self.font_body.render(t("ui:end_screen_methods_used"), True, COLOR_TEXT_DIM)
            self.screen.blit(m_header, (w // 2 - 150, y))
            y += 30
            for m_name, m_count in methods.items():
                line = f"- {m_name}: {m_count}"
                surf = self.font_body.render(line, True, COLOR_TEXT_MUTED)
                self.screen.blit(surf, (w // 2 - 130, y))
                y += 25
                
        # 8.1 FIX: Вердикт (крупный текст)
        verdict = data.get("verdict_text", "")
        if verdict:
            y += 20
            verdict_surf = self.font_header.render(verdict, True, COLOR_JOURNAL_TITLE)
            # Простой wrap текста
            max_width = w - 200
            words = verdict.split(' ')
            lines, current_line = [], ""
            for word in words:
                test_line = (current_line + " " + word).strip()
                if self.font_header.size(test_line)[0] <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            if current_line: lines.append(current_line)
            
            for i, line in enumerate(lines):
                surf = self.font_header.render(line, True, COLOR_JOURNAL_TITLE)
                self.screen.blit(surf, (100, y + i * 40))
            y += len(lines) * 40 + 30

        # 8.1 FIX: Итоги судеб
        fate_texts = data.get("fate_texts", [])
        if fate_texts:
            y += 20
            f_header = self.font_body.render(t("ui:end_screen_fates"), True, COLOR_TEXT_DIM)
            self.screen.blit(f_header, (100, y))
            y += 30
            for text in fate_texts:
                surf = self.font_body.render(f"• {text}", True, COLOR_TEXT_MUTED)
                self.screen.blit(surf, (120, y))
                y += 25

        # 8.1 FIX: Социальный граф
        rel_texts = data.get("relationship_texts", [])
        if rel_texts:
            y += 20
            r_header = self.font_body.render(t("ui:end_screen_relationships"), True, COLOR_TEXT_DIM)
            self.screen.blit(r_header, (100, y))
            y += 30
            for text in rel_texts[:5]: # Ограничиваем 5 записями, чтобы не вылезти за экран
                surf = self.font_body.render(f"• {text}", True, COLOR_TEXT_MUTED)
                self.screen.blit(surf, (120, y))
                y += 25

        # Подсказка для выхода
        y = h - 60
        hint = self.font_body.render(t("ui:end_screen_return_hint"), True, COLOR_TEXT_DIM)
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, y))
        
        return True
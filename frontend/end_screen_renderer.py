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
                
        # Подсказка для выхода
        y = h - 60
        hint = self.font_body.render(t("ui:end_screen_return_hint"), True, COLOR_TEXT_DIM)
        self.screen.blit(hint, (w // 2 - hint.get_width() // 2, y))
        
        return True
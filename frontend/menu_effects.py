"""
path: frontend/menu_effects.py
Назначение: Анимация дыма для главного меню — частицы с плавным движением и затуханием
Зависимости: pygame, random, math
Основные сущности: SmokeParticle, SmokeEmitter
"""

import pygame
import random
import math
from typing import List


class SmokeParticle:
    """Одна частица дыма — плавно поднимается, расширяется и затухает."""

    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "radius",
        "max_radius",
        "alpha",
        "life",
        "max_life",
        "grow_rate",
    )

    def __init__(self, x: float, y: float) -> None:
        self.x = x + random.uniform(-3, 3)
        self.y = y
        # Медленный дрейф вверх + лёгкое горизонтальное колебание
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(-0.8, -0.3)
        self.radius = random.uniform(2, 4)
        self.max_radius = random.uniform(15, 30)
        self.grow_rate = random.uniform(0.15, 0.35)
        self.alpha = random.randint(40, 80)
        self.life = 0.0
        self.max_life = random.uniform(2.0, 4.0)  # секунды

    def update(self, dt: float, wind: float = 0.0) -> bool:
        """Обновляет частицу. Возвращает False если частица умерла."""
        self.life += dt
        if self.life >= self.max_life:
            return False

        # Горизонтальный дрейф усиливается ветром
        self.vx += wind * dt * 0.5
        # Синусоидальное колебание
        self.vx += math.sin(self.life * 2.0 + self.x * 0.01) * dt * 0.5

        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60

        # Рост и затухание
        progress = self.life / self.max_life
        self.radius = min(self.radius + self.grow_rate, self.max_radius)
        # Быстрое появление, медленное затухание
        if progress < 0.1:
            self.alpha = int(80 * (progress / 0.1))
        else:
            self.alpha = int(80 * (1.0 - (progress - 0.1) / 0.9))

        self.alpha = max(0, min(80, self.alpha))
        return True


class SmokeEmitter:
    """Эмиттер дыма — создаёт частицы в заданной точке (труба)."""

    def __init__(self, x: float, y: float, rate: float = 8.0) -> None:
        self.x = x  # Позиция трубы (0-1 нормализованная)
        self.y = y
        self.rate = rate  # Частиц в секунду
        self._accumulator = 0.0
        self.particles: List[SmokeParticle] = []
        self.wind = 0.0  # Направление ветра (-1..1)
        self._wind_timer = 0.0

    def update(self, dt: float) -> None:
        """Обновляет все частицы и создаёт новые."""
        # Ветер меняется медленно
        self._wind_timer += dt
        if self._wind_timer > 3.0:
            self.wind = random.uniform(-0.5, 0.5)
            self._wind_timer = 0.0

        # Создание новых частиц
        self._accumulator += dt * self.rate
        while self._accumulator >= 1.0:
            self.particles.append(SmokeParticle(self.x, self.y))
            self._accumulator -= 1.0

        # Обновление существующих
        self.particles = [p for p in self.particles if p.update(dt, self.wind)]

    def draw(self, surface: pygame.Surface, screen_w: int, screen_h: int) -> None:
        """Отрисовывает все частицы на поверхности."""
        for p in self.particles:
            # Нормализованные координаты → пиксели
            px = int(p.x * screen_w)
            py = int(p.y * screen_h)
            r = int(p.radius)

            if r < 1 or p.alpha < 5:
                continue

            # Полупрозрачный круг дыма
            smoke_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            # Серый дым с голубоватым оттенком
            color = (160, 165, 175, p.alpha)
            pygame.draw.circle(smoke_surf, color, (r, r), r)
            surface.blit(smoke_surf, (px - r, py - r))


# pygame импортирован на уровне модуля

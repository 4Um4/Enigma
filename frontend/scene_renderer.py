"""
path: /frontend/scene_renderer.py

Рендер карты — переводит PerceivedScene в пиксели.
Координаты в метрах, SCALE = пикселей на метр.
Рисует только воспринимаемое (visible entities, audio как текст).

Назначение: Отрисовывает PerceivedScene на pygame.Surface — только то, что персонаж воспринимает
Зависимости: pygame, player_cognition.types
Основные сущности: SceneRenderer
"""
from typing import List, Optional, Tuple

import pygame

from sprite_resolver import get_entity_sprite
from game_types import (
    PerceivedEntity,
    PerceivedScene,
)

# === Пиксели на метр ===
SCALE = 40

# === Цвета рендера ===
_COLORS = {
    "bg_dark": (18, 18, 23),
    "floor_visible": (35, 35, 42),
    "floor_dim": (25, 25, 30),
    "wall": (100, 100, 110),
    "wall_visible": (140, 140, 150),
    "obstacle": (55, 55, 65),
    "obstacle_visible": (75, 75, 85),
    "object": (80, 100, 80),
    "object_visible": (100, 140, 100),
    "npc_body": (180, 140, 100),
    "npc_focused": (220, 180, 120),
    "player_body": (70, 170, 255),
    "player_focused": (100, 200, 255),
    "text_audio": (200, 180, 120),
    "text_body": (200, 120, 120),
    "text_environment": (140, 140, 140),
    "fog": (12, 12, 16),
    "attention_glow": (70, 170, 255, 40),
}


class SceneRenderer:
    """Отрисовывает PerceivedScene на Surface с камерой, центрированной на игроке"""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font_small = pygame.font.SysFont("consolas", 12)
        self.font_audio = pygame.font.SysFont("consolas", 13, italic=True)
        self.font_body = pygame.font.SysFont("consolas", 13)

    def render(
        self,
        scene: PerceivedScene,
        scene_w: float,
        scene_h: float,
        walls: List[dict],
        obstacles: List[dict],
        player_xy: Tuple[float, float],
    ) -> None:
        """
        Отрисовывает полный кадр.

        Args:
            scene: PerceivedScene из pipeline
            scene_w, scene_h: размер локации в метрах
            walls: spatial_walls из SceneState (рисуем всегда — геометрия комнаты)
            obstacles: spatial_obstacles (рисуем только воспринятые)
            player_xy: (x, y) игрока в метрах
        """
        self.screen.fill(_COLORS["bg_dark"])

        # Камера центрирована на игроке
        cam_x = player_xy[0] * SCALE - self.screen.get_width() // 2
        cam_y = player_xy[1] * SCALE - self.screen.get_height() // 2

        # 1. Пол — вся локация (тёмный)
        self._draw_floor(scene_w, scene_h, cam_x, cam_y)

        # 2. Стены — геометрия комнаты (видны всегда, но ярче если в LOS)
        self._draw_walls(walls, cam_x, cam_y, scene)

        # 3. Препятствия/объекты — только воспринимаемые
        self._draw_entities(scene.entities, cam_x, cam_y)

        # 4. NPC — только воспринимаемые
        self._draw_npcs(scene.entities, cam_x, cam_y, scene.attention_focus_id)

        # 5. Игрок — всегда виден
        self._draw_player(player_xy, cam_x, cam_y)

        # 6. HUD поверх карты — audio events, body state, environment
        self._draw_hud(scene)

    def _w2s(self, wx: float, wy: float, cam_x: float, cam_y: float) -> Tuple[int, int]:
        """Мировые координаты (метры) → экранные (пиксели)"""
        return int(wx * SCALE - cam_x), int(wy * SCALE - cam_y)

    def _draw_floor(self, w: float, h: float, cam_x: float, cam_y: float) -> None:
        sx, sy = self._w2s(0, 0, cam_x, cam_y)
        sw, sh = int(w * SCALE), int(h * SCALE)
        pygame.draw.rect(self.screen, _COLORS["floor_dim"], (sx, sy, sw, sh))

    def _draw_walls(
        self,
        walls: List[dict],
        cam_x: float,
        cam_y: float,
        scene: PerceivedScene,
    ) -> None:
        # Собираем ID препятствий которые игрок видит — стены рядом с ними ярче
        visible_obstacle_ids = {
            e.entity_id
            for e in scene.entities
            if e.visible and e.entity_type == "object"
        }

        for wall in walls:
            x1, y1 = self._w2s(wall["x1"], wall["y1"], cam_x, cam_y)
            x2, y2 = self._w2s(wall["x2"], wall["y2"], cam_x, cam_y)
            color = _COLORS["wall_visible"]
            pygame.draw.line(self.screen, color, (x1, y1), (x2, y2), 3)

    def _draw_entities(
        self,
        entities: List[PerceivedEntity],
        cam_x: float,
        cam_y: float,
    ) -> None:
        for entity in entities:
            if entity.entity_type != "object":
                continue
            if not entity.visible:
                continue

            raw = entity._raw_data
            ox, oy = entity.x, entity.y
            size = raw.get("size") or {}
            ow, oh = size.get("w", 1), size.get("h", 1)

            sx, sy = self._w2s(ox - ow / 2, oy - oh / 2, cam_x, cam_y)
            sw, sh = int(ow * SCALE), int(oh * SCALE)

            # TODO: убрать raw после добавления obj_type в PerceivedEntity
            obj_type = raw.get("type", "") if raw else ""
            sprite = get_entity_sprite(obj_type)

            if sprite:
                # Масштабируем тайл под физический размер объекта
                scaled = pygame.transform.scale(sprite, (sw, sh))
                self.screen.blit(scaled, (sx, sy))
            else:
                # Резервная отрисовка если спрайт не найден
                color = _COLORS["object_visible"] if entity.in_attention else _COLORS["object"]
                pygame.draw.rect(self.screen, color, (sx, sy, sw, sh), border_radius=3)

            # Подпись если в фокусе
            if entity.in_attention and entity.display_name:
                label = self.font_small.render(entity.display_name, True, (220, 220, 220))
                self.screen.blit(label, (sx, sy - 16))

    def _draw_npcs(
        self,
        entities: List[PerceivedEntity],
        cam_x: float,
        cam_y: float,
        focus_id: Optional[str],
    ) -> None:
        for entity in entities:
            if entity.entity_type != "npc":
                continue
            if not entity.visible:
                continue

            sx, sy = self._w2s(entity.x, entity.y, cam_x, cam_y)

            is_focused = entity.entity_id == focus_id

            # Спрайт NPC по id (fallback на кружок если не найден)
            sprite = get_entity_sprite(entity.entity_id)
            npc_size = 14 if is_focused else 11

            if sprite:
                scaled = pygame.transform.scale(sprite, (npc_size, npc_size))
                self.screen.blit(scaled, (sx - npc_size // 2, sy - npc_size // 2))
                if is_focused:
                    pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), npc_size // 2 + 2, 2)
            else:
                radius = 10 if is_focused else 7
                color = _COLORS["npc_focused"] if is_focused else _COLORS["npc_body"]
                pygame.draw.circle(self.screen, color, (sx, sy), radius)
                if is_focused:
                    pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), radius, 2)

            # Имя по confidence
            if entity.display_name:
                name_color = (255, 255, 255) if is_focused else (180, 180, 180)
                label = self.font_small.render(entity.display_name, True, name_color)
                self.screen.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

            # Inference badges — маленькие индикаторы
            self._draw_inference_badges(entity, sx, sy + radius + 4)

    def _draw_inference_badges(self, entity: PerceivedEntity, sx: int, sy: int) -> None:
        """Рисует маленькие цветные точки для поведенческих выводов"""
        badge_map = {
            "combat": (255, 80, 80),
            "armed": (255, 160, 60),
            "active_aggression": (255, 50, 50),
            "potential_aggression": (200, 120, 60),
            "potentially_hostile": (180, 100, 80),
            "communication": (100, 200, 100),
            "peaceful_interaction": (80, 180, 80),
            "friendly_action": (60, 160, 60),
        }

        x_offset = 0
        for inf in entity.inferences:
            color = badge_map.get(inf.inference_type)
            if color and inf.confidence > 0.4:
                pygame.draw.circle(self.screen, color, (sx + x_offset, sy), 3)
                x_offset += 8

    def _draw_player(self, xy: Tuple[float, float], cam_x: float, cam_y: float) -> None:
        sx, sy = self._w2s(xy[0], xy[1], cam_x, cam_y)
        # Треугольник-маркер игрока
        points = [
            (sx, sy - 12),
            (sx - 8, sy + 6),
            (sx + 8, sy + 6),
        ]
        pygame.draw.polygon(self.screen, _COLORS["player_body"], points)
        pygame.draw.polygon(self.screen, (255, 255, 255), points, 2)

    def _draw_hud(self, scene: PerceivedScene) -> None:
        """Отрисовывает текстовый HUD поверх карты"""
        y = 10
        sw = self.screen.get_width()

        # Audio events — верхний левый
        for audio in scene.audio_events:
            text = f"[{audio.description}]"
            if audio.direction:
                text += f" ({audio.direction})"
            surf = self.font_audio.render(text, True, _COLORS["text_audio"])
            self.screen.blit(surf, (10, y))
            y += 18

        # Body state — нижний левый
        y = sw - 10 - len(scene.player_body_state) * 18 - 20
        for state in scene.player_body_state:
            surf = self.font_body.render(state, True, _COLORS["text_body"])
            self.screen.blit(surf, (10, y))
            y += 18

        # Environment — нижний правый
        env_parts = []
        if scene.environment.light_perceived:
            env_parts.append(scene.environment.light_perceived)
        if scene.environment.noise_perceived:
            env_parts.append(scene.environment.noise_perceived)
        if scene.environment.smell_perceived:
            env_parts.append(scene.environment.smell_perceived)
        if env_parts:
            env_text = " | ".join(env_parts)
            surf = self.font_small.render(env_text, True, _COLORS["text_environment"])
            self.screen.blit(surf, (sw - surf.get_width() - 10, sw - 24))
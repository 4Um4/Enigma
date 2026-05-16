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

import math
import pygame

from presentation_firewall import sanitize_perceptual_input
from perceptual_momentum import PerceptualMomentum, ManifestationProfile

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
        self._prev_npc_positions: Dict[str, Tuple[float, float]] = {} # ADR-037: Для Temporal Assembly Delay
        self.font_small = pygame.font.SysFont("consolas", 12)
        self.font_audio = pygame.font.SysFont("consolas", 13, italic=True)
        self.font_body = pygame.font.SysFont("consolas", 13)
        # Lerp для угла поворота (Приоритет 0)
        self._visual_facing_angle = -1.5708  # -pi/2 (смотрит вверх)
        # Темпоральная инерция восприятия (S-curve, гистерезис, стохастика)
        self.momentum = PerceptualMomentum()

    def render(
        self,
        scene: PerceivedScene,
        scene_w: float,
        scene_h: float,
        walls: List[dict],
        obstacles: List[dict],
        player_xy: Tuple[float, float],
        player_facing: float = -1.5708,  # -pi/2 по умолчанию (смотрит вверх)
        dt: float = 0.016,  # Дельта времени для Lerp (Приоритет 0)
        avatar_state: Optional[dict] = None, # ADR-035: Феноменологическая проекция
        ambient_state: Optional[dict] = None, # ADR-037: Средовое давление
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

        # ADR-037: Вычисляем профиль деформации ДО отрисовки, чтобы влиять на камеру и позиции
        profile = ManifestationProfile()
        if avatar_state:
            sanitized = sanitize_perceptual_input(avatar_state, ambient_state)
            self.momentum.update(dt, sanitized)
            profile = self.momentum.current

        # Камера центрирована на игроке + Motion Bias (мир "давит" на игрока)
        cam_x = player_xy[0] * SCALE - self.screen.get_width() // 2
        cam_y = player_xy[1] * SCALE - self.screen.get_height() // 2
        
        # ADR-037: Motion Bias — снос камеры давлением среды
        cam_x -= int(profile.motion_bias[0] * SCALE * 2)
        cam_y -= int(profile.motion_bias[1] * SCALE * 2)

        # 1. Пол — вся локация (тёмный)
        self._draw_floor(scene_w, scene_h, cam_x, cam_y)

        # 2. Стены — геометрия комнаты (видны всегда, но ярче если в LOS)
        self._draw_walls(walls, cam_x, cam_y, scene)

        # 3. Препятствия/объекты — только воспринимаемые
        self._draw_entities(scene.entities, cam_x, cam_y)
        self._draw_obstacles(obstacles, cam_x, cam_y)

        # 4. NPC — только воспринимаемые (с Temporal Delay)
        self._draw_npcs(scene.entities, cam_x, cam_y, scene.attention_focus_id, player_xy, profile, dt=dt)

        # 5. Игрок — всегда виден
        # Lerp сглаживание поворота (Приоритет 0)
        import math
        diff = player_facing - self._visual_facing_angle
        # Кратчайший путь: нормализация разницы углов в диапазон [-pi, pi]
        diff = (diff + math.pi) % (2 * math.pi) - math.pi
        # Экспоненциальное сглаживание (~10 рад/сек)
        self._visual_facing_angle += diff * min(1.0, 10.0 * dt)
        
        self._draw_player(player_xy, cam_x, cam_y, self._visual_facing_angle)

        # 6. HUD поверх карты — audio events, body state, environment
        self._draw_hud(scene)

        # 7. Embodied Perception Interface — искажение рендера от состояния аватара и среды (ADR-035, ADR-037)
        if avatar_state:
            # Профиль уже вычислен в начале рендера, применяем оверлеи
            self._apply_avatar_perception_overlay(profile)

    def _apply_avatar_perception_overlay(self, profile: 'ManifestationProfile') -> None:
        """Накладывает визуальные искажения на основе Темпоральной Феноменологии.
        Работает ТОЛЬКО с ManifestationProfile (инерция, S-кривая, стохастика уже применены).
        """
        w, h = self.screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        # 1. Кровавая виньетка (с инерцией из ManifestationProfile)
        blood_vis = profile.blood_visibility
        if blood_vis > 0.01:
            alpha = int(min(150, blood_vis * 200))
            border_thickness = int(w * 0.15 * blood_vis)
            pygame.draw.rect(overlay, (180, 0, 0, alpha), (0, 0, w, border_thickness)) # Верх
            pygame.draw.rect(overlay, (180, 0, 0, alpha), (0, h - border_thickness, w, border_thickness)) # Низ
            pygame.draw.rect(overlay, (180, 0, 0, alpha), (0, 0, border_thickness, h)) # Лево
            pygame.draw.rect(overlay, (180, 0, 0, alpha), (w - border_thickness, 0, border_thickness, h)) # Право

        # 2. Туннельное зрение / Помутнение (с инерцией из ManifestationProfile)
        tunnel_factor = profile.attention_tunneling
        if tunnel_factor > 0.01: # Порог проявления (гистерезис)
            alpha = int(min(200, tunnel_factor * 220))
            vignette_thickness = int(w * 0.25 * tunnel_factor)
            pygame.draw.rect(overlay, (0, 0, 0, alpha), (0, 0, w, vignette_thickness)) # Верх
            pygame.draw.rect(overlay, (0, 0, 0, alpha), (0, h - vignette_thickness, w, vignette_thickness)) # Низ
            pygame.draw.rect(overlay, (0, 0, 0, alpha), (0, 0, vignette_thickness, h)) # Лево
            pygame.draw.rect(overlay, (0, 0, 0, alpha), (w - vignette_thickness, 0, vignette_thickness, h)) # Право

        # 3. Визуальная нестабильность (тремор экрана) — новый слой оптики
        if profile.visual_instability > 0.05:
            shake_x = int(random.gauss(0, profile.visual_instability * 3))
            shake_y = int(random.gauss(0, profile.visual_instability * 3))
            self.screen.scroll(shake_x, shake_y)

        # ADR-037: Contrast Instability — пульсация контраста (мир "дышит")
        if profile.contrast_instability > 0.05:
            alpha = int(random.gauss(0, profile.contrast_instability * 50))
            alpha = max(0, min(120, alpha)) # Ограничиваем, чтобы не засветить/затемнить полностью
            contrast_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            # Легкая сине-серая пульсация (холодок диссоциации/энтропии)
            contrast_overlay.fill((100, 100, 140, alpha))
            self.screen.blit(contrast_overlay, (0, 0))

        # Накладываем финальный оверлей
        if blood_vis > 0.01 or tunnel_factor > 0.01:
            self.screen.blit(overlay, (0, 0))

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

    def _draw_obstacles(
        self,
        obstacles: List[dict],
        cam_x: float,
        cam_y: float,
    ) -> None:
        """Отрисовывает мебель и препятствия из spatial_obstacles (Приоритет: фикс спрайтов объектов)"""
        for obj in obstacles:
            ox = obj.get("x", 0)
            oy = obj.get("y", 0)
            size = obj.get("size") or {}
            ow = size.get("w", obj.get("w", 1))
            oh = size.get("h", obj.get("h", 1))

            sx, sy = self._w2s(ox - ow / 2, oy - oh / 2, cam_x, cam_y)
            sw, sh = int(ow * SCALE), int(oh * SCALE)

            obj_type = obj.get("type", "")
            sprite = get_entity_sprite(obj_type)

            if sprite and sw > 0 and sh > 0:
                scaled = pygame.transform.scale(sprite, (sw, sh))
                self.screen.blit(scaled, (sx, sy))
            else:
                pygame.draw.rect(self.screen, _COLORS["obstacle_visible"], (sx, sy, sw, sh), border_radius=3)

    def _draw_npcs(
        self,
        entities: List[PerceivedEntity],
        cam_x: float,
        cam_y: float,
        focus_id: Optional[str],
        player_xy: Tuple[float, float],
        profile: ManifestationProfile = ManifestationProfile(), # ADR-037
        dt: float = 0.016, # Спринт 30: дельта времени для непрерывной кинематики
    ) -> None:
        # ADR-037: Temporal Assembly Delay — инерция сборки реальности
        delay_factor = profile.temporal_assembly_delay
        
        for entity in entities:
            if entity.entity_type != "npc":
                continue
            if not entity.visible:
                continue

            prev_x, prev_y = self._prev_npc_positions.get(entity.entity_id, (entity.x, entity.y))
            
            # Спринт 30: Непрерывная презентация. Фронтенд "разархивирует" время через скорость TraversalState
            if entity.traversal_status in ("PENDING", "MOVING") and entity.traversal_speed > 0:
                dx, dy = entity.x - prev_x, entity.y - prev_y
                dist = (dx**2 + dy**2)**0.5
                step = entity.traversal_speed * dt
                
                if dist <= step or dist < 0.01:
                    # Цель достигнута за этот кадр
                    render_x, render_y = entity.x, entity.y
                else:
                    # Двигаемся к целевой точке пропорционально скорости и dt
                    ratio = step / dist
                    render_x, render_y = prev_x + dx * ratio, prev_y + dy * ratio
            else:
                # Каузальная истина: без транзита позиция мгновенна (snap)
                render_x, render_y = entity.x, entity.y

            sx, sy = self._w2s(render_x, render_y, cam_x, cam_y)

            is_focused = entity.entity_id == focus_id

            # Резолв спрайта: приоритет по entity_id, fallback на тип "person" для всех NPC
            sprite = get_entity_sprite(entity.entity_id) or get_entity_sprite("person")
            radius = 10 if is_focused else 7
            npc_size = radius * 2

            if sprite:
                scaled = pygame.transform.scale(sprite, (npc_size, npc_size))
                self.screen.blit(scaled, (sx - npc_size // 2, sy - npc_size // 2))
                if is_focused:
                    pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), npc_size // 2 + 2, 2)
            else:
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

            # Визуальный индикатор внимания NPC (Приоритет 1)
            is_looking_at_player = is_focused or any(inf.type == "communication" for inf in entity.inferences)
            if is_looking_at_player:
                player_sx, player_sy = self._w2s(player_xy[0], player_xy[1], cam_x, cam_y)
                gaze_dx = player_sx - sx
                gaze_dy = player_sy - sy
                gaze_dist = math.hypot(gaze_dx, gaze_dy)
                if gaze_dist > 0:
                    ndx = gaze_dx / gaze_dist
                    ndy = gaze_dy / gaze_dist
                    start_x = sx + ndx * radius
                    start_y = sy + ndy * radius
                    end_x = sx + ndx * (radius + 10)
                    end_y = sy + ndy * (radius + 10)
                    pygame.draw.line(self.screen, (255, 255, 100), (start_x, start_y), (end_x, end_y), 2)

            # Спринт 30: Сохраняем визуальную позицию (после интерполяции), а не сырую позицию тика,
            # чтобы на следующем кадре непрерывное движение продолжилось, а не началось с начала
            self._prev_npc_positions[entity.entity_id] = (render_x, render_y)

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

    def _draw_player(self, xy: Tuple[float, float], cam_x: float, cam_y: float, facing: float) -> None:
        import math
        sx, sy = self._w2s(xy[0], xy[1], cam_x, cam_y)
        # Форма стрелки: базовая ориентация — ВПРАВО (angle = 0)
        base_points = [
            (12, 0),   # Наконечник
            (-6, -8),  # Левое крыло
            (-6, 8),   # Правое крыло
        ]
        cos_a = math.cos(facing)
        sin_a = math.sin(facing)
        # Поворот точек вокруг (0,0) и смещение к позиции на экране (sx, sy)
        points = [
            (bx * cos_a - by * sin_a + sx, bx * sin_a + by * cos_a + sy)
            for bx, by in base_points
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
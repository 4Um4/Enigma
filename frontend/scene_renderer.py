"""
path: /frontend/scene_renderer.py

Рендер карты — переводит PerceivedScene в пиксели.
Координаты в метрах, SCALE = пикселей на метр.
Рисует только воспринимаемое (visible entities, audio как текст).

Назначение: Отрисовывает PerceivedScene на pygame.Surface — только то, что персонаж воспринимает
Зависимости: pygame, player_cognition.types
Основные сущности: SceneRenderer
"""

import logging

logger = logging.getLogger(__name__)
import math  # noqa: E402
import random  # noqa: E402
from typing import Dict, List, Optional, Tuple  # noqa: E402

import pygame  # noqa: E402
from constants import (
    AGGRESSION_COLORS,
    COLOR_MANIFEST_DEFAULT,
    COLOR_TEXT_DIM,
    FONT_NAME_MAIN,
    FONT_NAME_UI,
    FONT_SIZE_AUDIO,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
    FONT_SIZE_TOOLTIP,
)
from constants import (  # noqa: E402
    RENDER_COLORS as _COLORS,
)
from constants import (
    SCALE_PIXELS_PER_METER as SCALE,
)
from game_types import (  # noqa: E402
    PerceivedEntity,
    PerceivedScene,
)
import json
from pathlib import Path
from map_editor.sprite_registry import get_entity_sprite, sprite_registry  # noqa: E402

# S176: Путь к файлам кампаний для загрузки кастомных спрайтов
_CAMPAIGN_DIR = Path(__file__).parent / "map_editor" / "campaigns"
from perceptual_momentum import ManifestationProfile, PerceptualMomentum  # noqa: E402
from presentation_firewall import sanitize_perceptual_input  # noqa: E402


class SceneRenderer:
    """Отрисовывает PerceivedScene на Surface с камерой, центрированной на игроке"""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self._prev_npc_positions: Dict[
            str, Tuple[float, float, float]
        ] = {}  # ADR-037: Для Temporal Assembly Delay (x, y, z)
        self._hover_npc_id: Optional[str] = None  # The Fool v2: Для тултипов наблюдений
        
        # S176: Кэш кастомных спрайтов из JSON карт (id -> [sheet, x, y, w, h])
        self._custom_sprites = {}
        if _CAMPAIGN_DIR.exists():
            for camp_dir in _CAMPAIGN_DIR.iterdir():
                loc_dir = camp_dir / "locations"
                if loc_dir.exists():
                    for json_file in loc_dir.glob("*.json"):
                        try:
                            with open(json_file, "r", encoding="utf-8-sig") as f:
                                data = json.load(f)
                            for npc in data.get("npcs", []):
                                if npc.get("sprite"):
                                    self._custom_sprites[npc["ref_id"]] = npc["sprite"]
                            for obj in data.get("objects", []):
                                if obj.get("sprite"):
                                    self._custom_sprites[obj["id"]] = obj["sprite"]
                        except Exception:
                            continue
        self.font_small = pygame.font.SysFont(FONT_NAME_MAIN, FONT_SIZE_SMALL)
        self.font_audio = pygame.font.SysFont(
            FONT_NAME_MAIN, FONT_SIZE_AUDIO, italic=True
        )
        self.font_body = pygame.font.SysFont(FONT_NAME_MAIN, FONT_SIZE_BODY)
        self.font_tooltip = pygame.font.SysFont(FONT_NAME_UI, FONT_SIZE_TOOLTIP)
        # Lerp для угла поворота (Приоритет 0)
        self._visual_facing_angle = -1.5708  # -pi/2 (смотрит вверх)
        # NEW-SPATIAL-003 FIX: Кэш для LERP сглаживания body_heading NPC
        self._prev_npc_headings: Dict[str, float] = {}
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
        avatar_state: Optional[dict] = None,  # ADR-035: Феноменологическая проекция
        ambient_state: Optional[dict] = None,  # ADR-037: Средовое давление
        speech_bubbles: Optional[dict] = None,  # ADR-SPEECH: Облачка над NPC
        player_speech: Optional[dict] = None,  # ADR-SPEECH: Облачко над игроком
        mood_indicators: Optional[
            dict
        ] = None,  # ADR-MANIFEST: Наблюдаемые физические проявления
        floor_rects: Optional[
            List[tuple]
        ] = None,  # S80.3b: Multi-chunk floors [(ox,oy,w,h), ...]
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
            # ADR-084: Визуальный след убран из консоли (60 фпс спам). Диагностика через CDS.
            # if profile.blood_visibility > 0.01 or profile.attention_tunneling > 0.01:
            #     logger.debug(f"[RENDER_TRACE] blood={profile.blood_visibility:.2f}, tunnel={profile.attention_tunneling:.2f}, noise={profile.visual_instability:.2f}")

        # Камера центрирована на игроке + Motion Bias (мир "давит" на игрока)
        cam_x = player_xy[0] * SCALE - self.screen.get_width() // 2
        cam_y = player_xy[1] * SCALE - self.screen.get_height() // 2

        # ADR-037: Motion Bias — снос камеры давлением среды
        cam_x -= int(profile.motion_bias[0] * SCALE * 2)
        cam_y -= int(profile.motion_bias[1] * SCALE * 2)

        # 1. Пол — все видимые чанки (S80.3b: бесшовный мир)
        if floor_rects:
            self._draw_floors(floor_rects, cam_x, cam_y)
        else:
            self._draw_floor(scene_w, scene_h, cam_x, cam_y)

        # 2. Стены — геометрия комнаты (видны всегда, но ярче если в LOS)
        self._draw_walls(walls, cam_x, cam_y, scene)

        # 3. Препятствия/объекты — только воспринимаемые
        self._draw_entities(scene.entities, cam_x, cam_y)
        self._draw_obstacles(obstacles, cam_x, cam_y)

        # 4. NPC — только воспринимаемые (с Temporal Delay)
        _npc_coords = self._draw_npcs(
            scene.entities,
            cam_x,
            cam_y,
            scene.attention_focus_id,
            player_xy,
            profile,
            dt=dt,
        )

        # 5. Игрок — всегда виден
        # Lerp сглаживание поворота (Приоритет 0)
        import math  # noqa: E402

        diff = player_facing - self._visual_facing_angle
        diff = (diff + math.pi) % (2 * math.pi) - math.pi
        self._visual_facing_angle += diff * min(1.0, 10.0 * dt)

        _player_coords = self._draw_player(
            player_xy,
            cam_x,
            cam_y,
            self._visual_facing_angle,
        )

        # 6. HUD поверх карты — audio events, body state, environment
        self._draw_hud(scene)

        # 7. Embodied Perception Interface — искажение рендера от состояния аватара и среды (ADR-035, ADR-037)
        if avatar_state:
            self._apply_avatar_perception_overlay(profile)

        return {"npcs": _npc_coords, "player": _player_coords}

    def _apply_avatar_perception_overlay(self, profile: "ManifestationProfile") -> None:
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
            pygame.draw.rect(
                overlay, (180, 0, 0, alpha), (0, 0, w, border_thickness)
            )  # Верх
            pygame.draw.rect(
                overlay,
                (180, 0, 0, alpha),
                (0, h - border_thickness, w, border_thickness),
            )  # Низ
            pygame.draw.rect(
                overlay, (180, 0, 0, alpha), (0, 0, border_thickness, h)
            )  # Лево
            pygame.draw.rect(
                overlay,
                (180, 0, 0, alpha),
                (w - border_thickness, 0, border_thickness, h),
            )  # Право

        # 2. Туннельное зрение / Помутнение (с инерцией из ManifestationProfile)
        tunnel_factor = profile.attention_tunneling
        if tunnel_factor > 0.01:  # Порог проявления (гистерезис)
            alpha = int(min(200, tunnel_factor * 220))
            vignette_thickness = int(w * 0.25 * tunnel_factor)
            pygame.draw.rect(
                overlay, (0, 0, 0, alpha), (0, 0, w, vignette_thickness)
            )  # Верх
            pygame.draw.rect(
                overlay,
                (0, 0, 0, alpha),
                (0, h - vignette_thickness, w, vignette_thickness),
            )  # Низ
            pygame.draw.rect(
                overlay, (0, 0, 0, alpha), (0, 0, vignette_thickness, h)
            )  # Лево
            pygame.draw.rect(
                overlay,
                (0, 0, 0, alpha),
                (w - vignette_thickness, 0, vignette_thickness, h),
            )  # Право

        # 3. Визуальная нестабильность (тремор экрана) — новый слой оптики
        if profile.visual_instability > 0.05:
            shake_x = int(random.gauss(0, profile.visual_instability * 3))
            shake_y = int(random.gauss(0, profile.visual_instability * 3))
            self.screen.scroll(shake_x, shake_y)

        # ADR-037: Contrast Instability — пульсация контраста (мир "дышит")
        if profile.contrast_instability > 0.05:
            alpha = int(random.gauss(0, profile.contrast_instability * 50))
            alpha = max(
                0, min(120, alpha)
            )  # Ограничиваем, чтобы не засветить/затемнить полностью
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
        """Single-chunk floor (legacy compatibility)."""
        sx, sy = self._w2s(0, 0, cam_x, cam_y)
        sw, sh = int(w * SCALE), int(h * SCALE)
        pygame.draw.rect(self.screen, _COLORS["floor_dim"], (sx, sy, sw, sh))

    def _draw_floors(self, floor_rects: list, cam_x: float, cam_y: float) -> None:
        """Multi-chunk floors (S80.3b). Рисует пол для каждого видимого чанка."""
        for rect in floor_rects:
            ox, oy, w, h = rect[0], rect[1], rect[2], rect[3]
            sx, sy = self._w2s(ox, oy, cam_x, cam_y)
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
        _visible_obstacle_ids = {
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
        # S81-ФИКС: Объекты рендерятся ТОЛЬКО через _draw_obstacles (top-left координаты).
        # _draw_entities использовал center-based offset (ox - ow/2), что давало
        # двойной рендер + смещение + растягивание объектов.
        # Подписи и attention-выделение перенесены в _draw_obstacles.
        pass

    # S81: Типы объектов, которые проходимы (не блокируют движение)
    _PASSABLE_TYPES = {"door", "door_transition", "transition", "window"}

    def _draw_obstacles(
        self,
        obstacles: List[dict],
        cam_x: float,
        cam_y: float,
    ) -> None:
        """Отрисовывает мебель и препятствия из spatial_obstacles (top-left координаты).
        Проходимые объекты (двери) рисуются полупрозрачными."""
        for obj in obstacles:
            # Бэкенд отдаёт x, y как левый верхний угол (scene_state_manager:560)
            ox = obj.get("x", 0)
            oy = obj.get("y", 0)
            ow = obj.get("w", 1)
            oh = obj.get("h", 1)

            sx, sy = self._w2s(ox, oy, cam_x, cam_y)
            sw, sh = int(ow * SCALE), int(oh * SCALE)

            obj_type = obj.get("type", "")
            # Data-driven: passability.walk приоритетнее type-хардкода
            is_passable = (
                obj.get("passability", {}).get("walk", False)
                or obj_type in self._PASSABLE_TYPES
            )

            # S176 FIX: Приоритет кастомного спрайта из кэша (id объекта)
            sprite_info = self._custom_sprites.get(obj.get("id"))
            sprite = None
            if sprite_info:
                if len(sprite_info) >= 5:
                    _t = int(sprite_info[5]) if len(sprite_info) > 5 else 220
                    _o = int(sprite_info[6]) if len(sprite_info) > 6 else 1
                    sprite = sprite_registry.get_rect(
                        sprite_info[0], int(sprite_info[1]), int(sprite_info[2]), 
                        int(sprite_info[3]), int(sprite_info[4]), _t, _o
                    )
                elif len(sprite_info) >= 3:
                    sprite = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])
            
            if not sprite:
                sprite = get_entity_sprite(obj_type)

            if sprite and sw > 0 and sh > 0:
                scaled = pygame.transform.scale(sprite, (sw, sh))
                if is_passable:
                    # Полупрозрачный рендер для проходимых объектов
                    scaled.set_alpha(160)
                self.screen.blit(scaled, (sx, sy))
            else:
                if is_passable:
                    # Проходимые объекты — пунктирная рамка
                    color = AGGRESSION_COLORS["peaceful_interaction"]
                    pygame.draw.rect(
                        self.screen, color, (sx, sy, sw, sh), 1, border_radius=3
                    )
                else:
                    pygame.draw.rect(
                        self.screen,
                        _COLORS["obstacle_visible"],
                        (sx, sy, sw, sh),
                        border_radius=3,
                    )

    def _draw_npcs(
        self,
        entities: List[PerceivedEntity],
        cam_x: float,
        cam_y: float,
        focus_id: Optional[str],
        player_xy: Tuple[float, float],
        profile: ManifestationProfile = ManifestationProfile(),  # ADR-037
        dt: float = 0.016,
    ) -> dict:
        _npc_coords = {}

        for entity in entities:
            if entity.entity_type != "npc":
                continue
            if not entity.visible:
                continue

            prev_x, prev_y, prev_z = self._prev_npc_positions.get(
                entity.entity_id, (entity.x, entity.y, entity.z)
            )

            # ADR-ETKE-RENDER: Два режима интерполяции
            # 1. Macro (TraversalState): PENDING/MOVING с traversal_speed — старая логика
            # 2. Micro (ETKE-IK velocity): entity.velocity от _process_continuous_motion —
            #    предсказание позиции между idle_tick'ами (без этого DriveVector микродвижения
            #    невооружённым глазом не видны, т.к. SUBSTEP_DT крошечный)
            if (
                entity.traversal_status in ("PENDING", "MOVING")
                and entity.traversal_speed > 0
            ):
                # Macro: интерполяция к цели по скорости traversal'а
                dx, dy = entity.x - prev_x, entity.y - prev_y
                dist = (dx**2 + dy**2) ** 0.5
                step = entity.traversal_speed * dt
                if dist <= step or dist < 0.01:
                    render_x, render_y = entity.x, entity.y
                else:
                    ratio = step / dist
                    render_x, render_y = prev_x + dx * ratio, prev_y + dy * ratio
            elif entity.velocity is not None and (
                abs(entity.velocity[0]) > 0.01 or abs(entity.velocity[1]) > 0.01
            ):
                # Micro: ETKE-IK velocity-based prediction.
                # Backend пишет new position + velocity каждый idle_tick.
                # Frontend экстраполирует: pos_render = pos_backend + velocity * time_since_last_tick
                # Это даёт плавное движение между idle_tick'ами.
                _vx, _vy = entity.velocity
                render_x = entity.x + _vx * dt
                render_y = entity.y + _vy * dt
            else:
                # Режим 3: LERP к целевой позиции (унификация с игроком)
                _NPC_LERP_SPEED = 1.2  # Скорость ходьбы (м/сек)
                # Отключаем порог телепортации: бэкенд может менять позицию скачком,
                # но фронтенд всегда должен плавно интерполировать к ней.
                dx, dy = entity.x - prev_x, entity.y - prev_y
                dist = (dx**2 + dy**2) ** 0.5
                if dist > 0.01:
                    step = _NPC_LERP_SPEED * dt
                    if step >= dist:
                        render_x, render_y = entity.x, entity.y
                    else:
                        ratio = step / dist
                        render_x = prev_x + dx * ratio
                        render_y = prev_y + dy * ratio
                else:
                    render_x, render_y = entity.x, entity.y

            self._prev_npc_positions[entity.entity_id] = (render_x, render_y, entity.z)
            sx, ground_sy = self._w2s(render_x, render_y, cam_x, cam_y)

            # S133: Z-projection. Спрайт и облачко смещаются вверх, земля (ground_sy) остается.
            # Z не изменяет мировую XY-позицию. Z берётся как snapshot value до аудита Temporal Pose.
            z_offset = int(entity.z * SCALE)
            sy = ground_sy - z_offset

            # The Fool v2: Моторный рендер (тупой, без эмоций)
            if entity.is_frozen:
                # ADR-141: Окаменелость — лёгкий визуальный замедлитель (пока без tint)
                pass
            if entity.is_shaking:
                _amp = int(
                    entity.instability * 7
                )  # ADR-141: Радикальное усиление дрожи (было 6)
                sx += random.randint(-_amp, _amp)
                sy += random.randint(-_amp, _amp)

            # ADR-141: Stagger — пошатывание при боли/шоке (вертикальная просадка позы)
            if entity.instability > 0.5:
                sy += int(entity.instability * 4)  # Проседание корпуса вниз

            is_focused = entity.entity_id == focus_id

            # S176 FIX: Приоритет кастомного спрайта из кэша
            sprite_info = self._custom_sprites.get(entity.entity_id)
            sprite = None
            if sprite_info:
                if len(sprite_info) >= 5:
                    _t = int(sprite_info[5]) if len(sprite_info) > 5 else 220
                    _o = int(sprite_info[6]) if len(sprite_info) > 6 else 1
                    sprite = sprite_registry.get_rect(
                        sprite_info[0], int(sprite_info[1]), int(sprite_info[2]), 
                        int(sprite_info[3]), int(sprite_info[4]), _t, _o
                    )
                elif len(sprite_info) >= 3:
                    sprite = sprite_registry.get(sprite_info[0], sprite_info[1], sprite_info[2])
            
            if not sprite:
                sprite = get_entity_sprite(entity.entity_id) or get_entity_sprite("person")
            
            # S176 FIX: Базовый размер NPC уменьшен на 20% для баланса
            npc_size = 90 if is_focused else 76
            radius = npc_size // 2

            # NEW-SPATIAL-003 FIX: LERP сглаживание для body_heading (убирает дёрганье спрайтов)
            _target_heading = getattr(entity, "body_heading", 1.5708)
            _prev_heading = self._prev_npc_headings.get(entity.entity_id, _target_heading)
            _diff = (_target_heading - _prev_heading + math.pi) % (2 * math.pi) - math.pi
            _heading = _prev_heading + _diff * 0.15
            self._prev_npc_headings[entity.entity_id] = _heading

            # S168: Pose Tense - визуализация напряжения тела
            _pose_tense = getattr(entity, "pose_tense", 0.0)
            
            if sprite:
                # S176 FIX: Сохраняем пропорции NPC
                sw, sh = sprite.get_size()
                ratio = min(npc_size / sw, npc_size / sh)
                nw, nh = int(sw * ratio), int(sh * ratio)
                scaled = pygame.transform.smoothscale(sprite, (nw, nh))
                # NEW-ORIENT-002 FIX: Вращаем спрайт по body_heading (Y инвертирован в pygame)
                _angle_deg = -math.degrees(_heading)
                rotated = pygame.transform.rotate(scaled, _angle_deg)
                _rect = rotated.get_rect(center=(sx, sy))
                self.screen.blit(rotated, _rect)
                
                if is_focused:
                    pygame.draw.circle(
                        self.screen, (255, 255, 255), (sx, sy), npc_size // 2 + 2, 2
                    )  # Белый контур фокуса
                elif _pose_tense > 0.5:
                    # Красный жёсткий контур при напряжении
                    pygame.draw.circle(
                        self.screen, (200, 50, 50), (sx, sy), npc_size // 2 + 2, 2
                    )
            else:
                # S168: Цвет треугольника меняется на красный при напряжении
                if _pose_tense > 0.5:
                    color = (200, 50, 50)
                else:
                    color = _COLORS["npc_focused"] if is_focused else _COLORS["npc_body"]
                # NEW-ORIENT-002 FIX: Рисуем треугольник вместо круга, чтобы была видна ориентация
                # _heading уже вычислен и сглажен выше (NEW-SPATIAL-003 FIX)
                _tip = (sx + 12 * math.cos(_heading), sy + 12 * math.sin(_heading))
                _left = (sx + 8 * math.cos(_heading + 2.5), sy + 8 * math.sin(_heading + 2.5))
                _right = (sx + 8 * math.cos(_heading - 2.5), sy + 8 * math.sin(_heading - 2.5))
                pygame.draw.polygon(self.screen, color, [_tip, _left, _right])
                if is_focused:
                    pygame.draw.circle(
                        self.screen, (255, 255, 255), (sx, sy), radius, 2
                    )  # Белый контур периферии

            # Имя по confidence
            if entity.display_name:
                _blur = getattr(entity, "blur_intensity", 0.0)
                # S169: Эффект "незнакомца" - серое полупрозрачное имя
                if _blur > 0.4:
                    name_color = (150, 150, 150)
                    label = self.font_small.render(entity.display_name, True, name_color)
                    label.set_alpha(150)
                else:
                    name_color = (255, 255, 255) if is_focused else COLOR_TEXT_DIM
                    label = self.font_small.render(entity.display_name, True, name_color)
                    
                self.screen.blit(label, (sx - label.get_width() // 2, sy - radius - 16))

            _npc_coords[entity.entity_id] = {"sx": sx, "sy": sy, "radius": radius}

            # Inference badges — маленькие индикаторы
            self._draw_inference_badges(entity, sx, sy + radius + 4)

            # BUG-S120.3: Текст проявлений рисуется выше (ADR-MANIFEST), квадраты убраны
            # BUG-P1-01: Рисуем конус взгляда (сектор) по body_heading
            if hasattr(entity, "body_heading"):
                _gaze_avoidance = getattr(entity, "gaze_avoidance", 0.0)
                
                # S168: Gaze Avoidance - конус взгляда отворачивается от игрока
                if _gaze_avoidance > 0.5:
                    _angle_to_player = math.atan2(player_xy[1] - entity.y, player_xy[0] - entity.x)
                    _heading = _angle_to_player + math.pi  # Смотрим строго в противоположную сторону
                    gaze_color = (150, 150, 150, 60)  # Серый отворот
                else:
                    _heading = entity.body_heading
                    gaze_color = (255, 255, 80, 60)  # Полупрозрачный жёлтый

                gaze_surface = pygame.Surface((100, 100), pygame.SRCALPHA)
                _cone_radius = 40
                _cone_width = math.pi / 4  # 45 градусов
                _points = [(50, 50)]  # центр
                _start_a = _heading - _cone_width / 2
                _step = _cone_width / 10
                for i in range(11):
                    _a = _start_a + i * _step
                    _points.append(
                        (
                            50 + math.cos(_a) * _cone_radius,
                            50 + math.sin(_a) * _cone_radius,
                        )
                    )
                pygame.draw.polygon(gaze_surface, gaze_color, _points)
                self.screen.blit(gaze_surface, (sx - 50, sy - 50))

            # Спринт 30: Сохраняем визуальную позицию (после интерполяции), а не сырую позицию тика,
            # чтобы на следующем кадре непрерывное движение продолжилось, а не началось с начала
            # S134.3: Сохраняем Z (0.0 для игрока/объектов без Z), чтобы избежать ValueError.
            _ent_z = getattr(entity, 'z', 0.0)
            self._prev_npc_positions[entity.entity_id] = (render_x, render_y, _ent_z)

            # Отслеживание наведения мыши (для тултипов) — используем экранные координаты
            _mouse_x, _mouse_y = pygame.mouse.get_pos()
            if abs(_mouse_x - sx) < 25 and abs(_mouse_y - sy) < 25:
                self._hover_npc_id = entity.entity_id

            # Рисуем тултип наблюдения при наведении (hover_text уже на русском из API)
            if self._hover_npc_id == entity.entity_id and entity.perception_cues:
                for _cue in entity.perception_cues:
                    _txt = _cue.get("hover_text") or _cue.get("cue_key", "...")
                    _font = self.font_tooltip
                    _surf = _font.render(
                        _txt, True, (255, 255, 230)
                    )  # Тёплый белый для тултипов
                    self.screen.blit(_surf, (sx - _surf.get_width() // 2, sy - 30))
                    break  # Показываем только первый (самый важный) cue

        return _npc_coords

    def _draw_mood_icons(self, tags: list, sx: int, sy: int) -> None:
        """Рисует иконки наблюдаемых физических проявлений (ADR-MANIFEST).
        tags: список строк вида 'manifest:tense', 'manifest:rigid' и т.д.
        """
        # Смещение по X, чтобы иконки не накладывались на inference_badges
        # inference_badges рисуются от sx с шагом 8.
        # Допустим, максимум 5 бейджей. Тогда стартовая X для иконок = sx + 40.
        _x_offset = 40
        
        _icon_map = {
            "manifest:tense": self._draw_tense_icon,
            "manifest:rigid": self._draw_rigid_icon,
            "manifest:unstable": self._draw_unstable_icon,
            "manifest:restless": self._draw_restless_icon,
            "manifest:suffering": self._draw_suffering_icon,
            "manifest:alert": self._draw_alert_icon,
        }
        
        for tag in tags:
            # Нормализуем тег: 'MANIFEST_TENSE' -> 'manifest:tense'
            _norm_tag = f"manifest:{tag.replace('MANIFEST_', '').lower()}" if tag.startswith("MANIFEST_") else tag
            draw_fn = _icon_map.get(_norm_tag)
            if draw_fn:
                draw_fn(sx + _x_offset, sy)
                _x_offset += 12  # Шаг между иконками

    def _draw_tense_icon(self, x: int, y: int) -> None:
        """Напряжение: маленький квадрат."""
        pygame.draw.rect(self.screen, (180, 180, 130), (x, y, 6, 6))

    def _draw_rigid_icon(self, x: int, y: int) -> None:
        """Окаменелость: прямоугольник."""
        pygame.draw.rect(self.screen, (140, 155, 185), (x, y, 4, 8))

    def _draw_unstable_icon(self, x: int, y: int) -> None:
        """Дрожь: зигзаг."""
        points = [(x, y+4), (x+2, y), (x+4, y+8), (x+6, y+2)]
        pygame.draw.lines(self.screen, (160, 150, 140), False, points, 1)

    def _draw_restless_icon(self, x: int, y: int) -> None:
        """Суета: два кружка."""
        pygame.draw.circle(self.screen, (185, 160, 120), (x, y), 2)
        pygame.draw.circle(self.screen, (185, 160, 120), (x+4, y+4), 2)

    def _draw_suffering_icon(self, x: int, y: int) -> None:
        """Страдание: крестик."""
        pygame.draw.line(self.screen, (130, 110, 100), (x, y), (x+6, y+6), 1)
        pygame.draw.line(self.screen, (130, 110, 100), (x+6, y), (x, y+6), 1)

    def _draw_alert_icon(self, x: int, y: int) -> None:
        """Внимание: треугольник."""
        points = [(x+3, y), (x, y+6), (x+6, y+6)]
        pygame.draw.polygon(self.screen, (200, 200, 160), points)

    def _draw_inference_badges(self, entity: PerceivedEntity, sx: int, sy: int) -> None:
        """Рисует маленькие цветные точки для поведенческих выводов"""
        badge_map = {
            "combat": AGGRESSION_COLORS["combat"],
            "armed": AGGRESSION_COLORS["armed"],
            "active_aggression": AGGRESSION_COLORS["active_aggression"],
            "potential_aggression": AGGRESSION_COLORS["potential_aggression"],
            "potentially_hostile": AGGRESSION_COLORS["potentially_hostile"],
            "communication": AGGRESSION_COLORS["communication"],
            "peaceful_interaction": AGGRESSION_COLORS["peaceful_interaction"],
            "friendly_action": AGGRESSION_COLORS["friendly_action"],
        }

        x_offset = 0
        for inf in entity.inferences:
            color = badge_map.get(inf.inference_type)
            if color and inf.confidence > 0.4:
                pygame.draw.circle(self.screen, color, (sx + x_offset, sy), 3)
                x_offset += 8

    def _draw_player(
        self,
        xy: Tuple[float, float],
        cam_x: float,
        cam_y: float,
        facing: float,
    ) -> dict:
        import math  # noqa: E402

        sx, sy = self._w2s(xy[0], xy[1], cam_x, cam_y)
        # Форма стрелки: увеличена для читаемости взгляда поверх PNG текстур
        base_points = [
            (16, 0),  # Наконечник
            (-8, -11),  # Левое крыло
            (-8, 11),  # Правое крыло
        ]
        cos_a = math.cos(facing)
        sin_a = math.sin(facing)
        # Поворот точек вокруг (0,0) и смещение к позиции на экране (sx, sy)
        points = [
            (bx * cos_a - by * sin_a + sx, bx * sin_a + by * cos_a + sy)
            for bx, by in base_points
        ]
        # Яркий контур 3px для видимости поверх любых текстур
        pygame.draw.polygon(self.screen, _COLORS["player_body"], points)
        pygame.draw.polygon(
            self.screen, (200, 230, 255), points, 3
        )  # Светло-голубой контур зоны

        return {"sx": sx, "sy": sy, "radius": 16}

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
        sh = self.screen.get_height()
        y = sh - 10 - len(scene.player_body_state) * 18 - 20
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
            self.screen.blit(surf, (sw - surf.get_width() - 10, sh - 24))

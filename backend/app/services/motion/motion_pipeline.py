# -*- coding: utf-8 -*-
"""
path: backend/app/services/motion/motion_pipeline.py
Назначение: L2/L3 компоненты ETKE-IK. SteeringResolver (вычисление скорости) и MotionIntegrator (интеграция позиции).
Зависимости: motion_core, typing
Основные сущности: SteeringResolver, MotionIntegrator
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Tuple

from app.core.constants import ETKE_IK_SUBSTEP_DT
from app.domain.motion_core import AffordanceVector, BodySchema, DriveVector

if TYPE_CHECKING:
    from app.services.spatial.world_topology_provider import WorldTopologyProvider


class CollisionAvoidance:
    """ETKE-IK 2.1: Реактивный слой коррекции направления.

    Работает ДО SteeringResolver. Проверяет геометрию (Affordance) и других NPC по курсу движения.
    Если впереди стена (can_pass < 0.1) или NPC — пытается сместиться влево или вправо.

    TODO (S92+): Заменить brute-force O(N²) на Spatial Hash / KD-Tree при достижении 100+ NPC.
    """

    LOOK_AHEAD = 1.5  # Дистанция проверки (в координатах)
    NPC_RADIUS = 0.8  # Радиус избегания других NPC

    @staticmethod
    def apply(
        drive: DriveVector,
        pos: Tuple[float, float],
        topology: "WorldTopologyProvider",
        region: str,
        npc_positions: Optional[Dict[str, dict]] = None,
        current_npc_id: Optional[str] = None,
    ) -> DriveVector:
        if drive.intensity <= 0.0:
            return drive

        # Точка перед нами
        future_pos = (
            pos[0] + drive.direction[0] * CollisionAvoidance.LOOK_AHEAD,
            pos[1] + drive.direction[1] * CollisionAvoidance.LOOK_AHEAD,
        )

        # S91: Проверка геометрии (стены)
        aff = topology.query_affordance_field(region, future_pos)
        if aff.can_pass < 0.5:
            return CollisionAvoidance._try_sides(
                drive, pos, topology, region, npc_positions, current_npc_id
            )

        # S91: Проверка других NPC (с учётом их скорости)
        if npc_positions:
            for npc_id, npc_pos_data in npc_positions.items():
                if npc_id == current_npc_id:
                    continue
                other_pos = npc_pos_data.get("local_position", {})
                if not other_pos:
                    continue
                ox, oy = other_pos.get("x", 0.0), other_pos.get("y", 0.0)

                # S91: Предсказываем позицию другого NPC (Velocity Awareness)
                other_vel = npc_pos_data.get("velocity", (0.0, 0.0))
                other_future_x = ox + other_vel[0] * ETKE_IK_SUBSTEP_DT
                other_future_y = oy + other_vel[1] * ETKE_IK_SUBSTEP_DT

                dist = math.hypot(
                    future_pos[0] - other_future_x, future_pos[1] - other_future_y
                )
                if dist < CollisionAvoidance.NPC_RADIUS:
                    return CollisionAvoidance._try_sides(
                        drive, pos, topology, region, npc_positions, current_npc_id
                    )

        return drive  # Путь свободен

    @staticmethod
    def _try_sides(
        drive: DriveVector,
        pos: Tuple[float, float],
        topology: "WorldTopologyProvider",
        region: str,
        npc_positions: Optional[Dict[str, dict]] = None,
        current_npc_id: Optional[str] = None,
    ) -> DriveVector:
        """Проверяет левый и правый векторы для уклонения."""
        # Проверяем левый вектор (перпендикуляр)
        left_dir = (-drive.direction[1], drive.direction[0])
        left_pos = (
            pos[0] + left_dir[0] * CollisionAvoidance.LOOK_AHEAD,
            pos[1] + left_dir[1] * CollisionAvoidance.LOOK_AHEAD,
        )
        if topology.query_affordance_field(region, left_pos).can_pass >= 0.5:
            if not CollisionAvoidance._check_npc_collision(
                left_pos, npc_positions, current_npc_id
            ):
                return DriveVector(left_dir, drive.intensity * 0.8, drive.primitive)

        # Проверяем правый вектор
        right_dir = (drive.direction[1], -drive.direction[0])
        right_pos = (
            pos[0] + right_dir[0] * CollisionAvoidance.LOOK_AHEAD,
            pos[1] + right_dir[1] * CollisionAvoidance.LOOK_AHEAD,
        )
        if topology.query_affordance_field(region, right_pos).can_pass >= 0.5:
            if not CollisionAvoidance._check_npc_collision(
                right_pos, npc_positions, current_npc_id
            ):
                return DriveVector(right_dir, drive.intensity * 0.8, drive.primitive)

        # Тупик — останавливаемся
        return DriveVector((0.0, 0.0), 0.0, drive.primitive)

    @staticmethod
    def _check_npc_collision(
        check_pos: Tuple[float, float],
        npc_positions: Optional[Dict[str, dict]] = None,
        current_npc_id: Optional[str] = None,
    ) -> bool:
        """S91: Проверяет, есть ли NPC в указанной точке (с учётом скорости)."""
        if not npc_positions:
            return False
        for npc_id, npc_pos_data in npc_positions.items():
            if npc_id == current_npc_id:
                continue
            other_pos = npc_pos_data.get("local_position", {})
            if not other_pos:
                continue
            ox, oy = other_pos.get("x", 0.0), other_pos.get("y", 0.0)

            # S91: Предсказываем позицию другого NPC
            other_vel = npc_pos_data.get("velocity", (0.0, 0.0))
            other_future_x = ox + other_vel[0] * ETKE_IK_SUBSTEP_DT
            other_future_y = oy + other_vel[1] * ETKE_IK_SUBSTEP_DT

            dist = math.hypot(
                check_pos[0] - other_future_x, check_pos[1] - other_future_y
            )
            if dist < CollisionAvoidance.NPC_RADIUS:
                return True
        return False


class SteeringResolver:
    """ETKE-IK 2.1: Вычисляет вектор скорости на основе давления (DriveVector) и среды.

    Формула (упрощенная):
    desired_velocity = normalize(direction) * max_velocity * intensity
    actual_velocity = lerp(current_velocity, desired_velocity, acceleration * dt)

    Учитывает grip (сцепление) и drag (сопротивление среды).
    """

    @staticmethod
    def resolve(
        drive: DriveVector,
        body: BodySchema,
        affordance: AffordanceVector,
        current_velocity: Tuple[float, float],
        dt: float = ETKE_IK_SUBSTEP_DT,  # ADR-O-302: Numeric substep
    ) -> Tuple[float, float]:
        """Вычисляет новую скорость (vx, vy).

        Args:
            drive: Вектор желания (direction, intensity).
            body: Кинематика тела (max_velocity, acceleration).
            affordance: Свойства среды (surface_grip, drag_coefficient).
            current_velocity: Текущая скорость (vx, vy).
            dt: Шаг времени (секунды).

        Returns:
            Новая скорость (vx, vy).
        """
        if drive.intensity <= 0.0 or (
            drive.direction[0] == 0.0 and drive.direction[1] == 0.0
        ):
            # Нет давления — тормозим
            return (0.0, 0.0)

        # 1. Желаемая скорость
        mag = math.hypot(drive.direction[0], drive.direction[1])
        if mag == 0:
            norm_dir = (0.0, 0.0)
        else:
            norm_dir = (drive.direction[0] / mag, drive.direction[1] / mag)

        desired_vx = norm_dir[0] * body.max_velocity * drive.intensity
        desired_vy = norm_dir[1] * body.max_velocity * drive.intensity

        # 2. Влияние среды (Grip & Drag)
        # Чем меньше grip, тем дольше тело разгоняется
        effective_acc = body.acceleration * affordance.surface_grip
        # Drag уменьшает максимальную скорость
        effective_max_v = body.max_velocity * (1.0 - affordance.drag_coefficient)

        # Ограничиваем желаемую скорость
        desired_mag = math.hypot(desired_vx, desired_vy)
        if desired_mag > effective_max_v:
            scale = effective_max_v / desired_mag
            desired_vx *= scale
            desired_vy *= scale

        # 3. Интерполяция к желаемой скорости (Lerp)
        t = min(1.0, effective_acc * dt)
        new_vx = current_velocity[0] + (desired_vx - current_velocity[0]) * t
        new_vy = current_velocity[1] + (desired_vy - current_velocity[1]) * t

        return (new_vx, new_vy)


class MotionIntegrator:
    """ETKE-IK 2.2: Интегрирует скорость в позицию (position += velocity * dt).

    Дополнительно:
    - Обновляет состояние усталости (stamina decay).
    - Применяет торможение (braking_force) при отсутствии DriveVector.
    """

    @staticmethod
    def integrate(
        position: Tuple[float, float],
        velocity: Tuple[float, float],
        body: BodySchema,
        affordance: AffordanceVector,
        dt: float = ETKE_IK_SUBSTEP_DT,  # ADR-O-302: Numeric substep
    ) -> Tuple[float, float]:
        """Обновляет позицию.

        Args:
            position: Текущая позиция (x, y).
            velocity: Текущая скорость (vx, vy).
            body: Кинематика тела.
            affordance: Свойства среды.
            dt: Шаг времени.

        Returns:
            Новая позиция (x, y).
        """
        new_x = position[0] + velocity[0] * dt
        new_y = position[1] + velocity[1] * dt

        # TODO: Проверка коллизий с affordance (can_pass == 0.0 -> стена)
        # Пока оставляем как есть, коллизии будут в WorldTopologyProvider.

        # S91: Эмит стигмергического следа (movement_density)
        # В будущем будет вызывать DynamicAffordanceField.apply_trace()

        return (new_x, new_y)

    @staticmethod
    def compute_exertion(
        velocity: Tuple[float, float],
        body: BodySchema,
        current_exertion: float,
        dt: float = ETKE_IK_SUBSTEP_DT,
    ) -> float:
        """Вычисляет уровень усталости (exertion_level).

        Бег = рост усталости, покой = восстановление.
        """
        speed = math.hypot(velocity[0], velocity[1])
        if speed > 0.1:
            # Усталость растет пропорционально скорости
            exertion_delta = (speed / body.max_velocity) * 0.1 * dt
            return min(1.0, current_exertion + exertion_delta)
        else:
            # Восстановление
            return max(0.0, current_exertion - 0.05 * dt)

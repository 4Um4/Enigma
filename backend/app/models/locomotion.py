"""
Файл: backend/app/models/locomotion.py
Назначение: Доменные модели физики перемещения. Отвечает на вопрос "как сильно шаги бьют по мембране?".
Зависимости: dataclasses, typing
Основные сущности: SurfaceDTO, KineticProfile, KineticDisturbance

TODO: Временный контракт для разработки и тестирования механики перемещения и акустики.
В будущем может быть расширен или переработан в зависимости от потребностей ADR-032 и   взаимодействия с другими системами (эмоции от боли, память от травмы, влияние на идентичность).
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SurfaceDTO:
    """Физические свойства поверхности для кинетического возмущения.
    Инжектируется из свойств узла SpatialService.
    """

    surface_id: str
    noise_amplification: float = (
        1.0  # Усиление акустики (грязь=0.2, дерево=1.5, металл=2.0)
    )
    friction: float = 0.5  # Сопротивление (влияет на каденс и затраты усталости)
    resonance: float = 0.0  # Резонанс структуры (эхо в пещере, гулкий мост)


@dataclass(frozen=True)
class KineticProfile:
    """Физические параметры сущности, влияющие на шум перемещения.
    Вычисляется из body_profile и экипировки.
    """

    weight: float = 70.0  # Масса в кг
    armor_rattle: float = 0.0  # Шум брони 0.0-1.0 (0=босой, 1=латы)
    base_stealth: float = 0.0  # Базовый коэффициент гашения звука (агильность/навык)


@dataclass(frozen=True)
class KineticDisturbance:
    """Результат шага по поверхности. НЕ событие, а физический факт воздействия на мембрану.
    Генерируется MovementStepper и конвертируется в FieldDisturbance(LOCOMOTION, ACOUSTIC).
    """

    source_entity: str
    position_xy: Tuple[float, float]
    surface: SurfaceDTO
    actor_profile: KineticProfile
    intensity: float  # Итоговая магнитуда (0.0 - 1.0+)
    cadence: float  # Частота шагов (шагов в секунду)

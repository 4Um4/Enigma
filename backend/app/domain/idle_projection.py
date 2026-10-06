"""
path: /project/backend/app/domain/idle_projection.py
Назначение: Контракт наблюдаемой проекции idle-событий (LC-01 / ADR-O-421,
    Ступень LC roadmap v4.3 §15). Формат {cause, target, value} — вербатим
    из каталога LC; строго read-only: DTO несёт только наблюдаемое
    содержимое уже произошедшего события мира, никаких ментальных полей
    NPC (Rule 11 — телепатия в UI запрещена).
Зависимости: dataclasses, typing
Основные сущности: IdleEventProjection, ProjectionValue
"""
from dataclasses import dataclass
from typing import Dict, Union

# Наблюдаемый скаляр: категория-строка, счётчик или мера. Не текст реплик
# (переговорный канал — perceived_narratives, S158), не внутренние дельты.
ProjectionValue = Union[str, int, float]


@dataclass(frozen=True)
class IdleEventProjection:
    """Наблюдаемое событие мира для игрока (канал «мир → игрок»).

    cause  — категория источника: значение EventType продюсера события;
    target — наблюдаемый актор (event.source — кто совершил/пережил);
    value  — компактная наблюдаемая суть (успех деятельности, жертва кражи).

    Время/тики в проекцию не входят (формат = ровно три поля — LC-01).
    """

    cause: str
    target: str
    value: ProjectionValue

    def to_front(self) -> Dict[str, ProjectionValue]:
        """Граница game_loop → routes: dict-контракт канала 'events'.

        FE-потребитель (game_screen) читает ключи cause/target — конвертация
        на границе, фронт не знает backend-классов (Устав §1.1/Закон 6.1).
        """
        return {"cause": self.cause, "target": self.target, "value": self.value}

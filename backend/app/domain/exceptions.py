"""
path: backend/app/domain/exceptions.py
Назначение: Онтологические исключения симуляции. Нарушение = физическая невозможность состояния.
Зависимости: Нет
Основные сущности: OntologyViolationError
"""


class OntologyViolationError(RuntimeError):
    """Критическое нарушение инвариантов модели (L5 Post-Commit Validation Gate).
    
    Выбрасывается, если состояние NPC нарушает законы физики психеи
    (Закон Сохранения Я, выход за границы диапазона, NaN/Inf).
    
    Это не баг данных. Это баг каузального конвейера.
    Перехватывать этот exception запрещено (No Repair Principle).
    """
    pass
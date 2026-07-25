"""
Файл: backend/app/services/social/dilemma_engine.py
Назначение: Хранение и активация дилемм.
Зависимости: typing, app.models.dilemma
"""

from typing import Dict, List, Set
from app.models.dilemma import MoralDilemma, DilemmaChoice, DilemmaResolution

class DilemmaEngine:
    """Управляет моральными дилеммами: Registered -> Triggered -> Resolved."""
    
    def __init__(self) -> None:
        self._dilemmas: Dict[str, MoralDilemma] = {}
        self._triggered: Set[str] = set()
        self._resolved: Set[str] = set()

    def register_dilemma(self, dilemma: MoralDilemma) -> None:
        self._dilemmas[dilemma.dilemma_id] = dilemma

    def check_triggers(self, revealed_secrets: List[str]) -> List[MoralDilemma]:
        """Активирует дилеммы при раскрытии секретов."""
        newly_triggered = []
        for dilemma in self._dilemmas.values():
            if dilemma.dilemma_id in self._triggered or dilemma.dilemma_id in self._resolved:
                continue
            if dilemma.trigger_condition in revealed_secrets:
                self._triggered.add(dilemma.dilemma_id)
                newly_triggered.append(dilemma)
        return newly_triggered

    def resolve(self, dilemma_id: str, choice: DilemmaChoice, tick: int) -> DilemmaResolution:
        """Фиксирует выбор игрока и возвращает последствия. Каузальный мост."""
        if dilemma_id not in self._dilemmas:
            raise ValueError(f"Dilemma {dilemma_id} not found.")
        # P7-07 FIX: Проверка необратимости должна идти до проверки триггера,
        # так как разрешённая дилемма удаляется из _triggered.
        if dilemma_id in self._resolved:
            raise ValueError(f"Dilemma {dilemma_id} is already resolved. Irreversible.")
        if dilemma_id not in self._triggered:
            raise ValueError(f"Dilemma {dilemma_id} is not triggered yet. Causality violation.")

        dilemma = self._dilemmas[dilemma_id]
        if choice not in dilemma.sides:
            raise ValueError(f"Invalid choice {choice} for dilemma {dilemma_id}.")

        self._resolved.add(dilemma_id)
        self._triggered.remove(dilemma_id) # Переводим из активных в разрешенные

        side = dilemma.sides[choice]
        return DilemmaResolution(
            dilemma_id=dilemma_id,
            choice=choice,
            tick=tick,
            consequences=side.consequences
        )
"""
path: backend/app/errors.py
Назначение: Кастомные исключения для инвариантов симуляции.
            SimulationIntegrityError поднимается в pipeline когда инвариант нарушен.
            НЕ должна перехватываться try/except — пусть игра упадёт громко.
Зависимости: typing
Основные сущности: SimulationIntegrityError
"""
from typing import List


class SimulationIntegrityError(Exception):
    """
    Поднимается когда инвариант симуляции нарушен в runtime.
    
    Формат сообщения — машино-читаемая первая строка (для CausalObserver),
    затем человекочитаемое описание и список подозреваемых файлов.
    """
    
    def __init__(self, invariant_id: str, message: str,
                 suspect_files: List[str], file: str = "", line: int = 0):
        self.invariant_id = invariant_id
        self.suspect_files = suspect_files
        self.source_file = file
        self.source_line = line
        
        machine = (f"[SIM_INTEGRITY] id={invariant_id} severity=CRITICAL "
                   f"file={file} line={line}")
        files_block = "\n".join(f"  - {f}" for f in suspect_files)
        full = f"{machine}\n{message}\nSuspect files:\n{files_block}"
        super().__init__(full)
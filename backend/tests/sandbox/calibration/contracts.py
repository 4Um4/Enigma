"""

"""

import numpy as np
from dataclasses import dataclass

@dataclass(frozen=True)
class CausalPressureVector:
    fear: float = 0.0
    control: float = 0.0
    significance: float = 0.0
    desire: float = 0.0
    volatility: float = 0.0

@dataclass(frozen=True)
class CausalStateVector:
    g_basis: np.ndarray
    last_commit_tick: int = 0
    version: int = 0
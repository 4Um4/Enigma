"""
АРХИТЕКТУРНЫЙ ПРИНЦИП (Metaphysical Core ADR):
Tick = causal spine (non-negotiable).
Kernel never depends from seconds.
All kernel randomness MUST go through KernelRNG.

ИСПОЛЬЗОВАНИЕ:
rng = KernelRNG(tick=42, npc_id="maid_lusya")
if rng.random() < 0.4: # deterministic for (42, "maid_lusya")
    ...

ГАРАНТИИ:
- Same (tick, npc_id) → same RNG sequence
- Different npc_id on same tick → independent sequences
- Replay determinism: same input → same output

Назначение: Deterministic RNG bound to (tick, npc_id). Единственный источник случайности в kernel layer.
Зависимости: stdlib (random, hashlib)
Основные сущности: KernelRNG
"""

import hashlib
import random
from typing import List, Any

class KernelRNG:
    """
    Deterministic RNG bound to (tick, npc_id).

    This is the ONLY randomness source in kernel layer.
    Physics layer (seconds-based) does NOT use this class.

    Seed derivation:
    seed_raw = f"{tick}:{npc_id}:{salt}".encode()
    seed = int(sha256(seed_raw).hexdigest()[:16], 16)  # 64-bit seed

    Guarantees:
    - Same (tick, npc_id, salt) → same seed → same sequence
    - Different npc_id or salt → different seed (independence)
    """

    def __init__(self, tick: int, npc_id: str, salt: str = ""):
        if not isinstance(tick, int) or tick < 0:
            raise ValueError(f"tick must be non-negative int, got {tick}")
        if not isinstance(npc_id, str) or not npc_id:
            raise ValueError(f"npc_id must be non-empty str, got {npc_id!r}")

        seed_raw = f"{tick}:{npc_id}:{salt}".encode("utf-8")
        # Используем первые 16 hex-символов (64 бита) для компактности seed
        seed = int(hashlib.sha256(seed_raw).hexdigest()[:16], 16)

        self._rng = random.Random(seed)
        self.seed = seed
        self.tick = tick
        self.npc_id = npc_id

    # ── Wrappers (explicit control boundary) ──────────────────────────
    # Каждый метод явно делегирует в _rng. Это создаёт clear API boundary:
    # kernel code использует ctx.rng.random(), не random.random().

    def sample(self, population: List[Any], k: int) -> List[Any]:
        """Детерминированный выбор k элементов из population."""
        return self._rng.sample(population, k)

    def random(self) -> float:
        """Return [0.0, 1.0) — deterministic for (tick, npc_id)."""
        return self._rng.random()

    def choice(self, seq):
        """Choose random element from seq — deterministic."""
        return self._rng.choice(seq)

    def uniform(self, a: float, b: float) -> float:
        """Return [a, b) — deterministic."""
        return self._rng.uniform(a, b)

    def choices(self, seq, weights=None, k: int = 1):
        """Choose k elements — deterministic."""
        return self._rng.choices(seq, weights=weights, k=k)

    def randint(self, a: int, b: int) -> int:
        """Return [a, b] inclusive — deterministic."""
        return self._rng.randint(a, b)

    def __repr__(self) -> str:
        return f"KernelRNG(tick={self.tick}, npc_id={self.npc_id!r}, seed={self.seed})"

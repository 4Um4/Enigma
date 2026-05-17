"""
Социальный граф NPC-NPC связей и структуры слухов.

path: /backend/app/models/social.py
Назначение: Структуры социального графа и пакетов слухов (чистые данные)
Зависимости: typing, dataclasses
Основные сущности: Relationship, Rumor, PropagationResult

Контракт:
- Relationship — направленная связь source → target
- Rumor — frozen пакет искажённой информации (LLM НЕ видит)
- PropagationResult — результат для применения к состоянию (возвращает SocialEngine)

Интеграция:
- SocialEngine загружает граф из config/npc/social/village_relations.json
- Runtime мутации (trust_delta, affection_delta) сохраняются отдельно от статичных base_*
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Relationship:
    """
    Направленная социальная связь source → target.

    base_* — из конфига (статичны, read-only)
    runtime_*_delta — мутируют в процессе игры через adjust_*()
    effective_* — вычисляемое свойство (base + delta, с капом [-1..1])
    """
    nature: str                    # "employer_employee", "business_partner", "handler_agent"
    base_trust: float              # из config, [-1..1]
    base_affection: float          # из config, [-1..1]
    runtime_trust_delta: float = 0.0
    runtime_affection_delta: float = 0.0
    fear: float = 0.0              # страх target перед source
    debt: float = 0.0              # долг target перед source
    shared_secrets: int = 0        # количество общих секретов

    @property
    def effective_trust(self) -> float:
        return max(-1.0, min(1.0, self.base_trust + self.runtime_trust_delta))

    @property
    def effective_affection(self) -> float:
        return max(-1.0, min(1.0, self.base_affection + self.runtime_affection_delta))

    def adjust_trust(self, delta: float) -> None:
        """Безопасная мутация: пересчитывает delta чтобы effective остался в [-1..1]."""
        new_effective = max(-1.0, min(1.0, self.effective_trust + delta))
        self.runtime_trust_delta = new_effective - self.base_trust

    def adjust_affection(self, delta: float) -> None:
        new_effective = max(-1.0, min(1.0, self.effective_affection + delta))
        self.runtime_affection_delta = new_effective - self.base_affection

    def to_runtime_dict(self) -> Dict:
        """Сериализация только runtime-части для saves/ (отдельно от статичного конфига)."""
        return {
            "runtime_trust_delta": self.runtime_trust_delta,
            "runtime_affection_delta": self.runtime_affection_delta,
            "fear": self.fear,
            "debt": self.debt,
            "shared_secrets": self.shared_secrets,
        }

    def apply_runtime_dict(self, data: Dict) -> None:
        """Восстановление runtime из saves/ (не трогает base_*)."""
        self.runtime_trust_delta = float(data.get("runtime_trust_delta", 0.0))
        self.runtime_affection_delta = float(data.get("runtime_affection_delta", 0.0))
        self.fear = float(data.get("fear", 0.0))
        self.debt = float(data.get("debt", 0.0))
        self.shared_secrets = int(data.get("shared_secrets", 0))


@dataclass(frozen=True)
class Rumor:
    """
    Пакет информации при социальном распространении.
    Frozen — создаётся в SocialEngine и передаётся без мутации.

    LLM НЕ видит этот объект.
    DM видит только continuity_note из PropagationResult.
    """
    origin_event_type: str         # "player_attacks", "player_insults"
    origin_target: str             # npc_id цели события
    origin_actor: str              # обычно "player"
    base_intensity: float          # оригинальная интенсивность события
    perceived_intensity: float     # после искажения (decay + trust bias)
    hop: int                       # хопов от первоисточника (1 = от свидетеля)
    carrier: str                   # npc_id того, кто передал слух
    distortion_applied: float      # разница decayed vs perceived (для debug)


@dataclass(frozen=True)
class PropagationResult:
    """
    Результат распространения слуха до конкретного NPC.
    Содержит всё для применения к состоянию и нарративу.

    НЕ применяется внутри SocialEngine — возвращается вызывающему коду (game_loop).
    Вызывающий решает: применить trust_delta через StateApplicator или игнорировать.
    """
    npc_id: str
    trust_delta: float             # изменение доверия NPC→actor (~0.02-0.08)
    stress_delta: float            # стресс от услышанного (только негативные)
    rumor: Rumor                   # полный слух для debug/logging
    continuity_note: str           # factual строка для SceneContinuity (без эмоций)
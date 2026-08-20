# backend/app/services/npc/trust_based_reliability_provider.py
"""
path: /project/backend/app/services/npc/trust_based_reliability_provider.py
Назначение: Канонический адаптер SourceReliabilityProvider (ADR-O-357, EPISTEMIC-002).
            reliability источника = нормированная функция доверия наблюдателя к источнику.
Зависимости: RelationshipStore (readonly), SourceReliabilityProvider (protocol,
             объявлен в app.services.npc.belief_revision_engine)
Основные сущности: TrustBasedReliabilityProvider

СТАТУС (S206, ADR-O-357 enforcement): данный провайдер — ЕДИНСТВЕННАЯ
каноническая реализация reliability для testimony. Инлайн-дубликат в
claim_event_subscriber.py удалён; живой контур GameLoop вживляет этот класс.
Расширение ADR-O-360 (context["source_type"] = direct_observation) добавлено
в Phase C. До-канонизационный BEFORE-трейс: reports/reliability_baseline_before.json.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ADR-O-357: порог врага. trust < -30 → утверждения источника вызывают обратный
# эффект (наблюдатель не верит, confidence убывает в BeliefRevisionEngine).
_ENEMY_TRUST_THRESHOLD: float = -30.0

# ADR-O-354: RelationshipStore хранит trust в масштабе 0-100
# (с отрицательной областью для враждебных отношений).
_TRUST_SCALE: float = 100.0

# Prior для неизвестного источника (нет store / нет записи о паре).
# ADR-O-357 не определяет trust незнакомой пары — до фактов о get_pair
# сохраняем паритет с живым поведением инлайн-провайдера (0.5).
# Смена prior — только отдельным ADR с собственным acceptance gate.
_UNKNOWN_SOURCE_TRUST: float = 50.0

# ADR-O-360 (Phase C): прямая достоверность канала наблюдения.
    # Калибруемый параметр, НЕ онтологическая константа: observation доминирует
# над testimony, но confidence ≠ truth (Invariant V), поэтому строго < 1.0.
# Модуляция (освещение/дистанция/угол) — отдельными ADR.
DIRECT_OBSERVATION_RELIABILITY: float = 0.9


class TrustBasedReliabilityProvider:
    """
    EPISTEMIC-002: Надёжность источника = нормированное доверие наблюдателя к источнику.

    Каузальная цепь:
      RelationshipStore.get_pair(campaign_id, observer, source)
        → trust (0-100, может быть отрицательным)
        → trust >= -30: нормализация в [0.0, 1.0]
        → trust <  -30: инверсия (отрицательная надёжность, враг не убеждает)
        → BeliefRevisionEngine.revise() использует как множитель confidence_delta

    Гарантия INV-EPISTEMIC-TRUST-MONOTONICITY (S204):
    монотонность по trust — большему доверию соответствует не меньшая reliability.
    Граница непрерывна: trust = -30 → 0.0, trust = -30-ε → -ε/70.
    """

    def __init__(self, relationship_store: Any, campaign_id: str) -> None:
        self._store = relationship_store
        self._campaign_id = campaign_id

    def get_reliability(
        self, observer: str, source: str, context: Optional[dict] = None
    ) -> float:
        """
        Возвращает надёжность источника в диапазоне [-1.0, 1.0].
        0.0 = нейтрально (нет данных / нейтральный trust),
        1.0 = абсолютное доверие, -1.0 = абсолютное недоверие.

        ADR-O-360: context["source_type"] = "direct_observation" — наблюдатель
        сам воспринял событие (не testimony). Возвращает достоверность канала
        восприятия, а не trust-функцию.
        """
        if context and context.get("source_type") == "direct_observation":
            return DIRECT_OBSERVATION_RELIABILITY

        trust = self._read_trust(observer, source)

        # Если наблюдатель считает источник врагом — обратный эффект (ADR-O-357).
        if trust < _ENEMY_TRUST_THRESHOLD:
            # Нормируем недоверие: -30 → 0.0⁻, -100 → -1.0.
            _distrust = abs(trust) - abs(_ENEMY_TRUST_THRESHOLD)
            _range = _TRUST_SCALE - abs(_ENEMY_TRUST_THRESHOLD)
            return -(_distrust / _range)

        # Нормальное доверие: 0 → 0.0, 100 → 1.0.
        return max(0.0, min(1.0, trust / _TRUST_SCALE))

    def _read_trust(self, observer: str, source: str) -> float:
        """Чтение trust из SSOT. Ошибки чтения не глотаются молча (L4).

        Отсутствие данных (нет store / нет пары / нет ключа trust) —
        не ошибка, а эпистемически значимый случай «неизвестный источник»:
        возвращаем явный prior (см. _UNKNOWN_SOURCE_TRUST).
        """
        if not self._store:
            logger.warning(
                "[TRUST_RELIABILITY] RelationshipStore отсутствует — "
                f"пара ({observer}, {source}) получает unknown-source prior."
            )
            return _UNKNOWN_SOURCE_TRUST
        try:
            rel_data = self._store.get_pair(self._campaign_id, observer, source)
            if not rel_data:
                return _UNKNOWN_SOURCE_TRUST
            return float(rel_data.get("trust", _UNKNOWN_SOURCE_TRUST))
        except Exception as e:
            # L4 (ADR-O-308): деградация в нейтральную reliability допустима
            # (убеждение не должно крашить тик из-за social-SSOT), но отказ
            # обязан быть наблюдаемым в логе.
            logger.warning(
                f"[TRUST_RELIABILITY] RelationshipStore.get_pair failed "
                f"для пары ({observer}, {source}): {e}. reliability = 0.0."
            )
            return 0.0
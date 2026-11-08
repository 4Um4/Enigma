"""
path: /project/backend/app/services/body_arbiter.py
Назначение: Step 3.2 Stage B — BodyArbiter authorization service.
    Разделяет Compatibility, Arbitration, Authorization.
    Читает намерения из intent_lifecycle, записывает arbitration_result.
    НЕ исполняет, НЕ публикует, НЕ гейтирует публикации.
    НЕ назначает победителя в режиме B.
    Не использует WillpowerGate.
Зависимости: app.domain.arbitration, app.services.avatar.player_intent_formation,
             app.services.avatar.avatar_intent_formation
Основные сущности: BodyArbiter, AuthorizationResult, AuthorizationDecision
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from app.domain.arbitration import (
    ArbitrationVerdict,
    CompatibilityClass,
    check_compatibility,
)

logger = logging.getLogger(__name__)


class AuthorizationDecision(Enum):
    """Решение авторизации для конкретного намерения."""
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class AuthorizationResult:
    """Результат авторизации BodyArbiter.

    Содержит отдельное решение для Player Intent и Avatar Intent.
    НЕ содержит победителя. НЕ исполняет эффекты.
    """
    player_decision: AuthorizationDecision
    avatar_decision: AuthorizationDecision
    player_intent_id: Optional[str]
    avatar_intent_id: Optional[str]
    compatibility: CompatibilityClass
    verdict: ArbitrationVerdict
    conflict_type: Optional[str]
    reason: str
    tick: int


class BodyArbiter:
    """Единый арбитр между Player Intent и Avatar Intent за контроль общего тела.

    Процесс:
      1. Чтение намерений из intent_lifecycle
      2. Compatibility check (Etap A)
      3. Arbitration — определение типа конфликта
      4. Authorization — запись AUTHORIZED/REJECTED/DEFERRED в lifecycle

    НЕ назначает победителя в обычном сопротивлении (режим B).
    НЕ исполняет физические или социальные эффекты.
    НЕ использует WillpowerGate.
    """

    def authorize(
        self,
        scene_state: Dict[str, Any],
        tick: int,
    ) -> AuthorizationResult:
        """Авторизует намерения Player и Avatar.

        Читает ACTIVE намерения из intent_lifecycle.
        Записывает arbitration_result в lifecycle entries.
        Возвращает AuthorizationResult с отдельными решениями.

        НЕ исполняет, НЕ публикует, НЕ гейтирует.
        """
        from app.services.avatar.avatar_intent_formation import (
            get_active_avatar_intent,
        )
        from app.services.avatar.player_intent_formation import (
            get_active_player_intent,
        )

        player_intent = get_active_player_intent(scene_state)
        avatar_intent = get_active_avatar_intent(scene_state)

        # Извлечь action и target для compatibility check
        player_action = player_intent.get("action") if player_intent else None
        player_target = player_intent.get("target") if player_intent else None
        avatar_action = avatar_intent.get("action") if avatar_intent else None
        avatar_target = avatar_intent.get("target") if avatar_intent else None

        player_intent_id = player_intent.get("intent_id") if player_intent else None
        avatar_intent_id = avatar_intent.get("intent_id") if avatar_intent else None

        # 1. Compatibility check (Etap A)
        compatibility = check_compatibility(
            player_action, avatar_action, player_target, avatar_target
        )

        # 2. Arbitration — определение типа конфликта
        verdict, conflict_type, player_dec, avatar_dec, reason = self._arbitrate(
            compatibility, player_intent is not None, avatar_intent is not None
        )

        # 3. Authorization — запись в lifecycle
        self._write_authorization(
            scene_state, player_intent_id, player_dec
        )
        self._write_authorization(
            scene_state, avatar_intent_id, avatar_dec
        )

        result = AuthorizationResult(
            player_decision=player_dec,
            avatar_decision=avatar_dec,
            player_intent_id=player_intent_id,
            avatar_intent_id=avatar_intent_id,
            compatibility=compatibility,
            verdict=verdict,
            conflict_type=conflict_type,
            reason=reason,
            tick=tick,
        )

        logger.info(
            f"[BODY_ARBITER] tick={tick} compatibility={compatibility.value} "
            f"verdict={verdict.value} player={player_dec.value} avatar={avatar_dec.value} "
            f"reason={reason}"
        )

        return result

    def _arbitrate(
        self,
        compatibility: CompatibilityClass,
        has_player: bool,
        has_avatar: bool,
    ) -> tuple[
        ArbitrationVerdict,
        Optional[str],
        AuthorizationDecision,
        AuthorizationDecision,
        str,
    ]:
        """Определяет тип конфликта и решения авторизации.

        Возвращает (verdict, conflict_type, player_decision, avatar_decision, reason).
        НЕ назначает победителя в режиме B.
        """
        # Нет одного намерения — нет конфликта.
        # DEFERRED для отсутствующего участника означает "не авторизовано,
        # т.к. намерения нет", а не "фиктивное отложенное действие".
        # _write_authorization не пишет в lifecycle (intent_id=None),
        # поэтому lifecycle не загрязняется.
        if not has_player and not has_avatar:
            return (
                ArbitrationVerdict.NO_CONFLICT,
                None,
                AuthorizationDecision.DEFERRED,
                AuthorizationDecision.DEFERRED,
                "no intents",
            )

        if not has_avatar:
            return (
                ArbitrationVerdict.NO_CONFLICT,
                None,
                AuthorizationDecision.AUTHORIZED,
                AuthorizationDecision.DEFERRED,
                "no avatar intent",
            )

        if not has_player:
            return (
                ArbitrationVerdict.NO_CONFLICT,
                None,
                AuthorizationDecision.DEFERRED,
                AuthorizationDecision.AUTHORIZED,
                "no player intent",
            )

        # Оба намерения есть — проверяем совместимость

        if compatibility == CompatibilityClass.COMPATIBLE:
            return (
                ArbitrationVerdict.NO_CONFLICT,
                None,
                AuthorizationDecision.AUTHORIZED,
                AuthorizationDecision.AUTHORIZED,
                "compatible intents",
            )

        if compatibility == CompatibilityClass.CONFLICT:
            # Конфликт — режим B (resistance) или C (struggle)
            # НЕ назначаем победителя. Оба DEFERRED.
            # BehaviorSelector (не реализован) определит поведение Avatar.
            return (
                ArbitrationVerdict.RESOLVE_RESISTANCE,
                "B",
                AuthorizationDecision.DEFERRED,
                AuthorizationDecision.DEFERRED,
                "conflict — resistance not resolved (behavior selector not calibrated)",
            )

        if compatibility == CompatibilityClass.CONDITIONAL:
            return (
                ArbitrationVerdict.DEFER_BOTH,
                "F",
                AuthorizationDecision.DEFERRED,
                AuthorizationDecision.DEFERRED,
                "conditional — conditions not verified",
            )

        if compatibility == CompatibilityClass.UNKNOWN:
            # UNKNOWN — недостаточно данных, НЕ доказательство невозможности.
            # DEFER_BOTH, не FAIL_BOTH — неизвестность сохраняет пространство
            # возможностей, а не закрывает его.
            return (
                ArbitrationVerdict.DEFER_BOTH,
                None,
                AuthorizationDecision.DEFERRED,
                AuthorizationDecision.DEFERRED,
                "unknown compatibility — insufficient data, deferred not failed",
            )

        # Fallback — не должно достигаться, все семантики CompatibilityClass обработаны выше.
        raise AssertionError(f"Unhandled compatibility class: {compatibility!r}")

    def _write_authorization(
        self,
        scene_state: Dict[str, Any],
        intent_id: Optional[str],
        decision: AuthorizationDecision,
    ) -> None:
        """Записывает arbitration_result в lifecycle entry.

        НЕ удаляет, НЕ исполняет, НЕ сбрасывает effect_status.
        """
        if intent_id is None:
            return

        lifecycle = scene_state.get("intent_lifecycle", {})
        entry = lifecycle.get(intent_id)
        if entry is None or not isinstance(entry, dict):
            return

        entry["arbitration_result"] = decision.value

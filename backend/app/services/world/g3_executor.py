# path: /project/backend/app/services/world/g3_executor.py
# Назначение: G3 (ADR-O-410) — исполнитель объектных действий, ПЕРВЫЙ
#     легальный runtime-writer WorldObjectStore. Получает УЖЕ разрешённый
#     интент (action_type + actor_id + target_id) и отвечает только
#     «исполнимо ли → мутация → исход»; целеполагание executor НЕ
#     выполняет (вердикт Мастера И-1: выбор цели — Decision/Opportunity,
#     Этап 2).
#     Статус-словарь (вердикт Мастера): G3_PASS — применил transition;
#     G3_NO_OP — допустимо, мутация не нужна; G3_REJECT — принял
#     ответственность и отклонил (события не будет); G3_SKIP — НЕ принял
#     ownership цели (passthrough; «не утверждает, что действие исполнено,
#     лишь не принимает на себя unresolved intent»).
#     Provenance — обёртка executor'а (D2): tick/actor/cause здесь;
#     сигнатуры стора не расширяются, стор НЕ агрегатор причинности.
# Зависимости: app.domain.object_fsms, app.domain.semantic_action,
#     app.services.world.world_object_store
# Основные сущности: G3Status, G3Outcome, execute_object_action
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from app.domain.object_fsms import TransitionVerdict
from app.domain.semantic_action import WorldActionType
from app.services.world.world_object_store import WorldObjectStore

logger = logging.getLogger(__name__)

# ═══ Реестр intent → WorldActionType (ЗАКРЫТ; ADR-O-410 §3) ═══
# Расширение = мини-ADR на каждое действие (табу ADR-O-362 — закрытые
# object-action реестры). v1: steal — единственный живой продюсер
# объектных интентов; STEAL = W5-интерпретация TAKE (ADR-O-376).
_ACTION_TO_WORLD: Dict[str, WorldActionType] = {
    "steal": WorldActionType.TAKE,
}


class G3Status(str, Enum):
    """Статусы исполнения. svc-слой, телеметрия — НЕ домен, НЕ стор."""

    G3_PASS = "G3_PASS"
    G3_NO_OP = "G3_NO_OP"
    G3_REJECT = "G3_REJECT"
    G3_SKIP = "G3_SKIP"


@dataclass(frozen=True)
class G3Outcome:
    """Результат исполнения: status + reason (+ факт перехода для
    телеметрии provenance при ненулевых вердиктах)."""

    status: G3Status
    reason: str = ""
    object_id: str = ""
    old_state: Optional[str] = None


def _g3_enabled() -> bool:
    """Env-флаг W3_G3_ENABLED (default OFF = no-op ДО вычислений;
    паттерн W3_G2_ENABLED, ADR-O-378)."""
    return os.environ.get("W3_G3_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


_VERDICT_TO_STATUS: Dict[TransitionVerdict, G3Status] = {
    TransitionVerdict.PASS: G3Status.G3_PASS,
    TransitionVerdict.NO_OP: G3Status.G3_NO_OP,
    TransitionVerdict.REJECT: G3Status.G3_REJECT,
}


def execute_object_action(
    scene_state: Dict[str, Any],
    action_type: str,
    actor_id: str,
    target_id: str,
    tick: int,
) -> G3Outcome:
    """Исполнить объектное действие над миром (единственный легальный
    runtime-путь к WorldObjectStore.apply_transition, Г4-цензус).

    Контракт вердиктов (ADR-O-410, D4/D5/D7):
      PASS/NO_OP → вызывающий публикует событие существующим путём;
      REJECT     → вызывающий переводит windup в INTERRUPTED, событие
                   НЕ публикуется (событие = утверждение факта);
      SKIP       → passthrough: ownership цели не принят.
    """
    if not _g3_enabled():
        return G3Outcome(G3Status.G3_SKIP, reason="disabled")
    _world_action = _ACTION_TO_WORLD.get(action_type)
    if _world_action is None:
        return G3Outcome(G3Status.G3_SKIP, reason=f"no_mapping({action_type})")
    if not target_id:
        return G3Outcome(G3Status.G3_SKIP, reason="no_target")
    _obj = WorldObjectStore.get(scene_state, target_id)
    if _obj is None:
        # D7a: нерезолвленная цель — производственная норма (steal-цели
        # без wo_-identity); ownership не принимается, путь вызывающего
        # не меняется.
        return G3Outcome(G3Status.G3_SKIP, reason="object_unresolved")
    _result = WorldObjectStore.apply_transition(
        scene_state, target_id, _world_action, actor_id
    )
    _outcome = G3Outcome(
        status=_VERDICT_TO_STATUS[_result.verdict],
        reason=_result.reason,
        object_id=target_id,
        old_state=_result.old_state,
    )
    logger.info(
        f"[G3_EXEC] tick={tick} actor={actor_id} "
        f"action={action_type}->{_world_action.value} target={target_id} "
        f"status={_outcome.status.value} reason={_outcome.reason!r} "
        f"old_state={_outcome.old_state!r} cause=g3:executor"
    )
    return _outcome

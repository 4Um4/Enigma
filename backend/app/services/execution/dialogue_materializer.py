"""
path: /backend/app/services/execution/dialogue_materializer.py
Назначение: Превращает доменный Artifact (результат диалога) в WorldEvent (EventDTO)
            для EventBus.
            P5-B: перед публикацией COMMUNICATION_CLAIM выполняет семантическую
            верификацию — проверяет, что LLM-текст реплики действительно выражает
            candidate Proposition. Только подтверждённый proposition становится
            claim'ом в EventBus; неподтверждённый — suppress'ится.

            Master directive (P5-B Step 2):
              Production-default = fail-closed. PassthroughVerifier НЕ является
              default'ом. Если verifier не передан в __init__ — materializer
              работает в режиме NO_VERIFIER: candidate proposition всегда
              suppress'ится с ERROR-логом (production misconfiguration alarm).
              NPC_SPOKE публикуется ВСЕГДА (речь состоялась).

Зависимости: app.domain.execution, app.services.events.event_types, app.models.events,
             app.services.cognition.proposition_verifier
Основные сущности: DialogueMaterializer
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from app.domain.execution import Artifact
from app.services.cognition.proposition_verifier import _VerifierProtocol
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


class DialogueMaterializer:
    """Связывает Execution Framework с миром симуляции (EventBus)."""

    def __init__(
        self,
        proposition_verifier: _VerifierProtocol | None = None,
    ) -> None:
        """
        Parameters
        ----------
        proposition_verifier:
            P5-B верификатор candidate proposition ↔ LLM-текст.
            Production wiring: PropositionVerifier(llm_client) — РЕАЛЬНАЯ
            семантическая проверка через LLM.

            Если None — materializer работает в NO_VERIFIER режиме:
            candidate proposition ВСЕГДА suppress'ится (fail-closed).
            Это production misconfiguration — лог на ERROR уровне, чтобы
            её нельзя было пропустить в логах. Тесты P1-P4, желающие
            старое структурное поведение, должны ЯВНО передавать
            PassthroughVerifier() в конструктор.

        NPC_SPOKE публикуется ВСЕГДА, независимо от verifier'а —
        речь состоялась (LLM сгенерировал текст), и suppress'ить её
        было бы семантически неверно (Master условие D).
        """
        self._verifier: _VerifierProtocol | None = proposition_verifier

    def materialize(self, artifact: Artifact) -> Iterable[Any]:
        if artifact.result_type != "dialogue_line" or not artifact.success:
            return []

        data = artifact.data

        from app.domain.events import EventDTO

        exposure_semantic = data.get("exposure", "normal")
        visibility = "public"
        if exposure_semantic in ["secret", "whisper"]:
            visibility = "whisper"
        elif exposure_semantic == "private":
            visibility = "private"

        from app.domain.communication import SELF_TALK_SENTINEL, exposure_radius

        _speech_radius = exposure_radius(exposure_semantic)
        if data.get("target_id") == SELF_TALK_SENTINEL:
            visibility = "whisper"
            _speech_radius = exposure_radius("whisper")

        from app.services.verbalization.tone_mapper import ToneMapper

        _tone = ToneMapper.map(data.get("emotional_state"))

        events: list[Any] = []

        # NPC_SPOKE публикуется ВСЕГДА — речь состоялась (LLM сгенерировал
        # текст). Proposition здесь НЕТ — это чистое speech-событие.
        events.append(EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source=data["speaker_id"],
            payload={
                "target_id": data.get("target_id"),
                "text": data["text"],
                "topic": data.get("topic"),
                "exposure": exposure_semantic,
                "tone": _tone,
                "intent_type": data.get("intent_type", "talk"),
            },
            visibility=visibility,  # type: ignore[arg-type]
            radius=_speech_radius,
            persistence_level="session",
        ))

        # S197 + P5-B: candidate Proposition верифицируется семантически
        # против финального LLM-текста. Только подтверждённый proposition
        # публикуется как COMMUNICATION_CLAIM.
        _prop_data = data.get("proposition")
        if _prop_data:
            _text = data.get("text", "")
            _confirmed = self._verify_proposition(_prop_data, _text, data)
            if _confirmed:
                events.append(EventDTO.create(
                    event_type=EventType.COMMUNICATION_CLAIM.value,
                    source=data["speaker_id"],
                    payload={
                        "target_id": data.get("target_id"),
                        "proposition": _prop_data,
                        "speech_act": "assert",
                        "tick": 0,
                        "verified_by": "proposition_verifier",
                    },
                    visibility=visibility,  # type: ignore[arg-type]
                    radius=_speech_radius,
                    persistence_level="session",
                ))

        return events

    def _verify_proposition(
        self,
        proposition: dict[str, Any],
        text: str,
        data: dict[str, Any],
    ) -> bool:
        """
        Master условие D: ошибка verifier не должна превращаться в
        успешную передачу. Все ветки rejection / error / missing-verifier
        возвращают False и логируются.

        Master условие A: NPC_SPOKE уже опубликован (в events), отмена
        невозможна — speech состоялся. Suppression касается только
        COMMUNICATION_CLAIM.
        """
        if self._verifier is None:
            logger.error(
                "P5-B NO_VERIFIER: candidate proposition present but no "
                "verifier wired — fail-closed suppression. This is a "
                "production misconfiguration. speaker=%s target=%s prop=%s "
                "text_head=%r",
                data.get("speaker_id"),
                data.get("target_id"),
                proposition,
                text[:160],
            )
            return False

        try:
            confirmed = self._verifier.verify(proposition, text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "P5-B: verifier.verify() raised — fail-closed suppression. "
                "speaker=%s target=%s prop=%s err=%s",
                data.get("speaker_id"),
                data.get("target_id"),
                proposition,
                exc,
            )
            return False

        if not confirmed:
            logger.info(
                "P5-B: proposition NOT confirmed by LLM text — "
                "COMMUNICATION_CLAIM suppressed. NPC_SPOKE still published. "
                "speaker=%s target=%s prop=%s text_head=%r",
                data.get("speaker_id"),
                data.get("target_id"),
                proposition,
                text[:160],
            )
        return confirmed

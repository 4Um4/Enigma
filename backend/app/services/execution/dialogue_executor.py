"""
path: /backend/app/services/execution/dialogue_executor.py
Назначение: Исполнитель задач типа DIALOGUE. Вызывает LLM (или заглушку) и возвращает артефакт.
Зависимости: app.domain.execution, app.domain.communication
Основные сущности: DialogueExecutor
"""
from __future__ import annotations

import concurrent.futures
import logging

from typing import Callable, Iterable, Optional
from app.domain.communication import DialogueRequest
from app.domain.disclosure import (
    DisclosureContext,
    InteractionPressure,
    SocialTarget,
    SocialTargetKind,
)
from app.domain.execution import Artifact, QueuedTask
from app.domain.intent_profiles import requires_dialogue_context, requires_llm_materialization
from app.domain.player_epistemics import SurfaceEvent, SurfaceKind
from app.services.npc.disclosure_decision import decide_disclosure
from app.services.npc.knowledge_retrieval import retrieve_knowledge
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

logger = logging.getLogger(__name__)

_L_TIMEOUT_SEC: float = 30.0  # 021 calibration (ARCH-022 timeout)

class DialogueContractViolation(Exception):
    """Нарушение контракта диалоговой системы (например, отсутствие STM)."""
    pass


class DialogueExecutor:
    """
    Исполнитель диалоговых задач.
    В продакшене вызывает LlmProvider. Соблюдает Эпистемический Барьер (ADR-TZ08-6).
    """

    def __init__(
        self,
        router=None,
        context_provider: Optional[Callable[[str, str], dict]] = None,
        belief_store=None,
        memory_manager=None,
        confession_parser=None, # V8-MVP-12 FIX
        discovery_bridge=None,  # P6/E1 (S255): Bridge — владелец перехода
        npc_states_provider=None,  # P6/E1: Callable[[cid], list[dict]]
        relationship_provider=None,  # P6/E1: Callable[[cid, k, r], dict]
        subject_resolver=None,  # P6/E1: Callable[[topic], SubjectRef]
    ):
        self._router = router
        self._memory_manager = memory_manager
        self._get_context = context_provider or (
            lambda npc_id, camp_id: {"name": npc_id, "description": ""}
        )
        self._belief_store = belief_store
        self._confession_parser = confession_parser
        # P6/E1 (S255): игрок-контур (late-binding: set_epistemic_wiring)
        self._discovery_bridge = discovery_bridge
        self._npc_states_provider = npc_states_provider
        self._relationship_provider = relationship_provider
        self._subject_resolver = subject_resolver
        # L-02: Валидатор реплик NPC
        from dataclasses import dataclass, field
        from uuid import uuid4

        from app.services.verbalization.response_validator import ResponseValidator

        @dataclass
        class NpcContract:
            system_prompt: str = ""
            user_prompt: str = ""
            max_sentences: int = 2
            contract_id: str = field(default_factory=lambda: uuid4().hex[:8])
            _forbidden_tuple: tuple[str, ...] = (
                "описывать действия за других",
                "задавать вопросы игроку напрямую",
                "упоминать игру, симуляцию, интерфейс",
            )
            @property
            def forbidden_actions(self) -> list[str]:
                return list(self._forbidden_tuple)

        self._validator = ResponseValidator(NpcContract())

    def set_epistemic_wiring(
        self,
        discovery_bridge=None,
        npc_states_provider=None,
        relationship_provider=None,
        subject_resolver=None,
    ) -> None:
        """P6/E1 (S255): late-binding игрок-контура (прецеденты:
        set_spatial_query_service; S211 set_epistemic_resolver)."""
        if discovery_bridge is not None:
            self._discovery_bridge = discovery_bridge
        if npc_states_provider is not None:
            self._npc_states_provider = npc_states_provider
        if relationship_provider is not None:
            self._relationship_provider = relationship_provider
        if subject_resolver is not None:
            self._subject_resolver = subject_resolver

    def execute(self, task: QueuedTask) -> Iterable[Artifact]:
        if not isinstance(task.payload, DialogueRequest):
            logger.error(f"[DIALOGUE_EXEC] Invalid payload type: {type(task.payload)}")
            yield Artifact(
                task_id=task.task_id,
                success=False,
                result_type="error",
                data={},
                error_message="Invalid payload for DialogueExecutor",
            )
            return

        req = task.payload
        logger.debug(
            f"[DIALOGUE_EXEC] Executing task for {task.owner_id} -> {req.target_id} on topic '{req.topic}'"
        )

        # S197: Извлекаем Proposition на верхнем уровне, чтобы он был доступен во всех ветках
        _proposition = getattr(req, "proposition", None)  # noqa: ENIGMA002

        # Если роутер не задан (sandbox/test), возвращаем заглушку
        if self._router is None:
            logger.warning("[DIALOGUE_EXEC] ModelRouter is None! Fallback to stub.")
            text = f"[Заглушка] {task.owner_id} обращается к {req.target_id} по теме: '{req.topic}'"
        elif not requires_llm_materialization(req.intent_type):
            # S199.2: Детерминированная материализация для claim-producing интентов без LLM
            text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"
        else:
            # ENIGMA-ARCH-022: LLM Execution Timeout.
            # Использует существующий cancellation boundary (router._abort_generation).
            # В будущем LLM_TIMEOUT_SEC будет вынесен в CalibrationProfile.
            import threading
            _timer = threading.Timer(_L_TIMEOUT_SEC, self._router._abort_generation)
            
            try:
                _timer.start()
                text = self._generate_with_router(task, req)
            except DialogueContractViolation as e:
                logger.warning(f"[DIALOGUE_EXEC] Contract violated: {e}")
                # BUGFIX: Возвращаем error artifact, а не success, т.к. текст не сгенерирован
                yield Artifact(
                    task_id=task.task_id,
                    success=False,
                    result_type="error",
                    data={},
                    error_message=str(e)
                )
                return
            except Exception as e:
                logger.error(f"[DIALOGUE_EXEC] LLM call failed (timeout or error) for {task.owner_id}: {e}")
                yield Artifact(
                    task_id=task.task_id,
                    success=False,
                    result_type="error",
                    data={},
                    error_message=f"LLM execution failed: {e}"
                )
                return
            finally:
                _timer.cancel()

        if not text:
            yield Artifact(
                task_id=task.task_id,
                success=False,
                result_type="error",
                data={},
                error_message="LLM failed or returned empty text (stub avoided)."
            )
            return

        # P6/E1 (S255): эмит — ТОЧКА УСПЕШНОЙ ДОСТАВКИ (DISCOVERY IS
        # DELIVERY: решение P5 материально только при доставленной
        # реплике; error-ветки выше не эмитят). Заменил вызов парсера
        # (V8-MVP-12): текст НЕ источник discovery — PROVENANCE, NOT
        # STRINGS. Писатель :109 — отдельным шагом ПОСЛЕ T8/T3.
        self._emit_dialogue_outcome(task, req)

        yield Artifact(
            task_id=task.task_id,
            success=True,
            result_type="dialogue_line",
            data={
                "speaker_id": task.owner_id,
                "target_id": req.target_id,
                "text": text,
                "exposure": req.exposure.semantic,
                "topic": req.topic,
                "emotional_state": req.emotional_state,
                "proposition": _proposition, # S198 FIX: Сохраняем эпистемическое утверждение для COMMUNICATION_CLAIM
                "intent_type": req.intent_type, # S201 FIX: Пробрасываем intent_type для ClaimEventSubscriber fallback
            },
        )

    def _emit_dialogue_outcome(self, task: QueuedTask, req: DialogueRequest) -> None:
        """P6/E1 (S255): игрок-контур P3→P4→P5→P6 в точке доставки.

        Гейты: bridge, req.target_id == "player" (D30; NPC→NPC — E2),
        провайдеры, NPCState(owner). Fail-open (S200/S201): проводка
        не роняет диалог. Итерация по KnowledgeItem (P5 — один item;
        Bridge идемпотентен). Давление V1 (alpha): topic-heat сессии —
        D-E1-PRESSURE; уточнение — Calibration Lab (beta).
        """
        if self._discovery_bridge is None:
            return
        if (req.target_id or "") != "player":
            return
        if self._npc_states_provider is None or self._subject_resolver is None:
            logger.info("[P6_E1] wiring неполный (provider/resolver) — эмит пропущен")
            return
        try:
            owner_raw = None
            for _n in (self._npc_states_provider(task.campaign_id) or []):
                if isinstance(_n, dict):
                    if (_n.get("npc_id") or _n.get("id")) == task.owner_id:
                        owner_raw = _n
                        break
            if owner_raw is None:
                logger.info(f"[P6_E1] NPCState не найден: {task.owner_id}")
                return
            owner_state = load_l2_state_from_runtime_dict(owner_raw)
            subject = self._subject_resolver(req.topic)
            items = retrieve_knowledge(owner_state, subject)
            if not items:
                return
            rel = {}
            if self._relationship_provider is not None:
                rel = self._relationship_provider(
                    task.campaign_id, task.owner_id, "player"
                ) or {}
            pressure = 0.0
            if self._memory_manager is not None:
                try:
                    pressure = float(
                        self._memory_manager.get_dialogue_pressure(
                            task.campaign_id, task.owner_id
                        )
                    )
                except Exception:
                    pressure = 0.0
            ctx = DisclosureContext(
                pressure=InteractionPressure.QUESTION,
                pressure_amount=pressure,
            )
            recipient = SocialTarget(SocialTargetKind.PERSON, "player")
            for item in items:
                outcome = decide_disclosure(owner_state, recipient, rel, item, ctx)
                self._discovery_bridge.process(
                    SurfaceEvent(
                        kind=SurfaceKind.DIALOGUE_OUTCOME,
                        tick=task.tick,
                        source_id=task.owner_id,
                        secret_id=outcome.secret_id,
                        disclosure_level=outcome.level,
                        subject_hint=req.topic,
                    )
                )
        except Exception as e:
            logger.warning(f"[P6_E1] emit failed (fail-open): {e}", exc_info=True)

    def _generate_with_router(self, task: QueuedTask, req: DialogueRequest) -> str:
        """Генерация через ModelRouter. Не блокирует симуляцию (Правило 2 ТЗ)."""
        ctx = self._get_context(task.campaign_id, task.owner_id)

        # L-05 FIX: Резолвим target_id в имя для LLM, чтобы избежать утечки ID в реплики
        _target_ctx = self._get_context(task.campaign_id, req.target_id) if req.target_id else {}
        _target_name = _target_ctx.get("name", req.target_id)

        # L-04: Жёсткий system prompt с языковыми правилами
        system_prompt = (
            "Ты — NPC в мире ENIGMA (тёмное фэнтези). Твоя задача — сказать одну короткую реплику (1-2 предложения). "
            "Говори ТОЛЬКО на русском языке. Не используй китайские иероглифы, английский текст или системные теги. "
            "Не описывай свои действия (например, 'идёт к двери'). Только прямая речь. "
            "Не упоминай игрока, симуляцию, интерфейс или механики игры. "
            "Оставайся в образе своего персонажа. "
            f"Тема разговора: {req.topic}. Намерение: {req.intent_type}."
        )

        # T-02: Добавляем crystallized beliefs в промпт, чтобы LLM знала отношение NPC
        _beliefs_text = ""
        if self._belief_store:
            _all_beliefs = self._belief_store.get_beliefs(task.owner_id)
            _target_beliefs = [b for b in _all_beliefs if b.source_id == req.target_id]

            _TRAIT_TO_TEXT = {
                "fear": "Ты боишься",
                "trust": "Ты доверяешь",
                "loyalty": "Ты предан",
                "anger": "Ты злишься на",
            }
            for b in _target_beliefs:
                _phrase = _TRAIT_TO_TEXT.get(b.trait, f"Ты относишься к {_target_name} как к {b.trait}")
                _beliefs_text += f"{_phrase} {_target_name} (уверенность: {b.weight:.2f}). "

        # T-04: Извлекаем npc_npc_context (историю взаимодействий с целью) из DialogueRequest
        _history_text = ""
        if getattr(req, "npc_npc_context", ""):  # noqa: ENIGMA002
            _history_text = f"Твои воспоминания об этой встрече: {req.npc_npc_context} "

        # BUG-DL-02 FIX: Инъекция STM-блока (контекст текущего разговора)
        _stm_text = ""
        if self._memory_manager is not None and task.campaign_id:
            _stm_text = self._memory_manager.get_stm_prompt_block_pair(
                task.campaign_id, task.owner_id, req.target_id
            )
        
        # Hard Contract (Принцип 2): Нет STM -> нельзя говорить canonical dialogue
        # Разрешаем только первый ход (intent_type="greeting"), чтобы установить контакт
        # Исключение: claim-producing интенты (warn, intimidate) не требуют контекста диалога.
        if not _stm_text and req.intent_type not in ("greeting", "approach") and requires_dialogue_context(req.intent_type):
            logger.warning(f"[DIALOGUE_EXEC] No STM for {task.owner_id} -> {req.target_id}, "
                           f"intent '{req.intent_type}' demoted to 'approach' (auto-recover).")
            from dataclasses import replace as _dc_replace
            req = _dc_replace(req, intent_type="approach")
        
        if _stm_text:
            _history_text += f"\n[Контекст текущего разговора]\n{_stm_text}\n"

        # V8-DLG-10 FIX: Используем prepared_prompt (из VerbalizationContext) или fallback на ручную сборку
        if req.prepared_prompt:
            user_prompt = req.prepared_prompt
        else:
            # L-03 FIX: Добавляем voice_profile, backstory, author_notes для уникального голоса
            user_prompt = (
                f"Твоё имя: {ctx.get('name', task.owner_id)}. "
                f"Краткое описание твоей натуры: {ctx.get('description', 'неизвестно')}. "
            )
            if ctx.get("voice_profile"):
                user_prompt += f"Твоя манера речи: {ctx['voice_profile']}. "
            if ctx.get("backstory"):
                user_prompt += f"Твоё прошлое: {ctx['backstory']}. "
            if ctx.get("author_notes"):
                user_prompt += f"Важные ограничения: {ctx['author_notes']}. "

        # Динамическая часть (добавляется всегда, так как STM и beliefs могли измениться)
        user_prompt += (
            f"Ты обращаешься к: {_target_name}. "
            f"{_beliefs_text}"
            f"{_history_text}"
            "Скажи свою реплику:"
        )

        try:
            from app.services.llm.router import GenerationParams
            raw = self._router.request_for_agent(
                agent_name="npc",
                prompt=user_prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=100)
            )

            # L-02: Валидация ответа LLM (отсечение китайского, английского, 4-й стены)
            validation = self._validator.validate(raw)
            if validation.is_fallback:
                # IPT-CLEANUP: WARNING → INFO. IPT использует fallback/stub LLM, который может возвращать не-русский текст.
                # В production это останется WARNING, но для IPT-лога это ожидаемый шум.
                logger.info(f"[DIALOGUE_EXEC] LLM response rejected ({validation.violation}). Using fallback.")

            return validation.text
        except Exception as e:
            logger.error(f"[DIALOGUE_EXEC] LLM call failed: {e}. Raising exception to prevent silent failure.")
            raise

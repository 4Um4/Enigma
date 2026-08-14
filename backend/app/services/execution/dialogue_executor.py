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
from app.domain.execution import Artifact, QueuedTask

logger = logging.getLogger(__name__)


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
    ):
        self._router = router
        self._memory_manager = memory_manager
        self._get_context = context_provider or (
            lambda npc_id, camp_id: {"name": npc_id, "description": ""}
        )
        self._belief_store = belief_store
        self._confession_parser = confession_parser
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

        # Если роутер не задан (sandbox/test), возвращаем заглушку
        if self._router is None:
            logger.warning("[DIALOGUE_EXEC] ModelRouter is None! Fallback to stub.")
            text = f"[Заглушка] {task.owner_id} обращается к {req.target_id} по теме: '{req.topic}'"
        else:
            try:
                text = self._generate_with_router(task, req)
            except DialogueContractViolation as e:
                logger.warning(f"[DIALOGUE_EXEC] Contract violated: {e}")
                yield Artifact(
                    task_id=task.task_id,
                    success=False,
                    result_type="error",
                    data={},
                    error_message=str(e),
                )
                return

        if not text:
            yield Artifact(
                task_id=task.task_id,
                success=False,
                result_type="error",
                data={},
                error_message="LLM failed or returned empty text (stub avoided)."
            )
            return

        # V8-MVP-12 FIX: Парсим ответ NPC на предмет признаний
        if self._confession_parser:
            try:
                self._confession_parser.parse_and_record(
                    npc_id=task.owner_id,
                    reply_text=text,
                    tick=task.tick, # Используем поле tick из QueuedTask
                    target_id=req.target_id
                )
            except Exception as e:
                logger.error(f"[DIALOGUE_EXEC] ConfessionParser failed: {e}", exc_info=True)

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
            },
        )

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
        if getattr(req, "npc_npc_context", ""):
            _history_text = f"Твои воспоминания об этой встрече: {req.npc_npc_context} "

        # BUG-DL-02 FIX: Инъекция STM-блока (контекст текущего разговора)
        _stm_text = ""
        if self._memory_manager is not None and task.campaign_id:
            _stm_text = self._memory_manager.get_stm_prompt_block_pair(
                task.campaign_id, task.owner_id, req.target_id
            )
        
        # Hard Contract (Принцип 2): Нет STM -> нельзя говорить canonical dialogue
        # Разрешаем только первый ход (intent_type="greeting"), чтобы установить контакт
        if not _stm_text and req.intent_type not in ("greeting", "approach"):
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
                logger.warning(f"[DIALOGUE_EXEC] LLM response rejected ({validation.violation}). Using fallback.")

            return validation.text
        except Exception as e:
            logger.error(f"[DIALOGUE_EXEC] LLM call failed: {e}. Raising exception to prevent silent failure.")
            raise

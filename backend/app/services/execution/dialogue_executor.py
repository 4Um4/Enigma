"""
path: /backend/app/services/execution/dialogue_executor.py
Назначение: Исполнитель задач типа DIALOGUE. Вызывает LLM (или заглушку) и возвращает артефакт.
Зависимости: app.domain.execution, app.domain.communication
Основные сущности: DialogueExecutor
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

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
        router: Any = None,
        context_provider: Optional[Callable[[str, str], dict]] = None,
        belief_store: Any = None,
        memory_manager: Any = None,
        confession_parser: Any = None,  # V8-MVP-12 FIX
        discovery_bridge: Any = None,  # P6/E1 (S255): Bridge — владелец перехода
        npc_states_provider: Any = None,  # P6/E1: Callable[[cid], list[dict]]
        relationship_provider: Any = None,  # P6/E1: Callable[[cid, k, r], dict]
        subject_resolver: Any = None,  # P6/E1: Callable[[topic], SubjectRef]
        epistemic_store: Any = None,  # COGNITIVE-CONTINUITY-01: for cognition block
    ) -> None:
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
        self._epistemic_store = epistemic_store  # COGNITIVE-CONTINUITY-01
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
        discovery_bridge: Any = None,
        npc_states_provider: Any = None,
        relationship_provider: Any = None,
        subject_resolver: Any = None,
        epistemic_store: Any = None,
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
        if epistemic_store is not None:
            self._epistemic_store = epistemic_store

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
        # A1 (RE-D2, вердикт Мастера): provenance текста — по ПРОИСХОЖДЕНИЮ,
        # не эвристикой по содержимому. "llm" ставится только в LLM-ветке;
        # детерминированная материализация (stub / requires_llm=False) содержит
        # machine-id латиницей BY DESIGN — LANG_LEAK (замок S292) к ней не
        # применяется: ложный ретрай звал LLM с потока петли → RE-D2.
        _text_source = "deterministic"
        logger.debug(
            f"[DIALOGUE_EXEC] Executing task for {task.owner_id} -> {req.target_id} on topic '{req.topic}'"
        )

        # S197: Извлекаем Proposition на верхнем уровне, чтобы он был доступен во всех ветках
        _proposition = getattr(req, "proposition", None)  # noqa: ENIGMA002

        # P7-A: вердикт disclosure выносится ДО вербализации, РОВНО ОДИН
        # раз на реплику (инвариант Мастера). LLM вербализует, не решает.
        _verdict = self._resolve_disclosure_verdict(task, req)

        # Если роутер не задан (sandbox/test), возвращаем заглушку
        if self._router is None:
            logger.warning("[DIALOGUE_EXEC] ModelRouter is None! Fallback to stub.")
            text = f"[Заглушка] {task.owner_id} обращается к {req.target_id} по теме: '{req.topic}'"
        elif not requires_llm_materialization(req.intent_type) and not (
            req.intent_type == "spread_rumor" and _proposition is not None
        ):
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
                _text_source = "llm"
                text = self._generate_with_router(task, req, _verdict)
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
                # B5-D2 FIX: spread_rumor + proposition — fallback to deterministic stub
                # when LLM fails. Social event (NPC_SPOKE + COMMUNICATION_CLAIM) must
                # complete regardless of LLM availability. Proposition is preserved
                # in artifact.data["proposition"] for materializer.
                if req.intent_type == "spread_rumor" and _proposition is not None:
                    # Stage B Observability: preserve llm_materialization_failed
                    try:
                        from app.services.logging_tools import jsonl_log
                        jsonl_log({
                            "level": "ERROR",
                            "agent": "template_fallback",
                            "fallback_reason": "llm_materialization_failed",
                            "npc_id": task.owner_id,
                            "intent_type": req.intent_type,
                            "target_id": req.target_id,
                            "error": str(e),
                        })
                    except Exception:
                        logger.debug("[OBS] llm_materialization_failed observability skipped (non-critical)")
                    # B5-D2 FIX: log that fallback was used
                    try:
                        from app.services.logging_tools import jsonl_log
                        jsonl_log({
                            "level": "WARNING",
                            "agent": "spread_rumor_fallback",
                            "fallback_reason": "spread_rumor_fallback_used",
                            "npc_id": task.owner_id,
                            "intent_type": req.intent_type,
                            "target_id": req.target_id,
                            "error": str(e),
                        })
                    except Exception:
                        logger.debug("[OBS] spread_rumor_fallback_used observability skipped (non-critical)")
                    logger.warning(
                        f"[DIALOGUE_EXEC] LLM failed for spread_rumor, "
                        f"falling back to deterministic stub: {e}"
                    )
                    text = f"[spread_rumor] {task.owner_id} -> {req.target_id}: {req.topic}"
                    # Don't return — continue to yield SUCCESS Artifact (L269-283)
                else:
                    # Original error handling for other intents
                    try:
                        from app.services.logging_tools import jsonl_log
                        jsonl_log({
                            "level": "ERROR",
                            "agent": "template_fallback",
                            "fallback_reason": "llm_materialization_failed",
                            "npc_id": task.owner_id,
                            "intent_type": req.intent_type,
                            "target_id": req.target_id,
                            "error": str(e),
                        })
                    except Exception:
                        logger.debug("[OBS] llm_materialization_failed observability skipped (non-critical)")
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

        # №3 (S292): language-leak gate. Русскоязычный мир — латинные вставки
        # LLM («Give me a name») ломают нарратив. Честная деградация (ADR-113):
        # измерить → один ретрай с усиленной директивой → при повторе лог+паблиш
        # как есть (не маскируем, не режем слова).
        import re as _re

        def _latin_share(s: str) -> float:
            _words = [w for w in _re.split(r"\s+", s.strip()) if w]
            if not _words:
                return 0.0
            _latin = sum(1 for w in _words if _re.search(r"[A-Za-z]", w))
            return _latin / len(_words)

        # A1: LANG_LEAK гейтит ТОЛЬКО текст LLM-происхождения. Детерминированный
        # текст публикуется как есть (machine-id ≠ language leak).
        if _text_source == "llm" and _latin_share(text) >= 0.25:
            logger.warning(
                f"[LANG_LEAK] {task.owner_id}: latin_share={_latin_share(text):.2f} "
                f"text={text[:80]!r} — retry with reinforced directive"
            )
            _retry_timer = None  # пред-связывание: finally ссылается всегда
            try:
                import threading as _th
                _retry_timer = _th.Timer(_L_TIMEOUT_SEC, self._router._abort_generation)
                _retry_timer.start()
                _reinforced = (  # noqa: ENIGMA001
                    f"{req.prepared_prompt}\n\n[СТРОГО: ответ ТОЛЬКО кириллицей. "
                    f"Ни одного латинского слова. Предыдущая попытка отклонена.]"
                ) if req.prepared_prompt else None
                _retry_req = (
                    type(req)(**{**req.__dict__, "prepared_prompt": _reinforced})
                    if hasattr(req, "__dict__")
                    else req
                )
                text = self._generate_with_router(task, _retry_req, _verdict)
            except Exception as _retry_err:
                logger.error(f"[LANG_LEAK] retry failed for {task.owner_id}: {_retry_err}")
            finally:
                if _retry_timer is not None:
                    try:
                        _retry_timer.cancel()
                    except Exception as _cancel_err:
                        # L4 (S292): cancel-сбой логируется; ретрай уже завершён —
                        # исходная генерация не деградирует от этого отказа.
                        logger.debug(f"[LANG_LEAK] retry timer cancel skipped: {_cancel_err}")
        # A1: LANG_LEAK гейтит ТОЛЬКО текст LLM-происхождения. Детерминированный
        # текст публикуется как есть (machine-id ≠ language leak).
        if _text_source == "llm" and _latin_share(text) >= 0.25:
            logger.error(
                f"[LANG_LEAK] {task.owner_id}: retry still leaked "
                f"(share={_latin_share(text):.2f}) — publishing as-is (honest degradation)"
            )

        # P6/E1 (S255): эмит — ТОЧКА УСПЕШНОЙ ДОСТАВКИ (DISCOVERY IS
        # DELIVERY: решение P5 материально только при доставленной
        # реплике; error-ветки выше не эмитят). Заменил вызов парсера
        # (V8-MVP-12): текст НЕ источник discovery — PROVENANCE, NOT
        # STRINGS. Писатель :109 — отдельным шагом ПОСЛЕ T8/T3.
        self._emit_dialogue_outcome(task, req, _verdict)

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

    def _resolve_disclosure_verdict(self, task: QueuedTask, req: DialogueRequest) -> Any:
        """P7-A: ЕДИНСТВЕННОЕ вычисление вердикта на реплику — ДО слов.
        Гейты E1 (S255) сохранены дословно: bridge, target=='player',
        провайдеры, NPCState(owner), fail-open. Возвращает DisclosureOutcome
        или None (unwired/нет знания/ошибка = без эмита, как в E1)."""
        if self._discovery_bridge is None:
            return None
        if (req.target_id or "") != "player":
            return None
        if self._npc_states_provider is None or self._subject_resolver is None:
            logger.info("[P6_E1] wiring неполный (provider/resolver) — эмит пропущен")
            return None
        try:
            owner_raw = None
            for _n in (self._npc_states_provider(task.campaign_id) or []):
                if isinstance(_n, dict):
                    if (_n.get("npc_id") or _n.get("id")) == task.owner_id:
                        owner_raw = _n
                        break
            if owner_raw is None:
                logger.info(f"[P6_E1] NPCState не найден: {task.owner_id}")
                return None
            owner_state = load_l2_state_from_runtime_dict(owner_raw)
            subject = self._subject_resolver(req.topic)
            items = retrieve_knowledge(owner_state, subject)
            if not items:
                return None
            rel: dict = {}
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
            # P5 — один item на реплику: инвариант Мастера «один вердикт».
            # (E1 итерировал items; смена политики зафиксирована в досье.)
            return decide_disclosure(owner_state, recipient, rel, items[0], ctx)
        except Exception as e:
            logger.warning(f"[P6_E1] verdict resolve failed (fail-open): {e}", exc_info=True)
            return None

    def _emit_dialogue_outcome(self, task: QueuedTask, req: DialogueRequest, verdict: Any) -> None:
        """P7-A: эмит из УЖЕ вычисленного вердикта (точка доставки — та же,
        что в E1: DISCOVERY IS DELIVERY). Повторное вычисление вердикта
        здесь = DOUBLE TRUTH — запрещено (инвариант Мастера)."""
        if verdict is None or self._discovery_bridge is None:
            return
        if (req.target_id or "") != "player":
            return
        try:
            self._discovery_bridge.process(
                SurfaceEvent(
                    kind=SurfaceKind.DIALOGUE_OUTCOME,
                    tick=task.tick,
                    source_id=task.owner_id,
                    secret_id=verdict.secret_id,
                    disclosure_level=verdict.level,
                    subject_hint=req.topic,
                )
            )
        except Exception as e:
            logger.warning(f"[P6_E1] emit failed (fail-open): {e}", exc_info=True)

    def _format_causal_context(self, ledger: list) -> str:
        """CC-09: Format causal_ledger entries for LLM prompt.

        Показывает NPC ПОЧЕМУ его состояние изменилось:
        причина (source) + величина (delta) + тик.
        Не новый SSOT — читает существующий causal_ledger.
        """
        _FIELD_MAP = {
            "trust": "доверие", "fear": "страх", "hp": "здоровье",
            "stress": "напряжение", "anger": "гнев",
        }
        lines = []
        for entry in ledger[-10:]:
            if not isinstance(entry, dict):
                continue
            _field = str(entry.get("field", "") or "")
            _source = str(entry.get("source", "") or "")
            if not _field and not _source:
                continue  # CC-09: skip empty entries (no fabrication)
            _field_text = _FIELD_MAP.get(_field, _field)
            _delta = float(entry.get("delta", 0.0) or 0.0)
            _tick = entry.get("tick", 0)
            _sign = "+" if _delta > 0 else ""
            lines.append(
                f"  • {_field_text} изменилось на {_sign}{_delta:.1f} "
                f"(причина: {_source}, тик: {_tick})"
            )
        if lines:
            return "[Причины изменений твоего состояния]:\n" + "\n".join(lines)
        return ""

    def _format_contradictions(self, agent_id: str, campaign_id: str) -> str:
        """Priority 4 Part A: Format polarity=False records (negations/contradictions).

        Показывает NPC противоречивые сведения — опровержения:
        "Ты слышал, что X НЕ оскорблял Y (от Z, уверенность: 0.30)"
        Не разрешает противоречие — только expose для LLM.
        Не новый SSOT — читает существующий EpistemicStore.
        """
        if self._epistemic_store is None:
            return ""
        try:
            records = self._epistemic_store.get_all_for_agent(agent_id)
        except Exception as e:
            print(f"[DIALOGUE_EXECUTOR] _epistemic_store.get_all_for_agent(agent_id={agent_id}) failed: {e}")
            return ""
        negations = [r for r in records if not r.proposition.polarity]
        if not negations:
            return ""
        _PRED_MAP = {
            "insulted": "оскорблял", "stole": "воровал у",
            "attacked": "нападал на", "helped": "помогал",
            "asserts": "утверждал",
        }
        lines = []
        for r in negations[-5:]:
            _subj = r.proposition.subject_id
            _pred = r.proposition.predicate.value
            _obj = r.proposition.object_id
            _source = r.source_id
            _conf = r.confidence
            _subj_name = self._get_context(_subj, campaign_id).get("name", _subj) if _subj else _subj
            _obj_name = self._get_context(_obj, campaign_id).get("name", _obj) if _obj else _obj
            _source_name = self._get_context(_source, campaign_id).get("name", _source) if _source else _source
            _pred_text = _PRED_MAP.get(_pred, str(_pred))
            lines.append(
                f"  • Ты слышал, что {_subj_name} НЕ {_pred_text} {_obj_name} "
                f"(от {_source_name}, уверенность: {_conf:.2f})"
            )
        if lines:
            return "[Противоречивые сведения, о которых ты знаешь]:\n" + "\n".join(lines)
        return ""

    @staticmethod
    def _verdict_directive(verdict: Any) -> str:
        """P7-A: сериализация вердикта в поведенческую директиву промпта.
        P5 решил ЧТО; P7 вербализует КАК; LLM не решает (DisclosureLevel)."""
        from app.domain.disclosure import DisclosureLevel as _DL

        if verdict is None:
            return ""
        _texts = {
            _DL.REVEAL: "ты решил полностью раскрыть это знание — расскажи о нём прямо",
            _DL.PARTIAL: "ты решил сказать лишь часть — намекни на суть, не раскрывая деталей",
            _DL.HINT: "ты решил лишь намекнуть — не раскрывай, о чём речь",
            _DL.DENY: "ты решил уклониться от ответа — не раскрывай знание, уйди от темы",
            _DL.REDIRECT: "ты решил сменить тему — мягко уведи разговор в сторону",
        }
        _t = _texts.get(verdict.level)
        if _t is None:
            return ""
        return f"[ДИРЕКТИВА РАСКРЫТИЯ: {verdict.level.value.upper()}] {_t}."

    def _generate_with_router(self, task: QueuedTask, req: DialogueRequest, verdict: Any = None) -> str:
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
        if not _stm_text and req.intent_type not in ("greeting", "approach") and requires_dialogue_context(req.intent_type) and not getattr(req, "proposition", None):
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

        # COGNITIVE-CONTINUITY-01: claim verbalization — факт, которым ты делишься.
        # LLM получает клейм и сама решает, как его передать своими словами.
        _proposition = getattr(req, "proposition", None)  # extract from DialogueRequest
        _claim_block = ""
        if _proposition is not None:
            _pred_map = {"insulted": "оскорбил", "stole": "украл у", "attacked": "напал на", "helped": "помог"}
            if isinstance(_proposition, dict):
                _subj_id = _proposition.get("subject_id", "")
                _pv = _proposition.get("predicate", "")
                _obj_id = _proposition.get("object_id", "")
            else:
                _subj_id = _proposition.subject_id
                _pv = getattr(_proposition.predicate, "value", str(_proposition.predicate))
                _obj_id = _proposition.object_id
            # COGNITIVE-CONTINUITY-01: resolve IDs to game names via _get_context
            # (same mechanism as CognitionContextResolver — не второй resolver)
            _subj_name = self._get_context(task.campaign_id, _subj_id).get("name", _subj_id) if _subj_id else _subj_id
            _obj_name = self._get_context(task.campaign_id, _obj_id).get("name", _obj_id) if _obj_id else _obj_id
            _pred_text = _pred_map.get(_pv, str(_pv))
            _claim_block = f"[Факт, которым ты делишься]: {_subj_name} {_pred_text} {_obj_name}. Передай это собеседнику своими словами.\n"

        # Динамическая часть (добавляется всегда, так как STM и beliefs могли измениться)
        user_prompt += (
            f"Ты обращаешься к: {_target_name}. "
            f"{_beliefs_text}"
            f"{_history_text}"
            f"{_claim_block}"
        )

        # COGNITIVE-CONTINUITY-01: cognition block — what NPC knows (beliefs + provenance)
        # Same CognitionContextResolver that feeds DMFrame — one mechanism, all consumers.
        if self._epistemic_store is not None and self._memory_manager is not None:
            try:
                from app.services.npc.cognition_context import CognitionContextResolver
                _cog = CognitionContextResolver(
                    self._memory_manager,
                    epistemic_store=self._epistemic_store,
                    context_provider=lambda npc_id: self._get_context(task.campaign_id, npc_id),
                )
                _cog_block = _cog.resolve_block(task.owner_id, req.target_id or "player")
                if _cog_block:
                    user_prompt += "\n" + _cog_block + "\n"
            except Exception as _cog_e:
                logger.warning(f"[DIALOGUE_EXEC] cognition block failed: {_cog_e}")

        # CC-09: causal context — WHY state changed (causal_ledger -> LLM prompt).
        # Не новый SSOT — читает существующий NPCState.causal_ledger (ADR-CAUSAL-SPINE).
        # NPC может объяснить изменение доверия/страха конкретным событием.
        if self._npc_states_provider is not None:
            try:
                _states = self._npc_states_provider(task.campaign_id)
                _npc_dict = next(
                    (s for s in (_states or [])
                     if s.get("npc_id") == task.owner_id or s.get("id") == task.owner_id),
                    None,
                )
                if _npc_dict:
                    _ledger = _npc_dict.get("causal_ledger", [])
                    if _ledger:
                        _causal_text = self._format_causal_context(_ledger)
                        if _causal_text:
                            user_prompt += "\n" + _causal_text + "\n"
            except Exception as _ce:
                logger.warning(f"[DIALOGUE_EXEC] causal context failed: {_ce}")

        # Priority 4 Part A: contradictions — polarity=False records visible to NPC.
        # NPC видит противоречивые сведения (опровержения) — не разрешает, а учитывает.
        # Не новый SSOT — читает существующий EpistemicStore (ADR-O-354).
        if self._epistemic_store is not None:
            try:
                _contr_text = self._format_contradictions(task.owner_id, task.campaign_id)
                if _contr_text:
                    user_prompt += "\n" + _contr_text + "\n"
            except Exception as _ce2:
                logger.warning(f"[DIALOGUE_EXEC] contradictions failed: {_ce2}")

        user_prompt += "Скажи свою реплику:"

        # P7-A: директива вердикта в промпт — LLM вербализует, не решает
        _directive = self._verdict_directive(verdict)
        if _directive:
            user_prompt += f" {_directive}"

        # B4-R6: Full prompt capture (observability only — no game logic change)
        try:
            import time
            from app.services.logging_tools import log_full_prompt
            log_full_prompt({
                "event": "llm_request",
                "request_id": task.task_id,
                "speaker_id": task.owner_id,
                "agent_name": "npc",
                "tick": getattr(task, "tick", None),
                "campaign_id": task.campaign_id,
                "intent_type": req.intent_type,
                "topic": req.topic,
                "target_id": req.target_id,
                "proposition": getattr(req, "proposition", None),
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": 100,
                "timestamp": time.time(),
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "token_count": "unavailable — use llama-server /tokenize for exact counts",
            })
        except Exception:
            logger.debug("[OBS] full prompt capture skipped (request)")

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

            # B4-R6: Response capture
            try:
                from app.services.logging_tools import log_full_prompt
                log_full_prompt({
                    "event": "llm_response",
                    "request_id": task.task_id,
                    "speaker_id": task.owner_id,
                    "raw_response": raw,
                    "validated_text": validation.text,
                    "validation_fallback": validation.is_fallback,
                    "validation_violation": getattr(validation, "violation", None),
                })
            except Exception:
                logger.debug("[OBS] response capture skipped")
            return validation.text
        except Exception as e:
            logger.error(f"[DIALOGUE_EXEC] LLM call failed: {e}. Raising exception to prevent silent failure.")
            raise

"""
Декомпозитор биографии (ADR-O-420, CCH-2).

Файл: backend/app/services/chronicle/biography_decomposer.py
Назначение: фрагмент автора → BiographyDecomposition (transient, не канон).
Зависимости: app.domain.chronicle; LLM — через ModelRouter (VRAM-семафор).
Основные сущности: BiographyDecomposer

ДЕТЕРМИНИЗМ (прецеденты, второй механизм запрещён):
- temperature=0.0; seed НЕ дублируется здесь — за ним llama_cpp_provider
  (_complete_via_server, KernelRNG salt=prompt) — тот же путь, что compressor;
- retry ×1 при DecompositionError (FR-2.2: retry → «не разобрано»);
- DEBT-CHRONICLE-REPLAY: replay-кэш промптов (llm_cache.LLMCache.record)
  не подключён — рекордер привязан к тик-сессии, редактор вне тика.
  Подключение — отдельная задача контура replay (маркер для владельца).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Final, List, Optional

from app.domain.chronicle import (
    BiographyDecomposition,
    DecompositionItem,
)
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
    DecompositionError,
)

# S371.3-GBNF: GBNF grammar для декомпозиции хроник (config/chronicle_decompose.gbnf).
# Ленивая загрузка с кэшем; None при отсутствии — fallback на /v1/chat/completions.
_GBNF_PATH = Path(__file__).resolve().parents[4] / "config" / "chronicle_decompose.gbnf"
_grammar_cache: Optional[str] = None


def _load_chronicle_grammar() -> Optional[str]:
    """S371.3-GBNF: загружает GBNF грамматику для декомпозиции хроник.

    Ленивая загрузка с кэшем (грамматика статична). None если файл отсутствует
    — декомпозер откатывается на /v1/chat/completions (existing path).
    """
    global _grammar_cache
    if _grammar_cache is not None:
        return _grammar_cache
    if not _GBNF_PATH.exists():
        logger.warning(f"[CHRONICLE_DECOMPOSER] GBNF grammar not found: {_GBNF_PATH} — fallback to /v1/chat/completions")
        return None
    _grammar_cache = _GBNF_PATH.read_text(encoding="utf-8")
    return _grammar_cache

logger = logging.getLogger(__name__)


def _default_roster_provider() -> Dict[str, str]:
    """S367: lazy default roster source — npc_loader.get_display_names.
    Единственный источник истины; per-call fetch (config правится вне тик-сессии).
    Ленивый импорт (цикл-безопасно)."""
    from app.services.npc.npc_loader import get_display_names
    return get_display_names()


# Детерминированный препарсинг возрастных якорей (FR-1.2/FR-2.x, Fast Path)
_AGE_ANCHOR: Final[re.Pattern] = re.compile(
    r"\[\s*(\d{1,3})\s*лет\s*\]|"            # [8 лет]
    r"в\s+(\d{1,3})\s*лет|"                  # в 14 лет
    r"с\s+(\d{1,3})\s*лет|"                  # с 12 лет
    r"к\s+(\d{1,3})\s*годам|"                # к 23 годам (S365)
    r"в\s+(\d{1,3})\s*год(а|у)?\b|"          # в 24 года / в 24 год / в 24 (S365)
    r"\bв\s+(\d{1,3})\b(?=\s+(?:он|она|они|застал|пошёл|пошла|начал|начала))",  # «В 24 застал» (S365)
    re.IGNORECASE
)


@dataclass(frozen=True)
class DecomposeResult:
    """Результат разбора: items или честная ошибка (без молчаливых фолбэков).

    S371.0: raw_response сохраняется при failure для диагностики JSON-ошибок
    (классификация truncation/unicode/quote/escape/unknown)."""

    ok: bool
    items: List[DecompositionItem]
    error: Optional[str] = None
    age_anchors: Optional[List[int]] = None
    raw_response: Optional[str] = None  # S371.0: сырой ответ LLM при failure (диагностика)

    @staticmethod
    def failure(error: str, raw_response: Optional[str] = None) -> "DecomposeResult":
        return DecomposeResult(ok=False, items=[], error=error, raw_response=raw_response)

    @staticmethod
    def success(items: List[DecompositionItem], age_anchors: List[int]) -> "DecomposeResult":
        return DecomposeResult(ok=True, items=items, age_anchors=age_anchors)


class BiographyDecomposer:
    """LLM-декомпозитор фрагмента. Канон не пишет — только предлагает (П1)."""

    PROMPT_FILE = "backend/prompts/chronicle_decompose_system.txt"

    def __init__(
        self,
        router: Optional[Any] = None,
        roster_provider: Optional[Any] = None,
    ) -> None:
        # Router инъекцией (тестируемость); ленивая загрузка — как у DM.
        # S367: roster_provider — callable () -> Dict[str, str]; None -> lazy
        # get_display_names (единственный источник истины, npc_loader).
        self._router = router
        self._system_prompt: Optional[str] = None
        self._roster_provider = roster_provider

    def _ensure_prompt(self) -> str:
        if self._system_prompt is None:
            from app.services.verbalization.prompt_loader import load_system_prompt
            self._system_prompt = load_system_prompt(self.PROMPT_FILE)
        return self._system_prompt

    @staticmethod
    def extract_age_anchors(text: str) -> List[int]:
        """Legacy: плоский список int. Deprecated — используйте extract_age_anchors_typed.

        Сохранён для backward-compat (тесты, S368 fallback). Возвращает только
        значения без различения CURRENT_AGE/DURATION/AT_AGE.
        """
        from app.services.chronicle.age_anchor import extract_age_anchors_typed
        return [a.value for a in extract_age_anchors_typed(text)]

    def build_user_prompt(
        self,
        fragment: str,
        age_anchors: List[int],
        roster: Optional[Dict[str, str]] = None,
    ) -> str:
        """Типизированные подсказки LLM (CCH-12 Point 1).

        S365: hint «не найдено» не протекает в prompt — иначе LLM повторяет
        его в summary (CoT-утечка). S367: roster (опц.) — снимок известных NPC.
        """
        # CCH-12 Point 1: типизированные anchors. Если передан плоский List[int]
        # (legacy), конвертируем в AMBIGUOUS — LLM получит явный сигнал, что
        # семантика якоря не установлена, и не должна выдумывать.
        from app.services.chronicle.age_anchor import (
            AgeAnchor, AgeAnchorKind, age_anchors_to_hint,
        )
        if age_anchors and not isinstance(age_anchors[0], AgeAnchor):
            # Legacy: плоский список int → AMBIGUOUS anchors
            typed_anchors = [
                AgeAnchor(value=v, kind=AgeAnchorKind.AMBIGUOUS, source_span=str(v))
                for v in age_anchors
            ]
        else:
            typed_anchors = age_anchors

        hints = age_anchors_to_hint(typed_anchors) if typed_anchors else ""
        if roster:
            names = ", ".join(sorted(str(v) for v in roster.values() if isinstance(v, str)))
            roster_block = (
                "ИЗВЕСТНЫЕ NPC (roster): " + names + ".\n"
                "Если target_hint не сопоставляется ОДНОЗНАЧНО ни с одним именем выше — "
                "задай ClarificationQuestion (SELECT_EXISTING_NPC/CREATE_NEW_NPC/"
                "UNKNOWN_PERSON/LEAVE_WHITE_SPOT).\n\n"
            )
        else:
            roster_block = ""
        return f"{hints}{roster_block}ФРАГМЕНТ:\n{fragment.strip()}"

    async def decompose(self, chronicle_id: str, fragment_ord: int, fragment: str) -> DecomposeResult:
        """
        Фрагмент → DecomposeResult. LLM через router.request(FACT_EXTRACTION);
        один retry; DecompositionError → failure() с текстом (не исключение).
        """
        if not fragment.strip():
            return DecomposeResult.failure("Пустой фрагмент")
        # CCH-12 Point 1: типизированные anchors. extract_age_anchors_typed
        # возвращает List[AgeAnchor]; конвертируем для DecomposeResult, который
        # пока хранит плоский List[int] (backward-compat response API).
        from app.services.chronicle.age_anchor import extract_age_anchors_typed
        typed = extract_age_anchors_typed(fragment)
        anchors = [a.value for a in typed]
        # Сохраняем типизированные anchors в result для downstream (промпт уже
        # их использует через build_user_prompt; response отдаёт плоский список).
        self._last_typed_anchors = typed
        roster = (self._roster_provider or _default_roster_provider)()
        user_prompt = self.build_user_prompt(fragment, anchors, roster)
        from app.services.llm.router import ModelRouter  # ленивый (цикл-безопасно)

        router = self._router or ModelRouter()
        system_prompt = self._ensure_prompt()
        last_error = ""
        import asyncio as _aio

        _POOL_WAITS = (1.0, 3.0, 5.0)  # сек пауз при «пул занят» (Q4_K_M выдыхает на серии)
        _pool_retry = 0
        for attempt in (1, 2):
            try:
                from app.services.llm.provider import GenerationParams

                # S371.3-GBNF: GBNF grammar через /completion endpoint.
                # Загружается один раз (лениво), передаётся в GenerationParams.grammar.
                # Провайдер ветвится: grammar задан → /completion, иначе /v1/chat/completions.
                _grammar = _load_chronicle_grammar()
                params = GenerationParams(
                    temperature=0.0,
                    max_tokens=2048,
                    response_format={"type": "json_object"},  # S371.3-pre: оставлен для совместимости (llama_cpp игнорирует)
                    grammar=_grammar,  # S371.3-GBNF: рабочий путь — /completion + grammar
                )
                raw = await router.request(
                    capability="fact_extraction",
                    prompt=user_prompt,
                    params=params,
                    system_prompt=system_prompt,
                )
                items = ChronicleDecompositionNormalizer.normalize(
                    raw, chronicle_id=chronicle_id, fragment_ord=fragment_ord, roster=roster
                )
                return DecomposeResult.success(items, anchors)
            except DecompositionError as e:
                last_error = str(e)
                last_raw = raw if 'raw' in locals() else None  # S371.0: сохранить сырой ответ для диагностики
                continue  # ровно один retry (FR-2.2)
            except RuntimeError as e:
                # L4: отказ пула виден на warn-уровне. «Пул занят» — возмущение
                # среды (LLM обрабатывает предыдущий запрос), НЕ приговор:
                # ждём и пробуем снова (вердикт Мастера «готов ждать»);
                # сдаёмся только после исчерпания пауз.
                if _pool_retry < len(_POOL_WAITS):
                    _w = _POOL_WAITS[_pool_retry]
                    _pool_retry += 1
                    logger.warning(
                        f"[CHRONICLE_DECOMPOSER] пул занят ({str(e)[:60]}) — пауза {_w}с, попытка {_pool_retry + 1}/4"
                    )
                    await _aio.sleep(_w)
                    continue  # тот же attempt, счётчик пул-ретраев отдельный
                logger.error(f"[CHRONICLE_DECOMPOSER] LLM-пул недоступен после ожидания: {e}")
                return DecomposeResult.failure(f"LLM-пул недоступен: {e}")
        return DecomposeResult.failure(
            f"Декомпозиция не удалась после retry: {last_error}",
            raw_response=last_raw if 'last_raw' in locals() else None,
        )

    def to_transient(self, chronicle_id: str, fragment_ord: int, result: DecomposeResult) -> BiographyDecomposition:
        """Transient-объект для UI (не персистится; не канон)."""
        return BiographyDecomposition(chronicle_id=chronicle_id, fragment_ord=fragment_ord, items=tuple(result.items))

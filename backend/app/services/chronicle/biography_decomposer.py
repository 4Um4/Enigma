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
from typing import Any, Dict, Final, List, Optional, cast

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

from app.services.chronicle.age_anchor import (
    AgeAnchor,
    AgeAnchorKind,
)


def validate_age_anchor_coverage(
    items: List["DecompositionItem"],
    age_anchors: List[AgeAnchor],
    fragment_ord: int,
    *,
    game_start_age: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """B (CCH-12 diagnostic): проверка отражения age_anchors в items.

    Возвращает список аномалий (пустой, если всё OK). Не меняет items,
    не блокирует pipeline, не создаёт EVENT автоматически.

    Проверяет:
    1. dangling_age_anchor — типизированный якорь (YEARS_AGO/DURATION/
       AT_AGE/SINCE_AGE) не отражён ни в одном item.
    2. years_ago_equals_current_age — YEARS_AGO == game_start_age
       (если game_start_age задан): LLM перепутала текущий возраст
       с years_ago.
    3. ambiguous_anchor_misused_as_years_ago (Fix 2) — EVENT.years_ago
       совпадает с AMBIGUOUS anchor value, и в age_anchors НЕТ YEARS_AGO
       с тем же значением. LLM интерпретировала «N лет» (текущий возраст)
       как «N лет назад».
    4. ambiguous_anchor_misused_as_duration (Fix 2) — то же для
       EVENT.duration_years.

    Не считает числовое совпадение окончательным доказательством ошибки
    (Мастер): сохраняет source_span и ordinal для ручной проверки.

    Args:
        items: нормализованные DecompositionItem (после normalize()).
        age_anchors: типизированные AgeAnchor из fragment.
        fragment_ord: для логирования.
        game_start_age: если задан — дополнительная проверка
            years_ago == game_start_age.
    """
    anomalies: List[Dict[str, Any]] = []

    # Снимок значений по типам якорей
    years_ago_values = {
        a.value for a in age_anchors if a.kind is AgeAnchorKind.YEARS_AGO
    }
    duration_values = {
        a.value for a in age_anchors if a.kind is AgeAnchorKind.DURATION
    }
    ambiguous_anchors = [
        a for a in age_anchors if a.kind is AgeAnchorKind.AMBIGUOUS
    ]

    # Проверка 1: dangling типизированных якорей
    for anchor in age_anchors:
        if anchor.kind is AgeAnchorKind.AMBIGUOUS:
            continue  # AMBIGUOUS не обязана отражаться в items

        covered = False
        for item in items:
            payload = item.draft_payload
            if anchor.kind is AgeAnchorKind.YEARS_AGO:
                if payload.get("years_ago") == anchor.value:
                    covered = True
                    break
            elif anchor.kind is AgeAnchorKind.DURATION:
                if payload.get("duration_years") == anchor.value:
                    covered = True
                    break
            elif anchor.kind in (AgeAnchorKind.AT_AGE, AgeAnchorKind.SINCE_AGE):
                if payload.get("age") == anchor.value:
                    covered = True
                    break

        if not covered:
            anomalies.append({
                "anomaly_type": "dangling_age_anchor",
                "fragment_ord": fragment_ord,
                "anchor_kind": anchor.kind.value,
                "anchor_value": anchor.value,
                "source_span": anchor.source_span,
                "severity": "warning",
                "hint": f"age_anchor {anchor.kind.value}={anchor.value} "
                        f"not reflected in any item",
            })

    # Проверка 2: years_ago == game_start_age (если задан)
    if game_start_age is not None and game_start_age > 50:
        for anchor in age_anchors:
            if (
                anchor.kind is AgeAnchorKind.YEARS_AGO
                and anchor.value == game_start_age
            ):
                anomalies.append({
                    "anomaly_type": "years_ago_equals_current_age",
                    "fragment_ord": fragment_ord,
                    "anchor_value": anchor.value,
                    "game_start_age": game_start_age,
                    "source_span": anchor.source_span,
                    "severity": "warning",
                    "hint": f"years_ago={anchor.value} == game_start_age="
                            f"{game_start_age} — LLM возможно перепутала "
                            f"текущий возраст с years_ago",
                })

    # Проверка 3 (Fix 2): AMBIGUOUS anchor → EVENT.years_ago
    # Если EVENT.years_ago совпадает с AMBIGUOUS anchor value,
    # и в age_anchors НЕТ YEARS_AGO с тем же значением —
    # LLM интерпретировала «N лет» как «N лет назад».
    for amb in ambiguous_anchors:
        # Пропускаем, если есть YEARS_AGO с тем же значением —
        # тогда это легитимное использование
        if amb.value in years_ago_values:
            continue

        for item in items:
            payload = item.draft_payload
            if (
                item.kind.value == "EVENT"
                and payload.get("years_ago") == amb.value
            ):
                anomalies.append({
                    "anomaly_type": "ambiguous_anchor_misused_as_years_ago",
                    "fragment_ord": fragment_ord,
                    "anchor_value": amb.value,
                    "source_span": amb.source_span,
                    "item_summary": payload.get("summary", ""),
                    "severity": "warning",
                    "hint": f"EVENT.years_ago={amb.value} совпадает с "
                            f"AMBIGUOUS anchor («{amb.source_span}»), "
                            f"но YEARS_AGO с тем же значением не извлечён. "
                            f"LLM возможно перепутала текущий возраст с "
                            f"years_ago. Требуется ручная проверка.",
                })

    # Проверка 4 (Fix 2): AMBIGUOUS anchor → EVENT.duration_years
    for amb in ambiguous_anchors:
        if amb.value in duration_values:
            continue

        for item in items:
            payload = item.draft_payload
            if (
                item.kind.value == "EVENT"
                and payload.get("duration_years") == amb.value
            ):
                anomalies.append({
                    "anomaly_type": "ambiguous_anchor_misused_as_duration",
                    "fragment_ord": fragment_ord,
                    "anchor_value": amb.value,
                    "source_span": amb.source_span,
                    "item_summary": payload.get("summary", ""),
                    "severity": "warning",
                    "hint": f"EVENT.duration_years={amb.value} совпадает с "
                            f"AMBIGUOUS anchor («{amb.source_span}»), "
                            f"но DURATION с тем же значением не извлечён. "
                            f"Требуется ручная проверка.",
                })

    return anomalies


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
        age_anchors: List[Any],  # List[int] legacy или List[AgeAnchor] typed
        roster: Optional[Dict[str, str]] = None,
        *,
        prior_context: str = "",
        npc_id: str = "",
    ) -> str:
        """Типизированные подсказки LLM (CCH-12 Point 1).

        S365: hint «не найдено» не протекает в prompt — иначе LLM повторяет
        его в summary (CoT-утечка). S367: roster (опц.) — снимок известных NPC.
        CCH-14: prior_context (опц.) — краткая сводка EVENT/RELATIONSHIP из
        предыдущих фрагментов (subject + action + object), чтобы LLM связывала
        cross-fragment действия (например, «насилие Орма над Люсей» в п.9
        как продолжение «изнасилования» из п.8, не новое «избивает»).
        """
        # CCH-12 Point 1: типизированные anchors. Если передан плоский List[int]
        # (legacy), конвертируем в AMBIGUOUS — LLM получит явный сигнал, что
        # семантика якоря не установлена, и не должна выдумывать.
        from app.services.chronicle.age_anchor import (
            AgeAnchor,
            AgeAnchorKind,
            age_anchors_to_hint,
        )
        if age_anchors and not isinstance(age_anchors[0], AgeAnchor):
            # Legacy: плоский список int → AMBIGUOUS anchors
            typed_anchors = [
                AgeAnchor(value=v, kind=AgeAnchorKind.AMBIGUOUS, source_span=str(v))
                for v in age_anchors
            ]
        else:
            # уже List[AgeAnchor] (или пусто) — narrowing через isinstance не срабатывает
            typed_anchors = cast("List[AgeAnchor]", age_anchors)

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
        # CCH-14: cross-fragment context — сводка уже декомпозированных
        # EVENT/RELATIONSHIP из предыдущих фрагментов. LLM использует для
        # разрешения местоимений и сохранения типа действия.
        if prior_context:
            ctx_block = (
                "ПРЕДЫДУЩИЙ КОНТЕКСТ (уже разобрано):\n"
                f"{prior_context}\n"
                "Используй для связи действий между фрагментами. Если во "
                "фрагменте упоминается «насилие X над Y», а в предыдущих "
                "фрагментах уже было изнасилование X над Y — это продолжение "
                "того же действия, не новое «избивает».\n\n"
            )
        else:
            ctx_block = ""
        # USL-2 SUBJECT_ATTRIBUTION_FIX: блок ХРОНИКА в начало user-prompt,
        # чтобы LLM знала, чью биографию декомпозирует (npc_id — основной субъект).
        # Без этого LLM путает «он» с другим NPC (SUBJECT_ATTRIBUTION_ERROR —
        # guard_borko/merchant_goran drafts: LLM подменяла Борко/Горана на Орма).
        chronicle_block = f"ХРОНИКА: {npc_id} (основной субъект повествования).\n\n" if npc_id else ""
        return f"{chronicle_block}{hints}{roster_block}{ctx_block}ФРАГМЕНТ:\n{fragment.strip()}"

    async def decompose(
        self,
        chronicle_id: str,
        fragment_ord: int,
        fragment: str,
        *,
        prior_context: str = "",
    ) -> DecomposeResult:
        """
        Фрагмент → DecomposeResult. LLM через router.request(FACT_EXTRACTION);
        один retry; DecompositionError → failure() с текстом (не исключение).

        CCH-14: prior_context — сводка EVENT/RELATIONSHIP из предыдущих
        фрагментов (subject + action + object). Загружается caller'ом
        (routes_chronicle) из существующего draft.
        """
        if not fragment.strip():
            return DecomposeResult.failure("Пустой фрагмент")
        # CCH-12 Point 1: типизированные anchors. extract_age_anchors_typed
        # возвращает List[AgeAnchor]; конвертируем для DecomposeResult, который
        # пока хранит плоский List[int] (backward-compat response API).
        from app.services.chronicle.age_anchor import extract_age_anchors_typed
        typed = extract_age_anchors_typed(fragment)
        # CCH-12 Point 1: передаём List[AgeAnchor] напрямую в build_user_prompt,
        # не плоский List[int] — иначе build_user_prompt конвертирует все в
        # AMBIGUOUS, и DURATION/AT_AGE/SINCE_AGE классификация теряется.
        # DecomposeResult.age_anchors (legacy плоский) для response API.
        anchors = [a.value for a in typed]
        roster = (self._roster_provider or _default_roster_provider)()
        user_prompt = self.build_user_prompt(fragment, typed, roster, prior_context=prior_context, npc_id=chronicle_id)
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
                    max_tokens=6144,  # CCH-14: было 4096, увеличено для п.15 Люси (1161 chars) + prior_context
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
                    raw,
                    chronicle_id=chronicle_id,
                    fragment_ord=fragment_ord,
                    roster=roster,
                    subject_id=chronicle_id,
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

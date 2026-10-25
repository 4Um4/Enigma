# -*- coding: utf-8 -*-
"""
S368 DIAGNOSTICS (runtime-археология age-пути декомпозера).
  1) проверяет/поднимает LLM-сервер; 2) гоняет РЕАЛЬНЫЙ BiographyDecomposer.decompose()
  по контрольному фрагменту (MUTATIONS:366) на ТЕКУЩЕМ (WIP) коде;
  3) подсматривает сырой ответ LLM обёрткой над normalizer;
  4) реплицирует route-конверсию age -> historical_age (routes_chronicle.py:263-267);
  5) пишет отчёт ТОЛЬКО в reports/s368_age_dump.txt.
Никаких записей в draft/canon (R1/R3). Запуск: python scripts/s368_age_dump.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / 'backend'
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

FRAGMENT = (
    "В 8 лет Люся осталась без родителей. Её взял к себе трактирщик Торнин — "
    "дальний родственник матери. С тех пор Люся живёт в трактире Торнина "
    "и работает там официанткой."
)
NPC_ID = "maid_lusya"


def _finish(lines):
    blob = "\n".join(lines)
    out = _ROOT / "reports" / "s368_age_dump.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(blob, encoding="utf-8")
    print(blob)
    print(f"[SAVED] {out}")
    return 0


def main() -> int:
    lines = ["=== S368 AGE DUMP ===", f"[CWD] {Path.cwd()}"]

    # -- 0. LLM-сервер --------------------------------------------------------
    import urllib.error
    import urllib.request

    from app.core.config import settings

    base = settings.llama_cpp_server_url.replace("/v1", "")
    try:
        urllib.request.urlopen(base + "/health", timeout=3)
        lines.append(f"[LLM] сервер уже поднят: {base}")
    except (urllib.error.URLError, OSError) as exc:
        lines.append(f"[LLM] сервер недоступен ({exc!r}), пробую start_llama_server()")
        try:
            from scripts.llm_server_manager import start_llama_server

            if not start_llama_server():
                lines.append("LLM_UNAVAILABLE: start_llama_server() -> False")
                return _finish(lines)
            lines.append("[LLM] сервер поднят скриптом")
        except Exception as exc2:
            lines.append(f"LLM_UNAVAILABLE: {exc2!r}")
            return _finish(lines)

    # -- 1. декомпозер на ТЕКУЩЕМ (WIP) коде ----------------------------------
    from app.services.chronicle.biography_decomposer import BiographyDecomposer

    try:
        from app.services.llm.router import initialize_router

        initialize_router()
        lines.append("[ROUTER] initialize_router() ok")
    except Exception as exc:
        lines.append(f"[ROUTER] initialize_router() пропущен: {exc!r}")

    d = BiographyDecomposer()

    try:
        anchors = d.extract_age_anchors(FRAGMENT)
    except TypeError:
        anchors = type(d).extract_age_anchors(FRAGMENT)
    lines.append(f"[ANCHORS] {anchors}")

    user_prompt = None
    try:
        kwargs = {}
        if "roster" in inspect.signature(d.build_user_prompt).parameters:
            try:
                from app.services.chronicle.biography_decomposer import (
                    _default_roster_provider,
                )

                kwargs["roster"] = _default_roster_provider()
            except Exception as exc:
                lines.append(f"[ROSTER] провайдер недоступен: {exc!r}")
        user_prompt = d.build_user_prompt(FRAGMENT, anchors, **kwargs)
        lines.append(f"[USER_PROMPT] len={len(user_prompt)}")
        lines.append("[USER_PROMPT_BEGIN]")
        lines.append(user_prompt)
        lines.append("[USER_PROMPT_END]")
    except Exception as exc:
        lines.append(f"[USER_PROMPT] ОШИБКА: {exc!r}")

    system_prompt = None
    for attr in ("_ensure_prompt", "_load_system_prompt", "_get_system_prompt", "_system_prompt"):
        fn = getattr(d, attr, None)
        if callable(fn):
            try:
                system_prompt = fn()
                lines.append(f"[SYSTEM_PROMPT] via {attr}() len={len(system_prompt)}")
                break
            except Exception:
                pass
    if not system_prompt:
        p = _ROOT / "backend" / "prompts" / "chronicle_decompose_system.txt"
        if p.exists():
            system_prompt = p.read_text(encoding="utf-8")
            lines.append(f"[SYSTEM_PROMPT] via файл, len={len(system_prompt)}")
        else:
            lines.append("[SYSTEM_PROMPT] НЕ НАЙДЕН")

    # -- 2. сырой ответ LLM: ловушка на normalizer, потом прямой вызов ---------
    raw_captures = []
    _orig_normalize = None
    try:
        from app.services.chronicle.decomposition_normalizer import (
            ChronicleDecompositionNormalizer,
        )

        _orig_normalize = ChronicleDecompositionNormalizer.normalize

        def _spy(raw_text, *args, **kwargs):
            txt = raw_text if isinstance(raw_text, str) else str(raw_text)
            if not raw_captures or raw_captures[-1] != txt:
                raw_captures.append(txt)
            return _orig_normalize(raw_text, *args, **kwargs)

        ChronicleDecompositionNormalizer.normalize = staticmethod(_spy)
        lines.append("[SPY] normalizer обёрнут, ждём сырой ответ")
    except Exception as exc:
        lines.append(f"[SPY] не удалось обернуть normalizer: {exc!r}")

    result = None
    try:
        maybe = d.decompose(NPC_ID, 0, FRAGMENT)
        result = asyncio.run(maybe) if inspect.iscoroutine(maybe) else maybe
    except Exception as exc:
        lines.append(f"[DECOMPOSE] ОШИБКА: {exc!r}")

    if not raw_captures and user_prompt is not None:
        lines.append("[RAW] ловушка не сработала, пробую прямой вызов router.request()")
        try:
            from app.services.llm.provider import GenerationParams
            from app.services.llm.router import ModelRouter

            params = GenerationParams(
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = asyncio.run(
                ModelRouter().request(
                    capability="fact_extraction",
                    prompt=user_prompt,
                    params=params,
                    system_prompt=system_prompt,
                )
            )
            raw_captures.append(raw)
        except Exception as exc:
            lines.append(f"[RAW] прямой вызов не удался: {exc!r}")

    if raw_captures:
        lines.append("[RAW_LLM_BEGIN]")
        lines.extend(raw_captures)
        lines.append("[RAW_LLM_END]")
    else:
        lines.append("[RAW_LLM] НЕ ЗАХВАЧЕН")

    # -- 3. items из result; если decompose упал — нормализуем raw руками ------
    items = list(getattr(result, "items", None) or [])
    if not items and raw_captures:
        try:
            from app.services.chronicle.decomposition_normalizer import (
                ChronicleDecompositionNormalizer,
            )

            items = ChronicleDecompositionNormalizer.normalize(
                raw_captures[0], chronicle_id=f"chronicle_{NPC_ID}", fragment_ord=0
            )
            lines.append("[FALLBACK] нормализую raw вручную")
        except Exception as exc:
            lines.append(f"[FALLBACK] нормализация не удалась: {exc!r}")

    lines.append(
        f"[RESULT] ok={getattr(result, 'ok', None)} "
        f"error={getattr(result, 'error', None)!r} "
        f"age_anchors={getattr(result, 'age_anchors', None)}"
    )

    with_age = 0
    for idx, it in enumerate(items):
        p = dict(getattr(it, "draft_payload", {}) or {})
        age = p.get("age", p.get("historical_age"))
        age_value = age if isinstance(age, int) else None  # реплика route:263-267 (§S368)
        # Синхронизировано с routes_chronicle.py:§S368 — детерминированный fallback
        # для EVENT при единственном age_anchor. См. test_s368_age_route_fallback.py.
        if (
            age_value is None
            and getattr(it, "kind", None) is not None
            and getattr(it.kind, "value", None) == "EVENT"
            and getattr(result, "age_anchors", None)
            and len(result.age_anchors) == 1
        ):
            _ev_count = sum(
                1 for x in (getattr(result, "items", None) or [])
                if getattr(x, "kind", None) is not None
                and getattr(x.kind, "value", None) == "EVENT"
            )
            if _ev_count == 1:
                age_value = result.age_anchors[0]
        if age_value is not None:
            with_age += 1
        kind = getattr(it, "kind", None)
        lines.append(
            f"[ITEM {idx}] kind={getattr(kind, 'value', kind)} "
            f"needs={getattr(it, 'needs_confirmation', None)} "
            f"conf={getattr(it, 'confidence', None)}"
        )
        lines.append(f"  payload_keys={sorted(p)}")
        lines.append(
            f"  age={p.get('age')!r} day={p.get('day')!r} "
            f"historical_age={p.get('historical_age')!r} -> route_age={age_value!r}"
        )
        lines.append("  payload_full=" + json.dumps(p, ensure_ascii=False))

    lines.append(f"[S368_METRIC] items={len(items)} with_age_int={with_age}")
    lines.append("=== END S368 AGE DUMP ===")
    return _finish(lines)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback

        blob = "=== S368 AGE DUMP CRASHED ===\n" + traceback.format_exc()
        try:
            out = _ROOT / "reports" / "s368_age_dump.txt"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(blob, encoding="utf-8")
            print("[SAVED] " + str(out))
        except Exception:
            pass
        print(blob)
        raise



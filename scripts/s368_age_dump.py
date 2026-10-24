path: scripts/s368_age_dump.py
Назначение: S368 DIAGNOSTICS (ЧАСТЬ VIII.5) — runtime-археология age-пути декомпозера:
            dump сырого LLM-ответа + нормализованных draft_payload без усечения.
            Контрольный тест из протокола S368 (MUTATIONS:366).
Зависимости: app.services.chronicle.biography_decomposer, decomposition_normalizer, llm.router
Основные сущности: main() — единственная точка входа; запись только reports/s368_age_dump.txt
''' + "'''" if False else @'
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

FRAGMENT = (
    "В 8 лет Люся осталась без родителей. Её взял к себе трактирщик Торнин — "
    "дальний родственник матери. С тех пор Люся живёт в трактире Торнина "
    "и работает там официанткой."
)


def main() -> int:
    import urllib.error
    import urllib.request

    from app.core.config import settings

    try:
        urllib.request.urlopen(settings.llama_cpp_server_url.replace("/v1", "") + "/health", timeout=3)
        print("[LLM] сервер уже поднят")
    except (urllib.error.URLError, OSError):
        from scripts.llm_server_manager import start_llama_server
        if not start_llama_server():
            print("LLM_UNAVAILABLE")
            return 1

    from app.services.chronicle.biography_decomposer import (
        BiographyDecomposer,
        _default_roster_provider,
    )
    from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer
    from app.services.llm.provider import GenerationParams
    from app.services.llm.router import ModelRouter, initialize_router

    initialize_router()

    d = BiographyDecomposer()
    anchors = BiographyDecomposer.extract_age_anchors(FRAGMENT)
    roster = _default_roster_provider()
    user_prompt = d.build_user_prompt(FRAGMENT, anchors, roster)
    system_prompt = d._ensure_prompt()

    lines = []
    lines.append(f"[ANCHORS] {anchors}")
    lines.append(f"[USER_PROMPT_HEAD] {user_prompt[:200]!r}")

    async def _raw_once() -> str:
        router = ModelRouter()
        params = GenerationParams(
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        return await router.request(
            capability="fact_extraction",
            prompt=user_prompt,
            params=params,
            system_prompt=system_prompt,
        )

    raw = asyncio.run(_raw_once())
    lines.append("[RAW_LLM_BEGIN]")
    lines.append(raw)
    lines.append("[RAW_LLM_END]")

    items = ChronicleDecompositionNormalizer.normalize(
        raw, chronicle_id="chronicle_maid_lusya", fragment_ord=0, roster=roster
    )
    for idx, it in enumerate(items):
        p = it.draft_payload
        lines.append(
            f"[ITEM {idx}] kind={it.kind.value} needs={it.needs_confirmation} "
            f"payload_keys={sorted(p.keys())} age_in_payload={p.get('age', '<MISSING>')!r}"
        )
        lines.append("  payload_full=" + json.dumps(p, ensure_ascii=False))

    blob = "\n".join(lines)
    out = Path("reports/s368_age_dump.txt")
    out.write_text(blob, encoding="utf-8")
    print(blob)
    print(f"[SAVED] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

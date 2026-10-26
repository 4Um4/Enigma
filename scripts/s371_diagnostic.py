"""
S371.1: Диагностика max_tokens 2048 vs 4096 — один фактор.

Прогоняет 6 падающих фрагментов из reports/s368_full_run.txt с двумя
значениями max_tokens (2048 и 4096), сохраняет raw_response (S371.0),
сравнивает валовое количество DecompositionError.

Принципы (CCH-S371):
- один фактор за эксперимент (только max_tokens)
- фиксированный корпус (6 фрагментов из s368_full_run.txt)
- без regex-парсинга JSON
- сохранение provenance (raw_response)
- не менять temperature/seed/промпт
- не менять модель только ради JSON-compliance

Запуск: python scripts/s371_diagnostic.py
Артефакт: reports/s371_diagnostic_{timestamp}.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.WARNING)
logging.disable(logging.WARNING)

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("AIDM_DATA_DIR", str(_ROOT / "backend" / "test_data"))
os.environ.setdefault("AIDM_SAVES_DIR", str(_ROOT / "backend" / "test_data" / "test_campaign"))


@dataclass
class FragmentResult:
    npc_id: str
    fragment_ord: int
    max_tokens: int
    ok: bool
    error: Optional[str]
    raw_response: Optional[str]
    items_count: int
    latency_ms: float


async def _decompose_one(
    decomposer: Any,
    chronicle_id: str,
    fragment_ord: int,
    fragment: str,
    max_tokens: int,
) -> FragmentResult:
    """Один вызов decompose() с заданным max_tokens (через mock params)."""
    from app.services.llm.provider import GenerationParams

    # Patch GenerationParams default max_tokens для этого вызова
    original_init = GenerationParams.__init__

    def _patched_init(self, **kwargs):
        kwargs["max_tokens"] = max_tokens
        original_init(self, **kwargs)

    GenerationParams.__init__ = _patched_init
    try:
        t0 = time.time()
        result = await decomposer.decompose(chronicle_id, fragment_ord, fragment)
        latency_ms = (time.time() - t0) * 1000
        return FragmentResult(
            npc_id=chronicle_id,
            fragment_ord=fragment_ord,
            max_tokens=max_tokens,
            ok=result.ok,
            error=result.error,
            raw_response=result.raw_response,
            items_count=len(result.items),
            latency_ms=latency_ms,
        )
    finally:
        GenerationParams.__init__ = original_init


def _load_fragments_from_s368() -> List[Dict[str, Any]]:
    """Загружает 6 падающих фрагментов из reports/s368_full_run.txt + канон-файлы."""
    s368_path = _ROOT / "reports" / "s368_full_run.txt"
    if not s368_path.exists():
        print(f"[WARN] {s368_path} не найден — используем минимальный корпус")
        return []

    fragments: List[Dict[str, Any]] = []
    npc_pattern = r"\[NPC\]\s+(\S+)\s+\(статус:"
    import re
    content = s368_path.read_text(encoding="utf-16")
    lines = content.splitlines()
    current_npc: Optional[str] = None
    for line in lines:
        npc_match = re.search(npc_pattern, line)
        if npc_match:
            current_npc = npc_match.group(1)
            continue
        if "NOT_DECOMPOSED" in line and current_npc:
            ord_match = re.search(r"\[(\d+)/\d+\]", line)
            if ord_match:
                fragments.append({
                    "npc_id": current_npc,
                    "fragment_ord": int(ord_match.group(1)) - 1,
                })
    return fragments


def _load_fragment_text(npc_id: str, fragment_ord: int) -> Optional[str]:
    """Загружает текст фрагмента из канон-файла NPC."""
    canon_path = _ROOT / "config" / "npc" / "chronicles" / f"{npc_id}.json"
    if not canon_path.exists():
        return None
    doc = json.loads(canon_path.read_text(encoding="utf-8-sig"))
    author_text = doc.get("author_text", "")
    import re
    parts = re.split(r"(?m)^(?=\d+\.\s)", author_text)
    parts = [p.strip() for p in parts if p.strip()]
    if fragment_ord < len(parts):
        return parts[fragment_ord]
    return None


async def main() -> int:
    from app.services.chronicle.biography_decomposer import BiographyDecomposer
    from app.services.llm.provider_manager import initialize_model_pool

    # S371.2: прямая инициализация ModelPool (backend не нужен; LLM-сервер на :8181 жив)
    print("[S371.2] Инициализация ModelPool...")
    init_results = initialize_model_pool()
    print(f"[S371.2] ModelPool init: {init_results}")

    fragments_meta = _load_fragments_from_s368()
    if not fragments_meta:
        print("[S371.1] Корпус пуст — нет падающих фрагментов в s368_full_run.txt")
        return 1

    print(f"[S371.1] Корпус: {len(fragments_meta)} падающих фрагментов")

    # Загрузить тексты фрагментов
    fragments: List[Dict[str, Any]] = []
    for fm in fragments_meta:
        text = _load_fragment_text(fm["npc_id"], fm["fragment_ord"])
        if text:
            fragments.append({**fm, "text": text})
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: {len(text)} знаков")
        else:
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: ТЕКСТ НЕ НАЙДЕН")

    if not fragments:
        print("[S371.1] Нет текстов фрагментов — корпус пуст")
        return 1

    # Диагностика: max_tokens 2048 vs 4096
    results_2048: List[FragmentResult] = []
    results_4096: List[FragmentResult] = []

    for max_tokens in (2048, 4096):
        print(f"\n[S371.1] Прогон с max_tokens={max_tokens}...")
        decomposer = BiographyDecomposer()
        for frag in fragments:
            print(f"  {frag['npc_id']} [{frag['fragment_ord']}]...", end=" ")
            try:
                result = await _decompose_one(
                    decomposer,
                    frag["npc_id"],
                    frag["fragment_ord"],
                    frag["text"],
                    max_tokens,
                )
                status = "OK" if result.ok else "FAIL"
                print(f"{status} ({result.latency_ms:.0f}мс)")
                if result.raw_response:
                    print(f"    raw[:200]: {result.raw_response[:200]!r}")
            except Exception as e:
                print(f"EXC: {e}")
                result = FragmentResult(
                    npc_id=frag["npc_id"],
                    fragment_ord=frag["fragment_ord"],
                    max_tokens=max_tokens,
                    ok=False,
                    error=str(e),
                    raw_response=None,
                    items_count=0,
                    latency_ms=0.0,
                )
            if max_tokens == 2048:
                results_2048.append(result)
            else:
                results_4096.append(result)

    # Сводка
    ok_2048 = sum(1 for r in results_2048 if r.ok)
    ok_4096 = sum(1 for r in results_4096 if r.ok)
    fail_2048 = len(results_2048) - ok_2048
    fail_4096 = len(results_4096) - ok_4096

    print("\n[S371.1] СВОДКА:")
    print(f"  max_tokens=2048: {ok_2048} OK / {fail_2048} FAIL (из {len(results_2048)})")
    print(f"  max_tokens=4096: {ok_4096} OK / {fail_4096} FAIL (из {len(results_4096)})")

    # Сохранить артефакт
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_path = _ROOT / "reports" / f"s371_diagnostic_{timestamp}.json"
    artifact = {
        "timestamp": timestamp,
        "fragments_count": len(fragments),
        "results_2048": [asdict(r) for r in results_2048],
        "results_4096": [asdict(r) for r in results_4096],
        "summary": {
            "max_tokens_2048": {"ok": ok_2048, "fail": fail_2048},
            "max_tokens_4096": {"ok": ok_4096, "fail": fail_4096},
        },
    }
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[S371.1] Артефакт: {artifact_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
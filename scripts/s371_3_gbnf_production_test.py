"""
S371.3-GBNF production server test: 7 фрагментов через BiographyDecomposer.decompose.

Production path: decompose() → router.request(FACT_EXTRACTION) → provider → /completion + grammar.
Реальный промпт (system + user с фрагментом биографии), не короткий общий prompt.

Для каждого фрагмента:
- ответ получен без timeout
- JSON полностью разбирается (json.loads OK)
- root-объект закрыт (ends_with_brace)
- items содержит данные (не пустой массив от слабого промпта)
- сервер остаётся доступным после запроса

Сравнение с baseline: 7/7 FAIL (TRUNCATION, missing final }) → ожидаем 7/7 OK.

Запуск: python scripts/s371_3_gbnf_production_test.py
Артефакт: reports/s371_3_gbnf_production_{timestamp}.json
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("AIDM_DATA_DIR", str(_ROOT / "backend" / "test_data"))
os.environ.setdefault("AIDM_SAVES_DIR", str(_ROOT / "backend" / "test_data" / "test_campaign"))


@dataclass
class FragmentResult:
    npc_id: str
    fragment_ord: int
    ok: bool
    error: Optional[str]
    raw_response: str
    json_parsed: bool
    json_error: Optional[str]
    items_count: int
    latency_ms: float
    ends_with_brace: bool
    server_alive_post: bool


def _probe_health() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open("http://localhost:8181/health", timeout=3).read()
        return True
    except Exception:
        return False


def _load_fragments_from_s368() -> List[Dict[str, Any]]:
    s368_path = _ROOT / "reports" / "s368_full_run.txt"
    if not s368_path.exists():
        print(f"[WARN] {s368_path} не найден")
        return []

    fragments: List[Dict[str, Any]] = []
    content = s368_path.read_text(encoding="utf-16")
    current_npc: Optional[str] = None
    for line in content.splitlines():
        npc_match = re.search(r"\[NPC\]\s+(\S+)\s+\(статус:", line)
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
    canon_path = _ROOT / "config" / "npc" / "chronicles" / f"{npc_id}.json"
    if not canon_path.exists():
        return None
    doc = json.loads(canon_path.read_text(encoding="utf-8-sig"))
    author_text = doc.get("author_text", "")
    parts = re.split(r"(?m)^(?=\d+\.\s)", author_text)
    parts = [p.strip() for p in parts if p.strip()]
    if fragment_ord < len(parts):
        return parts[fragment_ord]
    return None


async def _decompose_one(decomposer: Any, chronicle_id: str, fragment_ord: int, fragment: str) -> Any:
    return await decomposer.decompose(chronicle_id, fragment_ord, fragment)


async def main() -> int:
    from app.services.chronicle.biography_decomposer import BiographyDecomposer
    from app.services.llm.provider_manager import initialize_model_pool

    print("[S371.3-GBNF-PROD] Инициализация ModelPool...")
    init_results = initialize_model_pool()
    print(f"[S371.3-GBNF-PROD] ModelPool init: {init_results}")

    if not _probe_health():
        print("[S371.3-GBNF-PROD] Сервер мёртв — подними сначала")
        return 1

    fragments_meta = _load_fragments_from_s368()
    if not fragments_meta:
        print("[S371.3-GBNF-PROD] Корпус пуст")
        return 1

    print(f"[S371.3-GBNF-PROD] Корпус: {len(fragments_meta)} фрагментов")

    fragments: List[Dict[str, Any]] = []
    for fm in fragments_meta:
        text = _load_fragment_text(fm["npc_id"], fm["fragment_ord"])
        if text:
            fragments.append({**fm, "text": text})
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: {len(text)} знаков")
        else:
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: ТЕКСТ НЕ НАЙДЕН")

    if not fragments:
        print("[S371.3-GBNF-PROD] Нет текстов — корпус пуст")
        return 1

    print(f"\n[S371.3-GBNF-PROD] Прогон {len(fragments)} фрагментов через production path...")

    results: List[FragmentResult] = []
    decomposer = BiographyDecomposer()

    for frag in fragments:
        print(f"  {frag['npc_id']} [{frag['fragment_ord']}]...", end=" ")

        if not _probe_health():
            print("СЕРВЕР МЁРТВ — STOP")
            results.append(FragmentResult(
                npc_id=frag["npc_id"], fragment_ord=frag["fragment_ord"],
                ok=False, error="server dead before request", raw_response="",
                json_parsed=False, json_error=None, items_count=0,
                latency_ms=0, ends_with_brace=False, server_alive_post=False,
            ))
            break

        t0 = time.time()
        try:
            result = await _decompose_one(
                decomposer, frag["npc_id"], frag["fragment_ord"], frag["text"]
            )
            latency_ms = (time.time() - t0) * 1000

            if result.ok:
                items_count = len(result.items)
                raw = ""
                json_parsed = True
                json_error = None
                ends_with_brace = True
                status = f"OK (items={items_count}, {latency_ms:.0f}мс)"
            else:
                items_count = 0
                raw = result.raw_response or ""
                json_parsed = False
                json_error = result.error
                ends_with_brace = raw.strip().endswith("}") if raw else False
                status = f"FAIL ({result.error[:80]}, {latency_ms:.0f}мс)"

        except Exception as e:
            latency_ms = (time.time() - t0) * 1000
            items_count = 0
            raw = ""
            json_parsed = False
            json_error = str(e)
            ends_with_brace = False
            status = f"EXC ({e!s:.80}, {latency_ms:.0f}мс)"

        server_alive = _probe_health()
        print(f"{status} | server={server_alive}")

        results.append(FragmentResult(
            npc_id=frag["npc_id"], fragment_ord=frag["fragment_ord"],
            ok=(json_parsed and items_count > 0),
            error=json_error, raw_response=raw,
            json_parsed=json_parsed, json_error=json_error,
            items_count=items_count, latency_ms=latency_ms,
            ends_with_brace=ends_with_brace, server_alive_post=server_alive,
        ))

        if not server_alive:
            print("  СЕРВЕР УПАЛ — STOP")
            break

        await asyncio.sleep(3)

    # Сводка
    ok_count = sum(1 for r in results if r.ok)
    json_ok = sum(1 for r in results if r.json_parsed)
    ends_brace = sum(1 for r in results if r.ends_with_brace)
    server_alive_end = results[-1].server_alive_post if results else False

    print(f"\n[S371.3-GBNF-PROD] СВОДКА:")
    print(f"  Total: {len(results)}")
    print(f"  JSON parsed OK: {json_ok}/{len(results)}")
    print(f"  Ends with '}}': {ends_brace}/{len(results)}")
    print(f"  Items > 0: {sum(1 for r in results if r.items_count > 0)}/{len(results)}")
    print(f"  Full success (json+items): {ok_count}/{len(results)}")
    print(f"  Server alive at end: {server_alive_end}")

    print(f"\n[S371.3-GBNF-PROD] СРАВНЕНИЕ С BASELINE:")
    print(f"  Baseline (без GBNF):  3/7 OK @ 2048 (4/7 OK @ 4096) — 7/7 TRUNCATION")
    print(f"  GBNF production:       {ok_count}/{len(results)} OK")

    # Latency table
    print(f"\n[S371.3-GBNF-PROD] LATENCY:")
    for r in results:
        print(f"  {r.npc_id} [{r.fragment_ord}]: {r.latency_ms:.0f}ms, items={r.items_count}, ok={r.ok}")

    # Сохранить артефакт
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_path = _ROOT / "reports" / f"s371_3_gbnf_production_{timestamp}.json"
    artifact = {
        "timestamp": timestamp,
        "fragments_count": len(fragments),
        "results": [asdict(r) for r in results],
        "summary": {
            "json_parsed_ok": json_ok,
            "ends_with_brace": ends_brace,
            "items_gt_0": sum(1 for r in results if r.items_count > 0),
            "full_success": ok_count,
            "server_alive_at_end": server_alive_end,
        },
        "baseline_comparison": {
            "baseline_ok_2048": 3,
            "baseline_ok_4096": 4,
            "baseline_truncation": 7,
            "gbnf_ok": ok_count,
        },
    }
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[S371.3-GBNF-PROD] Артефакт: {artifact_path}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
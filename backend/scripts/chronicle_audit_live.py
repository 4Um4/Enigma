"""Live semantic audit via HTTP to uvicorn (штатный pipeline).

Для одного NPC: author_text → фрагменты → POST /decompose (через uvicorn,
который уже поднял ModelPool) → собрать draft → seeder → NPCState.

Кампания изолирована: silver_wolf_audit_live (не трогает silver_wolf originals).
Все артефакты: backend/audit_live/{npc_id}/

Usage: python scripts/chronicle_audit_live.py <npc_id>
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BASE_URL = "http://localhost:8000"
_CAMPAIGN = "silver_wolf_audit_live"  # изолированная
_AUDIT_DIR = Path(__file__).resolve().parent.parent / "audit_live"
_CANON_DIR = Path(__file__).resolve().parents[2] / "config" / "npc" / "chronicles"
_FRAG_PATTERN = re.compile(r"^\s*(\d+)\.\s*(.+)$", re.MULTILINE)

_CRITICAL_MARKERS = (
    "насил", "изнасил", "шантаж", "донос", "предал", "предательство",
    "убил", "убийств", "измен", "преступл", "контрабанд",
)


def load_author_text(npc_id: str) -> str:
    p = _CANON_DIR / f"{npc_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Канон не найден: {p}")
    return json.loads(p.read_text(encoding="utf-8")).get("author_text", "")


def split_fragments(author_text: str) -> List[Tuple[int, str]]:
    matches = list(_FRAG_PATTERN.finditer(author_text))
    if not matches:
        return [(0, author_text.strip())] if author_text.strip() else []
    fragments: List[Tuple[int, str]] = []
    header = author_text[: matches[0].start()].strip()
    if header:
        fragments.append((0, header))
    for i, m in enumerate(matches):
        n = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(author_text)
        fragments.append((n, author_text[start:end].strip()))
    return fragments


def _http_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        return {"_http_error": e.code, "_body": body_text}
    except urllib.error.URLError as e:
        return {"_url_error": str(e.reason)}


def _http_get(path: str) -> Dict[str, Any]:
    req = urllib.request.Request(_BASE_URL + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        return {"_http_error": e.code, "_body": body_text}
    except urllib.error.URLError as e:
        return {"_url_error": str(e.reason)}


async def decompose_via_http(
    npc_id: str, frag_ord: int, fragment_text: str
) -> Dict[str, Any]:
    """POST /api/chronicle/{campaign_id}/{npc_id}/decompose — штатный pipeline."""
    path = f"/api/chronicle/{_CAMPAIGN}/{npc_id}/decompose"
    body = {
        "campaign_id": _CAMPAIGN,
        "npc_id": npc_id,
        "fragment_ord": frag_ord,
        "fragment": fragment_text,
    }
    return _http_post(path, body)


def get_draft(npc_id: str) -> Dict[str, Any]:
    """GET /api/chronicle/{campaign_id}/{npc_id}/draft."""
    return _http_get(f"/api/chronicle/{_CAMPAIGN}/{npc_id}/draft")


def get_character_debug(npc_id: str) -> Dict[str, Any]:
    """GET /api/chronicle/{campaign_id}/{npc_id}/debug."""
    return _http_get(f"/api/chronicle/{_CAMPAIGN}/{npc_id}/debug")


async def run_live_audit(npc_id: str) -> Dict[str, Any]:
    out_dir = _AUDIT_DIR / npc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "02_raw_llm").mkdir(exist_ok=True)
    (out_dir / "03_normalized").mkdir(exist_ok=True)

    author_text = load_author_text(npc_id)
    (out_dir / "00_author_text.txt").write_text(author_text, encoding="utf-8")

    fragments = split_fragments(author_text)
    with open(out_dir / "01_fragments.jsonl", "w", encoding="utf-8") as f:
        for n, text in fragments:
            f.write(json.dumps({"n": n, "text": text}, ensure_ascii=False) + "\n")

    print(f"[{npc_id}] {len(fragments)} фрагментов (включая шапку)")
    print(f"[{npc_id}] Кампания: {_CAMPAIGN} (изолированная)")
    print(f"[{npc_id}] Pipeline: HTTP → uvicorn → ModelPool → qwen_7b (temp=0.9)\n")

    coverage_warnings: List[Dict[str, Any]] = []
    per_point: List[Dict[str, Any]] = []

    for frag_ord, (point_n, text) in enumerate(fragments):
        is_header = point_n == 0
        label = "HEADER" if is_header else f"POINT_{point_n}"
        print(f"  [{npc_id}] frag_ord={frag_ord} {label} ({len(text)} chars)...", end=" ", flush=True)

        result = await decompose_via_http(npc_id, frag_ord, text)

        (out_dir / "02_raw_llm" / f"{frag_ord:02d}_point{point_n:02d}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if "_http_error" in result or "_url_error" in result:
            print(f"FAIL: {result}")
            per_point.append({
                "frag_ord": frag_ord, "point_n": point_n, "is_header": is_header,
                "text_preview": text[:120],
                "ok": False, "error": result.get("_http_error") or result.get("_url_error"),
                "items_count": 0, "items_kinds": [],
            })
            continue

        status = result.get("status")
        if status == "NOT_DECOMPOSED":
            print(f"NOT_DECOMPOSED: {result.get('error', '')[:80]}")
            per_point.append({
                "frag_ord": frag_ord, "point_n": point_n, "is_header": is_header,
                "text_preview": text[:120],
                "ok": False, "error": result.get("error", ""),
                "items_count": 0, "items_kinds": [],
            })
            continue

        items = result.get("items", [])
        coverage = result.get("coverage", {})
        items_count = len(items)
        items_kinds = [it.get("kind", "?") for it in items]
        warning = coverage.get("critical_topic_warning")

        print(f"items={items_count} kinds={items_kinds} warn={'YES' if warning else 'no'}")

        (out_dir / "03_normalized" / f"{frag_ord:02d}_point{point_n:02d}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        per_point.append({
            "frag_ord": frag_ord, "point_n": point_n, "is_header": is_header,
            "text_preview": text[:120],
            "ok": True, "items_count": items_count, "items_kinds": items_kinds,
            "critical_topic_warning": warning,
            "coverage": coverage,
        })

        if items_count == 0 and not is_header:
            if any(m in text.lower() for m in _CRITICAL_MARKERS):
                coverage_warnings.append({
                    "point_n": point_n, "frag_ord": frag_ord,
                    "text_preview": text[:120],
                    "warning": "critical_topic_zero_items",
                    "coverage_warning_from_api": warning,
                })

    # 04. Get final draft
    print(f"\n[{npc_id}] Получение финального draft...")
    draft_resp = get_draft(npc_id)
    (out_dir / "04_draft_response.json").write_text(
        json.dumps(draft_resp, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 05. Try character_debug (NPCState)
    print(f"[{npc_id}] Запрос character_debug (NPCState snapshot)...")
    debug_resp = get_character_debug(npc_id)
    (out_dir / "06_npcstate_snapshot.json").write_text(
        json.dumps(debug_resp, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 07. Summary
    total_items = sum(p.get("items_count", 0) for p in per_point)
    real_points = [p for p in per_point if not p["is_header"]]
    zero_items_points = sum(1 for p in real_points if p.get("items_count", 0) == 0)
    http_failures = sum(1 for p in per_point if not p.get("ok", False))

    summary = {
        "npc_id": npc_id,
        "campaign": _CAMPAIGN,
        "pipeline": "HTTP → uvicorn → ModelPool → qwen_7b (temperature=0.9)",
        "total_fragments": len(fragments),
        "real_points_count": len(real_points),
        "total_items": total_items,
        "zero_items_points": zero_items_points,
        "http_failures": http_failures,
        "coverage_warnings_count": len(coverage_warnings),
        "coverage_warnings": coverage_warnings,
        "per_point": per_point,
    }

    (out_dir / "07_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = [
        f"# Live audit: {npc_id}",
        f"",
        f"- Pipeline: HTTP → uvicorn → qwen_7b (temperature=0.9)",
        f"- Campaign: {_CAMPAIGN} (изолированная, оригиналы не тронуты)",
        f"- Total fragments: {len(fragments)} (включая шапку)",
        f"- Real points: {len(real_points)}",
        f"- Total items produced: {total_items}",
        f"- Zero-items points: {zero_items_points}",
        f"- HTTP failures: {http_failures}",
        f"- Coverage warnings (critical topic + 0 items): {len(coverage_warnings)}",
        f"",
        f"## Per-point breakdown",
        f"",
        f"| point | frag | chars | items | kinds | warn |",
        f"|-------|------|-------|-------|-------|------|",
    ]
    for p in per_point:
        kinds = ", ".join(p.get("items_kinds", [])) or "—"
        label = "HDR" if p["is_header"] else f"#{p['point_n']}"
        warn = "⚠️" if p.get("critical_topic_warning") else ""
        md.append(f"| {label} | {p['frag_ord']} | {len(p['text_preview'])}+ | {p.get('items_count', 0)} | {kinds} | {warn} |")

    if coverage_warnings:
        md.append(f"\n## ⚠️ Critical topic warnings (zero items)\n")
        for w in coverage_warnings:
            md.append(f"- point {w['point_n']} (frag_ord={w['frag_ord']}): {w['text_preview']}...")

    (out_dir / "07_summary.md").write_text("\n".join(md), encoding="utf-8")

    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/chronicle_audit_live.py <npc_id>")
        sys.exit(1)
    npc_id = sys.argv[1]
    print(f"=== Live audit: {npc_id} ===")
    print(f"=== Output dir: backend/audit_live/{npc_id}/ ===\n")
    summary = asyncio.run(run_live_audit(npc_id))
    print(f"\n=== Summary ===")
    print(f"Total items: {summary['total_items']}")
    print(f"Zero-items points: {summary['zero_items_points']} / {summary['real_points_count']}")
    print(f"HTTP failures: {summary['http_failures']}")
    print(f"Coverage warnings: {summary['coverage_warnings_count']}")
    print(f"\nDetailed: backend/audit_live/{npc_id}/07_summary.md")
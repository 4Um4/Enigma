"""
S371.3-GBNF spike: proof that GBNF grammar via /completion fixes 7/7 TRUNCATION.

Принципы (CCH-S371 / мандат S371.3-GBNF-SPIKE):
- read-only spike — не меняет production-код
- GBNF через /completion endpoint (подтверждено probe 5)
- ChatML prompt из _build_chatml_prompt (существующий контракт)
- проверка json.loads на каждом ответе (не только статус декомпозиции)
- сравнение с baseline: 7/7 FAIL (TRUNCATION, missing final })

Запуск: python scripts/s371_3_gbnf_probe.py
Артефакт: reports/s371_3_gbnf_probe_{timestamp}.json
"""
from __future__ import annotations

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

URL_COMPLETION = "http://localhost:8181/completion"
GBNF_PATH = _ROOT / "config" / "chronicle_decompose.gbnf"
SYSTEM_PROMPT_PATH = _ROOT / "backend" / "prompts" / "chronicle_decompose_system.txt"


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
    has_items_key: bool
    ends_with_brace: bool


def _load_grammar() -> str:
    """Загружает GBNF-грамматику из config/chronicle_decompose.gbnf."""
    if not GBNF_PATH.exists():
        raise FileNotFoundError(f"GBNF grammar not found: {GBNF_PATH}")
    return GBNF_PATH.read_text(encoding="utf-8")


def _build_chatml_prompt(user_prompt: str, system_prompt: str) -> str:
    """Строит ChatML промпт (mirror _build_chatml_prompt из llama_cpp_provider)."""
    return (
        f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def _call_completion_with_grammar(
    prompt: str, grammar: str, max_tokens: int = 2048
) -> tuple[str, Optional[str]]:
    """POST /completion с grammar field → (content, error)."""
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "stream": False,
        "temperature": 0.0,
        "top_p": 0.9,
        "repeat_penalty": 1.12,
        "min_p": 0.1,
        "top_k": 40,
        "n_keep": 800,
        "stop": ["<|im_end|>", "</s>"],
        "grammar": grammar,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL_COMPLETION,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("content", ""), None
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _load_fragments_from_s368() -> List[Dict[str, Any]]:
    """Загружает 7 падающих фрагментов из reports/s368_full_run.txt + канон-файлы."""
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
    """Загружает текст фрагмента из канон-файла NPC."""
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


def _load_system_prompt() -> str:
    """Загружает system prompt из prompts/chronicle_decompose_system.txt."""
    if not SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"System prompt not found: {SYSTEM_PROMPT_PATH}")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_prompt(fragment: str) -> str:
    """Строит user prompt (mirror biography_decomposer.build_user_prompt — упрощённый)."""
    # Извлекаем возрастные якоря (regex из biography_decomposer.extract_age_anchors)
    anchors: List[str] = []
    patterns = [
        r"\[(\d+)\s*(?:год|лет|года)\]",
        r"в\s+(\d+)\s*(?:год|лет|года)",
        r"с\s+(\d+)\s*(?:год|лет|года)",
        r"к\s+(\d+)\s*(?:год|лет|года)",
        r"В\s+(\d+)\s+застал",
    ]
    for p in patterns:
        for m in re.finditer(p, fragment):
            anchors.append(m.group(0))

    anchor_str = ", ".join(anchors) if anchors else "(возрастных якорей не найдено)"
    return (
        f"Фрагмент биографии:\n{fragment}\n\n"
        f"Возрастные якоря: {anchor_str}\n\n"
        f"Декомпозируй фрагмент по схеме. Верни только валидный JSON."
    )


def main() -> int:
    # 1. Загрузить грамматику
    grammar = _load_grammar()
    print(f"[S371.3-GBNF] Грамматика загружена: {GBNF_PATH} ({len(grammar)} байт)")

    # 2. Загрузить system prompt
    system_prompt = _load_system_prompt()
    print(f"[S371.3-GBNF] System prompt: {len(system_prompt)} знаков")

    # 3. Загрузить 7 фрагментов
    fragments_meta = _load_fragments_from_s368()
    if not fragments_meta:
        print("[S371.3-GBNF] Корпус пуст — нет падающих фрагментов")
        return 1

    fragments: List[Dict[str, Any]] = []
    for fm in fragments_meta:
        text = _load_fragment_text(fm["npc_id"], fm["fragment_ord"])
        if text:
            fragments.append({**fm, "text": text})
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: {len(text)} знаков")
        else:
            print(f"  {fm['npc_id']} [{fm['fragment_ord']}]: ТЕКСТ НЕ НАЙДЕН")

    if not fragments:
        print("[S371.3-GBNF] Нет текстов — корпус пуст")
        return 1

    print(f"\n[S371.3-GBNF] Прогон {len(fragments)} фрагментов с grammar constraint...")

    results: List[FragmentResult] = []
    for frag in fragments:
        print(f"  {frag['npc_id']} [{frag['fragment_ord']}]...", end=" ")
        user_prompt = _build_user_prompt(frag["text"])
        chatml = _build_chatml_prompt(user_prompt, system_prompt)

        t0 = time.time()
        raw, err = _call_completion_with_grammar(chatml, grammar, max_tokens=2048)
        latency_ms = (time.time() - t0) * 1000

        if err:
            print(f"HTTP ERROR: {err}")
            results.append(FragmentResult(
                npc_id=frag["npc_id"], fragment_ord=frag["fragment_ord"],
                ok=False, error=err, raw_response="",
                json_parsed=False, json_error=None,
                items_count=0, latency_ms=latency_ms,
                has_items_key=False, ends_with_brace=False,
            ))
            continue

        # Проверить json.loads
        json_parsed = False
        json_error = None
        items_count = 0
        has_items_key = False
        ends_with_brace = raw.strip().endswith("}")

        try:
            data = json.loads(raw.strip())
            json_parsed = True
            has_items_key = "items" in data
            if has_items_key and isinstance(data["items"], list):
                items_count = len(data["items"])
            status = f"OK (json={json_parsed}, items={items_count}, ends_with_brace={ends_with_brace})"
        except json.JSONDecodeError as e:
            json_error = str(e)
            status = f"FAIL (json_error={json_error}, ends_with_brace={ends_with_brace})"

        print(f"{status} ({latency_ms:.0f}мс)")

        results.append(FragmentResult(
            npc_id=frag["npc_id"], fragment_ord=frag["fragment_ord"],
            ok=json_parsed and has_items_key,
            error=json_error, raw_response=raw,
            json_parsed=json_parsed, json_error=json_error,
            items_count=items_count, latency_ms=latency_ms,
            has_items_key=has_items_key, ends_with_brace=ends_with_brace,
        ))

    # Сводка
    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count
    json_ok = sum(1 for r in results if r.json_parsed)
    ends_brace = sum(1 for r in results if r.ends_with_brace)

    print(f"\n[S371.3-GBNF] СВОДКА:")
    print(f"  Total: {len(results)}")
    print(f"  JSON parsed OK: {json_ok}/{len(results)}")
    print(f"  Ends with '}}': {ends_brace}/{len(results)}")
    print(f"  Has 'items' key: {sum(1 for r in results if r.has_items_key)}/{len(results)}")
    print(f"  Full success (json+items): {ok_count}/{len(results)}")
    print(f"  FAIL: {fail_count}/{len(results)}")

    # Сравнение с baseline
    print(f"\n[S371.3-GBNF] СРАВНЕНИЕ С BASELINE:")
    print(f"  Baseline (без grammar):  3/7 OK @ 2048 (4/7 OK @ 4096)")
    print(f"  GBNF (этот прогон):      {ok_count}/{len(results)} OK")

    # Сохранить артефакт
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_path = _ROOT / "reports" / f"s371_3_gbnf_probe_{timestamp}.json"
    artifact = {
        "timestamp": timestamp,
        "grammar_file": str(GBNF_PATH),
        "fragments_count": len(fragments),
        "results": [asdict(r) for r in results],
        "summary": {
            "json_parsed_ok": json_ok,
            "ends_with_brace": ends_brace,
            "has_items_key": sum(1 for r in results if r.has_items_key),
            "full_success": ok_count,
            "fail": fail_count,
        },
        "baseline_comparison": {
            "baseline_2048_ok": 3,
            "baseline_2048_fail": 4,
            "gbnf_ok": ok_count,
            "gbnf_fail": fail_count,
        },
    }
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[S371.3-GBNF] Артефакт: {artifact_path}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
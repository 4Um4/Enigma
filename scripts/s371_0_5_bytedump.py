"""
S371.0.5: Байт-демп стойких JSON-ошибок декомпозиции хроник.

Диагностика (НЕ фикс): для каждого FAIL в свежем s371_diagnostic_*.json
артефакте пытается json.loads(raw_response), ловит JSONDecodeError,
демпает char e.pos с окружением и классифицирует природу ошибки.

Классы:
- JSON_SYNTAX_NEWLINE: char e.pos — \\n или \\r (raw newline в string value)
- JSON_SYNTAX_CONTROL: char e.pos — control char < 0x20 (не newline)
- JSON_SYNTAX_OTHER: char e.pos — printable, но синтаксис нарушен
- TRUNCATION: raw_response не заканчивается на } или ] (обрыв)
- VALID_BUT_FAILED: json.loads прошёл, но decomposer упал по другой причине
- NO_RAW: raw_response=None (ошибка пула, не JSON)

Принципы (CCH-S371):
- только диагностика, никакого repair
- никаких regex на JSON
- сохранение provenance (char position, repr окружения)

Запуск: python scripts/s371_0_5_bytedump.py [artifact_path]
Без аргумента — берёт свежий reports/s371_diagnostic_*.json по mtime.
Артефакт: reports/s371_0_5_bytedump_{timestamp}.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]


def _classify(raw_response: Optional[str]) -> Dict[str, Any]:
    """Классифицирует природу одной FAIL-записи."""
    if raw_response is None:
        return {"class": "NO_RAW", "detail": "raw_response=None (ошибка пула, не JSON)"}

    text = raw_response.strip()
    if not text:
        return {"class": "EMPTY", "detail": "Пустой raw_response"}

    # Truncation check: ends with } or ] ?
    stripped = text.rstrip()
    ends_clean = stripped.endswith("}") or stripped.endswith("]")

    # Try parse — пусть json.loads сам скажет, где упал
    try:
        json.loads(text)
        return {
            "class": "VALID_BUT_FAILED",
            "detail": "json.loads прошёл — decomposer упал по другой причине",
            "ends_clean": ends_clean,
            "length": len(text),
        }
    except json.JSONDecodeError as e:
        pos = e.pos
        start = max(0, pos - 30)
        end = min(len(text), pos + 30)
        context = text[start:end]
        char_at_pos = text[pos] if pos < len(text) else "<EOF>"

        # Классификация char
        if char_at_pos == "\n":
            char_class = "NEWLINE (\\n)"
            error_class = "JSON_SYNTAX_NEWLINE"
        elif char_at_pos == "\r":
            char_class = "CARRIAGE_RETURN (\\r)"
            error_class = "JSON_SYNTAX_NEWLINE"
        elif char_at_pos == "\t":
            char_class = "TAB (\\t)"
            error_class = "JSON_SYNTAX_CONTROL"
        elif isinstance(char_at_pos, str) and len(char_at_pos) == 1 and ord(char_at_pos) < 0x20:
            char_class = f"CONTROL (0x{ord(char_at_pos):02x})"
            error_class = "JSON_SYNTAX_CONTROL"
        elif char_at_pos == "<EOF>":
            char_class = "EOF (truncation)"
            error_class = "TRUNCATION"
        else:
            char_class = f"PRINTABLE ({char_at_pos!r})"
            error_class = "JSON_SYNTAX_OTHER"

        return {
            "class": error_class,
            "detail": e.msg,
            "pos": pos,
            "char_at_pos": char_at_pos,
            "char_class": char_class,
            "context_repr": repr(context),
            "context_visible": context,
            "ends_clean": ends_clean,
            "length": len(text),
        }


def _find_latest_artifact() -> Optional[Path]:
    """Берёт свежий reports/s371_diagnostic_*.json по mtime."""
    candidates = sorted(
        (_ROOT / "reports").glob("s371_diagnostic_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> int:
    artifact_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _find_latest_artifact()
    if not artifact_path or not artifact_path.exists():
        print("[S371.0.5] Артефакт не найден. Укажите путь: python scripts/s371_0_5_bytedump.py <path>")
        return 1

    print(f"[S371.0.5] Артефакт: {artifact_path}")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    # Собрать все FAIL с raw_response из обоих прогонов (2048 + 4096)
    fails: List[Dict[str, Any]] = []
    for key in ("results_2048", "results_4096"):
        for entry in artifact.get(key, []):
            if not entry.get("ok") and entry.get("raw_response"):
                fails.append({
                    "npc_id": entry["npc_id"],
                    "fragment_ord": entry["fragment_ord"],
                    "max_tokens": entry["max_tokens"],
                    "raw_response": entry["raw_response"],
                    "error": entry.get("error", ""),
                })

    if not fails:
        print("[S371.0.5] Нет FAIL с raw_response — нечего демпать")
        return 0

    print(f"[S371.0.5] Анализ {len(fails)} FAIL-записей...\n")

    results: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {}

    for fail in fails:
        cls = _classify(fail["raw_response"])
        result = {
            "npc_id": fail["npc_id"],
            "fragment_ord": fail["fragment_ord"],
            "max_tokens": fail["max_tokens"],
            **cls,
        }
        results.append(result)
        class_counts[cls["class"]] = class_counts.get(cls["class"], 0) + 1

        print(f"  {fail['npc_id']} [{fail['fragment_ord']}] @ {fail['max_tokens']}: {cls['class']}")
        if "char_at_pos" in cls:
            print(f"    pos={cls.get('pos')} char={cls['char_class']}")
            print(f"    context: {cls.get('context_repr', '')[:120]}")
        print(f"    detail: {cls['detail']}")
        if cls.get("ends_clean") is False:
            print(f"    ENDS NOT CLEAN (truncation?): last 30 chars = {fail['raw_response'][-30:]!r}")
        print()

    print("[S371.0.5] СВОДКА КЛАССОВ:")
    for cls, count in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"  {cls}: {count}")

    # Сохранить артефакт
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = _ROOT / "reports" / f"s371_0_5_bytedump_{timestamp}.json"
    out = {
        "timestamp": timestamp,
        "source_artifact": str(artifact_path),
        "fails_analyzed": len(fails),
        "class_counts": class_counts,
        "results": results,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[S371.0.5] Артефакт: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
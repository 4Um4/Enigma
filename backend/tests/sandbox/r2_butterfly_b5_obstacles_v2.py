# backend/tests/sandbox/r2_butterfly_b5_obstacles_v2.py
"""
R2-BUTTERFLY-B5-OBSTACLES v2 — чтение реализаций трёх препятствий.

Цель: прочитать конкретные участки кода, которые probe v1 нашёл, но не раскрыл:
  1. _prop_target_in_reach — реализация, порог дистанции
  2. BeliefRevisionEngine — формула confidence = 0.215
  3. EpistemicContextResolver — полная логика report_proposition

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import List
import io

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_butterfly_b5_obstacles_v2.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _find_function_bounds(src: str, func_name: str):
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        if line.startswith("def ") and func_name in line:
            func_start = i
            break
        if line.startswith("    def ") and func_name in line:
            func_start = i
            break
    if func_start is None:
        return None
    indent_of_def = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = len(lines)
    for j in range(func_start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent_of_def and (line.lstrip().startswith("def ") or line.lstrip().startswith("class ")):
            func_end = j
            break
    return func_start, func_end


# ============================================================================
# ЧТЕНИЕ 1: _prop_target_in_reach — реализация, порог дистанции
# ============================================================================
def read1_prop_target_in_reach() -> None:
    _print_section("ЧТЕНИЕ 1: _prop_target_in_reach — реализация, порог дистанции")

    pd_path = _BACKEND / "app/services/phases/post_decision.py"
    if not pd_path.exists():
        print(f"[file not found: {pd_path}]")
        return
    src = pd_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find _prop_target_in_reach function
    bounds = _find_function_bounds(src, "_prop_target_in_reach")
    if bounds is None:
        print("[function _prop_target_in_reach not found]")
        # Search for PROP_TARGET_IN_REACH context
        for i, line in enumerate(lines, 1):
            if "PROP_TARGET_IN_REACH" in line:
                print(f"\n  L{i}: {line.rstrip()}")
                for j in range(max(0, i - 5), min(len(lines), i + 10)):
                    if j != i - 1:
                        print(f"  L{j+1}: {lines[j].rstrip()}")
        return

    start, end = bounds
    print(f"\nFound _prop_target_in_reach at L{start + 1}, ends at L{end}")
    print(f"Function body ({end - start} lines):\n")
    for j in range(start, end):
        print(f"L{j+1:4d}: {lines[j]}")

    # Also show context around L613 (the warning log)
    print(f"\n--- Контекст L605-620 (вокруг warning PROP_TARGET_IN_REACH) ---")
    for line in _read_lines(pd_path, 605, 620):
        print(line)

    # Read test_butterfly_cold_start.py to understand test conditions
    print(f"\n--- test_butterfly_cold_start.py — условия тестов ---")
    test_path = _BACKEND / "tests/micro/test_butterfly_cold_start.py"
    if test_path.exists():
        test_src = test_path.read_text(encoding="utf-8", errors="replace")
        print(test_src[:3000])
    else:
        print(f"[file not found: {test_path}]")


# ============================================================================
# ЧТЕНИЕ 2: BeliefRevisionEngine — формула confidence = 0.215
# ============================================================================
def read2_belief_revision_engine() -> None:
    _print_section("ЧТЕНИЕ 2: BeliefRevisionEngine — формула confidence")

    # Search for BeliefRevisionEngine
    greps = [
        "BeliefRevisionEngine", "belief_revision", "revise_belief",
        "update_confidence", "compute_confidence", "testimony_confidence",
        "_CLAIM_WEIGHT", "trust_factor", "reliability",
        "source_confidence", "witness_confidence",
    ]

    for pattern in greps:
        print(f"\n--- Поиск '{pattern}' ---")
        found = []
        for f in _BACKEND.rglob("*.py"):
            if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
                continue
            if f == _THIS:
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                if pattern in line:
                    found.append((f, i, line.rstrip()))
        print(f"  Найдено {len(found)} совпадений:")
        for path, ln, line in found[:15]:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")

    # Read the belief_revision_engine if found
    bre_path = _BACKEND / "app/services/npc/belief_revision_engine.py"
    if not bre_path.exists():
        # Search for it
        for f in _BACKEND.rglob("*.py"):
            if "belief_revision" in f.name.lower():
                bre_path = f
                break
    if bre_path.exists():
        print(f"\n--- BeliefRevisionEngine file: {bre_path.relative_to(_BACKEND)} ---")
        src = bre_path.read_text(encoding="utf-8", errors="replace")
        lines = src.split("\n")
        # Show all confidence-related code
        print(f"\n--- Строки с confidence ---")
        for i, line in enumerate(lines, 1):
            if "confidence" in line.lower() or "trust" in line.lower() or "reliability" in line.lower() or "weight" in line.lower():
                print(f"  L{i}: {line.rstrip()}")

        # Show full functions that compute confidence
        print(f"\n--- Полные функции с confidence ---")
        for i, line in enumerate(lines):
            if "def " in line and ("confidence" in line.lower() or "revise" in line.lower() or "update" in line.lower()):
                bounds = _find_function_bounds(src, line.split("(")[0].split("def ")[-1].strip())
                if bounds:
                    s, e = bounds
                    print(f"\n  Function at L{s+1}–L{e}:")
                    for j in range(s, e):
                        print(f"  L{j+1}: {lines[j]}")
    else:
        print("[BeliefRevisionEngine file not found]")

    # Also check self_relevance_gate.py for _CLAIM_WEIGHT
    srg_path = _BACKEND / "app/services/npc/self_relevance_gate.py"
    if not srg_path.exists():
        for f in _BACKEND.rglob("*.py"):
            if "self_relevance" in f.name.lower():
                srg_path = f
                break
    if srg_path.exists():
        print(f"\n--- self_relevance_gate: {srg_path.relative_to(_BACKEND)} ---")
        src = srg_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["_CLAIM_WEIGHT", "confidence", "reliability", "trust"]):
                print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# ЧТЕНИЕ 3: EpistemicContextResolver — полная логика report_proposition
# ============================================================================
def read3_epistemic_context_resolver() -> None:
    _print_section("ЧТЕНИЕ 3: EpistemicContextResolver — полная логика report_proposition")

    ecr_path = _BACKEND / "app/services/npc/epistemic_context_resolver.py"
    if not ecr_path.exists():
        print(f"[file not found: {ecr_path}]")
        return
    src = ecr_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    print(f"\n--- Полный файл ({len(lines)} lines) ---")
    for i, line in enumerate(lines, 1):
        print(f"L{i:4d}: {line}")

    # Also check epistemology.py for EpistemicRecord / EpistemicContext
    print(f"\n--- app/domain/epistemology.py (key parts) ---")
    epi_path = _BACKEND / "app/domain/epistemology.py"
    if epi_path.exists():
        src = epi_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["class Epistemic", "report_proposition", "confidence",
                                          "CONFIDENCE_THRESHOLD", "testimony", "source_id",
                                          "original_source_id", "Predicate"]):
                print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# ЧТЕНИЕ 4: claim_event_subscriber — как слух записывается в EpistemicStore
# ============================================================================
def read4_claim_event_subscriber() -> None:
    _print_section("ЧТЕНИЕ 4: claim_event_subscriber — как слух записывается в EpistemicStore")

    ces_path = _BACKEND / "app/services/events/claim_event_subscriber.py"
    if not ces_path.exists():
        print(f"[file not found: {ces_path}]")
        return
    src = ces_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    print(f"\n--- Полный файл ({len(lines)} lines) ---")
    for i, line in enumerate(lines, 1):
        print(f"L{i:4d}: {line}")


# ============================================================================
# ЧТЕНИЕ 5: post_decision.py — как SPREAD_RUMOR выполняется
# ============================================================================
def read5_post_decision_spread_rumor() -> None:
    _print_section("ЧТЕНИЕ 5: post_decision.py — SPREAD_RUMOR execution")

    pd_path = _BACKEND / "app/services/phases/post_decision.py"
    if not pd_path.exists():
        print(f"[file not found: {pd_path}]")
        return
    src = pd_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find SPREAD_RUMOR handling
    print(f"\n--- Строки с SPREAD_RUMOR / spread_rumor ---")
    for i, line in enumerate(lines, 1):
        if "SPREAD_RUMOR" in line or "spread_rumor" in line:
            print(f"  L{i}: {line.rstrip()}")

    # Show full context around PROP_TARGET_IN_REACH (L600-650)
    print(f"\n--- Контекст L580-650 (вокруг PROP_TARGET_IN_REACH и SPREAD_RUMOR) ---")
    for line in _read_lines(pd_path, 580, 650):
        print(line)

    # Show the function that handles SPREAD_RUMOR
    print(f"\n--- Поиск функции, обрабатывающей spread_rumor ---")
    for i, line in enumerate(lines):
        if ("def " in line and "spread" in line.lower()) or ("def " in line and "rumor" in line.lower()):
            bounds = _find_function_bounds(src, line.split("(")[0].split("def ")[-1].strip())
            if bounds:
                s, e = bounds
                print(f"\n  Function at L{s+1}–L{e}:")
                for j in range(s, min(e, s + 60)):
                    print(f"  L{j+1}: {lines[j]}")


# ============================================================================
# ИТОГ: сводка препятствий
# ============================================================================
def final_summary() -> None:
    _print_section("ИТОГ — полная карта препятствий")

    print(f"""
=============================================================================
ПОЛНАЯ КАРТА ПРЕПЯТСТВИЙ ДЛЯ BUTTERFLY B5
=============================================================================

ПРЕПЯТСТВИЕ 1: PROP_TARGET_IN_REACH
  Файл: app/services/phases/post_decision.py
  Функция: _prop_target_in_reach(scene, speaker_id, target_id)
  Порог дистанции: [будет показан в ЧТЕНИИ 1]
  Условие: speaker и target в одной локации + дистанция <= порога
  Если BLOCKED: NPC_SPOKE публикуется БЕЗ proposition в payload
  → слух не доходит до PropositionVerifier
  → EpistemicStore Торнина НЕ обновляется

ПРЕПЯТСТВИЕ 2: REPORT_CONFIDENCE_THRESHOLD = 0.25
  Файл: app/services/npc/epistemic_context_resolver.py L32
  Использование: L95-101 — фильтр для report_proposition
  Семантика:
    - EpistemicContextResolver.resolve(agent_id) перебирает все EpistemicRecords
    - Если pred == Predicate.INSULTED и confidence >= 0.25
      и object_id != agent_id и subject_id != agent_id
      → record.proposition становится report_proposition в EpistemicContext
    - report_proposition кормится в DecisionHub
    - Если report_proposition есть → DecisionHub может выбрать SPREAD_RUMOR
  В B4: confidence Торнина = 0.215 < 0.25 → report_proposition = None
  → нет SPREAD_RUMOR от Торнина → нет причинной реакции

ПРЕПЯТСТВИЕ 3: confidence = 0.215
  Файл: BeliefRevisionEngine (точный файл — ЧТЕНИЕ 2)
  Формула: [будет показана в ЧТЕНИИ 2]
  Ожидаемые коэффициенты:
    - source confidence (Люси) × trust_factor (Торнин→Люся) × claim_weight
    - Или: testimony_confidence = source_conf × listener_trust
  Для преодоления 0.25:
    - Повысить trust(Торнин, Люся) — но это данные, не production-код
    - Повторная передача слуха (corroboration) — может повысить confidence
    - Прямое наблюдение (Торнин сам видит оскорбление) — confidence = 1.0

=============================================================================
ВОЗМОЖНЫЕ СЦЕНАРИИ ДЛЯ B5
=============================================================================

Сценарий 1: Преодолеть PROP_TARGET_IN_REACH
  - Если порог дистанции < 3.55m (расстояние Люся-Торнин)
  - Нужен NPC movement для сближения
  - После FLEE fix NPC могут двигаться
  - Но движение зависит от DecisionHub (schedule/seek_ally)
  - Можно подождать достаточное количество ticks, пока NPC сблизятся

Сценарий 2: Преодолеть REPORT_CONFIDENCE_THRESHOLD
  - confidence=0.215 нужно повысить до >= 0.25
  - Без изменения production-кода:
    (a) Повторная передача слуха от другого NPC (corroboration)
    (b) Дополнительные свидетельства (другие NPC тоже передают слух)
    (c) Больше ticks — если confidence растёт со временем
  - Если ни один естественный путь не работает → PARTIAL

Сценарий 3: Доказать причинную реакцию даже с confidence < 0.25
  - Если Торнин всё равно произносит реплику (через TALK, а не SPREAD_RUMOR)
  - И содержание реплики связано с услышанным
  - → причинная реакция доказана через TALK, а не SPREAD_RUMOR
  - Но это слабее (TALK не требует report_proposition)

=============================================================================
РЕКОМЕНДАЦИЯ
=============================================================================

1. Прочитать реализации (этот probe v2)
2. На основе формулы confidence понять, можно ли естественным путём
   преодолеть 0.25
3. Если нет — эксперимент B5 с 20 ticks, фиксировать PARTIAL
   с точной причиной: "confidence 0.215 < threshold 0.25"
4. Если PROP_TARGET_IN_REACH блокирует → зафиксировать
   и проверить, могут ли NPC сблизиться за 20 ticks
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-BUTTERFLY-B5-OBSTACLES v2 — чтение реализаций")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try: read1_prop_target_in_reach()
    except Exception as e: print(f"[read1 error: {e}]"); traceback.print_exc()

    try: read2_belief_revision_engine()
    except Exception as e: print(f"[read2 error: {e}]"); traceback.print_exc()

    try: read3_epistemic_context_resolver()
    except Exception as e: print(f"[read3 error: {e}]"); traceback.print_exc()

    try: read4_claim_event_subscriber()
    except Exception as e: print(f"[read4 error: {e}]"); traceback.print_exc()

    try: read5_post_decision_spread_rumor()
    except Exception as e: print(f"[read5 error: {e}]"); traceback.print_exc()

    try: final_summary()
    except Exception as e: print(f"[final error: {e}]"); traceback.print_exc()

    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)

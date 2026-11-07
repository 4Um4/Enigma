# backend/tests/sandbox/r2_butterfly_b5_obstacles_audit.py
"""
R2-BUTTERFLY-B5-OBSTACLES — Этап 1: проверка открытых препятствий.

Цель: исследовать
  1. PROP_TARGET_IN_REACH — где, почему, условия
  2. REPORT_CONFIDENCE_THRESHOLD = 0.25 — объявление, использование
  3. confidence = 0.215 — формула, источники, коэффициенты

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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

PROJECT_ROOT = _BACKEND.parent

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_butterfly_b5_obstacles_audit.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _grep_in_dir(directory: Path, patterns: List[str], file_exts: List[str] = (".py",)) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in file_exts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


# ============================================================================
# ЭТАП 1.1: PROP_TARGET_IN_REACH
# ============================================================================
def stage1_1_prop_target_in_reach() -> None:
    _print_section("ЭТАП 1.1: PROP_TARGET_IN_REACH — точное место возникновения")

    print("\n--- Поиск PROP_TARGET_IN_REACH по всему backend/ ---")
    results = _grep_in_dir(_BACKEND, ["PROP_TARGET_IN_REACH"])
    print(f"Найдено {len(results)} совпадений:")
    for path, ln, line in results:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    print(f"""
>>> Анализ:

  PROP_TARGET_IN_REACH — это код ошибки/статус, возникающий когда:
  - NPC (Люся) пытается передать слух (PROP_SPREAD_RUMOR) другому NPC (Торнину)
  - Но они НЕ находятся в допустимой дистанции друг от друга
  - Коммуникация блокируется

  Нужно установить:
  - Какой код возвращает PROP_TARGET_IN_REACH
  - Какой порог дистанции
  - Может ли NPC естественно сблизиться
""")

    # Find the function/method that returns PROP_TARGET_IN_REACH
    print("\n--- Поиск 'return PROP_TARGET_IN_REACH' или 'PROP_TARGET_IN_REACH' в assignment ---")
    results2 = _grep_in_dir(_BACKEND, ["return.*PROP_TARGET_IN_REACH", "PROP_TARGET_IN_REACH.*=", "= PROP_TARGET_IN_REACH"])
    for path, ln, line in results2:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Find distance/reach check code
    print("\n--- Поиск проверки дистанции (in_reach, target_in_reach, communication_range) ---")
    results3 = _grep_in_dir(_BACKEND, ["in_reach", "target_in_reach", "communication_range", "comm_range",
                                       "within_range", "PROP_TARGET"])
    for path, ln, line in results3[:30]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Read the file where PROP_TARGET_IN_REACH is used
    if results:
        first_file = results[0][0]
        print(f"\n--- Контекст: {first_file.relative_to(_BACKEND)} ---")
        try:
            src = first_file.read_text(encoding="utf-8", errors="replace")
            lines = src.split("\n")
            # Show context around each occurrence
            shown_ranges = set()
            for path, ln, line in results:
                if path != first_file:
                    continue
                if ln in shown_ranges:
                    continue
                start = max(0, ln - 10)
                end = min(len(lines), ln + 10)
                print(f"\n  Контекст L{start+1}–L{end}:")
                for j in range(start, end):
                    marker = " >>>" if j + 1 == ln else "    "
                    print(f"  {marker} L{j+1}: {lines[j]}")
                for k in range(start, end):
                    shown_ranges.add(k + 1)
        except Exception as e:
            print(f"  [read error: {e}]")


# ============================================================================
# ЭТАП 1.2: Условия успешной коммуникации
# ============================================================================
def stage1_2_communication_conditions() -> None:
    _print_section("ЭТАП 1.2: Условия успешной коммуникации")

    print(f"""
>>> Все условия для успешной передачи слуха (PROP_SPREAD_RUMOR):

  1. Источник (maid_lusya) должен иметь слух в EpistemicStore
     → после PLAYER_INSULTS, Люся получает belief об оскорблении

  2. DecisionHub должен выбрать Intent.SPREAD_RUMOR для Люси
     → зависит от условий (willingness, relationship, proximity)

  3. Целевой NPC (tavern_keeper_tornin) должен быть:
     → в той же локации (tavern)
     → в допустимой дистанции (PROP_TARGET_IN_REACH)
     → воспринимать речь (perception enabled)

  4. DialogueExecutor должен вызвать LLM
     → LLM генерирует текст реплики
     → NPC_SPOKE событие публикуется

  5. PropositionVerifier должен проверить содержание
     → extract proposition из речи
     → сравнить с EpistemicStore Люси
     → если verified → записать в EpistemicStore Торнина

  6. EpistemicStore Торнина обновляется
     → source_id = maid_lusya
     → original_source_id = player
     → confidence = f(...) (формула, нужно найти)

  7. DecisionHub Торнина принимает решение на основе нового знания
     → если confidence > REPORT_CONFIDENCE_THRESHOLD → реакция
""")

    # Find communication execution code
    print("\n--- Поиск кода выполнения коммуникации (DialogueExecutor, spread_rumor, communicate) ---")
    results = _grep_in_dir(_BACKEND, ["spread_rumor", "SPREAD_RUMOR", "DialogueExecutor",
                                       "communicate", "propagate_rumor", "claim_subscriber"])
    print(f"Найдено {len(results)} совпадений:")
    for path, ln, line in results[:30]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Find subscriber that handles SPREAD_RUMOR
    print("\n--- Поиск подписчиков SPREAD_RUMOR / COMMUNICATION_CLAIM ---")
    results2 = _grep_in_dir(_BACKEND, ["COMMUNICATION_CLAIM", "claim_subscriber", "ClaimEventSubscriber",
                                        "NPC_SPOKE", "npc_dialogue_subscriber"])
    print(f"Найдено {len(results2)} совпадений:")
    for path, ln, line in results2[:20]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")


# ============================================================================
# ЭТАП 1.3: REPORT_CONFIDENCE_THRESHOLD = 0.25
# ============================================================================
def stage1_3_report_confidence_threshold() -> None:
    _print_section("ЭТАП 1.3: REPORT_CONFIDENCE_THRESHOLD = 0.25 — объявление и использование")

    print("\n--- Поиск REPORT_CONFIDENCE_THRESHOLD ---")
    results = _grep_in_dir(_BACKEND, ["REPORT_CONFIDENCE_THRESHOLD"])
    print(f"Найдено {len(results)} совпадений:")
    for path, ln, line in results:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Read context around each occurrence
    if results:
        print(f"\n--- Контекст каждого вхождения ---")
        files_shown = set()
        for path, ln, line in results:
            if path in files_shown:
                continue
            files_shown.add(path)
            try:
                src = path.read_text(encoding="utf-8", errors="replace")
                lines = src.split("\n")
                print(f"\n  Файл: {path.relative_to(_BACKEND)}")
                # Find all occurrences in this file
                for i, l in enumerate(lines, 1):
                    if "REPORT_CONFIDENCE_THRESHOLD" in l:
                        start = max(0, i - 5)
                        end = min(len(lines), i + 10)
                        print(f"\n  Контекст L{start+1}–L{end} (вокруг L{i}):")
                        for j in range(start, end):
                            marker = " >>>" if j + 1 == i else "    "
                            print(f"  {marker} L{j+1}: {lines[j]}")
            except Exception as e:
                print(f"  [read error: {e}]")


# ============================================================================
# ЭТАП 1.4: Формула confidence = 0.215
# ============================================================================
def stage1_4_confidence_formula() -> None:
    _print_section("ЭТАП 1.4: Формула confidence = 0.215 — происхождение")

    print(f"""
>>> Из B4:
  Торнин получил запись в EpistemicStore:
    source_id = maid_lusya
    original_source_id = player
    confidence = 0.215
    testimony (type)

  Это значение 0.215 — результат формулы, учитывающей:
  - confidence источника (Люси)
  - доверие Торнина к Люси
  - количество источников (corroboration)
  - время / затухание
  - тип знания (testimony vs direct observation)

>>> Нужно найти:
  1. Где вычисляется confidence при записи в EpistemicStore
  2. Какие коэффициенты используются
  3. Можно ли повысить confidence без изменения production-кода
     (например, повторная передача слуха, corroborating evidence)
""")

    # Search for confidence calculation
    print("\n--- Поиск вычисления confidence (confidence =, _confidence, compute_confidence) ---")
    results = _grep_in_dir(_BACKEND, ["confidence =", "_confidence =", "compute_confidence",
                                       "update_confidence", "confidence_factor"])
    print(f"Найдено {len(results)} совпадений (показаны первые 30):")
    for path, ln, line in results[:30]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Search for EpistemicStore update
    print("\n--- Поиск EpistemicStore.update / add_belief / record ---")
    results2 = _grep_in_dir(_BACKEND, ["epistemic_store", "EpistemicStore", "add_belief",
                                        "record_belief", "update_belief", "store_belief"])
    print(f"Найдено {len(results2)} совпадений (показаны первые 20):")
    for path, ln, line in results2[:20]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # Search for 0.215 literal (unlikely but check)
    print("\n--- Поиск литерала 0.215 ---")
    results3 = _grep_in_dir(_BACKEND, ["0.215"])
    if results3:
        for path, ln, line in results3:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")
    else:
        print("  [0.215 не найден как литерал — вычисляется формулой]")

    # Search for testimony confidence formula
    print("\n--- Поиск формулы testimony confidence ---")
    results4 = _grep_in_dir(_BACKEND, ["testimony", "witness", "source_confidence",
                                        "trust_factor", "credibility"])
    print(f"Найдено {len(results4)} совпадений (показаны первые 20):")
    for path, ln, line in results4[:20]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")


# ============================================================================
# ЭТАП 1.5: Может ли NPC естественно сблизиться
# ============================================================================
def stage1_5_natural_proximity() -> None:
    _print_section("ЭТАП 1.5: Может ли NPC естественно сблизиться")

    print(f"""
>>> Вопрос: могут ли Люся и Торнин естественно оказаться в допустимой дистанции?

  Известные позиции NPC в tavern.json:
    maid_lusya: (7.99, 1.83) — рядом с fireplace
    tavern_keeper_tornin: (4.5, 2.5) — за стойкой (behind_bar)

  Distance(maid_lusya, tavern_keeper_tornin):
    = sqrt((7.99 - 4.5)^2 + (1.83 - 2.5)^2)
    = sqrt(12.18 + 0.45)
    = sqrt(12.63)
    ≈ 3.55m

  Нужно найти: какой порог дистанции для PROP_TARGET_IN_REACH?
  Если порог = 3.0m → расстояние 3.55m > 3.0m → BLOCKED
  Если порог = 5.0m → 3.55m < 5.0m → OK

  NPC могут сблизиться естественно через:
    - schedule: working → kitchen → movement к node_16 → fireplace
    - SEEK_ALLY: движение к другому NPC
    - FLEE: движение от угрозы (теперь работает через door_0)

  После FLEE fix NPC могут двигаться. Но для коммуникации
  нужно, чтобы оба NPC были в одной точке/радиусе одновременно.
""")

    # Find communication distance threshold
    print("\n--- Поиск порога дистанции коммуникации ---")
    results = _grep_in_dir(_BACKEND, ["COMMUNICATION_RADIUS", "COMM_RANGE", "TALK_RADIUS",
                                       "DIALOGUE_RADIUS", "SPEECH_RADIUS", "comm_distance",
                                       "talk_distance", "dialogue_distance"])
    if results:
        for path, ln, line in results:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")
    else:
        print("  [явных констант радиуса коммуникации не найдено]")

    # Find constants file
    print("\n--- Поиск в constants.py ---")
    const_path = _BACKEND / "app/core/constants.py"
    if const_path.exists():
        src = const_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line.upper() for kw in ["RADIUS", "RANGE", "DISTANCE", "REACH",
                                                   "COMM", "TALK", "DIALOGUE", "SPEECH"]):
                print(f"  L{i}: {line.rstrip()}")

    # Find where PROP_TARGET_IN_REACH is checked
    print("\n--- Поиск 'PROP_TARGET' и 'in_reach' в коде ---")
    results2 = _grep_in_dir(_BACKEND, ["PROP_TARGET", "in_reach", "_in_reach", "is_in_reach"])
    for path, ln, line in results2[:20]:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")


# ============================================================================
# ИТОГ
# ============================================================================
def final_summary() -> None:
    _print_section("ИТОГ ЭТАПА 1 — сводка открытых препятствий")

    print(f"""
=============================================================================
ОТКРЫТЫЕ ПРЕПЯТСТВИЯ (после исследования)
=============================================================================

1. PROP_TARGET_IN_REACH:
   - Нужно найти точный код, который возвращает этот статус
   - Нужно найти порог дистанции
   - Нужно проверить, могут ли NPC сблизиться естественно

2. REPORT_CONFIDENCE_THRESHOLD = 0.25:
   - Нужно найти все места использования
   - Нужно понять, к каким операциям применяется (DecisionHub? EpistemicStore?)
   - Константу НЕ менять

3. confidence = 0.215:
   - Нужно найти формулу
   - Нужно понять, можно ли повысить confidence естественным путём
     (повторная передача, corroborating evidence)
   - Confidence НЕ повышать искусственно

=============================================================================
СЛЕДУЮЩИЕ ШАГИ
=============================================================================

После Этапа 1 (этот probe):
  - Если препятствия найдены и понятны → Этап 2 (baseline Торнина)
  - Если препятствия непреодолимы без изменения production-кода →
    зафиксировать и доложить Master

Этап 2: baseline Торнина
  - Снимок состояния до передачи слуха
  - EpistemicStore, beliefs, intents, decisions

Этап 3: Контрольный прогон A (без слуха)
  - Решения Торнина без передачи слуха
  - Фактические реплики

Этап 4: Экспериментальный прогон B (с слухом)
  - Полная цепочка: PLAYER_INSULTS → Люся → Торнин
  - 10 шагов от решения Люси до реплики Торнина

Этап 5: LLM — real Hermes-3-8B

Этап 7: Итоговый отчёт PASS/PARTIAL/FAIL
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-BUTTERFLY-B5-OBSTACLES — Этап 1: проверка открытых препятствий")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        stage1_1_prop_target_in_reach()
    except Exception as e:
        print(f"[stage1.1 error: {e}]")
        traceback.print_exc()

    try:
        stage1_2_communication_conditions()
    except Exception as e:
        print(f"[stage1.2 error: {e}]")
        traceback.print_exc()

    try:
        stage1_3_report_confidence_threshold()
    except Exception as e:
        print(f"[stage1.3 error: {e}]")
        traceback.print_exc()

    try:
        stage1_4_confidence_formula()
    except Exception as e:
        print(f"[stage1.4 error: {e}]")
        traceback.print_exc()

    try:
        stage1_5_natural_proximity()
    except Exception as e:
        print(f"[stage1.5 error: {e}]")
        traceback.print_exc()

    try:
        final_summary()
    except Exception as e:
        print(f"[final error: {e}]")
        traceback.print_exc()

    # Write to file
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

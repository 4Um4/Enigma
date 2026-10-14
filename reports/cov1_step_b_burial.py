# reports/cov1_step_b_burial.py
"""
Одноразовый скрипт COV-1 / Шаг 1 / коммит B (burial ExpectationStore,
COV-D100; вердикт Мастера II.Г; ADR-O-426 §8). Версия 2.

v2: убрана синтаксически невалидная строка-заглушка (урок: py_compile
перед передачей); Устав правится в ОДНОМ списке с ОДНОЙ записью (v1
перезаписала бы файл из устаревшей переменной).

ПРЕДУСЛОВИЕ ТЕКУЩЕГО ДЕРЕВА: expectation_store.py уже удалён и
застейджен (git rm исполнен) — скрипт этот файл не трогает.

Дисциплина (РЕЖИМ §3.7): стражи — ТОЛЬКО полные строки кода; ЛЮБОЙ
провал = ABORT ДО записи. Идемпотент: повтор = ABORT (маркер — файл
журнала изменений Устава). Печатает пары БЫЛО/СТАЛО.
После исполнения и коммита НЕ перезапускать.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PY_TICK = ROOT / "backend" / "app" / "services" / "tick_orchestrator.py"
PY_IDLE = ROOT / "backend" / "app" / "services" / "phases" / "idle_services.py"
PY_RNG = ROOT / "scripts" / "lint_kernel_rng.py"
PY_WC = ROOT / "scripts" / "lint_wall_clock.py"
USTAV = ROOT / "docs" / "АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md"
USTAV_CH = ROOT / "docs" / "АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md"

# ── Полные строки-якоря (вербатим из файлов) ──
GRAVE_TICK_1 = "        # DEEP-015 FIX: Мёртвый код ExpectationStore (Active Inference) удалён."
GRAVE_TICK_2 = "        # Хранилище никогда не инициализировалось, блоки всегда были no-op."
KEEP_TICK = "        # Оставляем пустой словарь, чтобы не ломать контракт build_tick_state."
GRAVE_IDLE = "    # DEEP-015 FIX: Мёртвый код ExpectationStore (PE Decay) удалён."
ALLOW_LINE = '    "services/npc/expectation_store.py",'
USTAV_PHASE_OLD = "    → PE Decay (ExpectationStore), Affective Decay, Perceptual Decay"
USTAV_PHASE_NEW = "    → Affective Decay, Perceptual Decay"
USTAV_ROW_PREFIX = "| ExpectationStore |"

CHANGES_ENTRY = """# Журнал изменений АРХИТЕКТУРНОГО УСТАВА ENIGMA

> Протокол §9 Устава: каждое изменение пункта Устава фиксируется записью здесь — обоснование, проверка нарушения других пунктов, зависимые диаграммы. Последняя запись — сверху.

## Запись 1 — Burial ExpectationStore (COV-D100; ADR-O-426 §8; вердикт Мастера II.Г)

- **Ветка/эпоха:** Б / COV-1 Шаг 1, коммит B (burial).
- **Изменённые пункты Устава:**
  1. §3, Фаза 0.5: из каскада удалён шаг «PE Decay (ExpectationStore)». Обоснование: стор мёртв с DEEP-015 (wiring удалён, 0 инстанцирований, memory.db никогда не существовал), decay ни разу не исполнялся; удаление упоминания приводит доктрину в соответствие с фактическим конвейером (§13.5 — рантайм старше документации). Файл expectation_store.py удалён (COV-D100).
  2. §12.5, реестр сериализационных адаптеров: удалена строка ExpectationStore (модуль удалён; рантайм-адаптера не существовало, test_kernel_rng покрывал KernelRNG, не стор).
- **Какой баг лечит:** stale-строки Устава на удалённый модуль; мёртвый код захоронен полностью, без сохранения «на будущее» (вердикт II.Г).
- **Проверка нарушения других пунктов:** нарушений нет — реальный конвейер Фазы 0.5 не менялся (шаг был no-op с DEEP-015); реестр §12.5 остаётся полным для живых адаптеров; §1–§18 не затронуты.
- **Зависимые диаграммы/документы:** architecture/*.yaml — скан скриптом reports/cov1_step_b_burial.py (результат в его выводе); CAUSAL CONTRACT v3.0 §8 содержит то же PE Decay-упоминание — зарегистрировано хвостом COV-11 (строка COV-D100), правка вне данного изменения; roadmap §16 MEM-8 «реанимация expectation-контура DEEP-015» — владелец А (отныне: новый дизайн + регистрация в реестре сторов до использования, ADR-O-426).
"""


def _abort(msg: str) -> None:
    print(f"[ABORT] {msg}")
    print("[ABORT] Стоп ДО записи: ни один файл не изменён.")
    sys.exit(1)


def _load(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _save(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def _c(line: str) -> str:
    return line.rstrip("\r\n")


def _find_one(lines: list[str], needle: str, label: str) -> int:
    hits = [i for i, ln in enumerate(lines) if _c(ln) == needle]
    if len(hits) != 1:
        _abort(f"{label}: строка-якорь найдена {len(hits)} раз (ожидалась ровно 1): {needle.strip()[:70]}…")
    return hits[0]


def _print_pair(label: str, old: list[str], new: list[str]) -> None:
    print()
    print(f"══════════ {label} — БЫЛО ══════════")
    for ln in old:
        print(ln if ln.strip() else "<пустая строка>")
    print(f"══════════ {label} — СТАЛО ══════════")
    for ln in new:
        print(ln if ln.strip() else "<пустая строка>")
    if not new:
        print("(строки удалены; соседний контент не изменён)")


def main() -> None:
    print("[COV-1 / коммит B] Burial ExpectationStore (COV-D100) — скрипт v2")
    if USTAV_CH.exists():
        _abort("журнал изменений Устава уже существует — скрипт уже исполнен")
    for p in (PY_TICK, PY_IDLE, PY_RNG, PY_WC, USTAV):
        if not p.exists():
            _abort(f"нет файла: {p}")

    # ═══ ФАЗА 1: ВСЕ проверки ДО записи ═══
    tick, tick_bom = _load(PY_TICK)
    idle, idle_bom = _load(PY_IDLE)
    rng, rng_bom = _load(PY_RNG)
    wc, wc_bom = _load(PY_WC)
    ust, ust_bom = _load(USTAV)

    tl = tick.splitlines(keepends=True)
    i1 = _find_one(tl, GRAVE_TICK_1, "tick/грав-1")
    if _c(tl[i1 + 1]) != GRAVE_TICK_2:
        _abort("tick: за грав-1 ожидается грав-2 (полная строка) — структура файла изменилась")
    if _c(tl[i1 + 2]) != KEEP_TICK or not _c(tl[i1 + 3]).lstrip().startswith("_pe_mods_map"):
        _abort("tick: после могильных строк ожидается KEEP-комментарий + _pe_mods_map (живой контракт) — не найдено")

    il = idle.splitlines(keepends=True)
    i2 = _find_one(il, GRAVE_IDLE, "idle/грав")
    if _c(il[i2 + 1]).strip() != "":
        _abort("idle: за могильной строкой ожидается пустая строка — структура изменилась")
    if not _c(il[i2 + 2]).lstrip().startswith("# ADR-036"):
        _abort("idle: после пустой ожидается комментарий ADR-036 — структура изменилась")

    rl = rng.splitlines(keepends=True)
    i3 = _find_one(rl, ALLOW_LINE, "lint_kernel_rng/allowlist")
    wl = wc.splitlines(keepends=True)
    i4 = _find_one(wl, ALLOW_LINE, "lint_wall_clock/allowlist")

    ul = ust.splitlines(keepends=True)
    i5 = _find_one(ul, USTAV_PHASE_OLD, "Устав/Фаза-0.5")
    row_hits = [i for i, ln in enumerate(ul) if _c(ln).startswith(USTAV_ROW_PREFIX)]
    if len(row_hits) != 1:
        _abort(f"Устав/§12.5: строка реестра по префиксу найдена {len(row_hits)} раз (ожидалась ровно 1)")

    print("[OK] Все стражи пройдены (7 правок валидны). Применяю…")

    # ═══ ФАЗА 2: применения (проверки GREEN) ═══
    del tl[i1:i1 + 2]
    _save(PY_TICK, "".join(tl), tick_bom)
    _print_pair("tick_orchestrator: удаление 2 могильных строк (KEEP + _pe_mods_map сохранены)",
                [GRAVE_TICK_1, GRAVE_TICK_2], [])

    del il[i2:i2 + 2]
    _save(PY_IDLE, "".join(il), idle_bom)
    _print_pair("idle_services: удаление могильной строки + смежной пустой",
                [GRAVE_IDLE, ""], [])

    del rl[i3:i3 + 1]
    _save(PY_RNG, "".join(rl), rng_bom)
    _print_pair("lint_kernel_rng: удаление allowlist-строки", [ALLOW_LINE], [])

    del wl[i4:i4 + 1]
    _save(PY_WC, "".join(wl), wc_bom)
    _print_pair("lint_wall_clock: удаление allowlist-строки", [ALLOW_LINE], [])

    ul[i5] = ul[i5].replace(USTAV_PHASE_OLD, USTAV_PHASE_NEW)
    del ul[row_hits[0]]
    _save(USTAV, "".join(ul), ust_bom)
    _print_pair("Устав §3 Фаза 0.5: каскад без мёртвого шага", [USTAV_PHASE_OLD], [USTAV_PHASE_NEW])
    _print_pair("Устав §12.5: удаление строки реестра ExpectationStore",
                [USTAV_ROW_PREFIX + " …(строка реестра)"], [])

    USTAV_CH.write_bytes(CHANGES_ENTRY.encode("utf-8"))
    print()
    print("══════════ НОВЫЙ ФАЙЛ: docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md ══════════")
    print("(БЫЛО: файл отсутствовал; СТАЛО: журнал по протоколу §9 Устава, запись 1)")

    # ═══ Послепроверки (read-only сканы) ═══
    print()
    print("[SCAN] Остаточные упоминания ExpectationStore/expectation_store в .py:")
    for base in ("backend", "scripts", "frontend"):
        for f in (ROOT / base).rglob("*.py"):
            txt = f.read_bytes().decode("utf-8", errors="ignore")
            if "ExpectationStore" in txt or "expectation_store" in txt:
                rel = f.relative_to(ROOT).as_posix()
                zone = "ЗОНА-А (ожидаемо)" if any(
                    k in rel for k in ("state_applicator", "npc_tick_pipeline", "conclusion_store")
                ) else "!!! НЕОЖИДАННО — доложи"
                print(f"  {rel} — {zone}")
    print("[SCAN] architecture/*.yaml + CAUSAL CONTRACT (info, хвосты COV-11):")
    for pat in (ROOT / "architecture").rglob("*.yaml"):
        txt = pat.read_bytes().decode("utf-8", errors="ignore")
        if "ExpectationStore" in txt or "PE Decay" in txt:
            print(f"  {pat.relative_to(ROOT).as_posix()}")
    for pat in (ROOT / "docs").glob("*CAUSAL_CONTRACT*"):
        txt = pat.read_bytes().decode("utf-8", errors="ignore")
        if "ExpectationStore" in txt or "PE Decay" in txt:
            print(f"  {pat.relative_to(ROOT).as_posix()} (известный хвост COV-D100/COV-11)")
    print()
    print("[OK] Готово. Далее: гейты → pathspec-коммит B (deletion уже в индексе).")


if __name__ == "__main__":
    main()

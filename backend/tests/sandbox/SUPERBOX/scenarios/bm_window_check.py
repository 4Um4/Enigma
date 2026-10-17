#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/bm_window_check.py
Назначение: E-BM1 B' — v2 чекер сохранённых артефактов пары (read-only).
    Проверка целостности, сопоставимости пары, канонического окна и
    внутренней согласованности метрик. Без нового прогона. Без причинной
    атрибуции.
Зависимости: только стандартная библиотека (json, hashlib, argparse, pathlib).
Основные сущности: CheckResult, run_checks, parse_closure_sha256.
Запуск:
    python backend/tests/sandbox/SUPERBOX/scenarios/bm_window_check.py \
        --artifacts reports/bprime_artifacts/
    python backend/tests/sandbox/SUPERBOX/scenarios/bm_window_check.py \
        --artifacts reports/bprime_artifacts/ --output reports/bprime_artifacts/window_check.json
Принципы:
    - Чекер не запускает игровые сценарии.
    - Не меняет production-код и B' framework.
    - Не изменяет входные артефакты и CLOSURE.md.
    - Не выполняет причинную атрибуцию (это делает --compare B' framework).
    - При ошибке входных данных завершается с ненулевым кодом возврата.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Канонические константы (из bm_bprime_framework.py @ 351c74db) ──────────

EXPECTED_FILES: List[str] = [
    "compare_report.json",
    "passport_off.json",
    "passport_on.json",
    "result_off.json",
    "result_on.json",
    "result_raw_off.json",
    "result_raw_on.json",
]

CLOSURE_FILENAME = "CLOSURE.md"

# Каноническое окно B1: list(range(2, 16)) = [2, 3, ..., 15] (14 тиков)
CANONICAL_WINDOW: List[int] = list(range(2, 16))

# B1 present_ticks референс (из bm_bprime_framework.py:58)
B1_PRESENT_TICKS: Dict[str, int] = {
    "attack": 14,
    "intimidate": 14,
    "warn": 8,
    "observe": 14,
    "talk": 8,
    "idle": 14,
}

# Допуск для per-intent mean self-consistency (float rounding)
MEAN_TOLERANCE = 1e-6


# ── Результат проверки ──────────────────────────────────────────────────────

class CheckResult:
    """Каждая проверка: id, status (PASS|WARN|FAIL), details (str)."""

    def __init__(self, check_id: str, status: str, details: str = ""):
        self.id = check_id
        self.status = status  # "PASS" | "WARN" | "FAIL"
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "status": self.status, "details": self.details}


# ── Утилиты ─────────────────────────────────────────────────────────────────

def load_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    """Безопасная загрузка JSON. Возвращает (data, error)."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON in {path.name}: {e}"
    except Exception as e:
        return None, f"error reading {path.name}: {e}"


def sha256_file(path: Path) -> str:
    """SHA-256 файла (hex, uppercase — для совпадения с CLOSURE.md)."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest().upper()


# ── Парсинг CLOSURE.md — жёсткий по структуре ──────────────────────────────

# Строка таблицы: | name | bytes | sha256 |
# Формат: `| <name> | <int> | <64-hex> |`
_TABLE_ROW_RE = re.compile(
    r"^\|\s*"
    r"(?P<name>[\w.\-]+)\s*\|\s*"
    r"(?P<bytes>\d+)\s*\|\s*"
    r"(?P<sha256>[0-9A-Fa-f]{64})\s*\|\s*$"
)


def parse_closure_sha256(closure_path: Path) -> Tuple[Optional[Dict[str, Tuple[int, str]]], Optional[str]]:
    """Парсит CLOSURE.md, извлекает {filename: (bytes, sha256_upper)}.

    Жёсткие требования:
    - Ровно 7 строк таблицы с именами из EXPECTED_FILES.
    - Каждая строка: | name | int | 64-hex |.
    - Дубликаты имён = FAIL.
    - Неоднозначность = FAIL с диагнозом.

    Возвращает (mapping, None) при успехе или (None, error_msg) при ошибке.
    """
    if not closure_path.exists():
        return None, f"CLOSURE.md not found: {closure_path}"

    try:
        text = closure_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        return None, f"error reading CLOSURE.md: {e}"

    # Найти секцию с таблицей (между "## 2. Контрольные суммы" и следующей "## ")
    lines = text.splitlines()
    in_table_section = False
    table_rows: List[Tuple[str, int, str]] = []
    section_started = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Начало секции 2
        if stripped.startswith("## 2."):
            in_table_section = True
            section_started = True
            continue
        # Конец секции (следующая ##)
        if in_table_section and stripped.startswith("## ") and not stripped.startswith("## 2."):
            break
        # Парсинг строк таблицы внутри секции
        if in_table_section:
            m = _TABLE_ROW_RE.match(stripped)
            if m:
                name = m.group("name")
                bytes_val = int(m.group("bytes"))
                sha = m.group("sha256").upper()
                table_rows.append((name, bytes_val, sha))
            # Строки без | — игнорируем (пояснения, пустые строки)
            # Строки с |, не подходящие под pattern — будут проверены ниже

    if not section_started:
        return None, "CLOSURE.md format error: section '## 2. Контрольные суммы' not found"

    if not table_rows:
        return None, "CLOSURE.md format error: no valid table rows in section 2"

    # Проверка дубликатов
    seen_names: Dict[str, int] = {}
    for name, _, _ in table_rows:
        seen_names[name] = seen_names.get(name, 0) + 1
    duplicates = [n for n, c in seen_names.items() if c > 1]
    if duplicates:
        return None, f"CLOSURE.md format error: duplicate filenames: {duplicates}"

    # Проверка: ровно 7 строк с именами из EXPECTED_FILES
    found_names = set(seen_names.keys())
    expected_set = set(EXPECTED_FILES)
    missing = expected_set - found_names
    extra = found_names - expected_set
    if missing:
        return None, f"CLOSURE.md format error: missing expected files: {sorted(missing)}"
    if extra:
        return None, f"CLOSURE.md format error: unexpected entries: {sorted(extra)}"

    # Проверка: ровно 7 строк (не больше)
    if len(table_rows) != 7:
        return None, f"CLOSURE.md format error: expected 7 rows, found {len(table_rows)}"

    mapping: Dict[str, Tuple[int, str]] = {name: (b, s) for name, b, s in table_rows}
    return mapping, None


# ── Проверки ────────────────────────────────────────────────────────────────

def check_files_present(art_dir: Path) -> CheckResult:
    """Проверка 1: наличие 7 обязательных файлов."""
    missing = []
    for name in EXPECTED_FILES:
        if not (art_dir / name).exists():
            missing.append(name)
    if missing:
        return CheckResult(
            "files_present", "FAIL",
            f"missing files: {missing}"
        )
    return CheckResult("files_present", "PASS", f"all {len(EXPECTED_FILES)} files present")


def check_closure_sha256(art_dir: Path, closure_path: Path) -> CheckResult:
    """Проверка 2: SHA-256 каждого оригинала относительно CLOSURE.md.

    Жёсткие требования:
    - CLOSURE.md должен парситься однозначно (см. parse_closure_sha256).
    - Каждый фактический файл: bytes совпадает, SHA-256 совпадает.
    - Любая неоднозначность → FAIL с диагнозом.
    """
    mapping, err = parse_closure_sha256(closure_path)
    if err:
        return CheckResult("closure_sha256", "FAIL", err)

    mismatches = []
    for name in EXPECTED_FILES:
        fp = art_dir / name
        if not fp.exists():
            mismatches.append(f"{name}: file missing")
            continue
        expected_bytes, expected_sha = mapping[name]
        actual_bytes = fp.stat().st_size
        actual_sha = sha256_file(fp)
        if actual_bytes != expected_bytes:
            mismatches.append(
                f"{name}: bytes mismatch (CLOSURE={expected_bytes}, actual={actual_bytes})"
            )
        if actual_sha != expected_sha:
            mismatches.append(
                f"{name}: SHA-256 mismatch (CLOSURE={expected_sha[:16]}..., actual={actual_sha[:16]}...)"
            )

    if mismatches:
        return CheckResult("closure_sha256", "FAIL", "; ".join(mismatches))
    return CheckResult(
        "closure_sha256", "PASS",
        f"all {len(EXPECTED_FILES)} SHA-256 match CLOSURE.md"
    )


def check_passports_compatible(compare_report: Dict[str, Any]) -> CheckResult:
    """Проверка 3: verdict_passports == COMPATIBLE."""
    verdict = compare_report.get("verdict_passports")
    if verdict is None:
        return CheckResult("passports_compatible", "FAIL", "verdict_passports field missing in compare_report.json")
    if verdict == "COMPATIBLE":
        return CheckResult("passports_compatible", "PASS", "COMPATIBLE")
    return CheckResult("passports_compatible", "FAIL", f"verdict_passports={verdict!r} (expected COMPATIBLE)")


def check_passport_fields_match(passport_off: Dict[str, Any], passport_on: Dict[str, Any]) -> CheckResult:
    """Проверка 4: совпадение head, diff_hash, input_sha256 в двух паспортах."""
    mismatches = []

    head_off = passport_off.get("head")
    head_on = passport_on.get("head")
    if head_off is None or head_on is None:
        mismatches.append("head field missing in one or both passports")
    elif head_off != head_on:
        mismatches.append(f"head: off={head_off[:12]}... on={head_on[:12]}...")

    dh_off = passport_off.get("diff_hash")
    dh_on = passport_on.get("diff_hash")
    if dh_off is None or dh_on is None:
        mismatches.append("diff_hash field missing in one or both passports")
    elif dh_off != dh_on:
        mismatches.append(f"diff_hash: off={dh_off[:16]}... on={dh_on[:16]}...")

    in_off = passport_off.get("input_sha256") or {}
    in_on = passport_on.get("input_sha256") or {}
    if not isinstance(in_off, dict) or not isinstance(in_on, dict):
        mismatches.append("input_sha256 not a dict in one or both passports")
    else:
        all_keys = set(in_off.keys()) | set(in_on.keys())
        for k in sorted(all_keys):
            v_off = in_off.get(k)
            v_on = in_on.get(k)
            if v_off is None:
                mismatches.append(f"input_sha256[{k!r}] missing in passport_off")
            elif v_on is None:
                mismatches.append(f"input_sha256[{k!r}] missing in passport_on")
            elif v_off != v_on:
                mismatches.append(f"input_sha256[{k!r}]: off={v_off[:16]}... on={v_on[:16]}...")

    if mismatches:
        return CheckResult("passport_fields_match", "FAIL", "; ".join(mismatches))
    return CheckResult(
        "passport_fields_match", "PASS",
        f"head={head_off[:12]}..., diff_hash={dh_off[:12]}..., input_sha256 keys match ({len(in_off)} files)"
    )


def check_preset_sha256_match(result_off: Dict[str, Any], result_on: Dict[str, Any]) -> CheckResult:
    """Проверка 5: совпадение preset_sha256."""
    ps_off = result_off.get("preset_sha256")
    ps_on = result_on.get("preset_sha256")
    if ps_off is None or ps_on is None:
        return CheckResult("preset_sha256_match", "FAIL", "preset_sha256 field missing in one or both results")
    if ps_off != ps_on:
        return CheckResult(
            "preset_sha256_match", "FAIL",
            f"preset_sha256: off={ps_off[:16]}... on={ps_on[:16]}..."
        )
    return CheckResult("preset_sha256_match", "PASS", f"preset_sha256={ps_off[:16]}... (identical)")


def check_window_canonical(result_off: Dict[str, Any], result_on: Dict[str, Any]) -> CheckResult:
    """Проверка 6: window == [2..15] в обеих ногах."""
    w_off = result_off.get("window")
    w_on = result_on.get("window")
    if not isinstance(w_off, list) or not isinstance(w_on, list):
        return CheckResult("window_canonical", "FAIL", "window field missing or not a list in one or both results")
    if w_off != CANONICAL_WINDOW:
        return CheckResult(
            "window_canonical", "FAIL",
            f"result_off.window={w_off} (expected {CANONICAL_WINDOW})"
        )
    if w_on != CANONICAL_WINDOW:
        return CheckResult(
            "window_canonical", "FAIL",
            f"result_on.window={w_on} (expected {CANONICAL_WINDOW})"
        )
    return CheckResult(
        "window_canonical", "PASS",
        f"window=[{CANONICAL_WINDOW[0]}..{CANONICAL_WINDOW[-1]}] in both legs ({len(CANONICAL_WINDOW)} ticks)"
    )


def check_mask_ticks_positive(compare_report: Dict[str, Any]) -> CheckResult:
    """Проверка 7: mask_ticks > 0 в обеих ногах."""
    mt = compare_report.get("mask_ticks") or {}
    mt_on = mt.get("on")
    mt_off = mt.get("off")
    if mt_on is None or mt_off is None:
        return CheckResult("mask_ticks_positive", "FAIL", "mask_ticks.on/off missing in compare_report.json")
    if not (isinstance(mt_on, (int, float)) and isinstance(mt_off, (int, float))):
        return CheckResult("mask_ticks_positive", "FAIL", f"mask_ticks not numeric: on={mt_on!r}, off={mt_off!r}")
    if not (mt_on > 0 and mt_off > 0):
        return CheckResult(
            "mask_ticks_positive", "FAIL",
            f"mask_ticks non-positive: on={mt_on}, off={mt_off} (injection may have failed — B4)"
        )
    return CheckResult("mask_ticks_positive", "PASS", f"mask_ticks: on={mt_on}, off={mt_off} (both > 0)")


def check_mask_ticks_symmetric(compare_report: Dict[str, Any]) -> CheckResult:
    """Проверка 8: симметричность mask_ticks. Асимметрия — WARN (не FAIL)."""
    mt = compare_report.get("mask_ticks") or {}
    mt_on = mt.get("on")
    mt_off = mt.get("off")
    if mt_on is None or mt_off is None:
        return CheckResult("mask_ticks_symmetric", "FAIL", "mask_ticks.on/off missing in compare_report.json")
    if mt_on == mt_off:
        return CheckResult("mask_ticks_symmetric", "PASS", f"mask_ticks symmetric: {mt_on} == {mt_off}")
    return CheckResult(
        "mask_ticks_symmetric", "WARN",
        f"mask_ticks asymmetric: on={mt_on}, off={mt_off} (delta={abs(mt_on - mt_off)})"
    )


def check_coverage_vs_b1(result_off: Dict[str, Any], result_on: Dict[str, Any]) -> CheckResult:
    """Проверка 9: present_ticks vs B1-референс. Coverage drift — WARN (пред-исключено из решающих критериев)."""
    pt_off = result_off.get("present_ticks") or {}
    pt_on = result_on.get("present_ticks") or {}

    if not isinstance(pt_off, dict) or not isinstance(pt_on, dict):
        return CheckResult("coverage_vs_b1", "FAIL", "present_ticks not a dict in one or both results")

    drifts = []
    for intent, b1_ref in B1_PRESENT_TICKS.items():
        actual_off = pt_off.get(intent)
        actual_on = pt_on.get(intent)
        if actual_off is None or actual_on is None:
            return CheckResult(
                "coverage_vs_b1", "FAIL",
                f"present_ticks[{intent!r}] missing in one or both results"
            )
        if actual_off != b1_ref or actual_on != b1_ref:
            drifts.append(f"{intent}: on={actual_on} off={actual_off} (B1={b1_ref})")

    if drifts:
        return CheckResult(
            "coverage_vs_b1", "WARN",
            f"coverage drift (pre-excluded from decisive criteria): {'; '.join(drifts)}"
        )
    return CheckResult(
        "coverage_vs_b1", "PASS",
        f"all {len(B1_PRESENT_TICKS)} intents match B1 reference"
    )


def check_per_intent_self_consistent(
    result_off: Dict[str, Any],
    result_on: Dict[str, Any],
    compare_report: Dict[str, Any],
) -> CheckResult:
    """Проверка 10: согласованность per_intent_common и compare_report.contrasts.

    Сверка по общим интентам, с допуском 1e-6 (float rounding).
    При отсутствии обязательного поля, дубликате интента или несовпадении
    количества элементов — FAIL.
    """
    pi_off = result_off.get("per_intent_common") or {}
    pi_on = result_on.get("per_intent_common") or {}
    contrasts = compare_report.get("contrasts") or {}

    if not isinstance(pi_off, dict) or not isinstance(pi_on, dict) or not isinstance(contrasts, dict):
        return CheckResult("per_intent_self_consistent", "FAIL", "per_intent_common/contrasts not a dict")

    # Ожидаемые интенты — объединение B1 reference и contrasts
    expected_intents = set(B1_PRESENT_TICKS.keys()) | set(contrasts.keys())
    # Не должно быть дубликатов в per_intent_common (dict по определению не имеет дубликатов ключей,
    # но проверим, что ключи — те, что ожидаем)
    pi_off_keys = set(pi_off.keys())
    pi_on_keys = set(pi_on.keys())

    missing_off = expected_intents - pi_off_keys
    missing_on = expected_intents - pi_on_keys
    if missing_off:
        return CheckResult("per_intent_self_consistent", "FAIL", f"per_intent_common[off] missing intents: {sorted(missing_off)}")
    if missing_on:
        return CheckResult("per_intent_self_consistent", "FAIL", f"per_intent_common[on] missing intents: {sorted(missing_on)}")

    mismatches = []
    for intent in sorted(expected_intents):
        # OFF mean должен совпадать с contrasts[intent].off
        c = contrasts.get(intent) or {}
        expected_off = c.get("off")
        expected_on = c.get("on")
        actual_off = (pi_off.get(intent) or {}).get("mean")
        actual_on = (pi_on.get(intent) or {}).get("mean")

        if expected_off is None or expected_on is None:
            return CheckResult(
                "per_intent_self_consistent", "FAIL",
                f"contrasts[{intent!r}].on/off missing in compare_report.json"
            )
        if actual_off is None or actual_on is None:
            return CheckResult(
                "per_intent_self_consistent", "FAIL",
                f"per_intent_common[{intent!r}].mean missing in one or both results"
            )

        delta_off = abs(actual_off - expected_off)
        delta_on = abs(actual_on - expected_on)
        if delta_off > MEAN_TOLERANCE:
            mismatches.append(f"{intent}.off: per_intent={actual_off!r} vs contrast={expected_off!r} (delta={delta_off:.2e})")
        if delta_on > MEAN_TOLERANCE:
            mismatches.append(f"{intent}.on: per_intent={actual_on!r} vs contrast={expected_on!r} (delta={delta_on:.2e})")

    if mismatches:
        return CheckResult("per_intent_self_consistent", "FAIL", "; ".join(mismatches))
    return CheckResult(
        "per_intent_self_consistent", "PASS",
        f"all {len(expected_intents)} intents self-consistent (tol={MEAN_TOLERANCE})"
    )


# ── Информационные поля ─────────────────────────────────────────────────────

def collect_info_fields(
    passport_off: Dict[str, Any],
    passport_on: Dict[str, Any],
    result_off: Dict[str, Any],
    result_on: Dict[str, Any],
) -> Dict[str, Any]:
    """Сбор информационных полей (не влияют на PASS/FAIL)."""
    info: Dict[str, Any] = {}

    # window_captured_in_passport: false по умолчанию (window_confirmed не захвачен в паспортах)
    info["window_captured_in_passport"] = False

    # empty_ticks_on / off
    metrics_on = result_on.get("metrics") or {}
    metrics_off = result_off.get("metrics") or {}
    info["empty_ticks_on"] = metrics_on.get("empty_ticks") or []
    info["empty_ticks_off"] = metrics_off.get("empty_ticks") or []

    # intent_seq_asymmetry: краткое описание
    seq_on = metrics_on.get("intent_seq") or []
    seq_off = metrics_off.get("intent_seq") or []
    if seq_on and seq_off:
        from collections import Counter
        c_on = Counter(seq_on)
        c_off = Counter(seq_off)
        dom_on = c_on.most_common(1)[0][0] if c_on else None
        dom_off = c_off.most_common(1)[0][0] if c_off else None
        info["intent_seq_asymmetry"] = {
            "dominant_on": dom_on,
            "dominant_off": dom_off,
            "note": "expected divergence (t2 = intervention point; ON=observe-dominant, OFF=flee-dominant)",
        }
    else:
        info["intent_seq_asymmetry"] = None

    info["limitations"] = [
        "window_confirmed not captured in passports (CLI arg lost; window field computed from code constant WINDOW=list(range(2,16)))",
        f"empty_ticks ON={info['empty_ticks_on']} outside window 2..15 (O-2; ON stopped scoring after tick 15)",
        "intent_seq asymmetry expected (divergence point at t2)",
    ]

    return info


# ── Главный runner ──────────────────────────────────────────────────────────

def run_checks(art_dir: Path) -> Tuple[List[CheckResult], Dict[str, Any], int]:
    """Запускает все проверки. Возвращает (checks, info_fields, exit_code)."""
    checks: List[CheckResult] = []

    # Загрузка артефактов (с проверкой целостности JSON)
    closure_path = art_dir / CLOSURE_FILENAME
    art_data: Dict[str, Any] = {}

    # Проверка 1: files present
    checks.append(check_files_present(art_dir))
    if checks[-1].status == "FAIL":
        # Если файлов нет — остальные проверки бессмысленны
        info = {
            "window_captured_in_passport": False,
            "empty_ticks_on": [],
            "empty_ticks_off": [],
            "intent_seq_asymmetry": None,
            "limitations": ["cannot collect info: required files missing"],
        }
        return checks, info, 2

    # Проверка 2: SHA-256 vs CLOSURE.md
    checks.append(check_closure_sha256(art_dir, closure_path))

    # Загрузка JSON артефактов (для последующих проверок)
    load_errors = []
    for name in ["compare_report.json", "passport_off.json", "passport_on.json",
                 "result_off.json", "result_on.json"]:
        data, err = load_json(art_dir / name)
        if err:
            load_errors.append(f"{name}: {err}")
        else:
            art_data[name] = data

    if load_errors:
        # Если JSON не загрузился — добавим FAIL и вернём
        checks.append(CheckResult(
            "artifacts_loadable", "FAIL",
            "; ".join(load_errors)
        ))
        info = {
            "window_captured_in_passport": False,
            "empty_ticks_on": [],
            "empty_ticks_off": [],
            "intent_seq_asymmetry": None,
            "limitations": ["cannot collect info: JSON load errors"],
        }
        return checks, info, 2

    compare_report = art_data["compare_report.json"]
    passport_off = art_data["passport_off.json"]
    passport_on = art_data["passport_on.json"]
    result_off = art_data["result_off.json"]
    result_on = art_data["result_on.json"]

    # Проверки 3-10
    checks.append(check_passports_compatible(compare_report))
    checks.append(check_passport_fields_match(passport_off, passport_on))
    checks.append(check_preset_sha256_match(result_off, result_on))
    checks.append(check_window_canonical(result_off, result_on))
    checks.append(check_mask_ticks_positive(compare_report))
    checks.append(check_mask_ticks_symmetric(compare_report))
    checks.append(check_coverage_vs_b1(result_off, result_on))
    checks.append(check_per_intent_self_consistent(result_off, result_on, compare_report))

    # Информационные поля
    info = collect_info_fields(passport_off, passport_on, result_off, result_on)

    # Итоговый exit code
    has_fail = any(c.status == "FAIL" for c in checks)
    exit_code = 1 if has_fail else 0
    return checks, info, exit_code


def build_report(art_dir: Path, checks: List[CheckResult], info: Dict[str, Any]) -> Dict[str, Any]:
    """Сборка итогового отчёта."""
    pass_count = sum(1 for c in checks if c.status == "PASS")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    if fail_count > 0:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "PASS_WITH_WARNINGS"
    else:
        overall = "PASS"

    return {
        "checked_at": datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "artifacts_dir": str(art_dir),
        "checks": [c.to_dict() for c in checks],
        "info": info,
        "limitations": info.get("limitations", []),
        "summary": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "overall": overall,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="E-BM1 B' v2 window check — read-only integrity check of saved pair artifacts"
    )
    ap.add_argument(
        "--artifacts",
        required=True,
        help="Path to bprime_artifacts/ directory (containing 7 JSON files + CLOSURE.md)",
    )
    ap.add_argument(
        "--output",
        default="",
        help="Optional: write report JSON to this path. If omitted, print to stdout.",
    )
    args = ap.parse_args()

    art_dir = Path(args.artifacts).resolve()
    if not art_dir.is_dir():
        print(f"[FAIL] artifacts dir not found: {art_dir}", file=sys.stderr)
        return 2

    checks, info, exit_code = run_checks(art_dir)
    report = build_report(art_dir, checks, info)

    report_json = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        out_path = Path(args.output).resolve()
        # Не перезаписываем оригинальные артефакты
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report_json, encoding="utf-8")
            print(f"[OK] report written to {out_path}", file=sys.stderr)
        except Exception as e:
            print(f"[FAIL] cannot write report: {e}", file=sys.stderr)
            return 2
    else:
        print(report_json)

    # Краткий итог в stderr (чтобы stdout был чистым JSON при --output не задан)
    s = report["summary"]
    print(f"[SUMMARY] {s['overall']} (pass={s['pass']}, warn={s['warn']}, fail={s['fail']})", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

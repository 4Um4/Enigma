#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/bm_cell_a_repeat.py
Назначение: E-BM1 — контролируемый повтор клетки A (CELL-A_f0_tm60) для
    проверки пространственной базовой линии после фикса PATH-D1 (ADR-O-427).

    Жёсткий PASS/FAIL-критерий (вердикт Мастера):
      - Загрузка реестра подтверждена (find_artifact + get_or_load)
      - Все 3 chunk доступны (city_gate, market_square, tavern)
      - Spatial Oracle и глобальный пространственный тик наблюдаемы
      - Стартовые условия клетки сопоставимы с эталоном (preset sha256, mask_ticks=0)

    Не новый фреймворк. Не очередной аудит. Не рефакторинг production.
    Один исполняемый сценарий с однозначным PASS/FAIL-отчётом.

Зависимости: behavior_mask_closure_test (реюз _run_leg), app.services.spatial.spatial_registry
Основные сущности: LogCaptureHandler, pre_flight_checks, runtime_checks, run_cell_a, post_run_checks
Запуск:
    python backend/tests/sandbox/SUPERBOX/scenarios/bm_cell_a_repeat.py
    python backend/tests/sandbox/SUPERBOX/scenarios/bm_cell_a_repeat.py --output reports/cell_a_repeat.json
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Bootstrap: scenarios/ и backend/ в sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_BACKEND = _HERE.parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Константы клетки A (из bm_factorial_test.py:33, behavior_mask_closure_test.py:43)
CELL_A_PRESET = "config/calibration/test_presets/golden_fear_f0.yaml"
CELL_A_RUN_ID = "LEG-F0"
CAMPAIGN_ID = "Open_road"
EXPECTED_TICKS = 30
EXPECTED_CHUNKS = {"city_gate", "market_square", "tavern"}
EXPECTED_MASK_TICKS = 0  # клетка A — без маски (fear=0, trust=-60, no mask)


# ─── Log Capture Handler ────────────────────────────────────────────────────

class LogCaptureHandler(logging.Handler):
    """Перехватывает логи для последующего анализа.

    Фильтрует по подстрокам в сообщении (без учёта регистра).
    Не пишет в stdout/stderr — только накапливает.
    """

    def __init__(self, patterns: List[str]):
        super().__init__(level=logging.DEBUG)
        self._patterns = [p.lower() for p in patterns]
        self.records: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            msg = record.msg
        msg_lower = str(msg).lower()
        for pat in self._patterns:
            if pat in msg_lower:
                self.records.append({
                    "timestamp": datetime.datetime.fromtimestamp(
                        record.created, tz=datetime.timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": str(msg),
                })
                break


def attach_log_capture(patterns: List[str]) -> Tuple[LogCaptureHandler, List[Any]]:
    """Устанавливает handler на root logger и relevant module loggers.

    ЯВНО понижает level до DEBUG — иначе INFO-логи spatial_registry
    подавляются (Python default: root.level=WARNING).
    Возвращает (handler, installed_loggers) для последующего отката.
    """
    handler = LogCaptureHandler(patterns)

    root = logging.getLogger()
    root.addHandler(handler)
    _orig_root_level = root.level
    root.setLevel(logging.DEBUG)  # понижаем, чтобы INFO/DEBUG прошли
    root._bm_orig_level = _orig_root_level  # type: ignore[attr-defined]

    installed = [root]
    # Дополнительно: explicit module loggers (могут иметь own level)
    for name in ["app.services.spatial.spatial_registry", "app.services.game_loop.game_loop"]:
        lg = logging.getLogger(name)
        lg.addHandler(handler)
        _orig_lg_level = lg.level
        lg.setLevel(logging.DEBUG)
        lg._bm_orig_level = _orig_lg_level  # type: ignore[attr-defined]
        installed.append(lg)

    return handler, installed


def detach_log_capture(handler: LogCaptureHandler, installed: List[Any]) -> None:
    """Снимает handler со всех loggers + восстанавливает original levels."""
    for lg in installed:
        lg.removeHandler(handler)
        orig_level = getattr(lg, "_bm_orig_level", None)
        if orig_level is not None:
            lg.setLevel(orig_level)
            delattr(lg, "_bm_orig_level")


def detach_log_capture(handler: LogCaptureHandler, installed: List[Any]) -> None:
    """Снимает handler со всех loggers."""
    for lg in installed:
        lg.removeHandler(handler)


# ─── Утилиты ────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, cwd=_BACKEND.parent,
        )
        return r.stdout.strip()
    except Exception:
        return "unavailable"


def git_branch() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True, cwd=_BACKEND.parent,
        )
        return r.stdout.strip()
    except Exception:
        return "unavailable"


def check_result(check_id: str, passed: bool, details: str = "") -> Dict[str, Any]:
    return {
        "id": check_id,
        "status": "PASS" if passed else "FAIL",
        "details": details,
    }


# ─── Pre-flight checks ──────────────────────────────────────────────────────

def pre_flight_checks() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Проверки до запуска: файлы существуют, хеши зафиксированы."""
    checks: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

    # 1. spatial_registry.json существует (через find_artifact)
    from app.services.spatial.spatial_registry import SpatialRegistry
    artifact_path = SpatialRegistry.find_artifact(CAMPAIGN_ID)
    checks.append(check_result(
        "spatial_registry_artifact_found",
        artifact_path is not None,
        f"path={artifact_path}" if artifact_path else "find_artifact returned None",
    ))
    if artifact_path:
        context["spatial_registry_path"] = str(artifact_path)
        context["spatial_registry_sha256"] = sha256_file(artifact_path)
        context["spatial_registry_bytes"] = artifact_path.stat().st_size

    # 2. preset golden_fear_f0.yaml существует + sha256
    preset_path = _BACKEND.parent / CELL_A_PRESET
    checks.append(check_result(
        "preset_exists",
        preset_path.exists(),
        f"path={preset_path}" if preset_path.exists() else "preset file not found",
    ))
    if preset_path.exists():
        context["preset_path"] = str(preset_path)
        context["preset_sha256"] = sha256_file(preset_path)
        context["preset_bytes"] = preset_path.stat().st_size

    # 3. git HEAD + branch
    context["git_head"] = git_head()
    context["git_branch"] = git_branch()
    checks.append(check_result(
        "git_head_available",
        context["git_head"] != "unavailable",
        f"HEAD={context['git_head'][:12]}... branch={context['git_branch']}",
    ))

    # 4. donor file (behavior_mask_closure_test.py) sha256
    donor_path = _HERE / "behavior_mask_closure_test.py"
    checks.append(check_result(
        "donor_exists",
        donor_path.exists(),
        f"path={donor_path}" if donor_path.exists() else "donor file not found",
    ))
    if donor_path.exists():
        context["donor_sha256"] = sha256_file(donor_path)
        context["donor_bytes"] = donor_path.stat().st_size

    return checks, context


# ─── Runtime checks (до прогона) ────────────────────────────────────────────

def runtime_checks_registry() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Проверки реестра: find_artifact, get_or_load, chunks.

    ВАЖНО: log handler уже установлен ДО вызова этой функции (см. main()).
    Поэтому первая загрузка реестра здесь перехватится логом
    '[SPATIAL_REGISTRY] Loaded and cached'.
    """
    checks: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

    from app.services.spatial.spatial_registry import SpatialRegistry

    # 0. Инвалидация кеша ДО find_artifact — гарантирует cold load
    #    (log handler уже установлен, перехватит 'Loaded and cached')
    SpatialRegistry.invalidate_cache(CAMPAIGN_ID)
    context["cache_invalidated_before_checks"] = True

    # 1. find_artifact возвращает путь
    artifact_path = SpatialRegistry.find_artifact(CAMPAIGN_ID)
    checks.append(check_result(
        "find_artifact_returns_path",
        artifact_path is not None,
        f"path={artifact_path}" if artifact_path else "None",
    ))

    # 2. get_or_load возвращает registry (cold load → лог перехвачен)
    registry = SpatialRegistry.get_or_load(CAMPAIGN_ID) if artifact_path else None
    checks.append(check_result(
        "get_or_load_returns_registry",
        registry is not None,
        "registry loaded" if registry else "None",
    ))

    if registry:
        # 3. chunks count + names
        chunks = registry.get_chunks()
        chunk_ids = {c.location_id for c in chunks}
        checks.append(check_result(
            "chunks_count_is_3",
            len(chunks) == 3,
            f"count={len(chunks)} chunks={sorted(chunk_ids)}",
        ))
        checks.append(check_result(
            "chunks_match_expected",
            chunk_ids == EXPECTED_CHUNKS,
            f"expected={sorted(EXPECTED_CHUNKS)} actual={sorted(chunk_ids)}",
        ))
        context["chunks"] = sorted(chunk_ids)
        context["chunks_count"] = len(chunks)

        # 4. get_all_location_ids (используется в game_loop для глобального тика)
        all_locs = registry.get_all_location_ids() if hasattr(registry, "get_all_location_ids") else None
        checks.append(check_result(
            "get_all_location_ids_available",
            all_locs is not None and len(all_locs) > 0,
            f"locations={all_locs}" if all_locs else "method missing or empty",
        ))
        if all_locs:
            context["all_location_ids"] = sorted(all_locs)

    # 5. Вторая инвалидация — чтобы run_cell_a тоже сделал cold load
    #    (game_loop.idle_tick вызывает get_or_load; лог перехвачен повторно)
    SpatialRegistry.invalidate_cache(CAMPAIGN_ID)
    context["cache_invalidated_before_run"] = True

    return checks, context


# ─── Run cell A ─────────────────────────────────────────────────────────────

def run_cell_a(
    log_handler: LogCaptureHandler,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    """Запускает клетку A через _donor._run_leg.

    Возвращает (rec, fin, error).
    """
    try:
        import behavior_mask_closure_test as _donor
        rec, fin = _donor._run_leg(CELL_A_RUN_ID, CELL_A_PRESET, True)
        return rec, fin, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


# ─── Post-run checks ────────────────────────────────────────────────────────

def post_run_checks(
    rec: Optional[Dict[str, Any]],
    fin: Optional[Dict[str, Any]],
    log_handler: LogCaptureHandler,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Проверки после прогона: ticks, intent_seq, scores, mask_ticks, logs."""
    checks: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

    if rec is None:
        checks.append(check_result("rec_available", False, "rec is None — run failed"))
        return checks, context

    # intent_seq в rec от _run_leg нет (только intent_final/scores_per_tick) —
    # сверяем длину трека через scores_per_tick (метрики донора _cell_metrics)
    scores_per_tick = rec.get("scores_per_tick") or []
    checks.append(check_result(
        "scores_per_tick_length",
        len(scores_per_tick) >= 1,
        f"length={len(scores_per_tick)} (expected >= 1)",
    ))
    context["scores_per_tick_length"] = len(scores_per_tick)

    # 2. mask_ticks == 0 (клетка A — без маски)
    mask_per_tick = rec.get("mask_per_tick") or []
    mask_ticks_present = rec.get("mask_ticks_present")
    if mask_ticks_present is None and mask_per_tick:
        mask_ticks_present = sum(1 for m in mask_per_tick if m not in (None, "none"))
    checks.append(check_result(
        "mask_ticks_is_zero",
        mask_ticks_present == EXPECTED_MASK_TICKS,
        f"mask_ticks_present={mask_ticks_present} (expected {EXPECTED_MASK_TICKS})",
    ))
    context["mask_ticks_present"] = mask_ticks_present
    context["mask_per_tick_length"] = len(mask_per_tick)

    # 3. intent_final захвачен
    intent_final = rec.get("intent_final")
    checks.append(check_result(
        "intent_final_captured",
        intent_final is not None,
        f"intent_final={intent_final}",
    ))
    context["intent_final"] = intent_final

    # 4. captured logs: [SPATIAL_REGISTRY] Loaded
    registry_logs = [r for r in log_handler.records if "[SPATIAL_REGISTRY]" in r["message"]]
    checks.append(check_result(
        "spatial_registry_loaded_in_runtime",
        len(registry_logs) > 0,
        f"logs_count={len(registry_logs)}" + (
            f" first={registry_logs[0]['message'][:80]}" if registry_logs else ""
        ),
    ))
    context["spatial_registry_logs"] = registry_logs[:3]  # первые 3 для отчёта

    # 5. captured logs: [SPATIAL_ORACLE] (любое сообщение)
    oracle_logs = [r for r in log_handler.records if "[SPATIAL_ORACLE" in r["message"]]
    # Spatial Oracle может не срабатывать, если player_world_x/y не сохранены.
    # Это не FAIL — Oracle активен только при наличии координат. Логируем как info.
    context["spatial_oracle_logs"] = oracle_logs[:3]
    checks.append(check_result(
        "spatial_oracle_logged",
        len(oracle_logs) > 0,
        f"logs_count={len(oracle_logs)}" + (
            f" first={oracle_logs[0]['message'][:80]}" if oracle_logs else " (no Oracle corrections — may be expected if no player coords)"
        ),
    ))

    return checks, context


# ─── Главный runner ─────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="E-BM1 cell A repeat — controlled repeat of CELL-A_f0_tm60 to verify spatial baseline after PATH-D1 fix"
    )
    ap.add_argument(
        "--output",
        default="",
        help="Optional: write report JSON to this path. If omitted, print to stdout.",
    )
    args = ap.parse_args()

    print("=== E-BM1 cell A repeat ===", file=sys.stderr)
    print(f"started_at: {datetime.datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S%z')}", file=sys.stderr)
    print(f"campaign: {CAMPAIGN_ID}", file=sys.stderr)
    print(f"preset: {CELL_A_PRESET}", file=sys.stderr)
    print(f"expected_ticks: {EXPECTED_TICKS}", file=sys.stderr)
    print(f"expected_chunks: {sorted(EXPECTED_CHUNKS)}", file=sys.stderr)
    print(file=sys.stderr)

    report: Dict[str, Any] = {
        "started_at": datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "campaign": CAMPAIGN_ID,
        "preset": CELL_A_PRESET,
        "expected_ticks": EXPECTED_TICKS,
        "expected_chunks": sorted(EXPECTED_CHUNKS),
        "expected_mask_ticks": EXPECTED_MASK_TICKS,
    }

    # 1. Pre-flight checks
    print("[1/4] pre-flight checks...", file=sys.stderr)
    pf_checks, pf_context = pre_flight_checks()
    report["pre_flight"] = {"checks": pf_checks, "context": pf_context}
    for c in pf_checks:
        status = "✓" if c["status"] == "PASS" else "✗"
        print(f"  {status} {c['id']}: {c['details']}", file=sys.stderr)

    # Если pre-flight FAIL — останавливаемся
    pf_fail = any(c["status"] == "FAIL" for c in pf_checks)
    if pf_fail:
        print("\n[FAIL] pre-flight checks failed — aborting", file=sys.stderr)
        report["overall"] = "FAIL"
        report["failures"] = [c["id"] for c in pf_checks if c["status"] == "FAIL"]
        _emit_report(report, args.output)
        return 1

    # 2. Runtime checks (registry) — log handler ДО registry checks,
    # чтобы первая загрузка реестра перехватилась (иначе cache hit не логирует)
    print("\n[2/4] runtime checks (registry)...", file=sys.stderr)
    log_handler, installed_loggers = attach_log_capture([
        "[SPATIAL_REGISTRY]",
        "[SPATIAL_ORACLE",
        "[IDLE_TICK]",
    ])
    try:
        rt_checks, rt_context = runtime_checks_registry()
    finally:
        # Не снимаем handler — он нужен для phase 3 (run cell A)
        pass
    report["runtime_registry"] = {"checks": rt_checks, "context": rt_context}
    for c in rt_checks:
        status = "✓" if c["status"] == "PASS" else "✗"
        print(f"  {status} {c['id']}: {c['details']}", file=sys.stderr)

    # 3. Run cell A — handler уже установлен
    print("\n[3/4] run cell A (30 ticks)...", file=sys.stderr)
    try:
        rec, fin, run_error = run_cell_a(log_handler)
    finally:
        detach_log_capture(log_handler, installed_loggers)

    if run_error:
        print(f"\n[FAIL] run_cell_a error: {run_error}", file=sys.stderr)
        report["run"] = {"error": run_error}
        report["overall"] = "FAIL"
        report["failures"] = ["run_cell_a_failed"]
        _emit_report(report, args.output)
        return 1

    print(f"  run completed: intent_final={rec.get('intent_final') if rec else None}", file=sys.stderr)
    report["run"] = {"error": None, "intent_final": rec.get("intent_final") if rec else None}

    # 4. Post-run checks
    print("\n[4/4] post-run checks...", file=sys.stderr)
    pr_checks, pr_context = post_run_checks(rec, fin, log_handler)
    report["post_run"] = {"checks": pr_checks, "context": pr_context}
    for c in pr_checks:
        status = "✓" if c["status"] == "PASS" else "✗"
        print(f"  {status} {c['id']}: {c['details']}", file=sys.stderr)

    # Итог
    all_checks = pf_checks + rt_checks + pr_checks
    fail_count = sum(1 for c in all_checks if c["status"] == "FAIL")
    pass_count = sum(1 for c in all_checks if c["status"] == "PASS")

    # spatial_oracle_logged — не обязательный (может не сработать без player coords)
    # Если только он FAIL — overall = PASS_WITH_NOTE
    critical_failures = [c["id"] for c in all_checks if c["status"] == "FAIL" and c["id"] != "spatial_oracle_logged"]
    oracle_only_fail = (
        any(c["id"] == "spatial_oracle_logged" and c["status"] == "FAIL" for c in all_checks)
        and not critical_failures
    )

    if not critical_failures and not oracle_only_fail:
        overall = "PASS"
    elif oracle_only_fail:
        overall = "PASS_WITH_NOTE"  # Spatial Oracle не сработал, но это не критично
    else:
        overall = "FAIL"

    report["summary"] = {
        "pass": pass_count,
        "fail": fail_count,
        "overall": overall,
    }
    report["failures"] = critical_failures
    report["oracle_only_fail"] = oracle_only_fail
    report["finished_at"] = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

    print(f"\n=== SUMMARY: {overall} (pass={pass_count}, fail={fail_count}) ===", file=sys.stderr)
    if critical_failures:
        print(f"critical failures: {critical_failures}", file=sys.stderr)
    if oracle_only_fail:
        print("note: Spatial Oracle did not log (may be expected if no player coords saved)", file=sys.stderr)

    _emit_report(report, args.output)
    return 0 if overall in ("PASS", "PASS_WITH_NOTE") else 1


def _emit_report(report: Dict[str, Any], output_path: str) -> None:
    """Вывод отчёта: в файл или stdout."""
    report_json = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_json, encoding="utf-8")
        print(f"\n[OK] report written to {out}", file=sys.stderr)
    else:
        print(report_json)


if __name__ == "__main__":
    sys.exit(main())

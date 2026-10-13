from __future__ import annotations

# reports/cov1_stamp_tool.py
"""
path: reports/cov1_stamp_tool.py
Назначение: COV-1 Шаг D — контролируемый стампинг живых БД (вердикт
Мастера I.3 — 8 условий; ADR-O-426 §7). Двухфазный:
  dry-run (по умолчанию): живые файлы ТОЛЬКО ЧИТАЮТСЯ — согласованная
    копия (online backup API, WAL-корректно) → классификация/план →
    ТЕНЕВОЕ применение к копии → верификация. Отчёт: консоль +
    reports/cov1_stamp_dryrun.json. Можно повторять без ограничений.
  --apply --confirm-stamp: ТОЛЬКО после явного подтверждения оператора:
    свежий пре-флайт (копия+тень; расхождение = СТОП, условие 8) →
    бэкап живого файла (backup API + верификация, условие 4) →
    применение (условие 5: только однозначные состояния — неоднозначное
    = MigrationError, файл нетронут) → послепроверка (условие 6) →
    reports/cov1_stamp_report.{json,md} (условие 7).
Условие 1 (бэкенд остановлен): исполнить при остановленном бэкенде;
  жёсткая защита — BEGIN IMMEDIATE транзакции раннера (активный писатель
  = "database is locked" = громкий отказ, не тишина).
После успешного --apply НЕ перезапускать (отчёт зафиксирован);
повторный запуск безвреден (ok-noop, идемпотентность II.3).
Зависимости: sqlite3, json, argparse, tempfile, datetime, pathlib, sys;
app.services.state.migration_runner (sys.path на backend/).
Основные сущности: _copy_db, _inspect, _shadow, cmd_dry, cmd_apply.
"""

import argparse
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.state import migration_runner as mr  # noqa: E402

DRY_JSON = ROOT / "reports" / "cov1_stamp_dryrun.json"
REPORT_JSON = ROOT / "reports" / "cov1_stamp_report.json"
REPORT_MD = ROOT / "reports" / "cov1_stamp_report.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reg_for(store_id: str, db_path: Path) -> mr.StoreRegistration:
    builtin = {r.store_id: r for r in mr.build_default_registry()}
    src = builtin[store_id]
    return mr.StoreRegistration(
        store_id=store_id,
        path_resolver=lambda p=db_path: p,
        bootstrap_classifier=src.bootstrap_classifier,
        migrations=src.migrations,
    )


def _copy_db(src: Path, dst: Path) -> None:
    """Согласованная копия: online backup API (корректен при WAL)."""
    s = sqlite3.connect(str(src))
    try:
        d = sqlite3.connect(str(dst))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _inspect(db: Path) -> dict:
    conn = sqlite3.connect(str(db))
    try:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        counts = mr._table_counts(conn)
    finally:
        conn.close()
    return {"user_version": version, "integrity": integrity, "counts": counts}


def _counts_preserved(before: dict, after: dict) -> bool:
    return all(after.get(t) == c for t, c in before.items()) and not (set(before) - set(after))


def _shadow(store_id: str, live: Path, tmp_dir: Path) -> dict:
    """Живой файл только читается; вся механика — на копии."""
    entry: dict = {"store_id": store_id, "live_path": str(live), "exists": live.exists()}
    if not live.exists():
        entry["classification"] = {"status": "skipped",
                                   "reason": "файл не существует — стор не активен (skip без создания)"}
        return entry
    entry["size_bytes"] = live.stat().st_size
    copy = tmp_dir / live.name
    _copy_db(live, copy)
    entry["copy_path"] = str(copy)
    before = _inspect(copy)

    plan = mr.run_startup_migrations([_reg_for(store_id, copy)], dry_run=True, make_backup=False)[0]
    entry["classification"] = {
        "status": plan.status,
        "detected_version": plan.detected_version,
        "head_version": plan.head_version,
        "plan": list(plan.plan),
        "reason": plan.reason,
        "counts": before["counts"],
    }

    shadow = mr.run_startup_migrations([_reg_for(store_id, copy)], dry_run=False, make_backup=False)[0]
    after = _inspect(copy)
    preserved = (after["counts"] == before["counts"]) if shadow.baseline_stamped \
        else _counts_preserved(before["counts"], after["counts"])
    entry["shadow"] = {
        "status": shadow.status,
        "applied": [list(a) for a in shadow.applied],
        "baseline_stamped": shadow.baseline_stamped,
        "version_before": before["user_version"],
        "version_after": after["user_version"],
        "integrity_after": after["integrity"],
        "counts_preserved": preserved,
    }
    return entry


def _entry_ok(e: dict) -> bool:
    if not e.get("exists", True):
        return True  # skip — не ошибка
    s = e.get("shadow")
    if not s:
        return False
    return (
        s["status"] == "ok"
        and s["version_after"] == e["classification"]["head_version"]
        and s["integrity_after"] == "ok"
        and s["counts_preserved"]
    )


def _print_entry(e: dict) -> None:
    print(f"  [{e.get('store_id')}] {e.get('live_path')}")
    if not e.get("exists", True):
        print("    skipped: файл не существует")
        return
    c = e.get("classification")
    if c:
        print(f"    классификация: {c['status']} (detected={c['detected_version']}, head={c['head_version']})")
        for step in c.get("plan", []):
            print(f"      план: {step}")
    s = e.get("shadow")
    if s:
        print(
            f"    тень: {s['status']} applied={s['applied']} baseline={s['baseline_stamped']} "
            f"v{s['version_before']}->{s['version_after']} integrity={s['integrity_after']} "
            f"counts_ok={s['counts_preserved']}"
        )
    if e.get("status") and not s:
        print(f"    статус: {e['status']} {e.get('reason', '')}")


def _write_json(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(report: dict) -> None:
    lines = [
        "# COV-1 Шаг D — отчёт стампинга живых БД",
        "",
        f"> ADR-O-426 §7; вердикт Мастера I.3 (8 условий). Режим: **{report['mode']}**. "
        f"Сгенерирован: {report['generated_at']}. Итог: **{'OK' if report.get('ok') else 'STOP/RED'}**.",
        "",
    ]
    for e in report["stores"]:
        lines.append(f"## {e['store_id']}")
        lines.append(f"- Файл: `{e['live_path']}`")
        if not e.get("exists", True):
            lines.append("- Статус: skipped (файл не существует; создание запрещено)")
            lines.append("")
            continue
        c = e.get("classification")
        if c:
            lines.append(
                f"- Классификация: {c['status']}; detected={c['detected_version']}, "
                f"HEAD={c['head_version']}; план: {c.get('plan') or '—'}"
            )
        s = e.get("shadow")
        if s:
            lines.append(
                f"- Тень на копии: {s['status']}; applied={s['applied']}; "
                f"baseline_stamped={s['baseline_stamped']}; "
                f"v{s['version_before']}→v{s['version_after']}; "
                f"integrity={s['integrity_after']}; данные сохранены={s['counts_preserved']}"
            )
        for key in ("status", "applied", "baseline_stamped", "backup_path",
                    "detected_version", "head_version", "version_before", "version_after",
                    "integrity_after", "reason"):
            if key in e and key not in ("classification", "shadow"):
                lines.append(f"- {key}: {e[key]}")
        if "counts_before" in e:
            lines.append(f"- counts_before: `{e['counts_before']}`")
            lines.append(f"- counts_after: `{e['counts_after']}`")
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def cmd_dry(tmp_dir: Path, *, quiet: bool = False) -> dict:
    report = {"mode": "dry-run", "generated_at": _now(), "tmp_dir": str(tmp_dir), "stores": []}
    if not quiet:
        print(f"[DRY-RUN] Копии в: {tmp_dir}")
        print("[DRY-RUN] Живые файлы НЕ изменяются (только чтение через backup API)")
    for reg in mr.build_default_registry():
        live = Path(reg.path_resolver())
        entry = _shadow(reg.store_id, live, tmp_dir)
        report["stores"].append(entry)
        if not quiet:
            _print_entry(entry)
    report["ok"] = all(_entry_ok(e) for e in report["stores"])
    if not quiet:
        print(f"[DRY-RUN] Итог: ok={report['ok']} — живые файлы НЕ тронуты")
        _write_json(DRY_JSON, report)
        print(f"[DRY-RUN] Отчёт: {DRY_JSON}")
    return report


def cmd_apply(tmp_dir: Path) -> int:
    print("[APPLY] Пре-флайт: свежая копия + тень (условие 8: расхождение = стоп)")
    pre = cmd_dry(tmp_dir, quiet=True)
    if not pre["ok"]:
        _write_json(DRY_JSON, pre)
        print("[ABORT] Пре-флайт НЕ зелёный — живые файлы НЕ тронуты (условие 8)")
        return 1
    print("[APPLY] Пре-флайт GREEN")
    report = {"mode": "apply", "generated_at": _now(), "preflight_tmp_dir": str(tmp_dir), "stores": []}
    print("[APPLY] Живые файлы: бэкап+верификация → применение → послепроверка")
    for reg in mr.build_default_registry():
        live = Path(reg.path_resolver())
        if not live.exists():
            entry = {"store_id": reg.store_id, "live_path": str(live), "exists": False,
                     "status": "skipped", "reason": "файл не существует"}
            report["stores"].append(entry)
            _print_entry(entry)
            continue
        before = _inspect(live)
        outcome = mr.run_startup_migrations([_reg_for(reg.store_id, live)], dry_run=False, make_backup=True)[0]
        after = _inspect(live)
        preserved = (after["counts"] == before["counts"]) if (outcome.baseline_stamped or outcome.status == "ok-noop") \
            else _counts_preserved(before["counts"], after["counts"])
        entry = {
            "store_id": reg.store_id,
            "live_path": str(live),
            "exists": True,
            "status": outcome.status,
            "detected_version": outcome.detected_version,
            "head_version": outcome.head_version,
            "applied": [list(a) for a in outcome.applied],
            "baseline_stamped": outcome.baseline_stamped,
            "backup_path": outcome.backup_path,
            "version_before": before["user_version"],
            "version_after": after["user_version"],
            "integrity_after": after["integrity"],
            "counts_before": before["counts"],
            "counts_after": after["counts"],
            "counts_preserved": preserved,
            "reason": outcome.reason,
        }
        report["stores"].append(entry)
        _print_entry(entry)
    report["ok"] = all(
        (not e.get("exists", True))
        or (
            e.get("status") in ("ok", "ok-noop")
            and e.get("version_after") == e.get("head_version")
            and e.get("integrity_after") == "ok"
            and e.get("counts_preserved")
        )
        for e in report["stores"]
    )
    _write_json(REPORT_JSON, report)
    _write_md(report)
    print(f"[APPLY] Итог: ok={report['ok']}")
    print(f"[APPLY] Отчёты: {REPORT_JSON} ; {REPORT_MD}")
    return 0 if report["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="COV-1 Step D: контролируемый стампинг живых БД")
    ap.add_argument("--apply", action="store_true", help="живой стампинг (по умолчанию — dry-run)")
    ap.add_argument("--confirm-stamp", action="store_true", help="обязательное подтверждение для --apply")
    args = ap.parse_args()
    tmp_dir = Path(tempfile.mkdtemp(prefix="cov1_stamp_"))
    if not args.apply:
        cmd_dry(tmp_dir)
        return 0
    if not args.confirm_stamp:
        print("[ABORT] --apply требует --confirm-stamp (явное подтверждение оператора; условие 8)")
        return 1
    return cmd_apply(tmp_dir)


if __name__ == "__main__":
    sys.exit(main())
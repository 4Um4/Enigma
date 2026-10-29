#!/usr/bin/env python3
"""
ME-1.6 Мигратор: разрешение двойного хранения location_templates/ vs campaigns/<id>/locations/

Назначение:
    - Сравнивает location_templates/*.json с campaigns/<campaign_id>/locations/*.json
      для каждой кампании (или указанной).
    - Сообщает о конфликтах (поле-уровневые расхождения).
    - По умолчанию: campaigns canonical (вердикт в.1); templates-only edits логируются
      как "orphaned edits, never reached the game".
    --apply-templates-edits: применяет правки templates к campaigns (если автор хочет
      сохранить утраченные правки). Safety-check: не заменяет массивы с campaigns-only ID.
    - Dry-run по умолчанию; --apply для записи.

Идемпотентность:
    Повторный прогон даёт тот же результат. Если campaigns уже canonical и templates
    не менялся — отчёт пустой.

Контракты:
    - Не трогает SpatialDataLoader / game_screen.py / world_context.py.
    - Не удаляет location_templates/ (он становится read-only starter library —
      это задача code changes, не migrator).
    - ME-1.9 (levels[]) / ME-1.11 (резервы) учтены: мигратор работает с любым
      JSON-содержимым, не предполагает конкретную схему.

Usage:
    python backend/scripts/me16_migrate_location_templates.py                    # dry-run, все кампании
    python backend/scripts/me16_migrate_location_templates.py --campaign Open_road
    python backend/scripts/me16_migrate_location_templates.py --apply            # campaigns canonical, no edits
    python backend/scripts/me16_migrate_location_templates.py --apply --apply-templates-edits
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# === Константы путей (Устав §12.1 — ключи/пути как константы) ===

ROOT = Path(__file__).resolve().parents[2]  # backend/scripts/ -> project root
TEMPLATES_DIR = ROOT / "frontend" / "map_editor" / "location_templates"
CAMPAIGNS_DIR = ROOT / "frontend" / "map_editor" / "campaigns"


def deep_diff(a: Any, b: Any, path: str = "") -> list[str]:
    """Рекурсивный diff двух JSON-значений. Возвращает список путей расхождений."""
    diffs: list[str] = []
    if type(a) is not type(b):
        diffs.append(f"{path}: type {type(a).__name__} vs {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        ak = set(a.keys())
        bk = set(b.keys())
        for k in sorted(ak - bk):
            diffs.append(f"{path}.{k}: only in templates" if path else f"{k}: only in templates")
        for k in sorted(bk - ak):
            diffs.append(f"{path}.{k}: only in campaigns" if path else f"{k}: only in campaigns")
        for k in sorted(ak & bk):
            sub = f"{path}.{k}" if path else k
            diffs.extend(deep_diff(a[k], b[k], sub))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: len {len(a)} vs {len(b)}")
        for i, (ae, be) in enumerate(zip(a, b)):
            diffs.extend(deep_diff(ae, be, f"{path}[{i}]"))
    else:
        if a != b:
            diffs.append(f"{path}: T={a!r}  C={b!r}")
    return diffs


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_campaigns() -> list[str]:
    if not CAMPAIGNS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in CAMPAIGNS_DIR.iterdir()
        if d.is_dir() and (d / "campaign.json").exists()
    )


def list_template_files() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(f.name for f in TEMPLATES_DIR.glob("*.json"))


def list_campaign_files(campaign_id: str) -> list[str]:
    cdir = CAMPAIGNS_DIR / campaign_id / "locations"
    if not cdir.exists():
        return []
    return sorted(f.name for f in cdir.glob("*.json"))


def _has_id_array(value: Any) -> bool:
    """Проверяет, является ли value массивом объектов с полем 'id'."""
    return (
        isinstance(value, list)
        and len(value) > 0
        and isinstance(value[0], dict)
        and "id" in value[0]
    )


def merge_templates_into_campaign(
    tpl: dict, camp: dict
) -> tuple[dict, list[str], list[str]]:
    """Применяет правки templates к campaigns (для --apply-templates-edits).

    Возвращает (merged_campaign, applied_actions, skipped_conflicts).
    Стратегия:
      - template-only top-level keys: добавить в campaigns
      - divergent fields: deep replace (templates выигрывает), КРОМЕ:
        - modified_at: не трогаем (timestamp campaigns)
        - массивы объектов с ID: если campaigns имеет ID не из templates — SKIP (конфликт)
    """
    applied: list[str] = []
    skipped: list[str] = []
    merged: dict = json.loads(json.dumps(camp))  # deep copy

    tpl_keys = set(tpl.keys())
    camp_keys = set(merged.keys())

    # Ключи только в templates — добавить
    for k in sorted(tpl_keys - camp_keys):
        merged[k] = tpl[k]
        applied.append(f"added top-level {k!r} from templates")

    # Ключи в обоих — deep replace для расходящихся
    for k in sorted(tpl_keys & camp_keys):
        if k == "modified_at":
            continue
        if tpl[k] == merged[k]:
            continue

        # Safety check: массив объектов с ID
        if _has_id_array(tpl[k]) and _has_id_array(merged[k]):
            tpl_ids = {o["id"] for o in tpl[k]}
            camp_ids = {o["id"] for o in merged[k]}
            only_camp = camp_ids - tpl_ids
            if only_camp:
                skipped.append(
                    f"SKIP {k!r}: campaigns has {len(only_camp)} unique ID(s) "
                    f"not in templates: {sorted(only_camp)[:5]}"
                )
                continue

        # Safe to replace
        merged[k] = json.loads(json.dumps(tpl[k]))
        applied.append(f"replaced {k!r} with templates version")

    return merged, applied, skipped


def migrate_campaign(
    campaign_id: str,
    apply: bool,
    apply_templates_edits: bool,
) -> dict:
    """Мигрирует одну кампанию. Возвращает отчёт."""
    report: dict = {
        "campaign": campaign_id,
        "template_files": list_template_files(),
        "campaign_files": list_campaign_files(campaign_id),
        "conflicts": [],
        "orphaned_template_edits": [],
        "actions": [],
        "skipped": [],
        "errors": [],
    }

    tpl_files = set(report["template_files"])
    camp_files = set(report["campaign_files"])

    # 1. Файлы только в templates — starter content not in campaign
    for f in sorted(tpl_files - camp_files):
        report["conflicts"].append({
            "file": f,
            "type": "template_only",
            "note": "starter file not in campaign",
        })
        if apply:
            src = TEMPLATES_DIR / f
            dst = CAMPAIGNS_DIR / campaign_id / "locations" / f
            save_json(dst, load_json(src))
            report["actions"].append(f"copied {f}: templates -> campaigns")

    # 2. Файлы только в campaigns — campaign-only file (легитимно)
    for f in sorted(camp_files - tpl_files):
        report["conflicts"].append({
            "file": f,
            "type": "campaign_only",
            "note": "campaign-only file (no starter template)",
        })

    # 3. Файлы в обоих — deep diff
    for f in sorted(tpl_files & camp_files):
        tpl = load_json(TEMPLATES_DIR / f)
        camp = load_json(CAMPAIGNS_DIR / campaign_id / "locations" / f)

        diffs = deep_diff(tpl, camp)
        if not diffs:
            continue

        orphan = [d for d in diffs if not d.startswith("modified_at")]
        report["conflicts"].append({
            "file": f,
            "type": "field_divergence",
            "diff_count": len(diffs),
            "diffs_sample": diffs[:20],
        })
        if orphan:
            report["orphaned_template_edits"].append({
                "file": f,
                "edits_count": len(orphan),
                "edits_sample": orphan[:10],
            })

        if apply and apply_templates_edits and orphan:
            merged, applied, skipped = merge_templates_into_campaign(tpl, camp)
            if applied:
                save_json(CAMPAIGNS_DIR / campaign_id / "locations" / f, merged)
                report["actions"].extend(
                    f"applied to {f}: {a}" for a in applied
                )
            if skipped:
                report["skipped"].extend(
                    f"{f}: {s}" for s in skipped
                )
        elif apply and not apply_templates_edits:
            report["actions"].append(
                f"{f}: campaigns canonical (verdikt v.1); "
                f"{len(orphan)} templates-only edits remain orphaned"
            )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ME-1.6: resolve location_templates/ vs campaigns/<id>/locations/ double storage"
    )
    parser.add_argument(
        "--campaign",
        default=None,
        help="specific campaign id (default: all campaigns)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="apply changes (default: dry-run, report only)",
    )
    parser.add_argument(
        "--apply-templates-edits",
        action="store_true",
        default=False,
        help="apply templates-only edits to campaigns (default: campaigns canonical, edits orphaned)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    print("ME-1.6 migrator: location_templates/ vs campaigns/<id>/locations/")
    print(f"  templates dir: {TEMPLATES_DIR}")
    print(f"  campaigns dir: {CAMPAIGNS_DIR}")
    print(f"  mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    print(
        f"  templates-edits: {'APPLY to campaigns' if args.apply_templates_edits else 'orphaned (campaigns canonical)'}"
    )
    print()

    if not TEMPLATES_DIR.exists():
        print(f"ERROR: templates dir not found: {TEMPLATES_DIR}", file=sys.stderr)
        return 1
    if not CAMPAIGNS_DIR.exists():
        print(f"ERROR: campaigns dir not found: {CAMPAIGNS_DIR}", file=sys.stderr)
        return 1

    campaigns = [args.campaign] if args.campaign else list_campaigns()
    if not campaigns:
        print("No campaigns found.", file=sys.stderr)
        return 1

    print(f"Campaigns to process: {campaigns}")
    print()

    total_conflicts = 0
    total_orphaned = 0
    total_actions = 0
    total_skipped = 0

    for cid in campaigns:
        report = migrate_campaign(
            cid,
            apply=args.apply,
            apply_templates_edits=args.apply_templates_edits,
        )

        conflicts = report["conflicts"]
        orphaned = report["orphaned_template_edits"]
        actions = report["actions"]
        skipped = report["skipped"]

        total_conflicts += len(conflicts)
        total_orphaned += len(orphaned)
        total_actions += len(actions)
        total_skipped += len(skipped)

        print(f"=== Campaign: {cid} ===")
        print(f"  template files: {len(report['template_files'])}")
        print(f"  campaign files: {len(report['campaign_files'])}")

        if conflicts:
            print(f"  conflicts: {len(conflicts)}")
            for c in conflicts:
                if c["type"] == "field_divergence":
                    print(
                        f"    [{c['file']}] field_divergence "
                        f"({c['diff_count']} diffs):"
                    )
                    for d in c["diffs_sample"][:5]:
                        print(f"      {d}")
                    if c["diff_count"] > 5:
                        print(f"      ... and {c['diff_count'] - 5} more")
                else:
                    print(f"    [{c['file']}] {c['type']}: {c['note']}")
        else:
            print("  conflicts: 0")

        if orphaned:
            print(f"  orphaned template edits: {len(orphaned)} file(s)")
            for o in orphaned:
                print(
                    f"    [{o['file']}] {o['edits_count']} orphaned edits"
                )

        if actions:
            label = "DRY-RUN" if dry_run else "APPLIED"
            print(f"  actions ({label}):")
            for a in actions:
                print(f"    {a}")

        if skipped:
            print(f"  skipped (conflicts need manual resolution): {len(skipped)}")
            for s in skipped:
                print(f"    {s}")

        print()

    print("=== SUMMARY ===")
    print(f"  campaigns processed: {len(campaigns)}")
    print(f"  total conflicts: {total_conflicts}")
    print(f"  total orphaned template edits: {total_orphaned}")
    print(f"  total actions: {total_actions} {'(dry-run)' if dry_run else '(applied)'}")
    print(f"  total skipped: {total_skipped}")

    if dry_run and total_conflicts > 0:
        print()
        print("Dry-run complete. To apply:")
        print("  --apply                          # campaigns canonical, templates edits stay orphaned")
        print("  --apply --apply-templates-edits  # apply templates edits to campaigns")

    return 0


if __name__ == "__main__":
    sys.exit(main())

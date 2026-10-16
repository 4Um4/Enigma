# path: backend/tests/sandbox/SUPERBOX/scenarios/ebm1_passport.py
# Назначение: H1-паспорт эксперимента E-BM1 (вердикт П2, усиленный контракт):
#   локальный самодостаточный паспорт прогона. HEAD-штамп НЕ доказывает чистоту
#   рантайма (инцидент Df3); паспорт фиксирует и незакоммиченное дерево.
#   Правило: нет обязательных полей -> прогон = наблюдение, НЕ заморозка.
# Зависимости: git CLI, stdlib. Production не импортируется и не меняется.
# Основные сущности: make_passport(), artifact_hashes(), freeze_valid(),
#   passports_compatible() (парные прогоны: argv исключается явно).
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SIGNIFICANT_ENV: Tuple[str, ...] = (
    "PYTHONHASHSEED", "COGNITION_DIAG", "R2_DIAG", "N18_EXP",
    "PYTHONDONTWRITEBYTECODE", "PYTHONWARNINGS",
)
# Значимые корни для манифеста untracked-содержимого (вердикт: снимок статуса
# сообщает о существовании, манифест — о содержимом). Gitignored-файлы
# (saves/, replay/) исключаются автоматически. Корни = whitelist-эвристика.
_UNTRACKED_ROOTS: Tuple[str, ...] = (
    "backend", "config", "frontend/map_editor/campaigns",
)
_MAX_UNTRACKED_BYTES = 8 * 1024 * 1024


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: List[str]) -> Optional[bytes]:
    try:
        out = subprocess.run(["git", *args], capture_output=True, check=True)
    except Exception:  # noqa: BLE001 — недоступность git фиксируется честно
        return None
    return out.stdout


def git_head() -> str:
    raw = _git(["rev-parse", "HEAD"])
    return raw.decode("utf-8", "replace").strip() if raw else "unavailable"


def status_porcelain() -> str:
    raw = _git(["status", "--porcelain"])
    return raw.decode("utf-8", "replace").strip() if raw else "unavailable"


def diff_hash() -> str:
    # Полный diff относительно HEAD: staged + unstaged отслеживаемых файлов.
    raw = _git(["diff", "HEAD"])
    if raw is None:
        return "unavailable"
    return hashlib.sha256(raw).hexdigest()


def untracked_manifest() -> Dict[str, Dict[str, Any]]:
    # Содержимое (SHA-256) незатреканных неигнорируемых файлов под значимыми
    # корнями: конфиг/реестр/локальный JSON могут менять рантайм, не трогая
    # Python-файлы (усиление вердикта П2).
    raw = _git(["ls-files", "--others", "--exclude-standard", *_UNTRACKED_ROOTS])
    if raw is None:
        return {"error": "unavailable"}
    manifest: Dict[str, Dict[str, Any]] = {}
    for rel in raw.decode("utf-8", "replace").splitlines():
        rel = rel.strip().replace("\\", "/")
        if not rel:
            continue
        try:
            size = Path(rel).stat().st_size
        except OSError:
            manifest[rel] = {"size": None, "sha256": "unreadable"}
            continue
        if size > _MAX_UNTRACKED_BYTES:
            manifest[rel] = {"size": size, "sha256": "skipped-oversize"}
            continue
        manifest[rel] = {"size": size, "sha256": sha256_file(rel)}
    return manifest


def runtime_manifest() -> Dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "argv": list(sys.argv),
        "cwd": str(Path.cwd()),
        "env": {k: os.environ.get(k) for k in _SIGNIFICANT_ENV},
    }


def make_passport(inputs: List[str]) -> Dict[str, Any]:
    return {
        "head": git_head(),
        "status_porcelain": status_porcelain(),
        "diff_hash": diff_hash(),
        "input_hashes": {p: sha256_file(p) for p in inputs},
        "untracked_manifest": untracked_manifest(),
        "runtime_manifest": runtime_manifest(),
    }


def artifact_hashes(paths: List[str]) -> Dict[str, str]:
    return {p: sha256_file(p) for p in paths}


_MANDATORY: Tuple[str, ...] = (
    "head", "status_porcelain", "diff_hash", "input_hashes",
    "untracked_manifest", "runtime_manifest",
)


def freeze_valid(passport: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Правило вердикта: нет обязательных полей -> НЕ каноническая заморозка."""
    problems: List[str] = []
    for key in _MANDATORY:
        if key not in passport:
            problems.append("missing:" + key)
        elif passport[key] == "unavailable":
            problems.append("unavailable:" + key)
    if passport.get("input_hashes") == {}:
        problems.append("empty:input_hashes")
    if "error" in passport.get("untracked_manifest", {}):
        problems.append("unavailable:untracked_manifest")
    return (not problems), problems


def passports_compatible(
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    ignore_argv: bool = True,
) -> Tuple[bool, List[str]]:
    """Парные прогоны (B' on/off): совпадать обязаны head, diff, porcelain,
    untracked, inputs, env; argv может отличаться флагом руки — исключён."""
    mismatches: List[str] = []
    for key in ("head", "diff_hash", "status_porcelain",
                "untracked_manifest", "input_hashes"):
        if p1.get(key) != p2.get(key):
            mismatches.append(key)
    r1 = p1.get("runtime_manifest", {})
    r2 = p2.get("runtime_manifest", {})
    for key in ("python", "cwd", "env"):
        if r1.get(key) != r2.get(key):
            mismatches.append("runtime:" + key)
    if not ignore_argv and r1.get("argv") != r2.get("argv"):
        mismatches.append("runtime:argv")
    return (not mismatches), mismatches
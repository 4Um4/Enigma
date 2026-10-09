"""
path: /project/scripts/lint_flags.py
Назначение: COV-0 Flag Registry enforcement (COV-D73 -> гейт COV-GC-04).
    Контракт Мастера: flags.yaml -> lint -> IPT; ручной синхронизации нет.
    Сканер (AST) собирает факты кода: env-чтения (os.environ.get/getenv,
    включая резолв констант-алиасов и any()-пары вида S203.4_x / S203_4_x),
    setdefault-писатели дефолтов (effective-семантика D8P-класса: модульный
    default != прод-эффективный), модульные булевы константы top-level,
    pydantic-поля Settings (env_prefix AIDM_; bool-поля + строковые
    replay_mode/environment). Сверка с architecture/flags.yaml:
      C1 NO-RECORD — флаг в коде без записи («новые флаги без вердикта
         не проходят CI», COV-GC-04);
      C2 STALE — запись без живого флага (флаг удалён — реестр протух);
      C3 DEFAULT-DRIFT — yaml != код; включая конфликт дефолтов между
         сайтами одного флага;
      C4 EFFECTIVE-DRIFT — setdefault-писатель не отражён в effective_default;
      C5 READ-MODE — import/call/mixed/pydantic;
      C6 DOC-DRIFT def-site — «default OFF|ON» в окне ±8/3 строк определения
         против фактического литерала (урок npc_dialogue_subscriber:25-30:
         флаг ON, комментарий OFF; usage-site — v2);
      C7 VERDICT — таксономия реестра.
    fail-loud: PARSE/registry-ошибки = RED, не тихий skip (L4).
Зависимости: ast, re, sys, pathlib, yaml (прецедент lint_relationship_engine).
Основные сущности: FlagSite, scan_file, run_lint.
Запуск (из корня проекта): python scripts/lint_flags.py  (exit 0 / 1)
"""

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = [ROOT / "backend" / "app", ROOT / "frontend"]
REGISTRY_PATH = ROOT / "architecture" / "flags.yaml"

VALID_VERDICTS = {
    "ROLLOUT-ON",
    "ROLLOUT-PENDING",
    "KEEP-LOG",
    "BURY",
    "INFRA",
    "AUDIT-NEEDED",
    "CALIBRATION",
}
PYDANTIC_SETTINGS_CLASS = "Settings"
PYDANTIC_STRING_FLAGS = {"replay_mode", "environment"}

_TRUTHY = {"1", "true", "yes", "on"}
_DOC_RE = re.compile(r"default\s+(ON|OFF)", re.IGNORECASE)
_DOC_WINDOW_BEFORE = 8
_DOC_WINDOW_AFTER = 3


class FlagSite:
    """Один сайт определения/чтения флага: файл:строка + литерал дефолта."""

    __slots__ = ("name", "read_mode", "default", "file", "line", "doc_claim")

    def __init__(
        self,
        name: str,
        read_mode: str,
        default: str,
        file: Path,
        line: int,
        doc_claim: Optional[str],
    ) -> None:
        self.name = name
        self.read_mode = read_mode
        self.default = default
        self.file = file
        self.line = line
        self.doc_claim = doc_claim


def _norm_default(value: object) -> str:
    """Нормализация литерала дефолта к сравнимой строке (none/true/false/литерал)."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _truthy(default_str: str) -> bool:
    return default_str.strip().lower() in _TRUTHY


def scan_file(py: Path) -> Tuple[Dict[str, List[FlagSite]], Dict[str, str]]:
    """Сканирует один .py: сайты флагов + setdefault-писатели."""
    src = py.read_text(encoding="utf-8-sig")
    lines = src.splitlines()
    tree = ast.parse(src)

    os_aliases: Set[str] = {"os"}
    string_consts: Dict[str, str] = {}
    for node in tree.body:
        targets: List[ast.Name] = []
        value: Optional[ast.expr] = None
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        for t in targets:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                string_consts[t.id] = value.value
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "os" and a.asname:
                    os_aliases.add(a.asname)

    sites: Dict[str, List[FlagSite]] = {}
    writers: Dict[str, str] = {}

    def _doc_claim(line_no: int) -> Optional[str]:
        # Окно вокруг определения: ловит def-site doc-drift (урок :25-30).
        lo = max(0, line_no - 1 - _DOC_WINDOW_BEFORE)
        hi = min(len(lines), line_no + _DOC_WINDOW_AFTER)
        for raw in lines[lo:hi]:
            m = _DOC_RE.search(raw)
            if m:
                return m.group(1).upper()
        return None

    def _str_of(node: Optional[ast.expr]) -> Optional[str]:
        # Constant-строка ИЛИ резолв константы-алиаса (ADR-O-421a-паттерн).
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return string_consts.get(node.id)
        return None

    def _env_kind(call: ast.Call) -> Optional[str]:
        f = call.func
        if isinstance(f, ast.Attribute) and f.attr in ("get", "setdefault"):
            base = f.value
            if (
                isinstance(base, ast.Attribute)
                and base.attr == "environ"
                and isinstance(base.value, ast.Name)
                # bootstrap-урок: локальные «import os as _os_*» в методах
                # (decision_hub:551/586/786, simulation:150, task_scheduler:570,
                # scene_state_manager:301/1255, integration:438, tick_utils:422,
                # downloader) не собирались top-level проходом — call-сайты
                # через алиас были невидимы (7 фантомных C2 + 1 C5). Любой
                # Name-базис с атрибутом .environ считаем os: слой намеренно
                # тупой/подозрительный (прецедент ADR-O-414), getenv-ветка
                # ниже по-прежнему строго по алиасам.
            ):
                return f.attr
        if isinstance(f, ast.Attribute) and f.attr == "getenv":
            base = f.value
            if isinstance(base, ast.Name) and base.id in os_aliases:
                return "getenv"
        return None

    class _Walker(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if node.name == PYDANTIC_SETTINGS_CLASS:
                # Settings: поля = pydantic-флаги (env_prefix AIDM_).
                # Внутрь не спускаемся: body — только объявления полей.
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.AnnAssign)
                        and isinstance(stmt.target, ast.Name)
                        and isinstance(stmt.value, ast.Constant)
                        and (
                            isinstance(stmt.value.value, bool)
                            or stmt.target.id in PYDANTIC_STRING_FLAGS
                        )
                    ):
                        nm = stmt.target.id
                        sites.setdefault(nm, []).append(
                            FlagSite(
                                nm,
                                "pydantic",
                                _norm_default(stmt.value.value),
                                py,
                                stmt.lineno,
                                _doc_claim(stmt.lineno),
                            )
                        )
                return
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            mode = "call" if self.depth > 0 else "import"
            kind = _env_kind(node)
            if kind in ("get", "getenv"):
                key = _str_of(node.args[0]) if node.args else None
                if key:
                    dflt = _str_of(node.args[1]) if len(node.args) > 1 else None
                    sites.setdefault(key, []).append(
                        FlagSite(
                            key,
                            mode,
                            _norm_default(dflt),
                            py,
                            node.lineno,
                            _doc_claim(node.lineno),
                        )
                    )
            elif kind == "setdefault":
                key = _str_of(node.args[0]) if node.args else None
                if key and len(node.args) > 1:
                    val = _str_of(node.args[1])
                    if val is not None:
                        writers[key] = val
            elif (
                isinstance(node.func, ast.Name)
                and node.func.id == "any"
                and node.args
                and isinstance(node.args[0], ast.GeneratorExp)
            ):
                # any()-пара алиасов (S203.4_x / S203_4_x): имена из Tuple,
                # дефолт — из environ.get(target, Const) внутри генератора.
                gen = node.args[0]
                for comp in gen.generators:
                    if not isinstance(comp.target, ast.Name):
                        continue
                    names: List[str] = []
                    if isinstance(comp.iter, ast.Tuple):
                        names = [
                            e.value
                            for e in comp.iter.elts
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str)
                        ]
                    if not names:
                        continue
                    tgt = comp.target.id
                    dflt: Optional[str] = None
                    _env_seen = False
                    for sub in ast.walk(gen):
                        if isinstance(sub, ast.Call) and _env_kind(sub) in (
                            "get",
                            "getenv",
                        ):
                            a0 = sub.args[0] if sub.args else None
                            if isinstance(a0, ast.Name) and a0.id == tgt:
                                dflt = (
                                    _str_of(sub.args[1])
                                    if len(sub.args) > 1
                                    else None
                                )
                                _env_seen = True
                                break
                    # bootstrap-урок 2 (act_consumer:127-131): any() над
                    # кортежем строк без environ.get внутри генератора —
                    # keyword-список (challenge-детект «соврал/врёшь/ложь»),
                    # не env-флаги: имена регистрируем только при живом
                    # env-обращении к переменной цели.
                    if not _env_seen:
                        continue
                    for nm in names:
                        sites.setdefault(nm, []).append(
                            FlagSite(
                                nm,
                                mode,
                                _norm_default(dflt),
                                py,
                                node.lineno,
                                _doc_claim(node.lineno),
                            )
                        )
            self.generic_visit(node)

    _Walker().visit(tree)

    # Модульные булевы константы — строго top-level (class-body DTO-поля
    # не флаги); ведущее «_» = внутреннее состояние (кэш-гварды), skip.
    for node in tree.body:
        nm: Optional[str] = None
        val: Optional[ast.expr] = None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            nm = node.targets[0].id
            val = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nm = node.target.id
            val = node.value
        if (
            nm
            and not nm.startswith("_")
            and isinstance(val, ast.Constant)
            and isinstance(val.value, bool)
        ):
            sites.setdefault(nm, []).append(
                FlagSite(nm, "import", _norm_default(val.value), py, node.lineno,
                         _doc_claim(node.lineno))
            )

    return sites, writers


def run_lint() -> Tuple[List[str], Dict[str, int]]:
    violations: List[str] = []
    sites: Dict[str, List[FlagSite]] = {}
    writers: Dict[str, str] = {}
    scanned = 0

    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for py in sorted(root.rglob("*.py")):
            scanned += 1
            try:
                s, w = scan_file(py)
            except (SyntaxError, OSError, UnicodeDecodeError) as exc:
                violations.append(f"PARSE {py.relative_to(ROOT)}: {exc}")
                continue
            for k, v in s.items():
                sites.setdefault(k, []).extend(v)
            writers.update(w)

    try:
        import yaml  # noqa: PLC0415 — отложенный импорт по прецеденту линтеров
    except ImportError:
        return (
            ["REGISTRY: PyYAML недоступен (прецедент lint_relationship_engine)"],
            {"scanned": scanned, "code_flags": len(sites), "registry": 0},
        )
    if not REGISTRY_PATH.exists():
        return (
            [f"REGISTRY: отсутствует {REGISTRY_PATH}"],
            {"scanned": scanned, "code_flags": len(sites), "registry": 0},
        )
    try:
        raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8-sig")) or {}
    except Exception as exc:  # parse-ошибка реестра = RED, не тихий skip
        return (
            [f"REGISTRY: parse error: {exc}"],
            {"scanned": scanned, "code_flags": len(sites), "registry": 0},
        )
    reg = raw.get("flags") or {}

    reg_by_name: Dict[str, dict] = {}
    for key, rec in reg.items():
        if not isinstance(rec, dict):
            violations.append(f"C7 {key}: запись не является dict")
            continue
        reg_by_name[key] = rec
        for al in rec.get("aliases") or []:
            reg_by_name[al] = rec

    # C7: таксономия вердиктов.
    for key, rec in reg.items():
        if isinstance(rec, dict) and rec.get("verdict") not in VALID_VERDICTS:
            violations.append(f"C7 {key}: недопустимый verdict={rec.get('verdict')!r}")

    # C2: stale-записи (флаг удалён из кода — реестр обязан следовать).
    for key, rec in reg.items():
        if not isinstance(rec, dict):
            continue
        names = [key] + list(rec.get("aliases") or [])
        if not any(n in sites for n in names):
            violations.append(f"C2 STALE {key}: записи нет в коде (флаг удалён?)")

    def _rel(s: FlagSite) -> str:
        return f"{s.file.relative_to(ROOT)}:{s.line}"

    # C1/C3/C5/C6: полнота + дрейфы по каждому код-флагу.
    for name, fl_sites in sorted(sites.items()):
        rec = reg_by_name.get(name)
        if rec is None:
            violations.append(
                f"C1 NO-RECORD {name} (первый сайт {_rel(fl_sites[0])}) — "
                f"флаг без вердикта реестра"
            )
            continue
        defaults = {s.default for s in fl_sites}
        if len(defaults) > 1:
            violations.append(
                f"C3 {name}: конфликт дефолтов между сайтами: {sorted(defaults)}"
            )
        ydef = _norm_default(rec.get("default"))
        for d in sorted(defaults):
            if d != ydef:
                violations.append(
                    f"C3 {name}: yaml default={ydef!r} != код {d!r} "
                    f"({_rel(fl_sites[0])})"
                )
        modes = {s.read_mode for s in fl_sites}
        expected = "mixed" if len(modes) > 1 else next(iter(modes))
        ymode = rec.get("read_mode")
        if ymode != expected:
            violations.append(
                f"C5 {name}: yaml read_mode={ymode!r} != код {expected!r}"
            )
        for s in fl_sites:
            if s.doc_claim == "ON" and not _truthy(s.default):
                violations.append(
                    f"C6 {name} DOC-DRIFT: def-site {_rel(s)} заявляет "
                    f"default ON, факт {s.default!r}"
                )
            elif s.doc_claim == "OFF" and _truthy(s.default):
                violations.append(
                    f"C6 {name} DOC-DRIFT: def-site {_rel(s)} заявляет "
                    f"default OFF, факт {s.default!r}"
                )

    # C4: setdefault-писатели обязаны отражаться в effective_default
    # (D8P-класс: модульный default != прод-эффективный).
    for name, wval in sorted(writers.items()):
        rec = reg_by_name.get(name)
        eff = _norm_default(rec.get("effective_default")) if rec else "none"
        if eff != wval:
            violations.append(
                f"C4 {name}: setdefault-писатель {wval!r} не отражён "
                f"(effective_default={eff!r})"
            )

    stats = {
        "scanned": scanned,
        "code_flags": len(sites),
        "registry": len(reg),
        "env_writers": len(writers),
    }
    return violations, stats


def main() -> int:
    violations, stats = run_lint()
    print(
        f"[CENSUS] scanned={stats['scanned']} code-flags={stats['code_flags']} "
        f"registry={stats['registry']} setdefault-writers={stats['env_writers']}"
    )
    for v in violations:
        print(f"  [FLAG-REGISTRY] {v}")
    if violations:
        print(f"FLAG-REGISTRY: {len(violations)} нарушений (COV-0 / COV-GC-04)")
        return 1
    print("FLAG-REGISTRY GREEN: реестр соответствует коду (COV-0 / COV-GC-04)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
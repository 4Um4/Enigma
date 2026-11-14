"""
path: scripts/lint_mem_triple.py
Назначение: INV-MEM-TRIPLE (#1) — AST-зеркало runtime writer guards (ADR-O-443,
             design v7 FINAL). Превентивный gate против обхода writer-guard
             для NPCState/BeliefState/EventMemory/PerceptualKernel.
Зависимости: stdlib only (ast, sys, pathlib).
Запуск: python scripts/lint_mem_triple.py

Authority extracted at lint-time from production AST:
- NPCState._ALLOWED_WRITERS (dict[str, set[str]])
- BeliefState._UPDATE_ALLOWED_WRITERS (set[str])
- PerceptualKernel._PK_ALLOWED_WRITERS (dict[str, set[str]])

Enforcement:
- A-1: NPCState field write; infer==NPCState; check module+field in _ALLOWED_WRITERS.
       infer fail -> WARN, not CRIT.
- A-2: BeliefState.update(); infer==BeliefState; check module in _UPDATE_ALLOWED_WRITERS.
       infer fail -> pass (dict.update ubiquitous).
- A-3: object.__setattr__(v, field, ...); v==NPCState -> check registry; v==BeliefState -> WARN (no authority);
       v==PerceptualKernel or EventMemory -> out of scope (no A-3 per Master narrowing); infer fail -> WARN.
- B8 skip (narrow): object.__setattr__(self, name_non_literal, ...) inside own
       __setattr__ of NPCState/PerceptualKernel — internal writer-guard impl, not bypass.
- V3-Q1 skip: object.__setattr__(self, literal_field, ...) inside own __post_init__
       of proven frozen=True dataclass; field declared in class body; self first positional.
- B construction WARN: NPCState/BeliefState/EventMemory(...) outside
       AUTHORIZED_CONSTRUCTION_MODULES ∪ DOMAIN_MODULES.

Residual coverage (documented, not solved in v7):
- No import-path tracking: schemas.NPCState (Pydantic) vs domain NPCState may merge in AST.
- WARN narrowing (v7.1): unknown types with NO evidence are PASS, not WARN.
  PASS means 'liner has no grounds to classify', NOT 'object is proven not NPCState'.
  WARN only when NPCState evidence existed but was invalidated by conflict
  (reassignment / conditional / unsupported binding).
- MEM-TRIPLE-DEBT-01: life_project_resolver bypasses NPCState writer guard
  (10 CRIT in baseline). Debt tracked separately, NOT allowlisted.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

EXTRACTION_TARGETS = {
    "NPCState": {
        "source": "models/npc_state.py",
        "class_name": "NPCState",
        "registry_var": "_ALLOWED_WRITERS",
        "kind": "dict_of_sets",
    },
    "BeliefState": {
        "source": "models/npc/beliefs.py",
        "class_name": "BeliefState",
        "registry_var": "_UPDATE_ALLOWED_WRITERS",
        "kind": "set_of_str",
    },
    "PerceptualKernel": {
        "source": "models/npc_state.py",
        "class_name": "PerceptualKernel",
        "registry_var": "_PK_ALLOWED_WRITERS",
        "kind": "dict_of_sets",
    },
}

B8_GUARDED_CLASSES = frozenset({"NPCState", "PerceptualKernel"})

AUTHORIZED_CONSTRUCTION_MODULES = {
    "NPCState": frozenset(
        {"app.models.npc_state", "app.services.npc.npc_loader", "app.services.player_avatar_service"}
    ),
    "BeliefState": frozenset({"app.services.npc.npc_loader"}),
    "EventMemory": frozenset(
        {
            "app.models.npc_state",
            "app.services.memory.memory_manager",
            "app.services.memory.promotion_engine",
            "app.services.chronicle.chronicle_seeder",
            "app.services.npc.npc_loader",
        }
    ),
}

DOMAIN_MODULES = {
    "NPCState": frozenset({"app.models.npc_state"}),
    "BeliefState": frozenset({"app.models.npc.beliefs"}),
    "EventMemory": frozenset({"app.models.npc_state"}),
    "PerceptualKernel": frozenset({"app.models.npc_state"}),
}

CONSTRUCTION_TRACKED = frozenset({"NPCState", "BeliefState", "EventMemory"})

ALLOWED_STATUSES = frozenset({"legacy_baseline", "approved"})
ALLOWED_ROLES = frozenset(
    {"npc_state_field_write", "beliefs_update", "npc_state_setattr", "beliefs_setattr", "construction_warn"}
)
ALLOWLIST: dict[tuple, dict] = {}
LEGACY_BASELINE_KEYS: frozenset = frozenset()

_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"
_EXTRACTION_ROOT = _DEFAULT_ROOT


class _ExtractionError(Exception):
    pass


def _extract_dict_of_sets(d):
    r = {}
    for k, v in zip(d.keys, d.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            raise _ExtractionError("non-string key")
        if not isinstance(v, ast.Set):
            raise _ExtractionError("non-set value")
        fs = set()
        for e in v.elts:
            if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                raise _ExtractionError("non-string set elem")
            fs.add(e.value)
        r[k.value] = fs
    return r


def _extract_set_of_str(s):
    r = set()
    for e in s.elts:
        if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
            raise _ExtractionError("non-string set elem")
        r.add(e.value)
    return r


def _extract_registry(class_name, var, kind, rel):
    src = _EXTRACTION_ROOT / rel
    if not src.exists():
        raise _ExtractionError(f"missing: {src}")
    try:
        tree = ast.parse(src.read_text(encoding="utf-8"))
    except SyntaxError as e:
        raise _ExtractionError(f"parse: {e}")
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == class_name:
            for stmt in n.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) and t.id == var:
                            return (
                                _extract_dict_of_sets(stmt.value)
                                if kind == "dict_of_sets"
                                else _extract_set_of_str(stmt.value)
                            )
    raise _ExtractionError(f"{class_name}.{var} not found in {rel}")


def _extract_all():
    auth = {}
    errs = []
    for cls, spec in EXTRACTION_TARGETS.items():
        try:
            auth[cls] = _extract_registry(cls, spec["registry_var"], spec["kind"], spec["source"])
        except _ExtractionError as e:
            auth[cls] = None
            errs.append(f"{cls}: {e}")
    return auth, errs


class _Binding:
    __slots__ = ("cnt", "types", "cond", "aug", "for_t", "with_a", "exc_a", "walrus")

    def __init__(self):
        self.cnt = 0
        self.types = set()
        self.cond = False
        self.aug = False
        self.for_t = False
        self.with_a = False
        self.exc_a = False
        self.walrus = False


class _Scope:
    __slots__ = ("kind", "parent", "bindings", "params")

    def __init__(self, kind, parent=None):
        self.kind = kind
        self.parent = parent
        self.bindings = {}
        self.params = {}


_KNOWN = frozenset({"NPCState", "BeliefState", "EventMemory", "PerceptualKernel"})


def _resolve_ann(node):
    if node is None:
        return None
    if isinstance(node, ast.Name) and node.id in _KNOWN:
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in _KNOWN:
        return node.value
    return None


def _infer(name, scope, class_def=None):
    if name == "self" and class_def is not None and class_def.name in _KNOWN:
        return class_def.name
    cur = scope
    while cur is not None:
        if name in cur.params:
            return cur.params[name]
        if name in cur.bindings:
            b = cur.bindings[name]
            if b.cnt > 1 or b.cond or b.aug or b.for_t or b.with_a or b.exc_a or b.walrus:
                return None
            if len(b.types) == 1:
                return next(iter(b.types))
            return None
        cur = cur.parent
    return None


def _had_evidence(name, scope, class_def=None):
    """Union of type evidence across all bindings for `name` in scope chain.
    Returns set of type names; empty if no evidence anywhere.
    Used to distinguish 'no evidence' (PASS) from 'evidence but conflicted' (WARN).
    """
    ev = set()
    if name == "self" and class_def is not None and class_def.name in _KNOWN:
        return {class_def.name}
    cur = scope
    while cur is not None:
        if name in cur.params:
            ev.add(cur.params[name])
            return ev
        if name in cur.bindings:
            ev |= cur.bindings[name].types
            return ev
        cur = cur.parent
    return ev


def _collect(stmts, scope, cond=False):
    for stmt in stmts:
        _collect_stmt(stmt, scope, cond)


def _collect_stmt(stmt, scope, cond):
    if isinstance(stmt, ast.Assign):
        vtype = None
        if isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id in _KNOWN:
            vtype = stmt.value.func.id
        for t in stmt.targets:
            if isinstance(t, ast.Name):
                b = scope.bindings.setdefault(t.id, _Binding())
                b.cnt += 1
                if vtype:
                    b.types.add(vtype)
                if cond:
                    b.cond = True
        for child in ast.walk(stmt):
            if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                b = scope.bindings.setdefault(child.target.id, _Binding())
                b.walrus = True
    elif isinstance(stmt, ast.AnnAssign):
        if isinstance(stmt.target, ast.Name):
            b = scope.bindings.setdefault(stmt.target.id, _Binding())
            b.cnt += 1
            a = _resolve_ann(stmt.annotation)
            if a:
                b.types.add(a)
            if cond:
                b.cond = True
    elif isinstance(stmt, ast.AugAssign):
        if isinstance(stmt.target, ast.Name):
            b = scope.bindings.setdefault(stmt.target.id, _Binding())
            b.cnt += 1
            b.aug = True
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        for t in ast.walk(stmt.target):
            if isinstance(t, ast.Name):
                b = scope.bindings.setdefault(t.id, _Binding())
                b.cnt += 1
                b.for_t = True
        _collect(stmt.body, scope, cond=True)
        _collect(stmt.orelse, scope, cond=True)
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            if item.optional_vars:
                for t in ast.walk(item.optional_vars):
                    if isinstance(t, ast.Name):
                        b = scope.bindings.setdefault(t.id, _Binding())
                        b.cnt += 1
                        b.with_a = True
        _collect(stmt.body, scope, cond=True)
    elif isinstance(stmt, ast.ExceptHandler):
        if stmt.name:
            b = scope.bindings.setdefault(stmt.name, _Binding())
            b.cnt += 1
            b.exc_a = True
        _collect(stmt.body, scope, cond=True)
    elif isinstance(stmt, ast.If):
        _collect(stmt.body, scope, cond=True)
        _collect(stmt.orelse, scope, cond=True)
    elif isinstance(stmt, ast.Try):
        _collect(stmt.body, scope, cond=True)
        _collect(stmt.orelse, scope, cond=True)
        _collect(stmt.finalbody, scope, cond)
        for h in stmt.handlers:
            _collect_stmt(h, scope, cond=True)
    elif isinstance(stmt, ast.While):
        _collect(stmt.body, scope, cond=True)
        _collect(stmt.orelse, scope, cond=True)
    elif isinstance(stmt, ast.Match):
        for c in stmt.cases:
            _collect(c.body, scope, cond=True)
    elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        pass
    else:
        for child in ast.walk(stmt):
            if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                b = scope.bindings.setdefault(child.target.id, _Binding())
                b.walrus = True


def _prepass_func(fn, parent):
    fs = _Scope("function", parent)
    for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs):
        a = _resolve_ann(arg.annotation)
        if a:
            fs.params[arg.arg] = a
    _collect(fn.body, fs)
    return fs


def _prepass_class(cls, parent):
    methods = []
    nested = []

    def walk(stmts):
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(stmt)
            elif isinstance(stmt, ast.ClassDef):
                nested.append(stmt)
            elif isinstance(stmt, ast.If):
                walk(stmt.body)
                walk(stmt.orelse)
            elif isinstance(stmt, ast.Try):
                walk(stmt.body)
                walk(stmt.orelse)
                walk(stmt.finalbody)
                for handler in stmt.handlers:
                    walk(handler.body)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                walk(stmt.body)
                walk(stmt.orelse)
            elif isinstance(stmt, ast.While):
                walk(stmt.body)
                walk(stmt.orelse)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                walk(stmt.body)
            elif isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    walk(case.body)

    walk(cls.body)
    scopes = {}
    for m in methods:
        scopes[id(m)] = _prepass_func(m, parent)
    for nc in nested:
        scopes.update(_prepass_class(nc, parent))
    return scopes


def _first_pos(fn):
    if fn.args.posonlyargs:
        return fn.args.posonlyargs[0].arg
    if fn.args.args:
        return fn.args.args[0].arg
    return None


def _module_shadow(tree, name):
    def walk(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.ImportFrom):
                for a in stmt.names:
                    if stmt.module == "dataclasses" and a.name == "dataclass" and not a.asname:
                        continue
                    if a.asname == name or a.name == name:
                        return True
            elif isinstance(stmt, ast.Import):
                for a in stmt.names:
                    if a.name == name:
                        return True
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if stmt.name == name:
                    return True
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        return True
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                    return True
            elif isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                    return True
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                for t in ast.walk(stmt.target):
                    if isinstance(t, ast.Name) and t.id == name:
                        return True
                if walk(stmt.body):
                    return True
                if walk(stmt.orelse):
                    return True
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for it in stmt.items:
                    if it.optional_vars:
                        for t in ast.walk(it.optional_vars):
                            if isinstance(t, ast.Name) and t.id == name:
                                return True
                if walk(stmt.body):
                    return True
            elif isinstance(stmt, ast.ExceptHandler):
                if stmt.name == name:
                    return True
                if walk(stmt.body):
                    return True
            elif isinstance(stmt, ast.If):
                if walk(stmt.body):
                    return True
                if walk(stmt.orelse):
                    return True
            elif isinstance(stmt, ast.Try):
                if walk(stmt.body):
                    return True
                if walk(stmt.orelse):
                    return True
                if walk(stmt.finalbody):
                    return True
                for h in stmt.handlers:
                    if walk([h]):
                        return True
            elif isinstance(stmt, ast.Match):
                for c in stmt.cases:
                    if walk(c.body):
                        return True
        return False

    return walk(tree.body)


def _frozen(cls, shadow):
    if shadow:
        return None
    for d in cls.decorator_list:
        if isinstance(d, ast.Name) and d.id == "dataclass":
            return False
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass":
            for kw in d.keywords:
                if kw.arg == "frozen":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool):
                        return kw.value.value
                    return None
            return False
    return None


def _b8_skip(node, fn, cls):
    if fn is None or cls is None:
        return False
    if fn.name != "__setattr__":
        return False
    if cls.name not in B8_GUARDED_CLASSES:
        return False
    if len(node.args) < 3:
        return False
    a0, a1 = node.args[0], node.args[1]
    if not isinstance(a0, ast.Name):
        return False
    if _first_pos(fn) != a0.id:
        return False
    if isinstance(a1, ast.Constant):
        return False
    return True


def _v3q1_skip(node, fn, cls, shadow):
    if fn is None or cls is None:
        return False
    if fn.name != "__post_init__":
        return False
    if _frozen(cls, shadow) is not True:
        return False
    if len(node.args) < 3:
        return False
    a0, a1 = node.args[0], node.args[1]
    if not isinstance(a0, ast.Name):
        return False
    if _first_pos(fn) != a0.id:
        return False
    if not (isinstance(a1, ast.Constant) and isinstance(a1.value, str)):
        return False
    field = a1.value
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == field:
                return True
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id == field:
                    return True
    return False


def _rel_to_module(rel):
    if not rel.endswith(".py"):
        return ""
    return "app." + rel[:-3].replace("/", ".")


def _match_module(module, patterns):
    for p in patterns:
        if module == p or module.startswith(p + "."):
            return p
    return None


def _scan_file(path, root, allow, auth, violations):
    rel = path.relative_to(root).as_posix()
    module = _rel_to_module(rel)
    discovered = set()
    try:
        src = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        violations.append(f"CRIT|{rel}|UNREADABLE: {e!r}")
        return discovered
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        violations.append(f"CRIT|{rel}|PARSE_ERROR: {e!r}")
        return discovered

    shadow = _module_shadow(tree, "dataclass")
    mod_scope = _Scope("module")
    _collect(tree.body, mod_scope)

    all_scopes = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_scopes[id(stmt)] = _prepass_func(stmt, mod_scope)
        elif isinstance(stmt, ast.ClassDef):
            all_scopes.update(_prepass_class(stmt, mod_scope))

    ctx = {}

    def walk(node, fn, cls):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Call)):
            ctx[id(node)] = (fn, cls)
        for child in ast.iter_child_nodes(node):
            nf, nc = fn, cls
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nf = node
            elif isinstance(node, ast.ClassDef):
                nc = node
            walk(child, nf, nc)

    walk(tree, None, None)

    def gs(fn):
        return all_scopes.get(id(fn), mod_scope) if fn else mod_scope

    for node in ast.walk(tree):
        # A-1
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            fn, cls = ctx.get(id(node), (None, None))
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                    var, field = t.value.id, t.attr
                    inferred = _infer(var, gs(fn), cls)
                    if inferred == "NPCState":
                        key = (rel, "npc_state_field_write", field)
                        discovered.add(key)
                        if key in allow:
                            continue
                        reg = auth.get("NPCState") or {}
                        matched = None
                        for mp, fs in reg.items():
                            if _match_module(module, [mp]):
                                matched = fs
                                break
                        if matched and ("*" in matched or field in matched):
                            continue
                        violations.append(f"CRIT|{rel}:{node.lineno}|field_write_unauthorized: {var}.{field}")
                    elif "NPCState" in _had_evidence(var, gs(fn), cls):
                        violations.append(f"WARN|{rel}:{node.lineno}|A-1 NPCState-evidence-conflicted: {var}.{field}")
                    # else: no NPCState evidence -> liniter cannot classify -> PASS (residual)
        # A-2
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update":
            if isinstance(node.func.value, ast.Name):
                var = node.func.value.id
                fn, cls = ctx.get(id(node), (None, None))
                if _infer(var, gs(fn), cls) == "BeliefState":
                    key = (rel, "beliefs_update", var)
                    discovered.add(key)
                    if key in allow:
                        continue
                    reg = auth.get("BeliefState") or set()
                    if module in reg:
                        continue
                    violations.append(f"CRIT|{rel}:{node.lineno}|beliefs_update_unauthorized: {var}.update")
        # A-3
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "__setattr__":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "object":
                fn, cls = ctx.get(id(node), (None, None))
                if _b8_skip(node, fn, cls):
                    continue
                if _v3q1_skip(node, fn, cls, shadow):
                    continue
                if len(node.args) < 3:
                    continue
                vn, fld = node.args[0], node.args[1]
                if not isinstance(vn, ast.Name):
                    continue
                var = vn.id
                field = fld.value if (isinstance(fld, ast.Constant) and isinstance(fld.value, str)) else None
                inferred = _infer(var, gs(fn), cls)
                if inferred == "NPCState":
                    key = (rel, "npc_state_setattr", var + (":" + field if field else ""))
                    discovered.add(key)
                    if key in allow:
                        continue
                    reg = auth.get("NPCState") or {}
                    matched = None
                    for mp, fs in reg.items():
                        if _match_module(module, [mp]):
                            matched = fs
                            break
                    if matched and "*" in matched:
                        continue
                    if field is None:
                        violations.append(f"WARN|{rel}:{node.lineno}|A-3 setattr non-literal field: {var}")
                        continue
                    if matched and field in matched:
                        continue
                    violations.append(
                        f"CRIT|{rel}:{node.lineno}|setattr_unauthorized: object.__setattr__({var}, {field!r}, ...)"
                    )
                elif inferred == "BeliefState":
                    key = (rel, "beliefs_setattr", var + (":" + field if field else ""))
                    discovered.add(key)
                    if key in allow:
                        continue
                    violations.append(f"WARN|{rel}:{node.lineno}|A-3 beliefs_setattr_no_authority: {var}")
                elif "NPCState" in _had_evidence(var, gs(fn), cls):
                    violations.append(
                        f"WARN|{rel}:{node.lineno}|A-3 NPCState-evidence-conflicted: object.__setattr__({var}, ...)"
                    )
                # else: no NPCState evidence -> PASS (residual)
        # Construction
        if isinstance(node, ast.Call):
            fn_name = None
            if isinstance(node.func, ast.Name):
                fn_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fn_name = node.func.attr
            if fn_name in CONSTRUCTION_TRACKED:
                allowed = AUTHORIZED_CONSTRUCTION_MODULES.get(fn_name, frozenset()) | DOMAIN_MODULES.get(
                    fn_name, frozenset()
                )
                if not _match_module(module, list(allowed)):
                    key = (rel, "construction_warn", fn_name)
                    discovered.add(key)
                    if key in allow:
                        continue
                    violations.append(f"WARN|{rel}:{node.lineno}|construction_outside_authorized: {fn_name}")

    return discovered


def _validate(key, meta, violations):
    rel, kind, ident = key
    status = meta.get("status", "")
    role = meta.get("role", "")
    rationale = (meta.get("rationale") or "").strip()
    adr = (meta.get("adr") or "").strip()
    hist = (meta.get("historical_basis") or "").strip()
    if status not in ALLOWED_STATUSES:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — status={status!r}")
        return
    if role not in ALLOWED_ROLES:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — role={role!r}")
        return
    if not rationale:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — no rationale")
        return
    is_leg = key in LEGACY_BASELINE_KEYS
    if status == "legacy_baseline":
        if not is_leg:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — legacy for non-legacy")
            return
        if not hist:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — no hist")
            return
        if adr:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — adr+hist")
            return
    if status == "approved":
        if is_leg:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — approved on legacy")
            return
        if not adr:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — no adr")
            return
        if hist:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — adr+hist")
            return


def _check_allow(allow, violations, discovered, *, production):
    if production:
        a, e = set(allow.keys()), set(LEGACY_BASELINE_KEYS)
        if a != e:
            violations.append(f"CRIT|<root>|KEYS_MISMATCH: only_allowlist={sorted(a - e)}, only_legacy={sorted(e - a)}")
    for k, m in allow.items():
        _validate(k, m, violations)
    for k in allow:
        if k not in discovered:
            rel, kind, ident = k
            violations.append(f"CRIT|{rel}|ORPHAN: {kind}:{ident}")


def run_lint(root=None, allowlist=None):
    _root = _DEFAULT_ROOT if root is None else Path(root)
    if allowlist is None and root is None:
        production = True
        _allow = dict(ALLOWLIST)
    elif allowlist is None:
        production = False
        _allow = {}
    else:
        production = False
        _allow = dict(allowlist)
    if not _root.exists():
        return [f"CRIT|<root>|ROOT_MISSING: {_root}"]
    violations = []
    auth, errs = _extract_all()
    for e in errs:
        violations.append(f"CRIT|<root>|AUTHORITY_EXTRACTION_FAILED: {e}")
    discovered = set()
    for p in sorted(_root.rglob("*.py")):
        discovered |= _scan_file(p, _root, _allow, auth, violations)
    _check_allow(_allow, violations, discovered, production=production)
    return violations


def main():
    v = run_lint()
    crit = [x for x in v if x.startswith("CRIT|")]
    warn = [x for x in v if x.startswith("WARN|")]
    if crit:
        print(f"[MEM-TRIPLE] CRIT={len(crit)}, WARN={len(warn)}")
        for x in crit[:10]:
            print(f"  - {x}")
        return 1
    if warn:
        print(f"[MEM-TRIPLE] WARN={len(warn)} (PASS with warnings)")
        for x in warn[:10]:
            print(f"  - {x}")
        return 0
    print("[MEM-TRIPLE] OK: 0 CRIT, 0 WARN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

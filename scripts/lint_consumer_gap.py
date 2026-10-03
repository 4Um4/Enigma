"""
path: /project/scripts/lint_consumer_gap.py
Назначение: Слой 1 INV-CONSUMER-GAP (ADR-O-414) — статический orphan-скан класса
    отказа «state exists ≠ state has consequence» (выборки: RE-D2 S248 — отношения;
    GC-09B S249 — тело; NL-D9 §7.7 — energy/hydration → decision/вербализация).
    Census полей схем (AST) → скан readers/writers (AST) → два вердикта:
    NO_READER (orphan: состояние никто не читает) и NO_WRITER (нет runtime-писателя).
    Статика ≤ surface: доказывает существование проводки, НЕ эффект (reader-для-лога,
    экзамен E4) — proof = Слой 3, пертурбация. Директива Мастера: Слой 1 намеренно
    тупой и подозрительный — скан по имени без type-inference; коллизии имён дают
    недодетект (безопасно), dataclasses.replace/непрямые записи дают ложный
    NO_WRITER (целевая подозрительность; при подавлении сверяться вручную).
    Схемы (models/) не сканируются как readers/writers: сериализационная граница
    (from_legacy/adapter) — не бизнес-проводка; иначе from_legacy легализовал бы всё.
Зависимости: ast, pathlib, re; scripts/consumer_gap_debts.py (см. его шапку).
Основные сущности: collect_schema_fields, scan_typed_usages, scan_container_usages, run_lint
Запуск (из корня проекта): python scripts/lint_consumer_gap.py
"""
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "backend" / "app"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from consumer_gap_debts import DEBT_FIELDS  # noqa: E402

# Layer 2 (ADR-O-414): causality_manifest — единственный semantic SSOT
# (вердикт Q-A). Импорт data-only модуля из app.models: script→model
# граница легальна (models не знает о скрипте, цикла нет).
sys.path.insert(0, str(ROOT / "backend"))  # корень пакета: import app.models...
try:
    from app.models.causality_manifest import (  # noqa: E402
        FIELD_CAUSALITY, KNOWN_ORGANS, KNOWN_TERMINALS,
    )
    _MANIFEST_OK = True
    _MANIFEST_ORGANS = KNOWN_ORGANS
    _MANIFEST_TERMINALS = KNOWN_TERMINALS
except Exception as _me:  # манифест отсутствует/сломан = вердикт, не тихий skip
    _MANIFEST_OK = False
    _MANIFEST_ERR = str(_me)
    FIELD_CAUSALITY = {}  # unbound-гвард для stats/M-блока (Pylance PossiblyUnbound)

MODEL_FILES = [
    APP / "models" / "npc_state.py",
    APP / "models" / "state_delta.py",
    APP / "models" / "delta_payloads.py",
]
# Typed readers/writers — ТЗ §5 Этап 1: services + api (runtime-контур).
# domain/ добавлен верификацией Этапа 1 (functional_loss: единственный ридер
# — vital_state.py: чистые функции над схемами = runtime-ридеры; ТЗ §5
# перечислял services/api — расширение, не противоречащее духу). models/
# НЕ сканируем: сериализационная граница легализовала бы все поля.
SCAN_DIRS = [APP / "services", APP / "api", APP / "domain"]
# Контейнерные дикт-домены — литеральные ключи по всему app (включая модели:
# их чтения в адаптерах легализуют ключ, что консервативно и безопасно).
CONTAINER_SCAN_ROOT = APP
CONTAINER_DOMAINS = {"body_state", "needs"}

_MARKER_RE = re.compile(r"CONSUMER-GAP-DEBT:\s*([A-Za-z0-9][A-Za-z0-9/_-]*)")
# authority обязан выглядеть как ссылка: NL-D9, AUD-D4, GC-11, S248, O-383...
# authority: ADR-*/NL-D*/AUD-D*/GC-* (через дефис) или голый S-номер (S248)
_AUTHORITY_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)+|S\d{2,4}")


def _snake(name: str) -> str:
    # Акронимы не дробим: NPCState → npc_state, InjuryDTO → injury_dto
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _domain_for(file: Path, cls: str) -> str:
    # Канон ключей ТЗ §4: payload-классы — "state_delta.<payload>.<field>";
    # остальные — snake(класс): npc_state.stress, perceptual_kernel.threat_gradient.
    if file.name == "delta_payloads.py":
        return f"state_delta.{_snake(cls)}"
    if cls == "StateDeltas":
        return "state_delta"
    return _snake(cls)


def _is_dataclass(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
    return False


def collect_schema_fields() -> Tuple[Dict[str, int], Dict[str, Set[str]]]:
    """Census typed-полей: ('domain.field' → строка декларации, класс → поля).
    ctor_fields — для keyword-детектора frozen-конструкторов (EventMemory(...))."""
    census: Dict[str, int] = {}
    ctor_fields: Dict[str, Set[str]] = {}
    for f in MODEL_FILES:
        if not f.exists():
            continue
        # utf-8-sig: часть файлов проекта несёт BOM (PEP 263 легален для
        # импорта, но ломает ast.parse через чистый utf-8)
        tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and _is_dataclass(node)):
                continue
            domain = _domain_for(f, node.name)
            # Только прямые AnnAssign тела класса: локальные аннотации внутри
            # методов (mods/surviving) полями не являются.
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    census[f"{domain}.{stmt.target.id}"] = stmt.lineno
                    ctor_fields.setdefault(node.name, set()).add(stmt.target.id)
    return census, ctor_fields


def _alias_bindings(tree: ast.AST) -> Dict[str, str]:
    """One-hop алиасы контейнеров: _body = npc.get('body_state') /
    _body = npc['body_state'] → {alias: domain}. Верифицированный класс
    слепоты (sleep_lifecycle_service: _body['sleep_onset_tick'] = tick).
    Локально по файлу, одна ступень — глубже не идём (тупость слоя)."""
    out: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            acc = _container_access(node.value)
            if acc and not acc[1]:
                out[node.targets[0].id] = acc[0]
            # .get-форма связки: _body = npc.get("body_state") — Call невидим
            # _container_access (верифицированный класс: sleep_lifecycle_service)
            elif acc is None and isinstance(node.value, ast.Call) \
                    and isinstance(node.value.func, ast.Attribute) \
                    and node.value.func.attr == "get" and node.value.args \
                    and isinstance(node.value.args[0], ast.Constant) \
                    and isinstance(node.value.args[0].value, str) \
                    and node.value.args[0].value in CONTAINER_DOMAINS:
                out[node.targets[0].id] = node.value.args[0].value
    return out


def _container_access(node: ast.expr) -> Optional[Tuple[str, List[str]]]:
    """Тупой резолвер пути к контейнерному домену. Три паттерна:
    x.body_state[...] / x['npc']['body_state'][...] / body_state[...] (Name-параметр
    по конвенции). Возвращает (домен, промежуточные литеральные ключи)."""
    if isinstance(node, ast.Attribute) and node.attr in CONTAINER_DOMAINS:
        return node.attr, []
    keys: List[str] = []
    base: ast.expr = node
    while isinstance(base, ast.Subscript) and isinstance(base.slice, ast.Constant) \
            and isinstance(base.slice.value, str):
        keys.append(base.slice.value)
        base = base.value
    keys.reverse()
    if isinstance(base, ast.Attribute) and base.attr in CONTAINER_DOMAINS:
        return base.attr, keys
    if isinstance(base, ast.Name) and base.id in CONTAINER_DOMAINS:
        return base.id, keys
    if keys and keys[0] in CONTAINER_DOMAINS:
        return keys[0], keys[1:]
    return None


def scan_model_writes(
    ctor_fields: Dict[str, Set[str]],
    field_names: Set[str],
    parse_errors: List[str],
) -> Dict[str, List[str]]:
    """Узкий проход по models: ТОЛЬКО конструкторные вызовы схем
    (Name(...kw=...)). from_legacy-билдеры — фактический write-путь
    frozen-классов; без прохода NO_WRITER ложен (~20 полей).
    Сериализационная граница сохранена: models не читатели и не
    атрибут-писатели. Сентинел-литералы (BODY_STATE_DISABLED) — writers
    КОНТЕЙНЕРНЫХ ключей, живут в scan_container_usages (namespace-урок:
    "disabled" — ключ body_state, не typed-поле; первая попытка в
    typed-namespace была no-op — прогон №7 байт-идентичен №6)."""
    result: Dict[str, List[str]] = {n: [] for n in field_names}
    for f in MODEL_FILES:
        if not f.exists():
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
        except Exception as _pe:
            parse_errors.append(f"{f.as_posix()} ({_pe.__class__.__name__})")
            continue
        rel = f.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ctor_fields:
                for kw in node.keywords:
                    if kw.arg and kw.arg in field_names:
                        result[kw.arg].append(f"{rel}:{node.lineno}")
    return result


def scan_container_usages(parse_errors: List[str]) -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    """Контейнерные ключи: 'domain.key' → readers/writers по литералам app.
    Writer = Subscript-Store; reader = Subscript-Load и .get('k')."""
    result: Dict[str, Dict[str, Dict[str, List[str]]]] = {d: {} for d in CONTAINER_DOMAINS}
    # Сентинел-литералы models собираются, но НЕ регистрируются сразу:
    # мердж в конце, только для уже известных census-ключей.
    sentinel_hits: List[Tuple[str, int, str]] = []

    def _reg(domain: str, key: str, kind: str, loc: str) -> None:
        result[domain].setdefault(f"{domain}.{key}", {"readers": [], "writers": []})[kind].append(loc)

    for f in CONTAINER_SCAN_ROOT.rglob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
        except Exception as _pe:
            # L4-честность: молчаливый skip = слепая зона скана (урок known_by:
            # единственный ридер жил в непарсящемся файле). Файл не маскируется
            # — попадает в вердикт PARSE. ROOT покрывает весь app, включая
            # зону typed-скана — покрытие полное без второй точки.
            parse_errors.append(f"{f.as_posix()} ({_pe.__class__.__name__})")
            continue
        rel = f.as_posix()
        aliases = _alias_bindings(tree)
        for node in ast.walk(tree):
            # индексный доступ: ключ = slice, но только на верхнем уровне домена
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                    and isinstance(node.slice.value, str):
                acc = _container_access(node.value)
                if acc:
                    domain, rest = acc
                    if not rest:
                        kind = "writers" if isinstance(node.ctx, ast.Store) else "readers"
                        _reg(domain, node.slice.value, kind, f"{rel}:{node.lineno}")
            # .get('k') — чтение (только верхний уровень + one-hop алиасы)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "get" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                acc = _container_access(node.func.value)
                if acc and not acc[1]:
                    _reg(acc[0], node.args[0].value, "readers", f"{rel}:{node.lineno}")
                elif not acc and isinstance(node.func.value, ast.Name) \
                        and node.func.value.id in aliases:
                    _reg(aliases[node.func.value.id], node.args[0].value,
                         "readers", f"{rel}:{node.lineno}")
            # индексный доступ через алиас: _body['sleep_onset_tick'] = tick
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                    and node.value.id in aliases and isinstance(node.slice, ast.Constant) \
                    and isinstance(node.slice.value, str):
                kind = "writers" if isinstance(node.ctx, ast.Store) else "readers"
                _reg(aliases[node.value.id], node.slice.value, kind, f"{rel}:{node.lineno}")
            # .update({'k': ...}) — writer-литералы (та же тупость, что Dict-литерал)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "update" and node.args \
                    and isinstance(node.args[0], ast.Dict):
                acc = _container_access(node.func.value)
                upd_dom: Optional[str] = None
                if acc and not acc[1]:
                    upd_dom = acc[0]
                elif not acc and isinstance(node.func.value, ast.Name) \
                        and node.func.value.id in aliases:
                    upd_dom = aliases[node.func.value.id]
                if upd_dom:
                    for k in node.args[0].keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            _reg(upd_dom, k.value, "writers", f"{rel}:{node.lineno}")
            # Dict-литерал целиком: x.body_state = {'current_hp': ...} → ключи = writers
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for t in node.targets:
                    dom: Optional[str] = None
                    if isinstance(t, ast.Attribute) and t.attr in CONTAINER_DOMAINS:
                        dom = t.attr
                    elif isinstance(t, ast.Subscript):
                        acc = _container_access(t.value)
                        if acc and not acc[1] and isinstance(t.slice, ast.Constant) \
                                and isinstance(t.slice.value, str) and t.slice.value in CONTAINER_DOMAINS:
                            dom = t.slice.value
                    if dom:
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                _reg(dom, k.value, "writers", f"{rel}:{node.lineno}")
            # Сентинел-константы models: NAME = {...} / NAME: T = {...}
            # (BODY_STATE_DISABLED npc_state:63): домен по имени константы
            # не выводим — собираем, мердж в хвосте функции (тупо и честно).
            # Локальные переменные — сужение типов для Pylance/mypy: доступ
            # node.value.keys после ветвления статически недоказуем.
            _sentinel_dict: Optional[ast.Dict] = None
            _sentinel_targets: List[ast.expr] = []
            _sentinel_line = 0
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                _sentinel_dict = node.value
                _sentinel_targets = list(node.targets)
                _sentinel_line = node.lineno
            elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Dict):
                _sentinel_dict = node.value
                _sentinel_targets = [node.target]
                _sentinel_line = node.lineno
            if _sentinel_dict is not None:
                for t in _sentinel_targets:
                    if isinstance(t, ast.Name) and "/models/" in rel:
                        for k in _sentinel_dict.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                sentinel_hits.append((rel, _sentinel_line, k.value))
    # Фаза 2: сентинел-ключи → writers ТОЛЬКО для ключей, уже живущих в
    # census (регистрация неизвестных создала бы фантомные NO_READER:
    # например ключи DRIVE_INTENT_MODIFIERS не в body_state-census)
    for _srel, _sln, _skey in sentinel_hits:
        for _d in CONTAINER_DOMAINS:
            _ck = f"{_d}.{_skey}"
            if _ck in result[_d]:
                result[_d][_ck]["writers"].append(f"{_srel}:{_sln}")
    return result


def scan_typed_usages(
    field_names: Set[str],
    ctor_fields: Dict[str, Set[str]],
    parse_errors: List[str],
) -> Dict[str, Dict[str, List[str]]]:
    result: Dict[str, Dict[str, List[str]]] = {n: {"readers": [], "writers": []} for n in field_names}
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"), filename=str(f))
            except Exception as _pe:
                parse_errors.append(f"{f.as_posix()} ({_pe.__class__.__name__})")
                continue
            rel = f.as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in field_names:
                    kind = "writers" if isinstance(node.ctx, ast.Store) else "readers"
                    result[node.attr][kind].append(f"{rel}:{node.lineno}")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in ("getattr", "setattr") and len(node.args) >= 2:
                    arg = node.args[1]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and arg.value in field_names:
                        kind = "writers" if node.func.id == "setattr" else "readers"
                        result[arg.value][kind].append(f"{rel}:{node.lineno}")
                # Keyword-конструирование frozen-классов (верифицировано:
                # EventMemory в memory_manager:337) — writer поля
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in ctor_fields \
                        and any(kw.arg in ctor_fields[node.func.id] for kw in node.keywords):
                    for kw in node.keywords:
                        if kw.arg and kw.arg in field_names:
                            result[kw.arg]["writers"].append(f"{rel}:{node.lineno}")
                # object.__setattr__(obj, "field", v) — форма persistence-писателей
                # после ADR-WRITE-GUARD (npc_loader и др.)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == "__setattr__" and len(node.args) >= 2 \
                        and isinstance(node.args[1], ast.Constant) \
                        and isinstance(node.args[1].value, str) \
                        and node.args[1].value in field_names:
                    result[node.args[1].value]["writers"].append(f"{rel}:{node.lineno}")
    return result


def run_lint() -> Tuple[List[str], Dict[str, int]]:
    """Возвращает (violations, stats). Формат строки: lint_kernel_rng."""
    census, ctor_fields = collect_schema_fields()
    typed_names = {k.rsplit(".", 1)[1] for k in census}
    parse_errors: List[str] = []
    typed = scan_typed_usages(typed_names, ctor_fields, parse_errors)
    ctor_w = scan_model_writes(ctor_fields, typed_names, parse_errors)
    for _name, _locs in ctor_w.items():
        typed[_name]["writers"].extend(_locs)
    cont = scan_container_usages(parse_errors)

    raw: List[Tuple[str, str, int]] = []  # (verdict, key, decl_line)
    for key, line in sorted(census.items()):
        name = key.rsplit(".", 1)[1]
        if not typed[name]["readers"]:
            raw.append(("NO_READER", key, line))
        if not typed[name]["writers"]:
            raw.append(("NO_WRITER", key, line))
    for domain in CONTAINER_DOMAINS:
        for key, bucket in sorted(cont[domain].items()):
            if not bucket["readers"]:
                raw.append(("NO_READER", key, 0))
            if not bucket["writers"]:
                raw.append(("NO_WRITER", key, 0))

    # §7 D2: реестр сам под надзором — authority без ссылки и stale-ключ = CRITICAL
    violations: List[str] = []
    for key, auth in DEBT_FIELDS.items():
        if not isinstance(auth, str) or not _AUTHORITY_RE.search(auth):
            violations.append(
                f"[CONSUMER-GAP-DEBT-FORMAT] scripts/consumer_gap_debts.py -> '{key}': "
                f"authority '{auth}' без ссылки на вердикт/долг (молчаливые подавления запрещены)"
            )
        elif key not in census and not (
            key.split(".", 1)[0] in cont
            and key in cont[key.split(".", 1)[0]]
        ):
            violations.append(
                f"[CONSUMER-GAP-STALE] scripts/consumer_gap_debts.py -> '{key}': "
                f"ключ отсутствует в census (поле удалено/переименовано) — запись реестра мертва"
            )

    # Файл, который AST не взял, — слепая зона (PARSE-класс), не тихий пропуск
    for pe in parse_errors:
        violations.append(f"[CONSUMER-GAP-PARSE] {pe} -> файл не разобран, скан к нему слеп")
    for verdict, key, line in sorted(raw):
        if key in DEBT_FIELDS and _AUTHORITY_RE.search(DEBT_FIELDS[key]):
            continue  # санкционированный долг — подавлен записью реестра
        violations.append(
            f"[CONSUMER-GAP-{verdict}] {key} -> orphan "
            f"(decl_line={line or 'container-literal'})"
        )

    # ── Layer 2: causality_manifest (ADR-O-414, Stage 2a) ──────────────────
    if not _MANIFEST_OK:
        violations.append(
            f"[MANIFEST-BROKEN] backend/app/models/causality_manifest.py -> импорт упал: {_MANIFEST_ERR}"
        )
    else:
        census_keys = set(census) | {k for d in cont.values() for k in d}
        # M-UNDECLARED / M-STALE: двусторонний гейт census<->manifest
        for k in sorted(census_keys - set(FIELD_CAUSALITY)):
            violations.append(f"[M-UNDECLARED] {k} -> нет декларации жизненного цикла в манифесте")
        for k in sorted(set(FIELD_CAUSALITY) - census_keys):
            violations.append(f"[M-STALE] {k} -> манифест-запись без поля в census (удалено/переименовано)")
        for k, fc in FIELD_CAUSALITY.items():
            # M-ORGAN / M-TERM: значения ∈ закрытым реестрам
            if fc.organ is not None and fc.organ not in _MANIFEST_ORGANS:
                violations.append(f"[M-ORGAN] {k} -> organ '{fc.organ}' вне KNOWN_ORGANS")
            if fc.terminal is not None and fc.terminal not in _MANIFEST_TERMINALS:
                violations.append(f"[M-TERM] {k} -> terminal '{fc.terminal}' вне KNOWN_TERMINALS")
            if fc.mode == "CAUSAL":
                # M-PROOF: proof-файл обязан существовать на диске
                if not fc.proof or not (ROOT / fc.proof).exists():
                    violations.append(
                        f"[M-PROOF] {k} -> CAUSAL без живого proof-файла ({fc.proof!r}; reader ≠ consequence)"
                    )
                # M-XREAD/M-XWRITE: CAUSAL обязан иметь проводку по Слою 1.
                # Bucket выбирается по природе ключа (урок №10bis: container-
                # ключ body_state.fatigue имеет проводку в cont, не в typed —
                # ложный вердикт «born-dead» для доказанного ADR-O-383 edge):
                if k in census:
                    _bucket = typed.get(k.rsplit(".", 1)[1], {"readers": [], "writers": []})
                else:
                    _dom = k.split(".", 1)[0]
                    _bucket = cont.get(_dom, {}).get(k, {"readers": [], "writers": []})
                if not _bucket["readers"]:
                    violations.append(f"[M-XREAD] {k} -> CAUSAL без reader'а (Слой 1 не видит проводку)")
                if not _bucket["writers"]:
                    violations.append(f"[M-XWRITE] {k} -> CAUSAL без writer'а (born-dead под видом каузальности)")
            elif fc.mode in ("PROJECTION", "DEBT"):
                # M-AUTH: authority обязателен («проекция чего, SSOT — кто»)
                if not fc.authority or not _AUTHORITY_RE.search(fc.authority):
                    violations.append(f"[M-AUTH] {k} -> {fc.mode} без authority-ссылки (лазейка «помечу и отвяжусь»)")
                # M-XREAD-CAUSAL-ONLY: PROJECTION без читателя легален (diagnostic-archive),
                # если terminal=diagnostic — иначе «проекция» без проекции
                if fc.mode == "PROJECTION" and not fc.terminal == "diagnostic" and fc.terminal != "projection":
                    _tn = k.rsplit(".", 1)[1]
                    if not typed.get(_tn, {"readers": []})["readers"] and fc.terminal not in (None, "persistence"):
                        violations.append(f"[M-PROJ] {k} -> PROJECTION без читателя и не diagnostic/persistence")

    _manifest = FIELD_CAUSALITY if _MANIFEST_OK else {}
    stats = {"manifest": len(_manifest),
             "parse_errors": len(parse_errors),
             "census_typed": len(census),
             "census_container": sum(len(v) for v in cont.values()),
             "no_reader": sum(1 for v, _, _ in raw if v == "NO_READER"),
             "no_writer": sum(1 for v, _, _ in raw if v == "NO_WRITER"),
             "debts": len(DEBT_FIELDS)}
    return violations, stats


if __name__ == "__main__":
    viol, st = run_lint()
    print(f"[CENSUS] typed={st['census_typed']} container={st['census_container']} "
          f"debts={st['debts']} manifest={st['manifest']} parse_errors={st['parse_errors']}")
    print(f"[RAW FINDINGS] NO_READER={st['no_reader']} NO_WRITER={st['no_writer']} "
          f"(подавлено реестром: {st['no_reader'] + st['no_writer'] - len([v for v in viol if v.startswith('[CONSUMER-GAP-NO')])})")
    if viol:
        print(f"❌ CONSUMER-GAP: {len(viol)} нарушений:")
        for v in viol:
            print(f"  {v}")
        sys.exit(1)
    print("✅ CONSUMER-GAP Слой 1: несанкционированных orphan-полей не найдено.")
    sys.exit(0)
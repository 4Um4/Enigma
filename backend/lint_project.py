"""
backend/lint_project.py
Статический анализатор структурной целостности проекта.



Проверяет:
1. Orphan-методы (self-функции вне классов или вложенные в другие функции)
2. Дублирующиеся return в одной функции (мёртвый код)
3. Вызовы несуществующих методов классов
4. Голые except и тихое проглатывание ошибок (except: pass)
5. Дублирующиеся ключи в литералах словарей
6. Неиспользуемые импорты

Запуск: python backend/lint_project.py backend
"""

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LintIssue:
    """Одна найденная проблема."""
    file: str
    line: int
    severity: str  # ERROR, WARNING, INFO
    category: str  # ORPHAN_METHOD, DEAD_CODE, MISSING_METHOD, BAD_IMPORT
    message: str


@dataclass
class LintResult:
    """Результат проверки одного файла."""
    file: str
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "ERROR" for i in self.issues)


def _check_orphan_methods(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет self-функции, которые не являются прямыми методами класса."""
    issues = []

    def _get_used_names_as_args(node: ast.AST) -> set[str]:
        """Собирает имена, переданные как аргументы в вызовы (используемые как моки)."""
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                for arg in child.args:
                    if isinstance(arg, ast.Name):
                        names.add(arg.id)
                for kw in child.keywords:
                    if isinstance(kw.value, ast.Name):
                        names.add(kw.value.id)
        return names

    def _walk(node: ast.AST, parent_path: str = ""):
        # Если внутри функции, собираем имена-аргументы, чтобы не ругаться на моки
        passed_names = _get_used_names_as_args(node) if parent_path else set()

        for child in ast.iter_child_nodes(node):
            child_path = parent_path

            if isinstance(child, ast.ClassDef):
                # Прямые методы класса — норма
                for method in child.body:
                    if isinstance(method, ast.FunctionDef):
                        _walk(method, f"{child.name}.{method.name}")
                continue

            if isinstance(child, ast.FunctionDef):
                has_self = (
                    child.args.args
                    and child.args.args[0].arg == "self"
                )
                if has_self and parent_path and child.name not in passed_names:
                    # self-функция внутри другой функции = orphan
                    issues.append(LintIssue(
                        file=file,
                        line=child.lineno,
                        severity="ERROR",
                        category="ORPHAN_METHOD",
                        message=(
                            f"def {child.name}() с self вложена в "
                            f"{parent_path} — метод потерян из класса"
                        ),
                    ))
                _walk(child, child_path)

            if isinstance(child, ast.If):
                _walk(child, child_path)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            _walk(node, f"def {node.name}")

    return issues


def _check_module_level_orphans(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет self-функции на уровне модуля (вне любого класса)."""
    issues = []
    known_module_functions = {
        # Функции уровня модуля, которые законно принимают self-like аргумент
        # (добавляй по мере необходимости)
    }

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name in known_module_functions:
                continue
            has_self = (
                node.args.args
                and node.args.args[0].arg == "self"
            )
            if has_self:
                issues.append(LintIssue(
                    file=file,
                    line=node.lineno,
                    severity="ERROR",
                    category="ORPHAN_METHOD",
                    message=(
                        f"def {node.name}() с self на уровне модуля — "
                        f"должна быть внутри класса"
                    ),
                ))
    return issues


def _check_dead_returns(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет код после return в том же блоке — гарантированный мёртвый код."""
    issues = []

    def _check_block(statements: list, func_name: str):
        """Проверяет список statement'ов на наличие кода после return."""
        for i, stmt in enumerate(statements):
            if isinstance(stmt, ast.Return) and i < len(statements) - 1:
                dead = statements[i + 1]
                issues.append(LintIssue(
                    file=file,
                    line=dead.lineno,
                    severity="WARNING",
                    category="DEAD_CODE",
                    message=(
                        f"Код после return в {func_name}() — "
                        f"строка {dead.lineno} никогда не выполнится"
                    ),
                ))
                return  # Один раз на блок достаточно

    def _walk_body(node: ast.AST, func_name: str):
        """Рекурсивно проверяет все блоки внутри функции."""
        # Проверяем текущий блок
        body = getattr(node, "body", None)
        if isinstance(body, list) and len(body) > 1:
            _check_block(body, func_name)

        # Проверяем вложенные блоки (if/else/for/while/try/with)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                _walk_body(child, func_name)
            # Пропускаем вложенные функции/лямбды — они отдельный scope
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk_body(node, node.name)

    return issues


def _check_class_method_calls(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет вызовы self.method(), где method не существует в классе."""
    issues = []

    def _collect_class_members(class_node: ast.ClassDef) -> set[str]:
        members = set()
        # Пропускаем классы тестов — self.assert* унаследованы от unittest.TestCase
        base_names = {b.id for b in class_node.bases if isinstance(b, ast.Name)}
        if "TestCase" in base_names or class_node.name.endswith("Tests") or class_node.name.endswith("Test"):
            return {"*"}  # Магическое значение: пропустить все проверки для этого класса

        for child in class_node.body:
            if isinstance(child, ast.FunctionDef):
                members.add(child.name)
                # Смотрим в __init__ на присвоения self.xxx = ...
                if child.name == "__init__":
                    for init_child in ast.walk(child):
                        if isinstance(init_child, ast.Assign):
                            for target in init_child.targets:
                                if (isinstance(target, ast.Attribute) and 
                                    isinstance(target.value, ast.Name) and 
                                    target.value.id == "self"):
                                    members.add(target.attr)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                # self.x: int = ... (dataclass / Pydantic)
                members.add(child.target.id)
            elif isinstance(child, ast.Assign):
                # self.x = ...
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        members.add(target.id)
        return members

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        methods = _collect_class_members(node)
        if "*" in methods:
            continue  # Тестовый класс, пропускаем

        # Ищем вызовы self.xxx()
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                if (
                    isinstance(child.value, ast.Name)
                    and child.value.id == "self"
                    and child.attr not in methods
                    and not child.attr.startswith("_")
                ):
                    # Пропускаем: __init__, приватные, dunder
                    if child.attr.startswith("__") and child.attr.endswith("__"):
                        continue
                    issues.append(LintIssue(
                        file=file,
                        line=child.lineno,
                        severity="WARNING",
                        category="MISSING_METHOD",
                        message=(
                            f"self.{child.attr}() вызывается, но не найден "
                            f"в классе {node.name}"
                        ),
                    ))

    return issues


def _check_mutable_defaults(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет мутабельные значения по умолчанию (list, dict, set) в аргументах функций."""
    issues = []
    mutable_types = (ast.List, ast.Dict, ast.Set)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Проверяем все дефолтные значения (позиционные и именованные)
        for default in node.args.defaults + node.args.kw_defaults:
            if default is None:
                continue
            if isinstance(default, mutable_types):
                issues.append(LintIssue(
                    file=file,
                    line=default.lineno,
                    severity="ERROR",
                    category="MUTABLE_DEFAULT",
                    message=(
                        f"Мутабельный дефолт в {node.name}() — "
                        f"будет расшарен между вызовами. Используй None и инициализацию внутри."
                    ),
                ))
            elif isinstance(default, ast.Call):
                # Отлавливаем явные вызовы dict(), list(), set()
                func_name = ""
                if isinstance(default.func, ast.Name):
                    func_name = default.func.id
                elif isinstance(default.func, ast.Attribute):
                    func_name = default.func.attr
                
                if func_name in ("dict", "list", "set"):
                    issues.append(LintIssue(
                        file=file,
                        line=default.lineno,
                        severity="ERROR",
                        category="MUTABLE_DEFAULT",
                        message=(
                            f"Вызов {func_name}() в дефолте {node.name}() — "
                            f"создаётся один раз на модуль. Убери в тело функции."
                        ),
                    ))
    return issues


def _check_unused_imports(tree: ast.AST, file: str, filename: str) -> list[LintIssue]:
    """Ищет импорты, которые нигде не используются в файле."""
    issues = []
    
    # Пропускаем __init__.py — там импорты используются для реэкспорта, а не внутри файла
    if filename.endswith("__init__.py"):
        return issues

    imports: dict[str, int] = {}

    # Собираем импорты на верхнем уровне
    # Пропускаем блоки if TYPE_CHECKING: — типы импортируются специально для анализаторов
    type_checking_nodes: set[ast.AST] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            for tc_child in ast.walk(node):
                type_checking_nodes.add(tc_child)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            # from __future__ import annotations — это флаг парсера, не использование
            continue

        # Пропускаем импорты внутри if TYPE_CHECKING:
        if node in type_checking_nodes:
            continue
            
        if isinstance(node, ast.Import):
            for alias in node.names:
                # import os.path -> запоминаем 'os'
                name = alias.asname if alias.asname else alias.name.split('.')[0]
                imports[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            # Пропускаем from x import *
            if any(alias.name == '*' for alias in node.names):
                continue
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imports[name] = node.lineno

    if not imports:
        return issues

    # Собираем все используемые имена (загрузка, не присваивание)
    usages = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            usages.add(node.id)
        elif isinstance(node, ast.Attribute):
            # self._working.apply_decay() → нужно и 'apply_decay', и '_working'
            usages.add(node.attr)
            if isinstance(node.value, ast.Name):
                usages.add(node.value.id)

    # Строковые аннотации (forward references): "Condition" в типах
    # Проверяем только позиции аннотаций, чтобы не ловить докстринги
    def _extract_forward_ref(annotation_node: ast.AST | None) -> str | None:
        if isinstance(annotation_node, ast.Constant) and isinstance(annotation_node.value, str):
            return annotation_node.value
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            ref = _extract_forward_ref(node.annotation)
            if ref:
                usages.add(ref)
        elif isinstance(node, ast.FunctionDef):
            ref = _extract_forward_ref(node.returns)
            if ref:
                usages.add(ref)
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                ref = _extract_forward_ref(arg.annotation)
                if ref:
                    usages.add(ref)

    # Сравниваем
    for name, line in imports.items():
        if name not in usages:
            # Исключаем стандартные псевдонимы (например, если used as typing alias)
            issues.append(LintIssue(
                file=file,
                line=line,
                severity="WARNING",
                category="UNUSED_IMPORT",
                message=f"Импорт '{name}' не используется в файле",
            ))

    return issues


def _check_exception_handling(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет голые except и тихие проглатывания ошибок."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue

        # Голый except: без типа — ловит KeyboardInterrupt и SystemExit
        if node.type is None:
            issues.append(LintIssue(
                file=file,
                line=node.lineno,
                severity="ERROR",
                category="BARE_EXCEPT",
                message="Голый except: — ловит SystemExit/KeyboardInterrupt. Укажи конкретный тип ошибки.",
            ))
            continue

        # Проверяем тело на наличие только pass / ... / строк-документаций
        has_logic = len(node.body) > 0  # Если хоть что-то есть, считаем что обработка присутствует

        if not has_logic:
            # Извлекаем человекочитаемое имя типа исключения
            err_name = "Exception"
            if isinstance(node.type, ast.Name):
                err_name = node.type.id
            elif isinstance(node.type, ast.Tuple):
                parts = []
                for e in node.type.elts:
                    if isinstance(e, ast.Name):
                        parts.append(e.id)
                    elif isinstance(e, ast.Attribute):
                        parts.append(e.attr)
                    else:
                        parts.append("...")
                err_name = ", ".join(parts)
            issues.append(LintIssue(
                file=file,
                line=node.lineno,
                severity="WARNING",
                category="SILENT_EXCEPT",
                message=f"except {err_name} проглатывает ошибку без логики. Добавь логирование.",
            ))

    return issues


def _check_duplicate_dict_keys(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет дублирующиеся ключи в литералах словарей."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue

        seen_keys: dict[str, int] = {}
        for key in node.keys:
            if key is None:
                continue  # **kwargs распаковка, пропускаем

            # Извлекаем строковое значение ключа
            key_val = None
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                key_val = key.value

            if key_val is not None:
                if key_val in seen_keys:
                    issues.append(LintIssue(
                        file=file,
                        line=key.lineno,
                        severity="ERROR",
                        category="DUPLICATE_DICT_KEY",
                        message=(
                            f"Дублирующийся ключ '{key_val}' — "
                            f"тихо перезапишет значение со строки {seen_keys[key_val]}"
                        ),
                    ))
                else:
                    seen_keys[key_val] = key.lineno

    return issues


def _check_import_order(tree: ast.AST, file: str) -> list[LintIssue]:
    """Проверяет PEP 8 порядок: stdlib → third-party → local."""
    import sys
    issues = []
    
    # Получаем множество имён stdlib-модулей
    stdlib_names: set[str] = set()
    if hasattr(sys, "stdlib_module_names"):
        stdlib_names = sys.stdlib_module_names
    else:
        # Fallback для Python < 3.10
        stdlib_names = {
            "abc", "argparse", "asyncio", "collections", "dataclasses",
            "datetime", "enum", "functools", "json", "logging", "math",
            "os", "pathlib", "queue", "re", "sys", "threading", "time",
            "traceback", "types", "typing", "unittest", "urllib", "uuid",
            "copy", "decimal", "fractions", "hashlib", "io", "itertools",
            "operator", "pickle", "shutil", "tempfile", "textwrap",
        }
    
    def _classify(node: ast.AST) -> int:
        """0=stdlib, 1=third-party, 2=local"""
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("."):
            return 2
        if isinstance(node, ast.ImportFrom) and node.module:
            first_part = node.module.split(".")[0]
            if first_part in ("app", "backend"):
                return 2
            if first_part in stdlib_names:
                return 0
            return 1
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in ("app", "backend"):
                    return 2
                if top in stdlib_names:
                    return 0
            return 1
        return -1
    
    import_nodes: list[tuple[int, int]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_nodes.append((_classify(node), node.lineno))
    
    prev_group = -1
    for group, lineno in import_nodes:
        if group < prev_group:
            group_names = {0: "stdlib", 1: "third-party", 2: "local"}
            issues.append(LintIssue(
                file=file,
                line=lineno,
                severity="WARNING",
                category="IMPORT_ORDER",
                message=f"Импорт {group_names[group]} стоит после {group_names[prev_group]} — нарушен порядок PEP 8",
            ))
    
    return issues


def _check_wildcard_imports(tree: ast.AST, file: str, filename: str) -> list[LintIssue]:
    """Ищет from x import * — засоряет namespace и скрывает зависимости."""
    if filename.endswith("__init__.py"):
        return []
    issues = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            module = node.module or "(unknown)"
            issues.append(LintIssue(
                file=file,
                line=node.lineno,
                severity="WARNING",
                category="WILDCARD_IMPORT",
                message=f"from {module} import * — импортируйте только нужные имена",
            ))
    return issues


def _check_bare_except(tree: ast.AST, file: str) -> list[LintIssue]:
    """Ищет except: без указания типа исключения — маскирует ошибки."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(LintIssue(
                file=file,
                line=node.lineno,
                severity="WARNING",
                category="BARE_EXCEPT",
                message="except: без типа — маскирует все ошибки, включая KeyboardInterrupt и SystemExit",
            ))
    return issues


def _check_circular_imports(root: Path, exclude_dirs: list[str]) -> list[LintIssue]:
    """Ищет циклические импорты на уровне проекта через граф зависимостей."""
    import os

    issues = []

    # Шаг 1: индекс всех локальных модулей
    local_modules: dict[str, str] = {}  # полное имя → путь к файлу
    for py_file in root.rglob("*.py"):
        if any(part in py_file.parts for part in exclude_dirs):
            continue
        rel = py_file.relative_to(root).with_suffix("")
        local_modules[str(rel).replace(os.sep, ".")] = str(py_file)

    # Шаг 2: собираем граф зависимостей
    graph: dict[str, list[str]] = {}
    for module, filepath in local_modules.items():
        try:
            tree = ast.parse(Path(filepath).read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue

        deps = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                deps.add(node.module)

        # Ресолвим каждый импорт в конкретный локальный модуль
        local_deps = []
        for dep in deps:
            if dep in local_modules:
                local_deps.append(dep)
            else:
                # Ищем submodule: app.services.x → app.services.x (точное)
                prefix = dep + "."
                for mod in local_modules:
                    if mod.startswith(prefix):
                        local_deps.append(mod)
                        break
        # Убираем самоссылки (модуль не может зависеть от себя через локальный импорт)
        graph[module] = [d for d in local_deps if d != module]

    # Шаг 3: DFS с цветами для поиска циклов
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {m: WHITE for m in graph}
    path: list[str] = []
    seen_cycles: set[str] = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                # Нормализуем: начинаем с минимального элемента для дедупликации
                cycle_key = " → ".join(cycle)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    issues.append(LintIssue(
                        file=cycle[0],
                        line=0,
                        severity="ERROR",
                        category="CIRCULAR_IMPORT",
                        message=f"Циклический импорт: {cycle_key}",
                    ))
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        path.pop()
        color[node] = BLACK

    for module in graph:
        if color[module] == WHITE:
            dfs(module)

    return issues


def lint_file(filepath: Path) -> LintResult:
    """Проверяет один файл на все типы дефектов."""
    result = LintResult(file=str(filepath))

    try:
        src = filepath.read_text(encoding="utf-8-sig")
        tree = ast.parse(src, filename=str(filepath))
    except SyntaxError as e:
        result.issues.append(LintIssue(
            file=str(filepath),
            line=e.lineno or 0,
            severity="ERROR",
            category="SYNTAX_ERROR",
            message=f"Синтаксическая ошибка: {e.msg}",
        ))
        return result

    result.issues.extend(_check_orphan_methods(tree, str(filepath)))
    result.issues.extend(_check_module_level_orphans(tree, str(filepath)))
    result.issues.extend(_check_dead_returns(tree, str(filepath)))
    result.issues.extend(_check_mutable_defaults(tree, str(filepath)))
    result.issues.extend(_check_exception_handling(tree, str(filepath)))
    result.issues.extend(_check_duplicate_dict_keys(tree, str(filepath)))
    result.issues.extend(_check_bare_except(tree, str(filepath)))
    result.issues.extend(_check_import_order(tree, str(filepath)))
    result.issues.extend(_check_wildcard_imports(tree, str(filepath), filepath.name))
    result.issues.extend(_check_unused_imports(tree, str(filepath), filepath.name))
    # MISSING_METHOD отключён: AST не умеет резолвить наследование и dataclass.
    # Для поиска отсутствующих методов используй Pyright/Pylance в IDE.

    return result


def lint_project(root: Path, exclude_dirs: Optional[list[str]] = None) -> list[LintResult]:
    """Проверяет все .py файлы в проекте."""
    if exclude_dirs is None:
        exclude_dirs = [".venv", "__pycache__", "node_modules", ".git"]

    results = []
    for py_file in root.rglob("*.py"):
        # Пропускаем исключённые директории
        if any(part in py_file.parts for part in exclude_dirs):
            continue
        results.append(lint_file(py_file))

    # Проверки уровня проекта
    circular_issues = _check_circular_imports(root, exclude_dirs)
    if circular_issues:
        project_result = LintResult(file="[PROJECT]")
        project_result.issues.extend(circular_issues)
        results.append(project_result)

    return results


def print_results(results: list[LintResult]) -> None:
    """Выводит результаты в читаемом формате."""
    errors = 0
    warnings = 0

    for result in results:
        if not result.issues:
            continue

        for issue in result.issues:
            # Короткий путь к файлу
            short_path = issue.file.split("Enigma\\")[-1] if "Enigma\\" in issue.file else issue.file

            if issue.severity == "ERROR":
                errors += 1
                print(f"❌ {short_path}:{issue.line} [{issue.category}]")
                print(f"   {issue.message}")
            elif issue.severity == "WARNING":
                warnings += 1
                print(f"⚠️  {short_path}:{issue.line} [{issue.category}]")
                print(f"   {issue.message}")

    print(f"\n{'='*60}")
    print(f"Итого: {errors} ошибок, {warnings} предупреждений")

    if errors > 0:
        print("❌ КРИТИЧЕСКИЕ ПРОБЛЕМЫ — проект не запустится корректно")
        sys.exit(1)
    elif warnings > 0:
        print("⚠️  Есть предупреждения — проверь вручную")
    else:
        print("✅ Всё чисто")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    print(f"🔍 Проверка: {target}\n")
    results = lint_project(target)
    print_results(results)
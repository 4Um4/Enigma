"""
Запуск: python scripts/APS.py

Назначение:
- строит граф импортов
- сжимает шум (stdlib + framework)
- нормализует доменную структуру
- считает базовую "архитектурную напряжённость"
"""

import ast
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("backend/app")

print(f"[SCAN ROOT] {ROOT.resolve()}")

# -----------------------------
# 1. СЖАТИЕ СИСТЕМЫ (ключевой слой)
# -----------------------------

NOISE_ROOTS = {
    "time",
    "pathlib",
    "logging",
    "subprocess",
    "contextlib",
    "atexit",
    "urllib",
    "asyncio",
    "os",
    "json",
    "ast",
}

FRAMEWORK_MAP = {
    "fastapi": "FASTAPI_CORE",
}


def normalize_import(name: str):
    root = name.split(".")[0]

    # 1. удаляем шум
    if root in NOISE_ROOTS:
        return None

    # 2. схлопываем фреймворки
    if root in FRAMEWORK_MAP:
        return FRAMEWORK_MAP[root]

    # 3. доменная зона ENIGMA остаётся как есть
    if name.startswith("app."):
        return name

    # 4. внешние зависимости (оставляем но упрощаем)
    return root


# -----------------------------
# 2. ПАРСИНГ
# -----------------------------


def safe_parse(file_path):
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return ast.parse(f.read(), filename=str(file_path))
    except Exception as e:
        print(f"[SKIP] {file_path} -> {e}")
        return None


graph = defaultdict(lambda: {"imports": set(), "imported_by": set()})

total_files = 0
skipped = 0

# -----------------------------
# 3. СБОР ГРАФА
# -----------------------------

for file_path in ROOT.rglob("*.py"):
    total_files += 1

    tree = safe_parse(file_path)
    if not tree:
        skipped += 1
        continue

    module = str(file_path.with_suffix("")).replace("\\", ".").replace("/", ".")
    # Убираем префикс "backend." — normalize_import использует "app.*"
    if module.startswith("backend."):
        module = module[len("backend.") :]

    raw_imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                raw_imports.add(n.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                raw_imports.add(node.module)

    # нормализация (КЛЮЧЕВОЙ СЛОЙ СЖАТИЯ)
    for imp in raw_imports:
        norm = normalize_import(imp)
        if norm:
            graph[module]["imports"].add(norm)
            graph[norm]["imported_by"].add(module)

# -----------------------------
# 4. ПРЕОБРАЗОВАНИЕ В СЖАТЫЙ ФОРМАТ
# -----------------------------

compressed_graph = {}

for node, data in graph.items():
    compressed_graph[node] = {
        "imports": sorted(list(data["imports"])),
        "imported_by": sorted(list(data["imported_by"])),
        "fan_out": len(data["imports"]),
        "fan_in": len(data["imported_by"]),
        "bottleneck_score": len(data["imports"]) * len(data["imported_by"]),
    }

# -----------------------------
# 5. МЕТА-ОТЧЁТ (важнее графа)
# -----------------------------

stats = {
    "total_files": total_files,
    "skipped_files": skipped,
    "nodes": len(compressed_graph),
    "top_bottlenecks": sorted(
        compressed_graph.items(), key=lambda x: x[1]["bottleneck_score"], reverse=True
    )[:10],
}

# -----------------------------
# 6. ВЫВОД
# -----------------------------

with open("deps_compressed.json", "w", encoding="utf-8") as f:
    json.dump(compressed_graph, f, indent=2)

with open("deps_stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, indent=2, default=str)

print("[DONE]")
print(f"[FILES] {total_files}, [SKIPPED] {skipped}")
print("[OUTPUT] deps_compressed.json + deps_stats.json")

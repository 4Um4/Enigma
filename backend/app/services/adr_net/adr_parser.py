# backend/app/services/adr_net/adr_parser.py
"""
path: backend/app/services/adr_net/adr_parser.py
Назначение: Парсинг ADR Impact Audits и Master Index в структурированный граф (Этап 4.1).
Зависимости: re, os, dataclasses
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

def normalize_adr_id(raw_id: str) -> str:
    """Приводит ID к единому формату: ADR-148, ADR-O-327, ADR-TZ08-1."""
    if not raw_id:
        return ""
    s = raw_id.strip().upper()
    if s.startswith("ADR-"):
        s = s[4:]
    if s.startswith("O"):
        s = s[1:].lstrip("-")
        if s.isdigit():
            return f"ADR-O-{int(s)}"
        return f"ADR-O-{s}"
    if s.isdigit():
        return f"ADR-{int(s)}"
    return f"ADR-{s}"

@dataclass
class ADRNode:
    adr_id: str
    adr_type: str  # STD, ONTO
    title: str
    description: str = ""
    files: List[str] = field(default_factory=list)
    domain: str = ""
    laws: List[str] = field(default_factory=list)

# Регулярка для парсинга строки вида: `ADR-148` [STD] **Title** — Desc.
# H-20 FIX: Разрешаем любые буквы (A-Z), цифры (0-9) и дефисы в ID и типе.
_ADR_LINE_REGEX = re.compile(r"`(ADR-[A-Za-z0-9./\-]+)`\s*\[([A-Za-z0-9\-]+)\]\s*\*\*(.+?)\*\*")
# B1 (S315): матчит "Files: X" И "Files (full: ADR-X_IMPACT.md): X" (форма
# атласа standalone-ADR — substring "Files:" её не находил, 36 списков терялись)
_FILES_REGEX = re.compile(r"[-*]?\s*\*{0,2}Files\b(?:\s*\([^)]*\))?:\s*(.+)")
# B1: значения без файлов (118/120 аудитов "Files: N/A") → пустой список
_FILES_NOT_APPLICABLE = {"N/A", "N/A.", "—", "-", "NA"}

def parse_impact_audit(filepath: str) -> Optional[ADRNode]:
    """Парсит один файл ADR-0XX_IMPACT.md."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.debug(f"ADR file read error: {e}")
        return None

    # Ищем первую строку с ADR ID
    match = _ADR_LINE_REGEX.search(content)
    if not match:
        return None

    adr_id = normalize_adr_id(match.group(1))
    adr_type = match.group(2)
    title = match.group(3).strip()

    # Ищем Files
    files_match = _FILES_REGEX.search(content)
    files = []
    if files_match:
        files = _parse_files_value(files_match.group(1))

    return ADRNode(
        adr_id=adr_id,
        adr_type=adr_type,
        title=title,
        files=files
    )

def parse_master_index(filepath: str) -> List[ADRNode]:
    """Парсит Master Index для извлечения Laws и маппинга в ADRs."""
    nodes: List[ADRNode] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.debug(f"ADR file read error: {e}")
        return nodes

    current_domain = ""
    current_law = ""
    current_files: List[str] = []

    for i, line in enumerate(lines):
        if line.startswith("## DOM-"):
            current_domain = line.replace("##", "").strip().split(":")[0]
        elif _ADR_LINE_REGEX.search(line):
            # B1 (S315): standalone-ADR секции атласа (`ADR-X` [TYPE] **Title**...)
            # не парсились вовсе — их Files (36+ списков) были невидимы.
            _m = _ADR_LINE_REGEX.search(line)
            assert _m is not None  # ветвление гарантирует матч; гигиена narrow
            _adr_id = normalize_adr_id(_m.group(1))
            _title = _m.group(3).strip()
            # Files ниже заголовка: standalone-записи имеют Суть/Taboo/Status
            # разной длины — окно до следующего заголовка (не фикс 5 строк).
            _standalone_files: List[str] = []
            for offset in range(1, 9):
                if i + offset >= len(lines):
                    break
                nxt = lines[i+offset]
                if _ADR_LINE_REGEX.search(nxt) or nxt.startswith("## "):
                    break  # дошли до следующего ADR/секции — своего Files нет
                files_match = _FILES_REGEX.search(nxt)
                if files_match:
                    _standalone_files = _parse_files_value(files_match.group(1))
                    break
            nodes.append(ADRNode(
                adr_id=_adr_id,
                adr_type=_m.group(2),
                title=_title,
                files=_standalone_files,
            ))
        elif line.startswith("**L"):
            # Пример: **L1: State Mutation Law** (ADR-001, 013, 117)
            law_match = re.match(r"\*\*(L[\d\.]+):\s*(.+?)\*\*\s*\((.+)\)", line)
            if law_match:
                current_law = law_match.group(1)
                law_title = law_match.group(2)
                adr_ids_raw = law_match.group(3).split(",")

                # Ищем Files в следующих строках (до 5 строк вниз, чтобы не промахнуться при длинном описании)
                current_files = []
                for offset in range(1, 6):
                    if i + offset < len(lines) and re.search(r"\bFiles\b", lines[i+offset]):
                        files_match = _FILES_REGEX.search(lines[i+offset])
                        if files_match:
                            current_files = _parse_files_value(files_match.group(1))
                        break

                for adr_id_raw in adr_ids_raw:
                    adr_id_raw = adr_id_raw.strip()
                    if not adr_id_raw: continue

                    adr_id = normalize_adr_id(adr_id_raw)

                    node = ADRNode(
                        adr_id=adr_id,
                        adr_type="LAW",
                        title=law_title,
                        domain=current_domain,
                        laws=[current_law],
                        files=current_files
                    )
                    nodes.append(node)

    return nodes

def _parse_files_value(raw: str) -> List[str]:
    """B1 (S315): экстракция файлов из значения Files-строки.

    Приоритет — backtick-сегменты (канон атласа): пути без пробелов,
    хвосты-проза («(IMPACT: отсутствует...)», О-383) отсекаются.
    Fallback — CSV с обрезкой по первому пробелу/бэктику.
    """
    raw = raw.strip().rstrip(".")
    if raw in _FILES_NOT_APPLICABLE:
        return []
    if raw.count("`") >= 2:
        files = [s.strip() for s in re.findall(r"`([^`]+)`", raw)]
    else:
        files = []
        for seg in raw.split(","):
            m = re.match(r"[`]*([^\s`,]+)", seg.strip())
            if m:
                files.append(m.group(1))
    return [f for f in files if f and f not in _FILES_NOT_APPLICABLE]


def _resolve_repo_path(path: str) -> str:
    """B1: дефолты run_parser относительны CWD — вызов из другого каталога
    (зонд №86) тихо давал 0/0. Резолвим от корня репо, если путь не найден."""
    if os.path.exists(path):
        return path
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    # adr_parser.py → adr_net → services → app → backend → ROOT
    candidate = os.path.join(repo_root, path)
    return candidate if os.path.exists(candidate) else path


def run_parser(audits_dir: str = "docs/audits", master_index: str = "docs/ADR (Architecture Decision Records).md") -> dict:
    """Собирает все ADR в словарь {adr_id: ADRNode}."""
    all_adrs = {}
    audits_dir = _resolve_repo_path(audits_dir)
    master_index = _resolve_repo_path(master_index)

    # 1. Парсим Master Index для получения Laws и Domains
    if os.path.exists(master_index):
        law_nodes = parse_master_index(master_index)
        for node in law_nodes:
            if node.adr_id not in all_adrs:
                all_adrs[node.adr_id] = node
            else:
                # Дополняем существующий
                existing = all_adrs[node.adr_id]
                existing.laws.extend(node.laws)
                if not existing.domain:
                    existing.domain = node.domain

    # 2. Парсим Impact Audits для получения Files и Descriptions
    if os.path.exists(audits_dir):
        for filename in os.listdir(audits_dir):
            if filename.endswith(".md") and "IMPACT" in filename:
                filepath = os.path.join(audits_dir, filename)
                audit_node = parse_impact_audit(filepath)
                if audit_node:
                    if audit_node.adr_id in all_adrs:
                        # Обновляем существующий
                        existing = all_adrs[audit_node.adr_id]
                        existing.title = audit_node.title
                        # B1 (S315): пустой Files аудита (N/A-конвенция, 118 шт.)
                        # НЕ затирает файлы, собранные из атласа master index.
                        if audit_node.files:
                            existing.files = audit_node.files
                        existing.adr_type = audit_node.adr_type
                    else:
                        all_adrs[audit_node.adr_id] = audit_node

    return all_adrs

if __name__ == "__main__":
    graph = run_parser()
    logger.info(f"Распознано ADR: {len(graph)}")
    for aid, node in list(graph.items())[:5]:
        logger.info(f"  {aid} [{node.adr_type}] {node.title} (Laws: {node.laws}, Files: {len(node.files)})")

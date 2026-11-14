"""Тесты INV-MEM-ANTI-ARCHIVE (#9) — scripts/lint_mem_anti_archive.py.

Спецификация: ADR-O-443, B1–B11 APPROVED (design v4 FINAL).
"""
import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lint_mem_anti_archive import run_lint  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _crit(result: list[str]) -> list[str]:
    return [v for v in result if v.startswith("CRIT|")]


def _warn(result: list[str]) -> list[str]:
    return [v for v in result if v.startswith("WARN|")]


# Class A — known forbidden prefixes (CRIT)
@pytest.mark.parametrize("mod", [
    "chromadb", "faiss", "pinecone", "weaviate", "qdrant_client", "qdrant",
    "milvus", "pymilvus", "sentence_transformers", "gensim", "annoy",
    "hnswlib", "lancedb", "marqo", "vespa", "pgvector",
])
def test_class_a_top_level_import_is_crit(tmp_path, mod):
    _write(tmp_path, "m.py", f"import {mod}\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for import {mod}, got: {r}"


@pytest.mark.parametrize("stmt", [
    "import chromadb.client\n",
    "import chromadb.client as cc\n",
    "from chromadb.client import Client\n",
])
def test_class_a_submodule_import_is_crit(tmp_path, stmt):
    _write(tmp_path, "m.py", stmt)
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {stmt!r}, got {r}"


# Class A: openai / cohere — только embeddings-контур (B9)
@pytest.mark.parametrize("stmt", [
    "import openai.embeddings\n",
    "import openai.embeddings as oe\n",
    "from openai.embeddings import create\n",
])
def test_openai_embeddings_contour_is_crit(tmp_path, stmt):
    _write(tmp_path, "m.py", stmt)
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {stmt!r}"


def test_b11_from_openai_import_embeddings_not_flagged(tmp_path):
    """B11 documented residual (design v4 §7).

    'from openai import embeddings' -> path = 'openai' (root only, B11).
    'openai' НЕ в FORBIDDEN_PREFIXES. Семантически это может подгружать
    openai.embeddings (attribute access), но статически не отличимо.
    Residual документирован; future INV-MEM-LLM-EMBEDDING-ATTR — отдельный
    инвариант, не этот линтер.
    """
    _write(tmp_path, "m.py", "from openai import embeddings\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], (
        f"B11: 'from openai import embeddings' resolves to 'openai' (root); "
        f"CRIT ожидался бы только при нарушении B11: {r}"
    )


def test_openai_without_embeddings_is_clean(tmp_path):
    _write(tmp_path, "m.py", "import openai\nfrom openai import OpenAI\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], f"openai без embeddings не должен ловиться: {r}"


# B11: from X import Y — консервативно X (корень)
def test_b11_from_chromadb_import_client_uses_root(tmp_path):
    _write(tmp_path, "m.py", "from chromadb import client\n")
    r = run_lint(root=tmp_path)
    assert any("chromadb" in v for v in _crit(r)), f"expected CRIT via root chromadb: {r}"


# Class B — heuristic (WARN, не CRIT) — B4
@pytest.mark.parametrize("mod", [
    "similarity_metrics", "my_embeddings_util", "vector_utils", "knn_lib", "chroma_helpers",
])
def test_class_b_heuristic_is_warn_not_crit(tmp_path, mod):
    _write(tmp_path, "m.py", f"import {mod}\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], f"heuristic {mod} не должен быть CRIT: {r}"
    assert _warn(r), f"heuristic {mod} должен быть WARN: {r}"


def test_class_b_stdlib_not_flagged(tmp_path):
    _write(tmp_path, "m.py", "import json\nimport re\nimport collections\n")
    r = run_lint(root=tmp_path)
    assert r == [], f"stdlib не должен ловиться: {r}"


def test_class_b_project_prefix_not_flagged(tmp_path):
    _write(tmp_path, "m.py", "from app.services.memory import foo\n")
    r = run_lint(root=tmp_path)
    assert r == [], f"app.* не должен ловиться: {r}"


# Class C — dynamic imports (B2)
def test_dynamic_import_direct_literal_is_crit(tmp_path):
    _write(tmp_path, "m.py", 'import importlib\nimportlib.import_module("faiss")\n')
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for literal import_module('faiss'): {r}"


def test_dynamic_import_dunder_literal_is_crit(tmp_path):
    _write(tmp_path, "m.py", '__import__("chromadb")\n')
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for __import__('chromadb'): {r}"


def test_dynamic_import_alias_importlib_as_il(tmp_path):
    _write(tmp_path, "m.py", 'import importlib as il\nil.import_module("faiss")\n')
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for il.import_module('faiss'): {r}"


def test_dynamic_import_alias_from_importlib_lm(tmp_path):
    _write(tmp_path, "m.py", 'from importlib import import_module as lm\nlm("chromadb")\n')
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for lm('chromadb'): {r}"


def test_dynamic_import_non_literal_is_warn(tmp_path):
    _write(tmp_path, "m.py", 'import importlib\nname = get_name()\nimportlib.import_module(name)\n')
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], f"non-literal должен быть WARN, не CRIT: {r}"
    assert _warn(r), f"non-literal должен дать WARN: {r}"


def test_dynamic_import_stdlib_literal_not_flagged(tmp_path):
    _write(tmp_path, "m.py", 'import importlib\nimportlib.import_module("json")\n')
    r = run_lint(root=tmp_path)
    assert r == [], f"import_module('json') не должен ловиться: {r}"


# Class D — artifacts (B1)
@pytest.mark.parametrize("literal", [
    '"vectors.faiss"', '"hnsw.index"', '"chroma.sqlite3"', '"embeddings.db"',
])
def test_artifact_vector_specific_is_crit(tmp_path, literal):
    _write(tmp_path, "m.py", f"p = {literal}\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {literal}: {r}"


@pytest.mark.parametrize("literal", [
    '"npc_profile.pkl"', '"world_coordinates.npy"', '"my_ann_data.ann"',
])
def test_artifact_common_no_context_not_flagged(tmp_path, literal):
    _write(tmp_path, "m.py", f"p = {literal}\n")
    r = run_lint(root=tmp_path)
    assert r == [], f"{literal} без vector-context не должен ловиться: {r}"


@pytest.mark.parametrize("literal", [
    '"faiss_index.pkl"', '"embeddings.npy"', '"vector_data.ann"',
])
def test_artifact_common_with_context_is_crit(tmp_path, literal):
    _write(tmp_path, "m.py", f"p = {literal}\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {literal} (vector-context): {r}"


# Robustness (B6)
def test_nested_deep_import_is_crit(tmp_path):
    _write(tmp_path, "deep/a/b/c/m.py", "import faiss\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), f"deep nested import must be found: {r}"


def test_two_violations_same_file(tmp_path):
    _write(tmp_path, "m.py", "import faiss\nimport chromadb\n")
    r = run_lint(root=tmp_path)
    assert len(_crit(r)) >= 2, f"expected >=2 CRIT, got {_crit(r)}"


def test_syntax_error_is_crit(tmp_path):
    _write(tmp_path, "m.py", "def broken(:\n")
    r = run_lint(root=tmp_path)
    assert any("PARSE_ERROR" in v for v in _crit(r)), f"syntax error must be CRIT: {r}"


def test_binary_encoding_is_crit(tmp_path):
    p = tmp_path / "m.py"
    p.write_bytes(b"\xff\xfe\x00bad")
    r = run_lint(root=tmp_path)
    assert any(("UNREADABLE" in v or "PARSE_ERROR" in v) for v in _crit(r)), f"bad encoding: {r}"


# Allowlist (B5 + B8 + B11)
def test_allowlist_exact_path_matches(tmp_path):
    _write(tmp_path, "m.py", "import faiss\n")
    allow = {("m.py", "faiss"): {"adr": "ADR-O-TEST", "rationale": "test only"}}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert r == [], f"allowlist exact match должен пройти: {r}"


def test_allowlist_parent_does_not_cover_submodule(tmp_path):
    _write(tmp_path, "m.py", "from chromadb.client import Client\n")
    allow = {("m.py", "chromadb"): {"adr": "ADR-O-TEST", "rationale": "test only"}}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert _crit(r), f"allowlist 'chromadb' не должен разрешать 'chromadb.client': {r}"


def test_allowlist_submodule_matches(tmp_path):
    _write(tmp_path, "m.py", "from chromadb.client import Client\n")
    allow = {("m.py", "chromadb.client"): {"adr": "ADR-O-TEST", "rationale": "test only"}}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert _crit(r) == [], f"allowlist 'chromadb.client' должен разрешить: {r}"


def test_allowlist_missing_adr_is_crit(tmp_path):
    _write(tmp_path, "m.py", "import faiss\n")
    allow = {("m.py", "faiss"): {"adr": "", "rationale": "test"}}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"missing adr must CRIT: {r}"


def test_allowlist_orphan_entry_is_crit(tmp_path):
    _write(tmp_path, "m.py", "import json\n")
    allow = {("m.py", "faiss"): {"adr": "ADR-O-TEST", "rationale": "test"}}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"orphan must CRIT: {r}"


# Baseline — B10 strict
def test_baseline_production_is_empty_strict():
    result = run_lint()
    assert result == [], f"production baseline != []: {result[:5]}"

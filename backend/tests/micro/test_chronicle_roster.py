"""path: backend/tests/micro/test_chronicle_roster.py
Назначение: C0.5 — ростер: id из JSON (не stem), деградация без падения.
Зависимости: pytest, npc_loader
Основные сущности: list_individual_ids"""

from __future__ import annotations


def test_roster_ids_from_json_not_stems(tmp_path, monkeypatch):
    from app.services.npc import npc_loader

    d = tmp_path / "individuals"
    d.mkdir()
    (d / "lusya.json").write_text('{"id": "maid_lusya"}', encoding="utf-8")
    (d / "tornin.json").write_text('{"id": "tavern_keeper_tornin"}', encoding="utf-8")
    monkeypatch.setattr(npc_loader, "_CONFIG_NPC_ROOT", tmp_path)
    # Имя файла (lusya) ≠ идентичность (maid_lusya) — тест-страж смешения.
    assert npc_loader.list_individual_ids() == ["maid_lusya", "tavern_keeper_tornin"]


def test_roster_degraded_not_silent(tmp_path, monkeypatch):
    from app.services.npc import npc_loader

    d = tmp_path / "individuals"
    d.mkdir()
    (d / "broken.json").write_text("{ не-json", encoding="utf-8")
    (d / "noid.json").write_text('{"name": "x"}', encoding="utf-8")
    (d / "ok.json").write_text('{"id": "a"}', encoding="utf-8")
    monkeypatch.setattr(npc_loader, "_CONFIG_NPC_ROOT", tmp_path)
    # Ни один битый файл не роняет ростер; no-id → stem-fallback; ok → id.
    ids = npc_loader.list_individual_ids()
    assert "a" in ids
    assert "noid" in ids
    assert all(isinstance(i, str) for i in ids)
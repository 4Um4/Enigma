"""CCH-12 Species infrastructure: вид как first-class понятие NPCProfileL0.

4 инварианта:
1. NPCProfileL0 без species → "" (UNKNOWN, НЕ "Человек" — anti-pattern routes.py:1279).
2. load_profile_from_legacy_json читает species из orm.json → 'gnome' (вертикальный proof).
3. orm.json содержит species='gnome' (авторское решение Мастера).
4. NPC без указанного вида сохраняют UNKNOWN (нет скрытой массовой подстановки).

Не покрывает: ancestry (родословная — отдельное измерение), PerceivedEntity,
NPCState (species в L0, не копируется без архитектурной необходимости).

ancestry (1/4 human через бабушку 1678 лет назад) — отдельная задача, не сводится
к species. species='gnome' фиксирует основной вид; происхождение живёт отдельно.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models.npc_profile import NPCProfileL0
from app.services.npc.npc_loader import load_profile_from_legacy_json

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_npc_profile_without_species_defaults_to_empty():
    """Инвариант 1: NPCProfileL0 без species → "" (UNKNOWN, не "Человек")."""
    profile = NPCProfileL0(
        id="test",
        name="Test",
        tier="minor",
        gender="male",
        archetype="commoner",
        drives_base={"control": 0.3, "significance": 0.2, "fear": 0.1, "desire": 0.4},
        psyche_base={"willpower": 50, "breakpoint": 70, "loyalty_true": 50.0},
        voice_profile="neutral",
    )
    assert profile.species == "", (
        "отсутствие species должно быть UNKNOWN (''), не 'human'"
    )


def test_npc_loader_reads_species_from_orm_json():
    """Инвариант 2: load_profile_from_legacy_json читает species из orm.json → 'gnome'.

    Реальный вертикальный proof: raw_data (config/npc/individuals/orm.json) →
    load_profile_from_legacy_json → NPCProfileL0.species == 'gnome'.
    """
    orm_path = _REPO_ROOT / "config" / "npc" / "individuals" / "orm.json"
    raw = json.loads(orm_path.read_text(encoding="utf-8"))
    profile = load_profile_from_legacy_json(raw)
    assert profile.species == "gnome", (
        f"load_profile_from_legacy_json должен читать species из orm.json. "
        f"Получено: {profile.species!r}. Ожидалось: 'gnome'."
    )


def test_orm_has_gnome_species():
    """Инвариант 3: orm.json содержит species='gnome' (авторское решение Мастера).

    Авторская истина: основной вид Орма — гном. Человеческое происхождение (1/4
    через бабушку по материнской линии, 1678 лет назад) — отдельное измерение
    (ancestry), не сводится к species. 'gnome' = авторский термин мира ENIGMA,
    не D&D 'dwarf'.
    """
    orm_path = _REPO_ROOT / "config" / "npc" / "individuals" / "orm.json"
    raw = json.loads(orm_path.read_text(encoding="utf-8"))
    assert raw.get("species") == "gnome", (
        "Орм должен иметь species='gnome' (авторское решение). "
        "Если значение изменилось — обнови тест И подтверди авторское решение."
    )


def test_other_npcs_keep_unknown_species():
    """Инвариант 4: NPC без указанного вида сохраняют UNKNOWN ('').

    Не заполняем 'human' по умолчанию. Скрытое лицо Shadow ≠ неизвестный вид —
    это два разных знания (что NPC собой представляет vs что может установить
    наблюдатель). Источник вида — авторский материал, не визуальное впечатление.
    """
    individuals_dir = _REPO_ROOT / "config" / "npc" / "individuals"
    npc_files = [
        "borko.json", "goran.json", "lusya.json",
        "shadow.json", "tornin.json",
    ]
    for fname in npc_files:
        path = individuals_dir / fname
        raw = json.loads(path.read_text(encoding="utf-8"))
        species = raw.get("species", "")
        assert species == "", (
            f"{fname}: species должен быть '' (UNKNOWN), не '{species}'. "
            f"Не подставляем 'human' без подтверждённого авторского источника."
        )
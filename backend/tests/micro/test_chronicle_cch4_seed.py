"""path: backend/tests/micro/test_chronicle_cch4_seed.py
Назначение: T-CCH-05/06 (микро-уровень) + запреты 1/3/4/5 ADR-O-423:
            детерминизм, изоляция знания (Марк), приоритет канона,
            future-отказ, trauma-без-triggers, реестр убеждений,
            valence-числа, new-game-гейт загрузчика.
Зависимости: pytest, chronicle_seeder, npc_loader, домен хроники
Основные сущности: тесты-функции + фикстура изоляции канон-папки"""

from __future__ import annotations

import json

import pytest

from app.domain.chronicle import (
    CauseKind,
    CauseRef,
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle import chronicle_seeder as seeder


# ── Фабрики домена (прямой ctor frozen-DTO = documented API домена) ─────────


def _sub(npc_id: str = "maid_lusya") -> EntityRef:
    return EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id)


def _event(eid: str, age, summary="событие", causes=()) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.EVENT,
        subject_id=_sub(),
        historical_age=age,
        payload={"summary": summary},
        causes=tuple(causes),
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=0,
    )


def _doc(entries=(), npc_id="maid_lusya", game_start_age=14) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        entries=tuple(entries),
        canonical=True,
        game_start_age=game_start_age,
    )


@pytest.fixture(autouse=True)
def _isolated_canon(monkeypatch, tmp_path):
    """Канон-папка тестов = tmp: ни один тест не читает/пишет прод-канон."""
    monkeypatch.setattr(seeder, "_cache", {"dir_mtime": None, "docs": {}})
    monkeypatch.setattr(seeder, "_canon_dir", lambda: tmp_path)
    return tmp_path


def _write_canon(tmp_path, doc: ChronicleDocument) -> None:
    from app.services.chronicle.chronicle_store import document_to_dict

    (tmp_path / f"{doc.npc_ref}.json").write_text(
        json.dumps(document_to_dict(doc), ensure_ascii=False), encoding="utf-8"
    )


# ── T-CCH-05: детерминизм ────────────────────────────────────────────────────


def test_seed_deterministic_two_runs(tmp_path):
    doc = _doc(
        entries=(
            _event("e1", 8, "убили семью"),
            _event("e2", 12, "ударил её"),
        )
    )
    _write_canon(tmp_path, doc)
    a = seeder.build_full_seed("maid_lusya")
    b = seeder.build_full_seed("maid_lusya")
    assert a is not None and b is not None
    assert a == b  # байт-в-байт (frozen-структуры, без wall-clock/random)


# ── T-CCH-06: изоляция знания («Марк не знает») ─────────────────────────────


def _knowledge(eid: str, knower: str, learned_age: int) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.KNOWLEDGE_LINK,
        subject_id=_sub(),
        payload={
            "event_ref": "ev_tornin",
            "knower": {
                "ref_kind": "RESOLVED",
                "npc_id": knower,
                "white_spot_id": None,
                "name_hint": "",
            },
            "learned_age": learned_age,
            "channel": "TOLD",
            "certainty": 1.0,
        },
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=1,
    )


def test_mark_isolation_goran_gets_nothing():
    # Знание лежит в хронике ВЛАДЕЛЬЦА события (Торнин @45); возраст
    # узнавания (17) — возраст ЗНАЮЩЕГО и конвертируется относительно
    # ЕГО хроники (Люся @27): (17-27)*365 = -3650. Смешение чужих
    # возрастов (Торнин 45) запрещено — тест-страж запрета 4.
    tornin_doc = _doc(
        entries=(
            _event("ev_tornin", 11, "Торнин убил человека"),
            _knowledge("kl1", "maid_lusya", 17),
        ),
        npc_id="tavern_keeper_tornin",
        game_start_age=45,
    )
    lusya_doc = _doc(entries=(), npc_id="maid_lusya", game_start_age=27)
    docs = {"tavern_keeper_tornin": tornin_doc, "maid_lusya": lusya_doc}
    assert seeder.build_seed_knowledge("merchant_goran", docs) == ()  # Марк — ноль
    lusya = seeder.build_seed_knowledge("maid_lusya", docs)
    assert len(lusya) == 1
    assert lusya[0].day == (17 - 27) * 365  # ось ЗНАНИЯ (возраст Люси), не события (11 Торнина)
    assert lusya[0].day != (11 - 45) * 365  # возраст владельца НЕ смешан
    assert lusya[0].hidden_from == ("player",)  # телепатия игроку запрещена


# ── Приоритет канона и legacy ────────────────────────────────────────────────


def test_no_canon_full_seed_none():
    assert seeder.build_full_seed("merchant_goran") is None


def test_future_age_fail_loud():
    doc = _doc(entries=(_event("e1", 20),), game_start_age=14)
    with pytest.raises(seeder.SeederError):
        seeder.build_seed_memories("maid_lusya", doc)


def test_no_age_anchor_sentinel():
    doc = _doc(entries=(_event("e1", None, "день неизвестен"),), game_start_age=14)
    mems = seeder.build_seed_memories("maid_lusya", doc)
    assert mems[0].day == seeder.SENTINEL_DAY


# ── Травмы: триггеры только авторские ───────────────────────────────────────


def _effect(eid, effect_kind, extra=None) -> ChronicleEntry:
    payload = {"summary": "последствие", "effect_kind": effect_kind}
    if extra:
        payload.update(extra)
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.EFFECT,
        subject_id=_sub(),
        payload=payload,
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=2,
    )


def test_trauma_without_triggers_not_created():
    doc = _doc(entries=(_effect("fx1", "trauma"),))
    assert seeder.build_seed_imprints(doc) == []


def test_trauma_with_triggers_exact_fields_only():
    doc = _doc(entries=(_effect("fx1", "trauma", {"triggers": ["violence"]}),))
    imps = seeder.build_seed_imprints(doc)
    assert len(imps) == 1
    assert imps[0]["trigger_tags"] == ("violence",)
    assert imps[0]["decay_rate"] == 0.0
    # ЛИШНИХ ключей нет: носитель восстанавливает AffectiveImprint(**imp)
    from app.models.affect import AffectiveImprint

    AffectiveImprint(**imps[0])  # не бросает


# ── Убеждения: закрытый реестр ───────────────────────────────────────────────


def _belief(eid, belief_type) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.BELIEF_SEED,
        subject_id=_sub(),
        payload={"statement": "формулировка автора", "belief_type": belief_type},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=3,
    )


def test_belief_registry_closed():
    doc = _doc(entries=(_belief("b1", "danger"), _belief("b2", "что-то_иное")))
    out = seeder.build_seed_beliefs(doc)
    assert out == {"danger": [seeder.SEED_BELIEF_VALUE, seeder.SEED_BELIEF_CONFIDENCE, "chronicle", 0]}


# ── Связи: числа из знака, происхождение, неразрешённые ────────────────────


def _rel(eid, obj_ref, valence) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.RELATIONSHIP,
        subject_id=_sub(),
        object_id=obj_ref,
        payload={"summary": "связь", "valence": valence},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=4,
    )


def test_relationship_valence_and_provenance():
    doc = _doc(
        entries=(
            _rel(
                "r1",
                EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="tavern_keeper_tornin"),
                "negative",
            ),
            _rel("r2", EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="кузнец"), "negative"),
            _rel("r3", EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="guard_borko"), "neutral"),
        )
    )
    out = seeder.build_seed_relationships("maid_lusya", doc)
    assert out == {"tavern_keeper_tornin": {"trust": seeder.SEED_TRUST_NEGATIVE, "chronicle_origin": "r1"}}


# ── Гейт загрузчика: новая игра vs резюме ───────────────────────────────────


def _lusya_canon_file(tmp_path) -> None:
    doc = _doc(
        entries=(
            _event("e1", 12, "ударил её"),
            _effect("fx1", "trauma", {"triggers": ["violence"]}),
            _belief("b1", "danger"),
        )
    )
    _write_canon(tmp_path, doc)


def test_loader_gate_new_game_seeds(tmp_path):
    from app.models.npc.beliefs import BeliefType
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    _lusya_canon_file(tmp_path)
    seeder._cache = {"dir_mtime": None, "docs": {}}  # сброс после записи файла
    raw = {"id": "maid_lusya", "psyche": {}}
    state = load_l2_state_from_runtime_dict(raw)
    assert state.beliefs.get(BeliefType.DANGER) is not None  # beliefs засеяны
    assert len(raw["affective_imprints"]) == 1  # импринт в дикт-носитель
    assert any(m.tags and m.tags[0].startswith("chronicle:") for m in state.narrative_cache)


def test_loader_gate_resume_closed(tmp_path):
    from app.models.npc.beliefs import BeliefType
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    _lusya_canon_file(tmp_path)
    seeder._cache = {"dir_mtime": None, "docs": {}}
    from app.models.npc_state import EventMemory

    # Stub — EventMemory (не ChronicleEntry): override-канал несёт объекты
    # памяти; поверх легальны только канон-секреты мира (_seed_canon_
    # secret_memories) — их не отрицаем, отрицаем chronicle-утечку.
    fake_memory = (
        EventMemory(
            event_type="origin",
            target_id="",
            emotion_tag="neutral",
            day=-1000,
            importance=0.5,
            clarity=1.0,
            confidence=1.0,
            decay_rate=0.001,
            summary="stub_sqlite_memory",
            npc_id="maid_lusya",
            tags=(),
            is_secret=False,
            known_by=(),
            hidden_from=(),
            accessibility=1.0,
            secret_id=None,
        ),
    )
    raw = {"id": "maid_lusya", "psyche": {}}
    state = load_l2_state_from_runtime_dict(raw, narrative_cache_override=fake_memory)
    assert state.beliefs.get(BeliefType.DANGER) is None  # гейт закрыт
    assert "affective_imprints" not in raw
    assert any(m.summary == "stub_sqlite_memory" for m in state.narrative_cache)
    assert all(m.event_type != "chronicle_knowledge" for m in state.narrative_cache)
    assert not any(m.tags and m.tags[0].startswith("chronicle:") for m in state.narrative_cache)


def test_loader_no_canon_legacy_intact(tmp_path):
    from app.models.truth_state import TruthState
    from app.services.npc import npc_loader

    # Изоляция от прод-канона секретов мира (truth_state_tavern) —
    # тестируется ТОЛЬКО legacy-ветка, поверх легальных сеялок.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(npc_loader, "_M1_TRUTH_STATE_CACHE", TruthState(secrets={}, relations=()))
    try:
        raw = {
            "id": "merchant_goran",
            "psyche": {},
            "origin_events": [
                {"summary": "старое событие", "day": -1000, "importance": 0.5, "tags": []}
            ],
        }
        state = npc_loader.load_l2_state_from_runtime_dict(raw)
        assert len(state.narrative_cache) == 1  # legacy-путь жив (T-CCH-09 база)
        assert state.narrative_cache[0].summary == "старое событие"
    finally:
        monkeypatch.undo()
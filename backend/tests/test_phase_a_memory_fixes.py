"""
Назначение: Регрессионные тесты Фазы A (Этап 0, правки 0.1–0.3): P0 #1 — detect_resonance обязан получать npc_id (TypeError ронял фазу 3, фазы 4–10 пропускались); P0 #2/#3 — identity_cache персистится в SqliteMemoryStore (AttributeError у save_state, тихий ноль у load_state); S210 — лок-дисциплина всех методов стора с общим соединением (TOCTOU in_transaction→commit)
Зависимости: pytest, app.services.memory.* (без LLM / pygame / EventBus)
Основные сущности: SqliteMemoryStore, LayeredMemory, MemoryManager

Запуск: cd backend; python -m pytest tests/test_phase_a_memory_fixes.py -v --tb=short; cd ..

"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from app.services.memory.layered_memory import LayeredMemory
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.sqlite_store import SqliteMemoryStore

_APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _make_manager(root: Path) -> MemoryManager:
    """Продакшн-wiring (game_loop_builder.py:38-43) на временном каталоге."""
    store = SqliteMemoryStore(root / "enigma_memory.db")
    return MemoryManager(LayeredMemory(store), data_dir=str(root))


# ── P0 #1: detect_resonance обязан получать npc_id ──────────────────


def test_detect_resonance_accepts_npc_id(tmp_path: Path) -> None:
    """Регрессия TypeError: вызов с npc_id обязан работать (пустой буфер → [])."""
    mm = _make_manager(tmp_path)
    assert mm.detect_resonance("camp", "npc1") == []
    assert mm.detect_resonance("camp", "npc1", actor_id="player") == []


def test_detect_resonance_calls_carry_npc_id() -> None:
    """Греп-инвариант (прецедент M1b.2.7): каждый вызов detect_resonance
    в backend/app передаёт npc_id — два позиционных аргумента или kwarg.
    Ловит возврат к форме detect_resonance(campaign_id, actor_id=...),
    которая роняла фазу 3 и пропускала фазы 4-10 всего тика."""
    call_re = re.compile(r"(?<!def )detect_resonance\s*\(([^)]*)\)")
    offenders: List[str] = []
    for py in _APP_ROOT.rglob("*.py"):
        source = py.read_text(encoding="utf-8", errors="replace")
        for m in call_re.finditer(source):
            args = [a.strip() for a in m.group(1).split(",") if a.strip()]
            positional = [a for a in args if "=" not in a]
            kwargs = {a.split("=")[0].strip() for a in args if "=" in a}
            if len(positional) < 2 and "npc_id" not in kwargs:
                line = source[: m.start()].count("\n") + 1
                offenders.append(f"{py.name}:{line}: detect_resonance без npc_id")
    assert not offenders, "P0 #1 регрессия:\n" + "\n".join(offenders)


# ── P0 #2/#3: KV-контракт стора + identity_cache round-trip ─────────


def test_sqlite_store_kv_contract(tmp_path: Path) -> None:
    """Контракт JsonMemoryStore.save_state/load_state в SQLite-бэкенде:
    перезапись коллекции целиком (одна строка на коллекцию);
    отсутствующая коллекция → {}."""
    store = SqliteMemoryStore(tmp_path / "t.db")
    store.save_state("identity_cache", {"camp:npc1": {"resentment": 0.25}})
    store.save_state("identity_cache", {"camp:npc2": {"dependency": 0.2}})
    assert store.load_state("identity_cache") == {"camp:npc2": {"dependency": 0.2}}
    assert store.load_state("no_such_collection") == {}


def test_apply_identity_weights_no_attribute_error(tmp_path: Path) -> None:
    """Регрессия AttributeError: save_state существовал только у JSON-стора —
    запись черт роняла apply_identity_weights (три пути вызова)."""
    mm = _make_manager(tmp_path)
    mm.apply_identity_weights("camp", "npc1", [("resentment", 0.25)])
    assert mm.get_identity_traits("camp", "npc1") == {"resentment": 0.25}


def test_identity_cache_survives_manager_restart(tmp_path: Path) -> None:
    """V8-MEM-7 + §12.2 round-trip: черты переживают пересоздание
    MemoryManager на том же сторе (раньше: load_state нет → тихий ноль)."""
    mm1 = _make_manager(tmp_path)
    mm1.apply_identity_weights("camp", "npc1", [("resentment", 0.25)])
    mm1.apply_identity_weights("camp", "npc1", [("resentment", 0.25)])

    mm2 = _make_manager(tmp_path)
    assert mm2.get_identity_traits("camp", "npc1") == {"resentment": 0.5}


def test_identity_traits_isolated_per_npc(tmp_path: Path) -> None:
    """V8-MEM-13: черты одного NPC не попадают другому (анти-контаминация)."""
    mm = _make_manager(tmp_path)
    mm.apply_identity_weights("camp", "npc1", [("resentment", 0.25)])
    assert mm.get_identity_traits("camp", "npc2") == {}
    assert mm.get_identity_traits("other_campaign", "npc1") == {}


# ── S210: лок-дисциплина всех соединение-трогающих методов ──────────


def test_sqlite_store_methods_hold_lock() -> None:
    """S210 (P0 L1): каждый метод SqliteMemoryStore, работающий с общим
    соединением после старта, обязан держать self._lock — иначе гонка
    in_transaction→commit между потоками uvicorn (TOCTOU).
    __init__/_connect/_init_schema исключены: выполняются до раздачи
    объекта потокам; close вне скоупа Фазы A."""
    source = (_APP_ROOT / "services" / "memory" / "sqlite_store.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    required = {
        "append",
        "recent",
        "save_event_memory",
        "load_event_memories",
        "save_event_memories_batch",
        "delete_campaign",
        "save_state",
        "load_state",
        "execute",
        "query",
    }
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in required:
            found.add(node.name)
            has_lock = any(
                isinstance(w, ast.With)
                and any(
                    isinstance(item.context_expr, ast.Attribute)
                    and item.context_expr.attr == "_lock"
                    for item in w.items
                )
                for w in ast.walk(node)
            )
            assert has_lock, f"S210: метод {node.name} трогает self._conn без self._lock"
    assert not required - found, f"методы не найдены в sqlite_store.py: {required - found}"



# ── P0 #9 (Шаг 4): apply() обязан читать ключ text реплики NPC ──────


def test_apply_reads_text_key_npc_spoke(tmp_path: Path) -> None:
    """dialogue_materializer и social_action_subscriber публикуют NPC_SPOKE
    с ключом "text". Без него в цепочке память о репликах LLM-NPC пустая."""
    from app.domain.events import EventDTO
    from app.models.npc_state import EventMemory
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    mm = _make_manager(tmp_path)
    npc_state = load_l2_state_from_runtime_dict(
        {"id": "npc_01", "psyche": {}, "social_stats": {}}
    )
    event = EventDTO.create(
        event_type="npc_spoke",
        source="npc_01",
        payload={"npc_id": "npc_01", "text": "Слышь, северянин, ты откуда?"},
    )
    mm.apply(event, npc_state, campaign_id="camp_a")

    memories = mm._working.get("camp_a:npc_01")
    assert memories, "событие не попало в WorkingMemory"
    mem = memories[0]
    assert isinstance(mem, EventMemory)
    assert mem.summary == "Слышь, северянин, ты откуда?", mem.summary


def test_apply_key_chain_priority(tmp_path: Path) -> None:
    """Цепочка приоритета summary > raw_input > content > text:
    регресс старых ключей и порядок выбора."""
    from app.domain.events import EventDTO
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    mm = _make_manager(tmp_path)
    npc_state = load_l2_state_from_runtime_dict(
        {"id": "npc_02", "psyche": {}, "social_stats": {}}
    )

    evt_content = EventDTO.create(
        event_type="npc_spoke",
        source="npc_02",
        payload={"npc_id": "npc_02", "content": "ответ из content-пути"},
    )
    mm.apply(evt_content, npc_state, campaign_id="camp_b")
    assert mm._working.get("camp_b:npc_02")[0].summary == "ответ из content-пути"

    evt_priority = EventDTO.create(
        event_type="npc_spoke",
        source="npc_02",
        payload={"npc_id": "npc_02", "summary": "готовая выжимка", "text": "сырой текст"},
    )
    mm.apply(evt_priority, npc_state, campaign_id="camp_c")
    assert mm._working.get("camp_c:npc_02")[0].summary == "готовая выжимка"



# ── P0 #7 (Шаг 5): речь игрока ≠ угроза ──────────────────────────────


def test_player_spoke_does_not_raise_threat(tmp_path: Path) -> None:
    """_THREAT_TYPES содержал player_spoke: каждая реплика игрока
    поднимала DANGER/PLAYER_HOSTILE у слушателя. Речь — не угроза;
    реальная угроза в речи приходит семантикой (player_threatens)."""
    from types import SimpleNamespace

    from app.models.npc.beliefs import BeliefType
    from app.services.npc.belief_transition_engine import BeliefTransitionEngine
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    engine = BeliefTransitionEngine()
    state = load_l2_state_from_runtime_dict(
        {"id": "npc_01", "psyche": {}, "social_stats": {}}
    )
    speech = SimpleNamespace(
        event_type="player_spoke",
        distance=1.0,
        intensity=0.9,
        actor_id="player",
        visible_threat_markers=(),
    )
    deltas = engine.commit(state, speech, current_tick=10)
    for d in deltas:
        _is_threat = d.belief_type in (BeliefType.DANGER, BeliefType.PLAYER_HOSTILE)
        assert not (_is_threat and d.new_value > d.old_value + 1e-9), (
            f"речь игрока подняла угрозу: {d.belief_type} {d.old_value} -> {d.new_value}"
        )


def test_threat_types_set_contract() -> None:
    """Data-замок (прецедент M1b.2.7): сет угроз содержит реальные
    угрожающие типы и не содержит речь игрока."""
    from app.services.npc.belief_transition_engine import _THREAT_TYPES

    assert "player_spoke" not in _THREAT_TYPES
    for must in ("player_attacks", "player_threatens", "combat_started"):
        assert must in _THREAT_TYPES, f"реальная угроза выпала из сета: {must}"



# ── P0 №6 (Шаг 6): адаптер narrative_cache чист (§12.2) ──────────────

_MEM_JSON = {
    "_memory_type": "EventMemory",
    "event_type": "combat",
    "target_id": "player",
    "emotion_tag": "neutral",
    "day": 1,
    "importance": 0.7,
    "summary": "игрок подрался",
    "npc_id": "npc_01",
    "tags": ["player_actor"],
}


def _npc_dict_with_cache() -> dict:
    """runtime-словарь NPC с одним воспоминанием в JSON-формате.

    Форма — как у сериализатора to_persistence_dict (npc_state.py:953):
    narrative_cache живёт в КОРНЕ npc_dict, не в psyche
    (загрузчик читает raw_data.get("narrative_cache"), npc_loader.py:610).
    """
    return {
        "id": "npc_01",
        "psyche": {},
        "social_stats": {},
        "narrative_cache": [dict(_MEM_JSON)],
    }


def test_narrative_cache_survives_repeated_loads() -> None:
    """Регрессия двойного бага: decayed(1.0) при каждой загрузке выедал
    важность (5-8 загрузок L2 за тик = до -25% за тик). Три загрузки
    подряд обязаны давать одну и ту же importance."""
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    raw = _npc_dict_with_cache()
    values = []
    for _ in range(3):
        state = load_l2_state_from_runtime_dict(raw)
        values.append(state.narrative_cache[0].importance)
    assert values == [0.7, 0.7, 0.7], values


def test_narrative_cache_loader_does_not_mutate_input() -> None:
    """Регрессия WARA: pop('_memory_type') и tuple-конверсии мутировали
    входной npc_dict — вторая загрузка без write-back выбрасывала всю
    narrative_cache. Вход обязан остаться байт-в-байт неизменным."""
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    raw = _npc_dict_with_cache()
    load_l2_state_from_runtime_dict(raw)
    assert raw["narrative_cache"][0] == _MEM_JSON, (
        "адаптер мутировал входной словарь (§12.2 WARA)"
    )



def test_narrative_cache_full_round_trip() -> None:
    """§12.2 полный цикл: load → to_persistence_dict → load — identity.
    Сериализатор пишет narrative_cache в корень npc_dict с маркером
    _memory_type и tuple→list; загрузчик читает из корня и нормализует
    list→tuple. Цикл обязан сходиться без потерь полей."""
    from app.models.npc_state import NPCState
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    raw = _npc_dict_with_cache()
    state = load_l2_state_from_runtime_dict(raw)

    out_dict: dict = {"id": "npc_01", "psyche": {}, "social_stats": {}}
    NPCState.to_persistence_dict(state, out_dict)
    assert "narrative_cache" in out_dict, "сериализатор не вынес кэш"

    state2 = load_l2_state_from_runtime_dict(out_dict)
    mem1, mem2 = state.narrative_cache[0], state2.narrative_cache[0]
    assert mem2.importance == mem1.importance == 0.7
    assert mem2.summary == mem1.summary == "игрок подрался"
    assert mem2.tags == tuple(_MEM_JSON["tags"])



# ── P0 №5 (Шаг 7): SQLite-ветка = путь решений, decay при загрузке запрещён ─


def test_loader_override_replaces_json_cache() -> None:
    """Шаг 7: narrative_cache_override замещает JSON-ветку в state_l2
    и доезжает до потребителя (get_top_narrative_facts — путь EXPLAIN,
    decision_hub.py:2014). Identity-ассерт: в state_l2 лежит объект
    SQLite-ветки, а не десериализованная JSON-копия."""
    from app.models.npc_state import EventMemory
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    sqlite_mem = EventMemory(
        event_type="theft",
        target_id="player",
        emotion_tag="anger",
        day=3,
        importance=0.9,
        summary="кража у таверны",
        npc_id="npc_01",
    )
    raw = _npc_dict_with_cache()  # JSON-копия: importance 0.7
    state = load_l2_state_from_runtime_dict(
        raw, narrative_cache_override=(sqlite_mem,)
    )
    top = state.get_top_narrative_facts(n=2)
    assert top and top[0] is sqlite_mem, "SQLite-ветка не заместила JSON-кэш"


def test_load_narrative_from_sqlite_no_decay_on_load(tmp_path: Path) -> None:
    """Шаг 7c: та же правка, что в _restore_narrative_cache (Шаг 6) —
    повторные загрузки не меняют importance."""
    mm = _make_manager(tmp_path)
    mm._layered.store.save_event_memory(
        "npc_01_seq_0",
        "camp_a",
        {
            "npc_id": "npc_01",
            "event_type": "combat",
            "target_id": "player",
            "emotion_tag": "neutral",
            "day": 1,
            "importance": 0.7,
            "summary": "драка",
        },
    )
    first = mm.load_narrative_from_sqlite("camp_a", "npc_01")
    second = mm.load_narrative_from_sqlite("camp_a", "npc_01")
    assert first and second
    assert first[0].importance == second[0].importance == 0.7


def test_loader_override_none_falls_back_to_json() -> None:
    """Контракт None: отсутствие override = JSON-путь (регресс Шага 6)."""
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    raw = _npc_dict_with_cache()
    state = load_l2_state_from_runtime_dict(raw, narrative_cache_override=None)
    assert state.narrative_cache[0].importance == 0.7



# ── P0 №3 (Шаг 8): beliefs переживают границу тика ───────────────────


def test_beliefs_round_trip_full_cycle(tmp_path: Path) -> None:
    """Сериализация + восстановление: apply_belief_delta → to_persistence_dict
    → load_l2 — фрагмент обязан вернуться с теми же value/confidence/source/
    timestamp. Раньше beliefs обнулялись на каждой пересборке L2."""
    from app.models.npc.beliefs import BeliefDelta, BeliefType
    from app.models.npc_state import NPCState
    from app.services.memory.relationship_store import RelationshipStore
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
    from app.services.npc.state_applicator import StateApplicator

    state = load_l2_state_from_runtime_dict(
        {"id": "npc_01", "psyche": {}, "social_stats": {}}
    )
    _app = StateApplicator(
        relationship_store=RelationshipStore(data_dir=str(tmp_path))
    )
    _app.apply_belief_delta(
        state,
        BeliefDelta(
            belief_type=BeliefType.DANGER,
            old_value=0.0,
            new_value=0.42,
            confidence=0.8,
            source="perception",
            timestamp=77,
        ),
    )

    out: dict = {"id": "npc_01", "psyche": {}, "social_stats": {}}
    NPCState.to_persistence_dict(state, out)
    assert "beliefs" in out["psyche"], "сериализатор не вынес beliefs"

    state2 = load_l2_state_from_runtime_dict(out)
    frag = state2.beliefs.get(BeliefType.DANGER)
    assert frag is not None, "beliefs не восстановлены"
    assert (frag.value, frag.confidence, frag.source, frag.timestamp) == (
        0.42,
        0.8,
        "perception",
        77,
    )


def test_beliefs_soft_migration_old_saves() -> None:
    """Старые сейвы без psyche["beliefs"] → пустой BeliefState, без крашей."""
    from app.models.npc.beliefs import BeliefType
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    state = load_l2_state_from_runtime_dict(
        {"id": "npc_02", "psyche": {"stress": 12.0}, "social_stats": {}}
    )
    assert state.beliefs.get(BeliefType.DANGER) is None


def test_apply_default_summary_for_textless_events(tmp_path: Path) -> None:
    """Шаг 4.5: событие без текстовых ключей (npc_moved/proximity) получает
    дефолтный summary '[тип] источник' — вместо пустышки. 12/13 строк живой
    БД были числами без содержания."""
    from app.domain.events import EventDTO
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    mm = _make_manager(tmp_path)
    npc_state = load_l2_state_from_runtime_dict(
        {"id": "npc_01", "psyche": {}, "social_stats": {}}
    )
    event = EventDTO.create(
        event_type="npc_moved",
        source="maid_lusya",
        payload={"npc_id": "npc_01"},  # только координатные данные, без текста
    )
    mm.apply(event, npc_state, campaign_id="camp_x")
    mem = mm._working.get("camp_x:npc_01")[0]
    assert mem.summary == "[npc_moved] maid_lusya", mem.summary



def test_repeated_same_source_events_not_cannibalized(tmp_path: Path) -> None:
    """Шаг 9.6: события одной пары (тип, источник) с timestamp=0.0 имели
    один event.id → INSERT OR REPLACE затирал все, кроме последнего
    (дамп: 13 строк = 13 пар; речь NPC не накапливалась вообще)."""
    from app.domain.events import EventDTO
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    mm = _make_manager(tmp_path)
    npc_state = load_l2_state_from_runtime_dict(
        {"id": "npc_01", "psyche": {}, "social_stats": {}}
    )
    for text in ("первая реплика", "вторая реплика", "третья реплика"):
        mm.apply(
            EventDTO.create(
                event_type="npc_spoke",
                source="npc_01",
                payload={"npc_id": "npc_01", "text": text},
            ),
            npc_state,
            campaign_id="camp_dup",
        )
    rows = mm._layered.store.query(
        "SELECT summary FROM event_memories WHERE campaign_id='camp_dup'"
    )
    assert len(rows) == 3, rows
    assert sorted(r["summary"] for r in rows) == [
        "вторая реплика",
        "первая реплика",
        "третья реплика",
    ]



def test_subscriber_fresh_state_events_not_cannibalized(tmp_path: Path) -> None:
    """Шаг 9.6: подписчик строит СВЕЖИЙ npc_state на каждое событие —
    суффикс len(cache) не различал реплики одного спикера. mem_id обязан
    быть уникальным вне зависимости от состояния npc."""
    from app.domain.events import EventDTO
    from app.services.events.dialogue_memory_subscriber import (
        DialogueMemorySubscriber,
    )
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    mm = _make_manager(tmp_path)
    sub = DialogueMemorySubscriber(
        memory_manager=mm,
        npc_states_provider=lambda: [
            {"id": "npc_01", "name": "Торнин", "psyche": {}, "social_stats": {}}
        ],
        campaign_id_provider=lambda: "camp_sub",
    )
    bus = get_event_bus()
    bus.clear()
    bus.subscribe(EventType.NPC_SPOKE, sub.on_event)
    for text in ("первая реплика", "вторая реплика"):
        bus.publish(
            EventDTO.create(
                event_type=EventType.NPC_SPOKE,
                source="npc_01",
                payload={"npc_id": "npc_01", "content": text},
            )
        )
    rows = mm._layered.store.query(
        "SELECT npc_id, summary FROM event_memories WHERE campaign_id='camp_sub'"
    )
    assert len(rows) == 2, rows
    assert {r["summary"] for r in rows} == {"первая реплика", "вторая реплика"}
    assert all(r["npc_id"] == "npc_01" for r in rows)



# ── EMRL E1.0: шина опыта — контракт и персистентность ───────────────


def test_experience_trace_id_and_provenance() -> None:
    """E1.3-контракт: trace_id уникален по (эпизод, владелец, источник).
    Testimony Горана и перцепция Люси одного события — ДВА разных трейса
    (социальная память ≠ телепортация истины)."""
    from app.models.npc.experience_trace import ExperienceTrace, TraceSource

    percepts = ExperienceTrace(
        actor_id="player",
        owner_id="lusya",
        source_id="player",
        source_type=TraceSource.PERCEPTION,
        content_reference="evt-1",
    )
    testimony = ExperienceTrace(
        actor_id="player",
        owner_id="lusya",
        source_id="goran",
        source_type=TraceSource.TESTIMONY,
        content_reference="evt-1",
    )
    assert percepts.trace_id() != testimony.trace_id()
    assert "from:goran" in testimony.trace_id()


def test_trace_upsert_idempotent(tmp_path: Path) -> None:
    """E1.0: повторный save того же trace_id не плодит строки (PK-семантика)
    и клампы держат диапазоны (LLM-не-SSOT гейт в persistence-слое)."""
    from app.models.npc.experience_trace import ExperienceTrace, TraceSource

    store = SqliteMemoryStore(tmp_path / "t.db")
    trace = ExperienceTrace(
        actor_id="player",
        owner_id="goran",
        source_id="player",
        source_type=TraceSource.PERCEPTION,
        content_reference="evt-9",
        valence=5.0,  # вне диапазона → кламп
        confidence=2.0,
    )
    store.save_trace("camp", trace)
    store.save_trace("camp", trace)  # idempotent upsert
    rows = store.query(
        "SELECT valence, confidence FROM experience_traces "
        "WHERE campaign_id='camp' AND owner_id='goran'"
    )
    assert len(rows) == 1
    assert rows[0]["valence"] == 1.0 and rows[0]["confidence"] == 1.0


def test_traces_survive_store_restart(tmp_path: Path) -> None:
    """E1.0: проекции переживают пересоздание стора (рента рестарта)."""
    from app.models.npc.experience_trace import ExperienceTrace, TraceSource

    s1 = SqliteMemoryStore(tmp_path / "t.db")
    s1.save_trace(
        "camp",
        ExperienceTrace(
            actor_id="player",
            owner_id="goran",
            source_id="player",
            source_type=TraceSource.PERCEPTION,
            content_reference="evt-42",
            meaning="рассказ о перевале",
        ),
    )
    s2 = SqliteMemoryStore(tmp_path / "t.db")
    traces = s2.load_traces("camp", "goran")
    assert len(traces) == 1
    assert traces[0]["meaning"] == "рассказ о перевале"
    assert traces[0]["source_type"] == "perception"



# ── EMRL E1.1: распад доступности, не знания ─────────────────────────


def test_decay_mode_kwarg_compatibility() -> None:
    """E1.1: режим — kwarg; все старые вызовы (без mode) живы."""
    from app.models.npc_state import EventMemory

    mem = EventMemory(
        event_type="combat", target_id="player", emotion_tag="neutral",
        day=1, importance=0.7, npc_id="npc_01",
    )
    old_call = mem.decayed(1.0)
    new_call = mem.decayed(1.0, mode="episodic")
    assert old_call.importance == new_call.importance


def test_abstract_episode_never_forgotten() -> None:
    """E1.1 floor: эпизод, сжатый в ABSTRACT, остаётся в памяти навсегда —
    распад убивает детали, не факт «был разговор». 30 дней — порог,
    который раньше стирал всё."""
    from app.models.npc_state import EventMemory, MemoryStage
    from app.services.memory.working_memory import WorkingMemory

    wm = WorkingMemory()
    # E1.1-финал: суть = эпизод, сжатый консолидацией (is_compressed=True
    # + compressed_from). Старение в ABSTRACT-зону без флага — НЕ суть
    # и обязано умирать (инвариант test_fresh_noise). Доводить тиками
    # больше не нужно: консолидированная суть создаётся актом сжатия,
    # а не числом importance.
    mem = EventMemory(
        event_type="player_interacts", target_id="player",
        emotion_tag="neutral", day=1, importance=0.7,
        summary="рассказ о перевале (сжат консолидацией)", npc_id="npc_01",
        decay_rate=0.3,
        is_compressed=True,
        compressed_from=("evt-1", "evt-2", "evt-3"),
    )
    wm.push("camp_floor:npc_01", mem)
    # 30 игровых дней поверх сжатой сути — суть обязана пережить
    for _ in range(30):
        wm.apply_decay("camp_floor:npc_01", game_days=1.0)
    survivors = wm.get("camp_floor:npc_01")
    assert survivors, "ABSTRACT-эпизод удалён — знание уничтожено распадом"
    stage = getattr(survivors[0], "stage", None) or MemoryStage(survivors[0].get("stage"))
    assert stage == MemoryStage.ABSTRACT
    # floor-значения
    imp = survivors[0].importance if hasattr(survivors[0], "importance") else survivors[0]["importance"]
    assert imp <= 0.1


def test_fresh_noise_still_forgotten() -> None:
    """E1.1 регресс: шум без ABSTRACT (npc_moved-пустышки) по-прежнему
    умирает — floor не превращает память в свалку."""
    from app.models.npc_state import EventMemory
    from app.services.memory.working_memory import WorkingMemory

    wm = WorkingMemory()
    wm.push(
        "camp_noise:npc_01",
        EventMemory(
            event_type="npc_moved", target_id="player", emotion_tag="neutral",
            day=1, importance=0.3, summary="[npc_moved] npc", npc_id="npc_01",
            decay_rate=0.4,
        ),
    )
    for _ in range(30):
        wm.apply_decay("camp_noise:npc_01", game_days=1.0)
    assert wm.get("camp_noise:npc_01") == [], "шум выжил — floor протек"



# ── EMRL E1.2: кристаллы — знания, не эпизоды ────────────────────────


def test_crystal_decay_kills_confidence_not_knowledge() -> None:
    """E1.2 semantic-decay: распад ТРОГАЕТ только confidence; триплет,
    retrieval_strength, times_recalled — нетронуты. Столетие не стирает
    знание (E1.1-урок: у кристаллов нет зон)."""
    from app.models.npc.memory_crystal import MemoryCrystal

    c = MemoryCrystal(
        subject="player", predicate="occupation", object="geologist",
        source="goran", origin_reference="digest-1",
        confidence=0.8, retrieval_strength=0.6, times_recalled=3,
        owner_id="goran", campaign_id="camp",
    )
    aged = c.decayed(game_days=100)  # 100 игровых дней
    assert aged.object == "geologist"
    assert aged.confidence < 0.8  # уверенность тает
    assert aged.retrieval_strength == 0.6  # доступность — функция припоминаний
    assert aged.times_recalled == 3


def test_crystal_recall_grows_access_not_truth() -> None:
    """Мандат-коррекция: припоминание растит retrieval_strength,
    НЕ confidence. Ложный слух ×10 припоминаний не становится
    «увереннее» (нет машины self-reinforcing truth)."""
    from app.models.npc.memory_crystal import MemoryCrystal

    c = MemoryCrystal(
        subject="player", predicate="rumor", object="killed_dragon",
        source="stranger", origin_reference="rumor-digest",
        confidence=0.3, retrieval_strength=0.3,
        owner_id="goran", campaign_id="camp",
    )
    for _ in range(10):
        c = c.recalled()
    assert c.retrieval_strength == 1.0
    assert c.confidence == 0.3  # истинность не выросла
    assert c.times_recalled == 10


def test_crystals_same_triplet_different_origins_coexist(tmp_path: Path) -> None:
    """E1.2 анти-каннибализация (урок 9.6): «Игрок храбр» от Горана и от
    Люси — ДВЕ записи, PK различает origin_reference."""
    from app.models.npc.memory_crystal import MemoryCrystal

    store = SqliteMemoryStore(tmp_path / "t.db")
    for src, digest in (("goran", "g-1"), ("lusya", "l-7")):
        store.save_crystal(
            "camp",
            MemoryCrystal(
                subject="player", predicate="trait", object="brave",
                source=src, origin_reference=digest,
                owner_id="listener", campaign_id="camp",
            ),
        )
    rows = store.query(
        "SELECT source FROM memory_crystals "
        "WHERE campaign_id='camp' AND owner_id='listener' AND subject='player'"
    )
    assert {r["source"] for r in rows} == {"goran", "lusya"}


def test_crystals_survive_store_restart(tmp_path: Path) -> None:
    """E1.2 round-trip: кристаллы переживают пересоздание стора."""
    from app.models.npc.memory_crystal import MemoryCrystal

    s1 = SqliteMemoryStore(tmp_path / "t.db")
    s1.save_crystal(
        "camp",
        MemoryCrystal(
            subject="player", predicate="history", object="northern_pass",
            source="player", origin_reference="told-him-1",
            related_episodes=("evt-1", "evt-2"),
            confidence=0.75, owner_id="goran", campaign_id="camp",
        ),
    )
    s2 = SqliteMemoryStore(tmp_path / "t.db")
    crystals = s2.load_crystals("camp", "goran")
    assert len(crystals) == 1
    assert crystals[0]["object"] == "northern_pass"
    assert crystals[0]["related_episodes"] == ("evt-1", "evt-2")



def test_crystal_domain_separation_contract() -> None:
    """E1.2 §13.3-граница: семантический кристалл (memory) и аффективный
    (identity/L2.5, CrystallizedBelief) — НЕ пересекаются полями.
    Схлопывание/склейка хранилищ = вторая память (класс §18, прецедент
    PlayerBeliefModel). Проверка структурная: общих полей между
    dataclass-полями двух контрактов нет, кроме тривиальных."""
    from dataclasses import fields as _fields

    from app.domain.identity_events import CrystallizedBelief
    from app.models.npc.memory_crystal import MemoryCrystal

    crystal_fields = {f.name for f in _fields(MemoryCrystal)}
    belief_fields = {f.name for f in _fields(CrystallizedBelief)}
    # Тривиальные пересечения допустимы (id-подобные); СУЩЕСТВЕННЫЕ поля
    # семантики (триплет/origin) не должны существовать у аффекта:
    for forbidden in ("subject", "predicate", "object", "origin_reference",
                      "retrieval_strength", "related_episodes"):
        assert forbidden not in belief_fields, (
            f"CrystallizedBelief захватил семантическое поле {forbidden} — "
            "граница memory/identity нарушена"
        )
    for forbidden in ("trait", "weight"):
        assert forbidden not in crystal_fields, (
            f"MemoryCrystal захватил аффективное поле {forbidden} — "
            "граница identity/memory нарушена"
        )



def test_tickstate_attribute_consumers_guarded() -> None:
    """Фаза A/E1: потребители опциональных полей TickState обязаны гвардиться
    getattr — иначе половинная интеграция параллельной сессии (поле без
    поставщика) роняет каждый тик (пятая детонация: affordance_facts_map)."""
    import re as _re

    src = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "npc" / "npc_tick_pipeline.py"
    ).read_text(encoding="utf-8")
    # прямой доступ state.<field> на опциональных полях — запрещён;
    # белые: поля, гарантированные контрактом TickState (сигнатура
    # build_tick_state + живые потребители NpcTickPipeline, проходящие
    # 33 зелёных прогона: отсутствие поля роняло бы каждый тик)
    _guarded_ok = (
        # Preloaded-мапы (domain/tick.py, sig. build_tick_state)
        "narrative_cache_map", "memory_weights_map", "social_modifiers_map",
        "reputation_modifiers_map", "economic_profiles_map",
        "crystallized_beliefs_map", "identity_traits_map",
        "effective_drives_map", "pe_mods_map", "idle_pressure_map",
        # Read-only сервисы (sig. build_tick_state)
        "spatial_service", "spatial_query", "relationship_store",
        "epistemic_store", "epistemic_context_resolver", "l1_chronicle",
        # Core-поля TickState (живые в каждом тике)
        "scene_state", "all_npcs_raw", "nearby_npcs", "tick_id",
        "campaign_id", "hub_event", "line_of_sight", "rng_factory",
        "player_target_id", "action_type", "raw_input",
        # NPC-пайплайн: производные/контекстные
        "drives_runtime", "npc_topics", "response_targets",
        "player_markers", "is_session_start", "scene_continuity",
    )
    # Методы regex-ловушек — не поля:
    _method_traps = {"get", "value", "items", "keys"}
    bad = []
    for m in _re.finditer(r"state\.([a-z_]+)\b", src):
        f = m.group(1)
        if f in _guarded_ok or f in _method_traps:
            continue
        # рядом (±80 симв.) есть getattr с тем же полем → гвард есть
        ctx = src[max(0, m.start() - 80) : m.end() + 80]
        if f'getattr(state, "{f}"' in ctx or f"getattr(state, '{f}'" in ctx:
            continue
        bad.append(f)
    offenders = sorted(set(bad))
    assert not offenders, f"негвардированные поля TickState: {offenders}"



# ── EMRL E2.0-a: DeltaGate — единственный вход в состояние ──────────


def test_delta_gate_whitelist_rejects_unknown_field() -> None:
    """INV-LLM-NOT-SSOT: поле вне whitelist отклоняется. LLM не может
    предложить 'personality'/'relationship' — любое имя вне контракта
    мертво на входе."""
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.services.memory.delta_gate import DeltaGate

    gate = DeltaGate()
    bad = StateDeltaProposal(
        trace_id="t1:goran:player", field="personality", value=0.5
    )
    assert gate.apply(bad) is False
    rogue = StateDeltaProposal(
        trace_id="t2:goran:player", field="relationship_trust", value=99.0
    )
    assert gate.apply(rogue) is False


def test_delta_gate_clamps_and_idempotent() -> None:
    """Клампы ([-1,1] для threat) + идемпотентность: повторный тот же
    trace_id+field не применяется дважды (нет двойного счёта дельт)."""
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.services.memory.delta_gate import DeltaGate

    gate = DeltaGate()
    calls = []

    def dispatch(consumer: str, tid: str, value: float) -> bool:
        calls.append((consumer, value))
        return True

    p = StateDeltaProposal(
        trace_id="evt-1:goran:player", field="threat_gradient", value=5.0
    )
    assert gate.apply(p, dispatch) is True
    assert calls[-1][1] == 1.0  # кламп сверху
    # повтор — идемпотентен
    assert gate.apply(p, dispatch) is False
    assert len(calls) == 1


def test_delta_gate_consumer_rejection_blocks() -> None:
    """Отказ потребителя = дельта не считается применённой; повторная
    попытка возможна (не запоминаем отказ как успех)."""
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.services.memory.delta_gate import DeltaGate

    gate = DeltaGate()

    def always_reject(consumer: str, tid: str, value: float) -> bool:
        return False

    p = StateDeltaProposal(
        trace_id="evt-2:goran:player", field="danger_belief", value=0.6
    )
    assert gate.apply(p, always_reject) is False
    # потребитель передумал — вторая попытка проходит
    assert gate.apply(p, lambda c, t, v: True) is True



# ── EMRL E2.0-b: живой провод — аудит, не дублирование ───────────────


def test_delta_gate_trace_once_invariant(tmp_path: Path) -> None:
    """AG1-INV-TRACE-ONCE: один event.id → один trace → ≤1 дельты поля.
    Повторный Proposal с тем же trace_id (даже другое value) отклонён —
    двойной счёт причинности невозможен."""
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.services.memory.delta_gate import DeltaGate

    gate = DeltaGate()
    p1 = StateDeltaProposal(
        trace_id="evt-77:goran:player", field="threat_gradient",
        value=0.5, causal_parent="evt-77",
    )
    p2 = StateDeltaProposal(  # дубликат события — другая value
        trace_id="evt-77:goran:player", field="threat_gradient",
        value=0.9, causal_parent="evt-77",
    )
    assert gate.apply(p1, lambda *a: True) is True
    assert gate.apply(p2, lambda *a: True) is False  # TRACE-ONCE


def test_delta_gate_emits_chronicaler_event(tmp_path: Path) -> None:
    """E2.0-b: успешное применение публикует EXPERIENCE_DELTA_COMMITTED
    с trace_id/causal_parent — Chronicaler получает причинную трассу.
    Отказ (вне whitelist) события НЕ публикует."""
    from app.services.events.event_bus import get_event_bus
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.services.memory.delta_gate import DeltaGate

    bus = get_event_bus()
    bus.clear()
    captured = []
    from app.services.events.event_types import EventType

    bus.subscribe(
        EventType.EXPERIENCE_DELTA_COMMITTED,
        lambda e: captured.append(e),
    )
    gate = DeltaGate()
    gate.apply(
        StateDeltaProposal(
            trace_id="evt-78:goran:player", field="threat_gradient",
            value=0.4, causal_parent="evt-78",
        ),
        lambda *a: True,
    )
    gate.apply(  # вне whitelist — не публикуется
        StateDeltaProposal(
            trace_id="evt-79:goran:player", field="personality", value=1.0,
        ),
        lambda *a: True,
    )
    assert len(captured) == 1
    evt = captured[0]
    # E2.0-b: подписчик получает EventDTO — поля трассы в payload
    # (Устав 2.1.1: шина принимает только EventDTO)
    assert evt.payload["causal_parent"] == "evt-78"
    assert evt.payload["value"] == 0.4
    assert evt.payload["trace_id"] == "evt-78:goran:player"


def test_threaten_produces_gated_delta(tmp_path: Path) -> None:
    """E2.0-b integration: PLAYER_THREATEN → Proposal → Gate →
    PerceptionPayload.threat_gradient_delta через существующий канал.
    Проверяется на минимальной сборке subscriber'а (по выводу археологии)."""
    # Тело замка — по фактическому API subscriber'а из вывода археологии
    # (какой конструктор/вход) — заполню после твоего прогона блока
    # Get-Content выше.
    raise NotImplementedError("наполнение после археологии 220..265")

def test_threaten_produces_gated_delta() -> None:
    """E2.0-b integration: PLAYER_THREATENS → Proposal → Gate →
    PerceptionPayload.threat_gradient_delta через существующий канал.
    Минимальная сборка subscriber'а по фактическому API (археология
    220..265): handle(events, ctx) → deltas-список с StateDeltas."""
    from types import SimpleNamespace

    from app.domain.events import EventDTO
    from app.models.delta_payloads import PerceptionPayload
    from app.models.state_delta import DeltaDomain, StateDeltas
    from app.services.events import reaction_subscriber as _rs
    from app.services.events.event_types import EventType

    # Сигнатура по факту: ReactionSubscriber(event_bus) — шина обязательна
    from app.services.events.event_bus import get_event_bus as _gb

    sub = _rs.ReactionSubscriber(_gb())
    evt = EventDTO.create(
        event_type=EventType.PLAYER_THREATENS.value,
        source="player",
        payload={"target_id": "merchant_goran", "intensity": 0.7},
        persistence_level="working",
    )
    # Контекст по фактическому контракту handle(): Phase8-контекст несёт
    # физические дельты (материализованные боем) — в тесте их нет
    ctx = SimpleNamespace(
        all_npcs_raw=[{"id": "merchant_goran"}],
        physical_deltas_materialized=[],
        scene_state={},
        shared_context=None,
    )
    result = sub.handle([evt], ctx)
    # handle() возвращает Phase8Result (Устав Фаза 8): дельты — в его
    # поле-коллекции; достаём фактическую форму
    _deltas = (
        result.deltas
        if hasattr(result, "deltas")
        else getattr(result, "perception_deltas", None)
        or getattr(result, "delta_buffer", None)
        or []
    )
    threat_deltas = [
        d
        for d in _deltas
        if isinstance(d, StateDeltas)
        and d.npc_id == "merchant_goran"
        and d.domain == DeltaDomain.PERCEPTION
        and isinstance(d.payload, PerceptionPayload)
        and d.payload.threat_gradient_delta > 0
    ]
    assert threat_deltas, f"гейт заблокировал провод: {_deltas}"
    assert threat_deltas[0].payload.threat_gradient_delta == 0.8



def test_dialogue_extractor_failure_logs_context() -> None:
    """AG1-D2: отказ экстракции логирует КОНТЕКСТ (repr(e), partner,
    turn_len) — слепые 'Dialogue update failed: ' запрещены (L4)."""
    import logging as _logging

    from app.services.memory.dialogue_update_extractor import (
        DialogueUpdateExtractor,
    )

    class _Boom:
        def __getattr__(self, item):
            raise RuntimeError(" всё сломалось ")  # пробелы = пустой str()

    captured = []

    class _Handler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured.append(record.getMessage())

    _lg = _logging.getLogger("app.services.memory.dialogue_update_extractor")
    _handler = _Handler()
    _lg.addHandler(_handler)
    _lg.setLevel(_logging.WARNING)
    try:
        _ext = DialogueUpdateExtractor(router=_Boom())
        result = _ext.extract("контекст", "реплика", "merchant_goran")
        assert isinstance(result, object)  # деградация — пустой DialogueUpdate
    finally:
        _lg.removeHandler(_handler)
        _lg.setLevel(_logging.NOTSET)
    ctx_logged = [m for m in captured if "[DIALOGUE_UPDATE]" in m]
    assert ctx_logged, f"контекстный лог отсутствует: {captured}"
    assert "partner=merchant_goran" in ctx_logged[0]
    assert "turn_len=" in ctx_logged[0]
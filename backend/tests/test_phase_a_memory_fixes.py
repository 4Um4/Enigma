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
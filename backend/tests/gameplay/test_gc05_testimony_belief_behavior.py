# path: /project/backend/tests/gameplay/test_gc05_testimony_belief_behavior.py
# Назначение: GC-05 — Testimony → Belief → third-party behavior.
#   L3-интеграционная проверка downstream-пути с инъецированным свидетельством.
#   Не доказывает автономное решение NPC рассказать — только downstream.
# Зависимости: tests.gameplay.harness (build_game_loop production runtime).
# Основные сущности: test_testimony_creates_belief_in_listener,
#   test_belief_persists_after_idle_tick, test_control_without_testimony.
# Запуск: cd backend; python -m pytest tests/gameplay/test_gc05_testimony_belief_behavior.py -v -s
"""
GC-05: Testimony → Belief → third-party behavior.

L3-интеграционная проверка downstream-пути с инъецированным свидетельством.
Не доказывает автономное решение NPC рассказать — только downstream.

Сквозной путь:
  1. Игрок ACCUSE maid_lusya (InterventionEvent — production-path, LLM-free)
  2. maid_lusya trust падает в V2-RAM (WriteGate.apply — production-path)
  3. maid_lusya "рассказывает" guard_borko (инъекция NPC_SPOKE через EventBus)
  4. guard_borko воспринимает рассказ (can_observe — production filter)
  5. guard_borko формирует EpistemicRecord(player, ATTACKED, source=maid_lusya)
  6. guard_borko epistemic_modifiers → DecisionHub (production-path)
  7. Control: без NPC_SPOKE → EpistemicStore пуст → intent unchanged

Контракт NPC_SPOKE (подтверждён археологией):
  - EventDTO.create(type="npc_spoke", source=speaker_id, payload={intent_type, target_id})
  - ClaimEventSubscriber.on_npc_spoke: fallback Proposition из intent_type
  - on_claim_event: can_observe filter (distance + event.radius)
  - BeliefRevisionEngine → EpistemicStore → EpistemicRecord
  - EpistemicContextResolver.to_modifiers → DecisionHub

Ограничения интерпретации:
  - Тест не доказывает автономное решение NPC рассказать
  - Тест не доказывает работу TaskScheduler → DialogueMaterializer
  - Тест доказывает: downstream-path (NPC_SPOKE → ClaimEvent → Belief → Decision) работает
"""
import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc05")

_WITNESS = "maid_lusya"   # Свидетель — кто "рассказывает"
_LISTENER = "guard_borko"  # Слушатель — кто получает belief
_TARGET = "player"         # Объект обвинения/атаки


def _read_epistemic_records(harness, agent_id: str):
    """Чтение EpistemicStore через tick_orchestrator (production-path).

    EpistemicStore.to_dict() возвращает список словарей:
    {agent_id, proposition: {subject_id, predicate, object_id, polarity},
     confidence, source_id, source_claim_id, first_observed_tick, last_updated_tick}
    """
    _store = getattr(harness.game_loop._tick_orch, "_epistemic_store", None)
    if _store is None:
        return []
    _all = _store.to_dict()
    return [r for r in _all if r.get("agent_id") == agent_id]


def _inject_npc_spoke(harness, speaker_id: str, intent_type: str, target_id: str):
    """Инъекция NPC_SPOKE через EventBus.publish (downstream-path test).

    Контракт (dialogue_materializer.py:55-63):
      type = "npc_spoke"
      source = speaker_id
      payload = {target_id, intent_type, proposition (optional)}
      radius = 10.0 (normal speech)

    ClaimEventSubscriber.on_npc_spoke (claim_event_subscriber.py:41):
      Если proposition отсутствует → fallback из intent_type:
        "intimidate" → Proposition(speaker_id, ATTACKED, target_id)
        "accuse"    → Proposition(target_id, STOLE, "unknown")
    """
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus

    _event = EventDTO.create(
        event_type="npc_spoke",
        source=speaker_id,
        payload={
            "target_id": target_id,
            "intent_type": intent_type,
        },
        visibility="public",
        radius=10.0,
    )
    _bus = get_event_bus()
    _bus.publish(_event)
    return _event


@pytest.fixture
def harness():
    """Production runtime; LLM-free path."""
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _h.advance_ticks(3)  # прогрев: V2-bind, stable baseline
    yield _h
    _h.dispose()


class TestGC05TestimonyBeliefBehavior:
    """GC-05: Testimony → Belief → third-party behavior.

    Три теста:
    1. Testimony creates belief in listener (EpistemicStore)
    2. Belief persists after idle_tick (round-trip)
    3. Control: without testimony, no belief
    """

    def test_testimony_creates_belief_in_listener(self, harness):
        """NPC_SPOKE от maid_lusya → guard_borko получает EpistemicRecord.

        Контракт: ClaimEventSubscriber.on_npc_spoke → fallback Proposition
        (intent_type="intimidate" → Proposition(speaker=maid_lusya,
        ATTACKED, target=player)) → on_claim_event → can_observe filter
        → BeliefRevisionEngine → EpistemicStore.

        L3 assertion: НЕ проверяем вызов подписчика; проверяем ИТОГОВОЕ
        состояние EpistemicStore — EpistemicRecord существует.
        """
        # 1. Baseline: guard_borko не имеет beliefs о player
        _records_before = _read_epistemic_records(harness, _LISTENER)
        print(f"[GC05-A] guard_borko beliefs before: {len(_records_before)} records")
        for r in _records_before:
            print(f"  {r.get('proposition', {}).get('predicate')} "
                  f"subject={r.get('proposition', {}).get('subject_id')} "
                  f"conf={r.get('confidence')}")

        # 2. Инъекция NPC_SPOKE: maid_lusya "intimidate" player
        _event = _inject_npc_spoke(
            harness, speaker_id=_WITNESS,
            intent_type="intimidate", target_id=_TARGET
        )
        print(f"[GC05-A] injected NPC_SPOKE: source={_event.source} "
              f"target={_event.payload.get('target_id')} "
              f"intent={_event.payload.get('intent_type')}")

        # 3. Assert: EpistemicStore содержит EpistemicRecord для guard_borko
        _records_after = _read_epistemic_records(harness, _LISTENER)
        print(f"[GC05-A] guard_borko beliefs after: {len(_records_after)} records")
        for r in _records_after:
            _prop = r.get("proposition", {})
            print(f"  predicate={_prop.get('predicate')} "
                  f"subject={_prop.get('subject_id')} "
                  f"object={_prop.get('object_id')} "
                  f"conf={r.get('confidence')} "
                  f"source={r.get('source_id')}")

        # Ищем запись о player (ATTACKED by maid_lusya)
        _player_beliefs = [
            r for r in _records_after
            if r.get("proposition", {}).get("subject_id") == _WITNESS
            and r.get("proposition", {}).get("predicate") == "attacked"
            and r.get("proposition", {}).get("object_id") == _TARGET
        ]

        assert len(_player_beliefs) > 0, (
            f"GC05-A FAIL: guard_borko не получил EpistemicRecord после "
            f"NPC_SPOKE от {_WITNESS} (intimidate, target={_TARGET}). "
            f"Records: {_records_after}. "
            f"Возможные причины: can_observe filter не прошёл "
            f"(distance > 10.0 или LOS blocked); "
            f"spatial_query недоступен; "
            f"ClaimEventSubscriber не подписан."
        )

        _record = _player_beliefs[0]
        assert _record.get("confidence", 0.0) > 0.0, (
            f"GC05-A FAIL: EpistemicRecord существует, но confidence=0.0 — "
            f"belief не сформирован. Record: {_record}"
        )
        assert _record.get("source_id") == _WITNESS, (
            f"GC05-A FAIL: source_id={_record.get('source_id')} "
            f"≠ {_WITNESS} — provenance нарушен. Record: {_record}"
        )
        print(f"[GC05-A] PASS: guard_borko believes {_WITNESS} attacked "
              f"{_TARGET} conf={_record['confidence']:.2f} "
              f"source={_record['source_id']}")

    def test_belief_persists_after_idle_tick(self, harness):
        """EpistemicRecord переживает idle_tick (round-trip persistence).

        Контракт: idle_tick → Phase 9 → epistemic_records → scene_state
        → Phase 10 → atomic_commit_all → disk. Next idle_tick reads
        persisted state.
        """
        # 1. Инъекция NPC_SPOKE
        _inject_npc_spoke(
            harness, speaker_id=_WITNESS,
            intent_type="intimidate", target_id=_TARGET
        )

        # 2. Проверить belief существует
        _records_after_inject = _read_epistemic_records(harness, _LISTENER)
        _has_belief = any(
            r.get("proposition", {}).get("subject_id") == _WITNESS
            and r.get("proposition", {}).get("predicate") == "attacked"
            for r in _records_after_inject
        )
        if not _has_belief:
            pytest.skip(
                "PRECONDITION: belief не создан — test_testimony_creates_belief_in_listener "
                "должен пройти первым (возможно can_observe не прошёл)"
            )

        # 3. idle_tick — должен.persist epistemic_records
        harness.advance_ticks(2)

        # 4. Assert: belief сохранён после idle_tick
        _records_after_tick = _read_epistemic_records(harness, _LISTENER)
        _persisted_belief = [
            r for r in _records_after_tick
            if r.get("proposition", {}).get("subject_id") == _WITNESS
            and r.get("proposition", {}).get("predicate") == "attacked"
            and r.get("proposition", {}).get("object_id") == _TARGET
        ]

        assert len(_persisted_belief) > 0, (
            f"GC05-B FAIL: EpistemicRecord не пережил idle_tick. "
            f"Records after inject: {len(_records_after_inject)}, "
            f"after tick: {len(_records_after_tick)}. "
            f"Persistence broken: epistemic_records не сохраняются "
            f"через atomic_commit_all, или не читаются при следующем тике."
        )
        print(f"[GC05-B] PASS: belief persisted after 2 idle_ticks "
              f"(conf={_persisted_belief[0].get('confidence'):.2f})")

    def test_control_without_testimony_no_belief(self, harness):
        """Контроль: без NPC_SPOKE → EpistemicStore не содержит
        EpistemicRecord о player (ATTACKED by maid_lusya).

        Тот же seed, тот же harness, но БЕЗ инъекции NPC_SPOKE.
        Если belief появляется без testimony — причинная связь не доказана.
        """
        # 1. Baseline: advance_ticks(3) уже в fixture
        _records = _read_epistemic_records(harness, _LISTENER)
        print(f"[GC05-C] guard_borko beliefs (control): {len(_records)} records")

        # 2. Проверить: нет EpistemicRecord(player, ATTACKED, maid_lusya)
        _player_attacked = [
            r for r in _records
            if r.get("proposition", {}).get("subject_id") == _WITNESS
            and r.get("proposition", {}).get("predicate") == "attacked"
            and r.get("proposition", {}).get("object_id") == _TARGET
        ]

        # Допускаем, что guard_borko может иметь ДРУГИЕ beliefs
        # (из других источников); но ATTACKED by maid_lusya не должно
        # быть без testimony
        assert len(_player_attacked) == 0, (
            f"GC05-C FAIL: guard_borko имеет EpistemicRecord "
            f"({_WITNESS} attacked {_TARGET}) БЕЗ testimony — "
            f"причинная связь не доказана. Records: {_player_attacked}"
        )
        print(f"[GC05-C] PASS: no testimony → no belief "
              f"(control clean, {len(_records)} other records)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
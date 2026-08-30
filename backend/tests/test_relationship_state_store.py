"""
path: /project/backend/tests/test_relationship_state_store.py
Назначение: Приёмочная сьюта фазы B / M1a (ТЗ-RE-01 v1.9 §10-B; ADR-O-370):
    (1) save/load round-trip бит-в-бит через реальную структуру scene_state
        (Устав §12.3-12.4: объекты создаются from_dict/фабриками, не конструкторами
        мечты); (2) single-writer: позитив (легальный вызывающий StateApplicator) +
        негатив (чужой модуль → ArchitecturalViolationError ДО мутации); (3)
        инварианты диапазонов [0,1], порядок Ф2 (target < deficit), закрытый реестр
        need_id (attachment отклонён); (4) старый сейв (ключ отсутствует →
        легитимные дефолты, scene_state не мутирован чтением); (5) clamp-границы;
    (6) read-контракт Мастера: frozen DTO, отсутствие alias-мутации; повреждённая
        структура → громкий ContractValidationError.
Зависимости: pytest, app.domain.relationship_contracts, app.services.*
Основные сущности: TestNeedContracts, TestStoreReadContract, TestStoreWriteContract,
    TestRoundTrip, TestOldSaveCompatibility.
"""

import copy
import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
from app.domain.relationship_contracts import (
    NEED_ID_INTIMACY,
    NEED_ID_SEXUAL,
    RE_NEED_SLOTS,
    ContractValidationError,
    ExclusivityRequirement,
    HardConstraint,
    NeedLevel,
    NeedSlot,
    PreferenceModel,
    exclusivity_requirement_from_dict,
    exclusivity_requirement_to_dict,
    hard_constraint_from_dict,
    hard_constraint_to_dict,
    need_level_from_dict,
    need_level_to_dict,
    preference_from_dict,
    preference_to_dict,
)
from app.errors import ArchitecturalViolationError
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.state_applicator import StateApplicator
from app.services.social.relationship_state_store import RelationshipStateStore

# ── Фикстуры реальности (§12.4: from_legacy/from_dict, не конструкторы) ──

NPC_ID = "maid_lusya"


@pytest.fixture()
def scene_state() -> Dict[str, Any]:
    """scene_state реальной структуры (прецедент SSM init-блока, ADR-O-370)."""
    return {
        "tick": 0,
        "game_time_seconds": 43200.0,
        "active_traversals": {},
        "active_commitments": {},
        "commitment_history": {},
        "commitment_ordinals": {},
        "relationship_state": {},
    }


@pytest.fixture()
def applicator() -> StateApplicator:
    return StateApplicator(
        relationship_store=RelationshipStore(data_dir=tempfile.mkdtemp())
    )


# ── 1. Контракты домена: валидация и инварианты ──


class TestNeedContracts:
    def test_registry_closed_attachment_absent(self):
        assert set(RE_NEED_SLOTS) == {NEED_ID_SEXUAL, NEED_ID_INTIMACY}

    @pytest.mark.parametrize("bad_value", [float("nan"), -0.1, 1.5])
    def test_need_level_rejects_out_of_range(self, bad_value):
        with pytest.raises(ContractValidationError):
            NeedLevel(need_id=NEED_ID_SEXUAL, current_intensity=bad_value)

    def test_need_level_rejects_unknown_need(self):
        with pytest.raises(ContractValidationError):
            NeedLevel(need_id="attachment", current_intensity=0.1)

    def test_need_slot_rejects_f2_violation(self):
        with pytest.raises(ContractValidationError):
            NeedSlot(need_id=NEED_ID_INTIMACY, target_pressure=0.9, deficit_threshold=0.3)

    @pytest.mark.parametrize("f", [float("nan"), -1.5, 2.0])
    def test_preference_rejects_bad_strength(self, f):
        with pytest.raises(ContractValidationError):
            PreferenceModel(pref_id="scenario_x", strength=f)

    def test_exclusivity_rejects_unknown_scope(self):
        with pytest.raises(ContractValidationError):
            ExclusivityRequirement(scope="total")

    def test_hard_constraint_rejects_bad_necessity(self):
        with pytest.raises(ContractValidationError):
            HardConstraint(constraint_id="honesty", necessity=1.5)

    def test_need_level_is_frozen(self):
        lvl = NeedLevel(need_id=NEED_ID_SEXUAL)
        with pytest.raises(dataclasses.FrozenInstanceError):
            lvl.current_intensity = 0.5  # type: ignore[misc]


# ── 2. Read-контракт стора (вердикт Мастера п.4) ──


class TestStoreReadContract:
    def test_defaults_without_mutation(self, scene_state):
        levels = RelationshipStateStore.get_need_levels(scene_state, NPC_ID)
        assert set(levels) == {NEED_ID_SEXUAL, NEED_ID_INTIMACY}
        assert all(v == NeedLevel(need_id=k) for k, v in levels.items())
        assert scene_state["relationship_state"] == {}  # чтение НЕ мутировало

    def test_read_returns_frozen_dto(self, scene_state):
        levels = RelationshipStateStore.get_need_levels(scene_state, NPC_ID)
        with pytest.raises(dataclasses.FrozenInstanceError):
            levels[NEED_ID_SEXUAL].current_intensity = 0.9  # type: ignore[misc]

    def test_old_save_without_key(self):
        ss: Dict[str, Any] = {"tick": 7}  # старый сейв без relationship_state
        levels = RelationshipStateStore.get_need_levels(ss, NPC_ID)
        assert levels[NEED_ID_SEXUAL].current_intensity == 0.0
        assert "relationship_state" not in ss  # чтение не создаёт ключ

    def test_corrupted_structure_fails_loud(self):
        ss: Dict[str, Any] = {"relationship_state": "corrupted"}
        with pytest.raises(ContractValidationError):
            RelationshipStateStore.get_need_levels(ss, NPC_ID)

    def test_exclusivity_default_none_is_directed(self, scene_state):
        req = RelationshipStateStore.get_exclusivity(scene_state, NPC_ID, "player")
        assert req.scope == "none"  # направленная норма A→B (вердикт №3)


# ── 3. Write-контракт: single-writer (позитив через легального вызывающего) ──


class TestStoreWriteContract:
    def test_legal_writer_passes_and_persists(self, applicator, scene_state):
        lvl = applicator.update_needs(scene_state, NPC_ID, NEED_ID_SEXUAL, pressure_delta=0.3)
        assert lvl.current_intensity == pytest.approx(0.3)
        stored = scene_state["relationship_state"]["needs"][NPC_ID][NEED_ID_SEXUAL]
        assert stored["current_intensity"] == pytest.approx(0.3)

    def test_accumulation_and_clamp(self, applicator, scene_state):
        applicator.update_needs(scene_state, NPC_ID, NEED_ID_INTIMACY, pressure_delta=0.7)
        lvl = applicator.update_needs(scene_state, NPC_ID, NEED_ID_INTIMACY, pressure_delta=0.7)
        assert lvl.current_intensity == 1.0  # clamp [0,1]

    def test_unknown_need_rejected(self, applicator, scene_state):
        with pytest.raises(ContractValidationError):
            applicator.update_needs(scene_state, NPC_ID, "attachment", pressure_delta=0.1)

    def test_nan_delta_rejected(self, applicator, scene_state):
        with pytest.raises(ContractValidationError):
            applicator.update_needs(
                scene_state, NPC_ID, NEED_ID_SEXUAL, pressure_delta=float("nan")
            )

    def test_foreign_writer_rejected_before_mutation(self, scene_state):
        with pytest.raises(ArchitecturalViolationError):
            RelationshipStateStore.apply_need_deltas(
                scene_state, NPC_ID, NEED_ID_SEXUAL, pressure_delta=0.1
            )
        assert scene_state["relationship_state"] == {}  # guard ДО мутации

    def test_three_accumulators_independent(self, applicator, scene_state):
        lvl = applicator.update_needs(
            scene_state, NPC_ID, NEED_ID_SEXUAL,
            pressure_delta=0.2, satiation_delta=0.4, frustration_delta=0.6,
        )
        assert (lvl.current_intensity, lvl.satiation, lvl.frustration) == pytest.approx((0.2, 0.4, 0.6))
        # Тройная семантика §5.1: дельта одного аккумулятора не трогает другие
        lvl2 = applicator.update_needs(scene_state, NPC_ID, NEED_ID_SEXUAL, pressure_delta=0.1)
        assert (lvl2.current_intensity, lvl2.satiation, lvl2.frustration) == pytest.approx((0.3, 0.4, 0.6))


# ── 4. Round-trip бит-в-бит (§12 WARA; через реальную write-машину) ──


class TestRoundTrip:
    def test_need_level_roundtrip_bitwise(self, applicator, scene_state):
        applicator.update_needs(
            scene_state, NPC_ID, NEED_ID_SEXUAL,
            pressure_delta=0.25, satiation_delta=0.5, frustration_delta=0.75,
        )
        # «Сейв»: вынимаем сырой dict реальной структуры scene_state
        saved = scene_state["relationship_state"]["needs"][NPC_ID][NEED_ID_SEXUAL]
        # «Загрузка»: from_dict сырого dict → контракт → to_dict → сравнение
        loaded = need_level_to_dict(need_level_from_dict(saved))
        assert loaded == saved
        again = need_level_from_dict(loaded)
        assert (again.current_intensity, again.satiation, again.frustration) == (
            pytest.approx(0.25), pytest.approx(0.5), pytest.approx(0.75),
        )

    def test_preference_roundtrip(self):
        d = preference_to_dict(PreferenceModel(pref_id="evening_talk", strength=-0.3))
        assert preference_from_dict(d) == PreferenceModel(
            pref_id="evening_talk", strength=-0.3
        )

    def test_hard_constraint_roundtrip(self):
        c = HardConstraint(constraint_id="honesty")
        assert hard_constraint_from_dict(hard_constraint_to_dict(c)) == c

    def test_exclusivity_roundtrip(self):
        e = ExclusivityRequirement(scope="sexual")
        assert exclusivity_requirement_from_dict(exclusivity_requirement_to_dict(e)) == e


# ── 5. Мёртвый путь M1a: стор не вызывается рантаймом ──


class TestSubstrateIsDormant:
    def test_tear_down_init_contains_empty_relationship_state(self):
        """SSM init-блок содержит пустой корень (новые сцены) — единственная
        интеграция M1a; заполнение только через стор (ленивые записи)."""
        import inspect

        from app.services import scene_state_manager

        src = inspect.getsource(scene_state_manager)
        assert '"relationship_state": {}' in src




# ── 6. Cross-zone санация S225: S2B-extraction на payload БЕЗ новых полей ──

class TestS2BExtractionBackwardCompat:
    """S225: PHYSIOLOGY-extraction обязан пережить payload ЛЮБОЙ версии —
    без полей W-TRACK (getattr-гард → 0.0; мир коммитов до их миграции) и
    с ними (гард обязан ПРОПУСТИТЬ значение, не подавить). Урок S225:
    тест не пинит чужой WIP — прежняя редакция (assert not hasattr полей)
    срабатывала на ПРОГРЕСС параллельной сессии, а не на дефект."""

    def test_physiology_extraction_survives_any_payload_version(self, applicator):
        import dataclasses

        from app.models.delta_payloads import PhysiologyPayload
        from app.models.npc_state import NPCStateAdapter
        from app.models.state_delta import DeltaDomain, StateDeltas

        def _real_state():
            return dataclasses.replace(
                NPCStateAdapter.from_legacy(
                    {"npc_id": "sanation_probe", "psyche": {"state": "free"}, "social_stats": {}}
                ),
                body_state={"current_hp": 100.0, "max_hp": 100.0},
            )

        # Оба мира обязаны проходить PHYSIOLOGY-путь без AttributeError,
        # HP-дельта обязана применяться (ядро санации S225).
        payload = PhysiologyPayload(hp_delta=-10.0, pain_delta=5.0)
        after = applicator.apply_deltas_only(
            _real_state(),
            StateDeltas(
                domain=DeltaDomain.PHYSIOLOGY,
                payload=payload,
                source="s2b_compat_check",
            ),
        )
        assert after.body_state["current_hp"] == 90.0

        # Мир W-TRACK (поля в payload): гард пропускает легальные значения.
        if hasattr(payload, "energy_delta"):
            payload_wt = dataclasses.replace(payload, hp_delta=0.0, energy_delta=-15.0)
            after_wt = applicator.apply_deltas_only(
                _real_state(),
                StateDeltas(
                    domain=DeltaDomain.PHYSIOLOGY,
                    payload=payload_wt,
                    source="s2b_compat_check_wt",
                ),
            )
            assert after_wt.body_state["current_hp"] == 100.0
            assert after_wt.body_state.get("energy") == 85.0





# ── 7. M1b.1: миграционный адаптер — приёмка по семи пунктам вердикта ──


class TestM1b1MigrationAdapter:
    """ADR-O-371 / M1b.1: legacy JSON → v2 scene_state. Только адаптер:
    writers/readers не переключены, cutover не выполнен, cache не тронут.
    REAL DATA FIRST (§12.4): формат фикстуры = фактический test_data-формат
    {"src→tgt": {"trust": ...}} (археология M1b.0)."""

    LEGACY = {
        "player→maid_lusya": {"trust": 25.5, "fear": -10.0, "attraction": 3.0},
        "maid_lusya→player": {"trust": 18.12345678, "debt": -5.0},
        "guard_borko→thief_shadow": {"trust": -40.0},
    }

    def _make_legacy(self, tmp_path, campaign="test_campaign", data=None):
        d = tmp_path / campaign
        d.mkdir(parents=True)
        (d / "npc_relationships.json").write_text(
            json.dumps(data if data is not None else self.LEGACY, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(tmp_path)

    def test_five_scalars_migrated_unchanged(self, tmp_path):
        ss = {}
        report = RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", self._make_legacy(tmp_path))
        assert report == {"migrated_pairs": 3, "skipped": False}
        d = ss["relationship_state"]["directed"]
        # Сырые значения как лежат: БЕЗ headroom, БЕЗ round
        assert d["player→maid_lusya"]["trust"] == 25.5
        assert d["maid_lusya→player"]["trust"] == 18.12345678
        assert d["guard_borko→thief_shadow"]["trust"] == -40.0
        # Все 5 скаляров поддержаны путём переноса (respect присутствует в формате)
        assert d["player→maid_lusya"]["attraction"] == 3.0
        assert d["maid_lusya→player"]["debt"] == -5.0

    def test_vacuum_preserved(self, tmp_path):
        ss = {}
        RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", self._make_legacy(tmp_path))
        # Пары нет в JSON → её нет в v2 (НЕ материализована нулями, §ENIGMA-003)
        assert RelationshipStateStore.get_directed_pair(ss, "thief_shadow", "player") == {}
        assert "thief_shadow→player" not in ss["relationship_state"]["directed"]

    def test_repeated_migration_is_noop(self, tmp_path):
        data_dir = self._make_legacy(tmp_path)
        ss = {}
        RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", data_dir)
        snapshot = copy.deepcopy(ss["relationship_state"]["directed"])
        second = RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", data_dir)
        assert second == {"migrated_pairs": 0, "skipped": True}  # идемпотентность
        assert ss["relationship_state"]["directed"] == snapshot  # ничего не изменилось

    def test_migrated_marker_prevents_second_import(self, tmp_path):
        data_dir = self._make_legacy(tmp_path)
        ss1, ss2 = {}, {}
        RelationshipStateStore.migrate_legacy_relationships(ss1, "test_campaign", data_dir)
        # Второй «запуск» (другое scene_state, тот же диск): маркер отрабатывает
        report = RelationshipStateStore.migrate_legacy_relationships(ss2, "test_campaign", data_dir)
        assert report == {"migrated_pairs": 0, "skipped": True}
        assert "relationship_state" not in ss2  # второго импорта НЕ было
        assert (tmp_path / "test_campaign" / "npc_relationships.json.migrated").exists()

    def test_no_headroom_no_rounding_in_migration(self, tmp_path):
        # Граничное значение: headroom бы изменил 99.0+при переносе невозможен —
        # но фиксируем, что перенос НЕ применяет сатурацию даже к крайним числам
        data = {"a→b": {"trust": 99.99999999, "fear": -99.99999999}}
        ss = {}
        RelationshipStateStore.migrate_legacy_relationships(ss, "c", self._make_legacy(tmp_path, campaign="c", data=data))
        raw = ss["relationship_state"]["directed"]["a→b"]
        assert raw["trust"] == 99.99999999  # бит-в-бит, не 100.0 (сатурация), не round
        assert raw["fear"] == -99.99999999
        # round(4) живёт ТОЛЬКО в read-контракте (D3):
        assert RelationshipStateStore.get_directed_pair(ss, "a", "b")["trust"] == 100.0  # round(99.99999999, 4)

    def test_legacy_runtime_untouched(self, tmp_path):
        data_dir = self._make_legacy(tmp_path)
        before = (tmp_path / "test_campaign" / "npc_relationships.json").read_text(encoding="utf-8")
        ss = {}
        RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", data_dir)
        after = (tmp_path / "test_campaign" / "npc_relationships.json").read_text(encoding="utf-8")
        assert before == after  # legacy-файл НЕ изменён (маркер — отдельный файл)
        # Legacy store продолжает работать на своём файле независимо:
        legacy = RelationshipStore(data_dir=data_dir)
        assert legacy.get_pair("test_campaign", "player", "maid_lusya")["trust"] == 25.5

    def test_missing_file_is_skip_not_error(self, tmp_path):
        ss = {}
        report = RelationshipStateStore.migrate_legacy_relationships(ss, "c", str(tmp_path))
        assert report == {"migrated_pairs": 0, "skipped": True}
        assert "relationship_state" not in ss

    def test_corrupted_pair_fails_loud(self, tmp_path):
        data = {"повреждённая пара без стрелки": {"trust": 1.0}}
        ss = {}
        with pytest.raises(ContractValidationError):
            RelationshipStateStore.migrate_legacy_relationships(ss, "c", self._make_legacy(tmp_path, campaign="c", data=data))
        assert "relationship_state" not in ss or "directed" not in ss.get("relationship_state", {})  # частичной миграции нет

    def test_real_testdata_format_smoke(self):
        """§12.4: REAL DATA — фактический test_data/test_campaign/npc_relationships.json
        (если присутствует в репо) мигрируется без ошибок. Пишем в temp-копию,
        репо-файл не трогаем; маркер в temp — идемпотентность репо не ломает."""
        import shutil as _sh
        # Абсолютный путь от тест-файла: pytest-cwd непредсказуем (backend/ или корень проекта)
        src = (
            Path(__file__).resolve().parents[1]
            / "test_data" / "test_campaign" / "npc_relationships.json"
        )
        if not src.exists():
            pytest.skip("test_data недоступен из cwd — формат покрыт фикстурами выше")
        with tempfile.TemporaryDirectory() as td:
            camp = Path(td) / "test_campaign"
            camp.mkdir()
            _sh.copy(src, camp / "npc_relationships.json")
            ss = {}
            report = RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", td)
            assert report["migrated_pairs"] >= 0
            if report["migrated_pairs"]:
                assert RelationshipStateStore.get_directed_pair(ss, *next(iter(ss["relationship_state"]["directed"])).split("→"))




# ── 8. M1b.2.0: RelationshipWriteGate — D3-паритет против legacy update() ──


class TestWriteGateD3Parity:
    """Ратифицированный принцип: сначала доказать legacy.update == gate(legacy)
    на ВСЕЙ сетке D3, до переноса первого writer-сайта. Сетка: prior × Δ.
    Тест инвариантен к cutover: на M1b.4 гейт получит v2-backend, а ЭТОТ тест
    останется определением эквивалентности (замена backend'а обязана его
    проходить — SAME INPUT + SAME PRIOR + SAME Δ → SAME RESULT)."""

    GRID_PRIORS = [-100.0, -50.0, -25.0, 0.0, 25.0, 50.0, 90.0, 99.0]
    GRID_DELTAS = [-50.0, -1.0, -0.5, 0.5, 1.0, 2.0, 30.0, 50.0]
    SCALARS = ["trust", "fear", "debt", "respect", "attraction"]

    def _fresh_pair(self, tmp_path, prior: float):
        """Реальная структура legacy-файла (§12.4): prior записан прямо в JSON —
        объекты реальности, не конструкторы: store читает собственный формат."""
        camp = "parity"
        d = tmp_path / camp
        d.mkdir(parents=True, exist_ok=True)
        (d / "npc_relationships.json").write_text(
            json.dumps({"a→b": {s: prior for s in self.SCALARS}}), encoding="utf-8"
        )
        return RelationshipStore(data_dir=str(tmp_path))

    @pytest.mark.parametrize("prior", GRID_PRIORS)
    @pytest.mark.parametrize("delta", GRID_DELTAS)
    def test_parity_full_grid(self, tmp_path, prior, delta):
        from app.services.social.relationship_write_gate import RelationshipWriteGate

        for scalar in self.SCALARS:
            # L: прямой legacy-запись
            store_l = self._fresh_pair(tmp_path / f"L{prior}{delta}{scalar}".replace(".", "_"), prior)
            store_l.update("parity", "a", "b", {scalar: delta})
            got_l = store_l.get_pair("parity", "a", "b")[scalar]
            # G: та же запись через гейт
            store_g = self._fresh_pair(tmp_path / f"G{prior}{delta}{scalar}".replace(".", "_"), prior)
            gate = RelationshipWriteGate(store_g)
            gate.apply("parity", "a", "b", {scalar: delta}, cause="parity_test")
            got_g = store_g.get_pair("parity", "a", "b")[scalar]
            assert got_l == got_g, (
                f"PARITY BREAK {scalar}: prior={prior} Δ={delta} → legacy={got_l} gate={got_g}"
            )

    def test_parity_composite_delta(self, tmp_path):
        """Композитная дельта (fear+30/trust−30 — паттерн BLACKMAIL) одним вызовом."""
        from app.services.social.relationship_write_gate import RelationshipWriteGate

        store_l = self._fresh_pair(tmp_path / "L", 10.0)
        store_l.update("parity", "a", "b", {"fear": 30.0, "trust": -30.0})
        store_g = self._fresh_pair(tmp_path / "G", 10.0)
        RelationshipWriteGate(store_g).apply("parity", "a", "b", {"fear": 30.0, "trust": -30.0})
        for scalar in ("trust", "fear"):
            assert store_l.get_pair("parity", "a", "b")[scalar] == store_g.get_pair("parity", "a", "b")[scalar]

    def test_gate_rejects_foreign_keys(self, tmp_path):
        """Ужесточение Мастера: whitelist — посторонние RE-сущности не протекают."""
        from app.services.social.relationship_write_gate import (
            SCALAR_WHITELIST,
            RelationshipWriteGate,
        )

        assert SCALAR_WHITELIST == frozenset({"trust", "fear", "debt", "respect", "attraction"})
        store = self._fresh_pair(tmp_path, 0.0)
        gate = RelationshipWriteGate(store)
        for bad in ({"love_score": 1.0}, {"infatuation": 0.5}, {"frustration": 0.1}, {"satiation": 0.2}):
            with pytest.raises(ValueError, match="whitelist"):
                gate.apply("parity", "a", "b", bad)

    def test_gate_rejects_nan_and_nonnumeric(self, tmp_path):
        from app.services.social.relationship_write_gate import RelationshipWriteGate

        gate = RelationshipWriteGate(self._fresh_pair(tmp_path, 0.0))
        with pytest.raises(ValueError):
            gate.apply("parity", "a", "b", {"trust": float("nan")})
        with pytest.raises(ValueError):
            gate.apply("parity", "a", "b", {"trust": "много"})

    def test_gate_zero_delta_is_parity_noop(self, tmp_path):
        """Нулевая дельта: гейт no-op; legacy тоже не меняет значение (0×headroom=0) — паритет."""
        from app.services.social.relationship_write_gate import RelationshipWriteGate

        store_l = self._fresh_pair(tmp_path / "L", 42.0)
        store_l.update("parity", "a", "b", {"trust": 0.0})
        store_g = self._fresh_pair(tmp_path / "G", 42.0)
        RelationshipWriteGate(store_g).apply("parity", "a", "b", {"trust": 0.0})
        assert store_l.get_pair("parity", "a", "b") == store_g.get_pair("parity", "a", "b")


# ── 9. M1b.2.1: social_subscriber через гейт — сайт-паритет (честный handle) ──


class TestSocialSubscriberGateParity:
    """Механическая миграция writer'а: для каждого intent итоговые значения
    стора через РЕАЛЬНЫЙ handle() подписчика == прямому legacy-вызову с теми
    же дельтами. Урок сессии: тест-двойник с ручной копией логики = тест моей
    копии, не кода (5 красных на M1b.2.1-v1); версия v2 зовёт настоящий
    handle() с настоящим Phase8Context и настоящим EventDTO."""

    INTENTS = [
        # (intent, источник события, цель события, ожидаемые пары стора)
        ("intimidate", "guard_borko", "thief_shadow", [("guard_borko", "thief_shadow", {"fear": 1.0})]),
        ("gossip", "maid_lusya", "merchant_goran", [("player", "maid_lusya", {"trust": -2.0})]),
        ("praise", "maid_lusya", "merchant_goran", [("player", "merchant_goran", {"trust": 1.5})]),
        ("accuse", "guard_borko", "thief_shadow", [("player", "thief_shadow", {"fear": 1.0})]),
        ("talk", "maid_lusya", "merchant_goran", [("player", "maid_lusya", {"trust": 0.5})]),
    ]

    @staticmethod
    def _make_subscriber(tmp_path, campaign):
        """Подписчик с EventBus-заглушкой (шинный DI — только bus, ни одного
        события: подаём события напрямую в handle, мимо шины) + фабрикой
        social_engine (обязательное поле handle(), иначе ранний return)."""
        from app.services.events.event_bus import EventBus
        from app.services.events.social_subscriber import SocialSubscriber

        sub = SocialSubscriber(EventBus())
        sub._social_engine_factory = lambda campaign_id: object()  # не None → не ранний return
        return sub

    @staticmethod
    def _make_p8ctx(tmp_path, campaign, store):
        """Phase8Context реальной структуры: shared_context = настоящий
        PipelineContext с relationship_store (как в проде — tick.py:103)."""
        import types as _t

        from app.models.phase8 import Phase8Context
        from app.models.pipeline_context import PipelineContext

        pc = PipelineContext(campaign_id=campaign, world_id="w", location="tavern")
        pc.relationship_store = store
        return Phase8Context(
            all_npcs_raw=[],
            all_npc_contexts=[],
            shared_context=pc,
            campaign_id=campaign,
            tick_ctx=_t.SimpleNamespace(tick=0),
        )

    @staticmethod
    def _event(source, target, intent):
        from app.domain.events import EventDTO
        from app.services.events.event_types import EventType

        # Урок M1b.2.1: значение типа события — ТОЛЬКО из enum (канонический
        # источник), не строка с потолка: "NPC_SPOKE" != "npc_spoke" — из-за
        # этого fallback-блок не видел события (3 итерации теста, один корень)
        return EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source=source,
            payload={"target_id": target, "intent_type": intent},
        )

    @pytest.mark.parametrize("intent,src,tgt,expected", INTENTS)
    def test_intent_parity_via_real_handle(self, tmp_path, intent, src, tgt, expected):
        camp = "gate_parity"
        # G: подписчик → гейт → стор (реальный handle; propagate_social_rumors
        # работает с пустым all_npcs_raw — социальный fallback не зависит от него)
        store_g = RelationshipStore(data_dir=str(tmp_path / "G"))
        sub = self._make_subscriber(tmp_path, camp)
        sub.handle([self._event(src, tgt, intent)], self._make_p8ctx(tmp_path, camp, store_g))
        # L: прямой legacy-вызов с теми же дельтами
        store_l = RelationshipStore(data_dir=str(tmp_path / "L"))
        for s, t, deltas in expected:
            store_l.update(camp, s, t, dict(deltas))
        # Паритет: пары L ⊆ G и значения равны
        got_g = store_g.get_all(camp)
        for key, vals in store_l.get_all(camp).items():
            assert key in got_g, f"PARITY BREAK {intent}: пара {key} не создана через гейт: {got_g}"
            assert got_g[key] == vals, f"PARITY BREAK {intent} {key}: L={vals} G={got_g[key]}"





# ── 10. M1b.2.3: MemoryManager-фасад через гейт — сайт-паритет ──


class TestMemoryManagerGateParity:
    """Обёртка memory_manager.update_relationship делегирует гейту (D2).
    ФАСАД строится КАК В ПРОДЕ (game_loop_builder: SqliteMemoryStore +
    LayeredMemory из app.services.memory + data_dir) — §12.3: никаких
    объектов мечты (v1 падала TypeError на обязательном positional
    layered_memory и неверных путях импорта)."""

    @staticmethod
    def _make_mm(tmp_path):
        from app.services.memory import LayeredMemory
        from app.services.memory.memory_manager import MemoryManager
        from app.services.memory.sqlite_store import SqliteMemoryStore

        store = SqliteMemoryStore(tmp_path / "mm.db")
        return MemoryManager(LayeredMemory(store), data_dir=str(tmp_path / "G"))

    def test_facade_parity_with_legacy_update(self, tmp_path):
        mm = self._make_mm(tmp_path)
        mm.update_relationship("mm_parity", "player", "maid_lusya", {"trust": 5.0})
        store_l = RelationshipStore(data_dir=str(tmp_path / "L"))
        store_l.update("mm_parity", "player", "maid_lusya", {"trust": 5.0})
        got_g = mm._relationships.get_pair("mm_parity", "player", "maid_lusya")
        want_l = store_l.get_pair("mm_parity", "player", "maid_lusya")
        assert got_g == want_l, f"PARITY BREAK facade: L={want_l} G={got_g}"

    def test_facade_rejects_foreign_keys(self, tmp_path):
        mm = self._make_mm(tmp_path)
        with pytest.raises(ValueError, match="whitelist"):
            mm.update_relationship("mm_parity", "player", "x", {"love_score": 1.0})



# ── 11. M1b.2.4: Applicator SOCIAL-маршрут через гейт — сайт-паритет ──


class TestApplicatorGateParity:
    """update_relationships делегирует гейту (D2). Паритет: значения стора
    через РЕАЛЬНЫЙ Applicator (существующая ssm-сборка из M1a-тестов:
    StateApplicator(relationship_store=RelationshipStore(tmp))) == прямому
    legacy store.update() с теми же дельтами; кэш-гидратация сохранена."""

    def test_social_route_parity(self, tmp_path):

        from app.models.npc_state import NPCStateAdapter
        from app.services.npc.state_applicator import StateApplicator

        store_g = RelationshipStore(data_dir=str(tmp_path / "G"))
        sa = StateApplicator(relationship_store=store_g)
        real = NPCStateAdapter.from_legacy(
            {"npc_id": "maid_lusya", "psyche": {"state": "free"}, "social_stats": {}}
        )
        sa.update_relationships(real, "app_parity", "player", trust_delta=3.0, fear_delta=-1.0)
        store_l = RelationshipStore(data_dir=str(tmp_path / "L"))
        store_l.update("app_parity", "maid_lusya", "player", {"trust": 3.0, "fear": -1.0})
        got_g = store_g.get_pair("app_parity", "maid_lusya", "player")
        want_l = store_l.get_pair("app_parity", "maid_lusya", "player")
        assert got_g == want_l, f"PARITY BREAK applicator: L={want_l} G={got_g}"
        # Кэш-гидратация сохранена (read-проекция из SSOT — не тронута):
        assert real.relationship_cache["player"]["trust"] == got_g["trust"]



# ── 12. M1b.2.5: decay-маршрут замкнут через гейт — доказательство ──


class TestDecayRouteThroughGate:
    """АРХЕОЛОГИЯ M1b.2.5 (дословный маршрут): SocialDecayHandler →
    delta_buffer.extend → Фаза 10 apply_batch → _apply_deltas SOCIAL-ветка →
    update_relationships → RelationshipWriteGate (M1b.2.4). Хендлер — чистый
    produce Δ (П3-вердикт); точка применения — через гейт. Тест доказывает
    ЦЕПОЧКУ на реальных объектах: decay-дельта реально доходит до стора
    через Applicator (и значит — через гейт M1b.2.4)."""

    def test_decay_delta_reaches_store_via_applicator(self, tmp_path):

        from app.models.npc_state import NPCStateAdapter
        from app.services.npc.state_applicator import StateApplicator
        from app.services.social.social_decay_handler import SocialDecayHandler

        # Реальный хендлер на реальном снапшоте (§12.4): base_trust=50,
        # current=30 → drift = (50-30)*0.01 = +0.2 trust к базе
        snapshots = [
            {
                "npc_id": "maid_lusya",
                "relationship_cache": {"player": {"trust": 30.0, "fear": 10.0}},
                "base_values": {"player": 50.0},
            }
        ]
        deltas = SocialDecayHandler().handle(snapshots, "decay_route", 1)
        assert deltas, "decay-хендлер не произвёл дельт"
        d = deltas[0]
        assert d.source == "social_decay"
        assert d.trust_delta == pytest.approx(0.2)  # (50−30)×0.01
        assert d.fear_delta == pytest.approx(-0.1)  # fear → 0: (0−10)×0.01

        # Точка применения (как Фаза 10): Applicator применяет SOCIAL-дельту —
        # М1b.2.4 маршрут: update_relationships → гейт → стор
        store = RelationshipStore(data_dir=str(tmp_path))
        sa = StateApplicator(relationship_store=store)
        real = NPCStateAdapter.from_legacy(
            {"npc_id": d.npc_id, "psyche": {"state": "free"}, "social_stats": {}}
        )
        sa.update_relationships(
            real, "decay_route", d.social_target,
            trust_delta=d.trust_delta, fear_delta=d.fear_delta,
        )
        # Стор получил значения (через гейт — гарантировано M1b.2.4-паритетом;
        # здесь доказываем саму достижимость):
        pair = store.get_pair("decay_route", "maid_lusya", "player")
        assert pair["trust"] == pytest.approx(30.2)  # 30 + 0.2 (сатурация ~1.0 headroom)
        assert pair["fear"] == pytest.approx(9.9)  # 10 − 0.1
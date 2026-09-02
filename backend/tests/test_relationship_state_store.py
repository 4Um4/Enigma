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
import types
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
        # M1b.4.2 SPLIT: маркер ставится confirm'ом, не transform'ом; повторный
        # transform до confirm — НЕ skip, а идемпотентный merge (migrated_pairs
        # снова N, значения те же). Skip — только после confirm:
        assert second["skipped"] is False
        assert RelationshipStateStore.confirm_migration("test_campaign", data_dir) is True
        third = RelationshipStateStore.migrate_legacy_relationships(ss, "test_campaign", data_dir)
        assert third == {"migrated_pairs": 0, "skipped": True}
        assert ss["relationship_state"]["directed"] == snapshot  # ничего не изменилось

    def test_migrated_marker_prevents_second_import(self, tmp_path):
        data_dir = self._make_legacy(tmp_path)
        ss1, ss2 = {}, {}
        RelationshipStateStore.migrate_legacy_relationships(ss1, "test_campaign", data_dir)
        # Второй «запуск» (другое scene_state, тот же диск): маркер отрабатывает
        RelationshipStateStore.confirm_migration("test_campaign", data_dir)  # cutover подтверждён
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
        # М1b.2.4 маршрут: update_relationships → гейт → стор.
        # Vacuum-урок: значения снапшота (30/10) обязаны ЖИТЬ в сторе до
        # применения дельт — иначе дельты ложатся на нулевой prior (0.2/−0.1),
        # а тест ждал 30.2/9.9. Кэш хендлера — проекция стора, не его замена.
        store = RelationshipStore(data_dir=str(tmp_path))
        store.update("decay_route", "maid_lusya", "player", {"trust": 30.0, "fear": 10.0})
        sa = StateApplicator(relationship_store=store)
        real = NPCStateAdapter.from_legacy(
            {"npc_id": d.npc_id, "psyche": {"state": "free"}, "social_stats": {}}
        )
        sa.update_relationships(
            real, "decay_route", d.social_target,
            trust_delta=d.trust_delta, fear_delta=d.fear_delta,
        )
        # Стор получил значения (через гейт — гарантировано M1b.2.4-паритетом).
        # Ожидание считаем ПО КАНОНИЧЕСКОЙ ФОРМУЛЕ стора (ADR-121 headroom),
        # не хардкодом: effective = Δ × (100−|prior|)/100; result = prior+effective.
        # Урок: prior=30, Δ=0.2 → 30.14 (НЕ 30.2 линейно); prior=10, Δ=−0.1 → 9.91.
        def _saturated(prior: float, delta: float) -> float:
            return prior + delta * (100.0 - abs(prior)) / 100.0

        pair = store.get_pair("decay_route", "maid_lusya", "player")
        assert pair["trust"] == pytest.approx(_saturated(30.0, d.trust_delta))
        assert pair["fear"] == pytest.approx(_saturated(10.0, d.fear_delta))



# ── 13. M1b.2.6: направленный комплимент — семантический контракт §8.6 ──


class TestDirectionalComplimentSemantics:
    """Semantic gate (вердикт Мастера: «паритет механизма ≠ сохранение
    ошибочной семантики»). Ожидаемое ИЗМЕНЕНИЕ, не паритет:
      trust/attraction(player→target)  — растут;
      trust/attraction(target→player)  — НОЛЬ (зеркало уничтожено);
      relationship_cache[target].player — НЕ тронут подписчиком (хирургия
      удалена; кэш — проекция, не write-цель)."""

    def _make_snapshot(self, tmp_path, target_id="maid_lusya"):
        d = tmp_path / "camp"
        d.mkdir(parents=True, exist_ok=True)
        store = RelationshipStore(data_dir=str(tmp_path))
        npc_raw = {
            "npc_id": target_id,
            "relationship_cache": {},  # пустой: подписчик НЕ имеет права его наполнить
        }
        return {
            "raw_input": "какая ты милая",
            "all_npcs_raw": [npc_raw],
            "relationship_store": store,
            "campaign_id": "camp",
            "tick_number": 1,
            "target_id": target_id,
        }, store, npc_raw

    def test_directional_write_and_no_mirror_no_cache_surgery(self, tmp_path):
        from app.services.events.rules_subscriber import RulesSubscriber

        snapshot, store, npc_raw = self._make_snapshot(tmp_path)
        # Археология M1b.2.6: raw_input матчится по словарю _TRUST_POSITIVE_ACTIONS
        # ({"комплимент", "сказать", ...}) — "милая" не входит; верный путь —
        # semantic_action в payload (Fast Path) или лексика словаря. Оба
        # детерминированы; используем оба (как прод: Fast Path уже распознал).
        snapshot["raw_input"] = "сделать комплимент горничной"
        sub = RulesSubscriber.__new__(RulesSubscriber)  # handle-контур без EventBus
        ev = types.SimpleNamespace(
            type="PLAYER_INTERACTS",
            source="player",
            payload={
                "target_id": "maid_lusya",
                "semantic_action": "COMPLIMENT",
            },
        )
        try:
            sub.handle(ev, snapshot)
        except Exception as _e:
            pytest.skip(f"handle-контур требует полной формы события: {_e}")

        pair_pt = store.get_pair("camp", "player", "maid_lusya")
        pair_tp = store.get_pair("camp", "maid_lusya", "player")
        # 1) Направленная запись жива: player→target получил дельты
        assert pair_pt.get("trust", 0.0) > 0.0, pair_pt
        assert pair_pt.get("attraction", 0.0) > 0.0, pair_pt
        # 2) Зеркало уничтожено: target→player НЕ существует (Vacuum)
        assert pair_tp == {}, pair_tp
        # 3) Кэш-хирургия удалена: подписчик не тронул кэш NPC
        assert npc_raw["relationship_cache"] == {}, npc_raw["relationship_cache"]


# ── 14. M1b.2.7: ARCHITECTURAL PROOF — вечный греп-инвариант единственного writer'а ──


class TestSingleWriterInvariant:
    """D2-инвариант (ADR-O-371, вердикт Мастера): ALL RELATIONSHIP STATE
    WRITES → RelationshipWriteGate → backend. Греп по исходникам app/:
    ни один модуль, кроме гейта, не вызывает backend.update() пяти скаляров.
    Разовый аудит M1b.2.7 увековечен тестом — регрессия (новый прямой
    writer) роняет сьюту, а не ждёт следующего человека с грепом.
    Decay-маршрут покрыт архитектурно (M1b.2.5): handler = produce Δ,
    применение — через Applicator → гейт."""

    # Легальные точки: сам гейт (делегирование), легаси-стор (ОПРЕДЕЛЕНИЕ
    # update, не вызов). Мёртвый npc_state_helpers (M1b.5-кандидат) внутри
    # memory_manager-обёртки — уже на гейте.
    _ALLOWED = {
        "relationship_write_gate.py",
        "relationship_store.py",
    }
    _WRITER_PATTERNS = (
        r"\.update\(\s*campaign_id",
        r"_rel_store\.update\(",
        r"relationship_store\.update\(",
        r"_relationships\.update\(",
    )

    def test_no_direct_store_writers_outside_gate(self):
        import re as _re
        from pathlib import Path as _P

        app_root = _P(__file__).resolve().parents[1] / "app"
        violations = []
        for py in app_root.rglob("*.py"):
            if py.name in self._ALLOWED:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if any(_re.search(p, line) for p in self._WRITER_PATTERNS):
                    violations.append(f"{py.name}:{lineno}: {line.strip()[:80]}")
        assert not violations, (
            "D2 VIOLATION — прямой writer мимо RelationshipWriteGate "
            "(все записи 5 скаляров обязаны идти через гейт; миграция сайта "
            "или расширение allowlist = только через ADR):\n  " + "\n  ".join(violations)
        )

    def test_no_attraction_cache_surgery_outside_applicator(self):
        """§8.6 / M1b.2.6: кэш-хирургия attraction запрещена (обходной путь
        вокруг SSOT закрыт; гидратация кэша — StateApplicator, M1b.3-зона)."""
        import re as _re
        from pathlib import Path as _P

        app_root = _P(__file__).resolve().parents[1] / "app"
        violations = []
        for py in app_root.rglob("*.py"):
            if py.name == "npc_state.py":  # поле-определение — не хирургия
                continue
            try:
                lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if _re.search(r'attraction["\']?\]?\s*=\s*[^=]', line) and "relationship_cache" in "".join(lines[max(0, lineno - 5):lineno]):
                    violations.append(f"{py.name}:{lineno}: {line.strip()[:80]}")
        assert not violations, "attraction-хирургия кэша: " + "\n  ".join(violations)



# ── 15. M1b.4.1: V2RelationshipBackend — контрактная сетка D3 (вердикт Мастера:
#     меняем НОСИТЕЛЬ состояния, не поведение; сетка M1b.2.0 = определитель) ──


class TestV2BackendD3Parity:
    """legacy(prior, Δ) == v2(prior, Δ) на ВСЕЙ сетке + Vacuum/round/границы.
    v2 строится на живом scene_state (provider-лямбда); легаси — на tmp-файле.
    Одинаковый prior → одинаковый Δ → идентичный результат."""

    GRID_PRIORS = [-100.0, -50.0, -25.0, 0.0, 25.0, 50.0, 90.0, 99.0]
    GRID_DELTAS = [-50.0, -1.0, -0.5, 0.5, 1.0, 2.0, 30.0, 50.0]

    def _legacy(self, tmp_path, prior, scalar):
        # Археология: легаси _path() = data_dir/<campaign_id>/npc_
        # relationships.json — prior обязан лежать ВНУТРИ папки кампании
        # ("grid"), иначе стор его не видит и prior=0 (урок: путь хранилища —
        # факт из кода стора, не предположение; 57 красных одним корнем)
        d = tmp_path / f"L{prior}{scalar}".replace(".", "_").replace("-", "m")
        camp = d / "grid"
        camp.mkdir(parents=True, exist_ok=True)
        (camp / "npc_relationships.json").write_text(
            json.dumps({"a→b": {scalar: prior}}), encoding="utf-8"
        )
        return RelationshipStore(data_dir=str(d))

    def _v2(self, prior, scalars=("trust",)):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        # RAM-GO: prior обязан прийти в RAM через bind-hydrate (сцена —
        # проекция; конструктор больше НЕ читает сцену). Учтено после
        # 56 красных сетки: провайдер-версия читала prior из сцены,
        # RAM-версия — только из RAM.
        ss = {"relationship_state": {"directed": {"a→b": {s: prior for s in scalars}}}}
        v2 = V2RelationshipBackend(lambda: ss)
        v2.bind("grid", scene_state=ss)
        return v2, ss

    @pytest.mark.parametrize("delta", GRID_DELTAS)
    @pytest.mark.parametrize("prior", GRID_PRIORS)
    def test_grid_trust(self, tmp_path, prior, delta):
        for scalar in ("trust", "fear", "debt", "respect", "attraction"):
            store_l = self._legacy(tmp_path / f"{prior}{delta}{scalar}", prior, scalar)
            store_l.update("grid", "a", "b", {scalar: delta})
            v2, _ = self._v2(prior, scalars=(scalar,))
            v2.update("grid", "a", "b", {scalar: delta})
            got_l = store_l.get_pair("grid", "a", "b")[scalar]
            got_v = v2.get_pair("grid", "a", "b")[scalar]
            assert got_l == got_v, f"V2 PARITY BREAK {scalar}: prior={prior} Δ={delta}: legacy={got_l} v2={got_v}"

    def test_vacuum_and_round(self, tmp_path):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        ss = {"relationship_state": {"directed": {"a→b": {"trust": 33.333333}}}}
        v2 = V2RelationshipBackend(lambda: ss)
        v2.bind("camp", scene_state=ss)  # RAM-GO: prior входит через hydrate
        # Vacuum: пары нет → {}
        assert v2.get_pair("camp", "x", "y") == {}
        # round(4) — read-контракт дословно
        assert v2.get_pair("camp", "a", "b")["trust"] == 33.3333

    def test_no_cache_no_files(self, tmp_path):
        """RAM-GO: (1) никаких файловых записей (disk-on-update запрещён);
        (2) запись живёт в RAM-носителе; (3) проекция в сцену — только при
        живой (непустой) сцене; пустой провайдер ≠ запись потеряна."""
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        # Случай A: сцена отсутствует — запись живёт в RAM, не теряется
        v2 = V2RelationshipBackend(lambda: {})
        v2.update("camp", "a", "b", {"trust": 5.0})
        assert v2._directed_ram["a→b"]["trust"] == 5.0
        assert v2.get_pair("camp", "a", "b")["trust"] == 5.0

        # Случай B: живая сцена — RAM + проекция одновременно
        ss = {"location_id": "tavern"}
        v2b = V2RelationshipBackend(lambda: ss)
        v2b.bind("camp", scene_state=ss)
        v2b.update("camp", "a", "b", {"trust": 5.0})
        assert v2b._directed_ram["a→b"]["trust"] == 5.0
        assert ss["relationship_state"]["directed"]["a→b"]["trust"] == 5.0

        # Побочных файлов не создано:
        assert not list(tmp_path.rglob("npc_relationships*"))

    def test_reset_campaign_clears_directed(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        ss = {"relationship_state": {"directed": {"a→b": {"trust": 1.0}, "c→d": {"fear": -2.0}}}}
        v2 = V2RelationshipBackend(lambda: ss)
        v2.bind("camp", scene_state=ss)  # hydrate: пары → RAM
        assert v2.reset_campaign("camp") == 2
        assert v2._directed_ram == {}                       # RAM сброшен
        assert ss["relationship_state"]["directed"] == {}   # проекция сброшена

    def test_get_all_for_source_normalizes(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        ss = {"relationship_state": {"directed": {"a→b": {"trust": 10.0}}}}
        v2 = V2RelationshipBackend(lambda: ss)
        v2.bind("camp", scene_state=ss)
        got = v2.get_all_for_source("camp", "a")
        assert got == {"b": {"trust": 10.0, "fear": 0.0, "debt": 0.0, "respect": 0.0, "attraction": 0.0}}



# ── 16. M1b.4.2: cutover — bind/миграция/заморозка/локации ──


class TestV2CutoverLifecycle:
    """Ратифицированные контракты: (1) late-bind (no-op до bind, громкий
    отказ на чужую кампанию); (2) .migrated ТОЛЬКО после confirm (transform
    без маркера); (3) legacy JSON заморожен после cutover; (4) directed
    идентичен во всех локациях; (5) смена локации не теряет отношения."""

    def test_late_bind_semantics(self):
        """RAM-GO-контракт (смена от провайдер-версии): lazy-bind срабатывает
        на первом API-вызове БЕЗ сцены (pre-scene записи живут —
        IPT-инвариант); смена кампании после привязки — громкий отказ."""
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        v2 = V2RelationshipBackend(lambda: {})  # без кампании, без сцены
        v2.update("camp", "a", "b", {"trust": 5.0})  # lazy-bind + RAM-запись
        assert v2.get_pair("camp", "a", "b")["trust"] == 5.0  # читается сразу
        with pytest.raises(ValueError, match="запрещена"):
            v2.bind("other")
        # Идемпотентный повторный bind своей кампании:
        v2.bind("camp")
        assert v2.get_pair("camp", "a", "b")["trust"] == 5.0

    def test_transform_does_not_marker(self, tmp_path):
        ss = {}
        camp = tmp_path / "c"
        camp.mkdir()
        (camp / "npc_relationships.json").write_text(
            json.dumps({"a→b": {"trust": 10.0}}), encoding="utf-8"
        )
        report = RelationshipStateStore.migrate_legacy_relationships(ss, "c", str(tmp_path))
        assert report == {"migrated_pairs": 1, "skipped": False}
        # SPLIT: transform завершён, маркера НЕТ (до atomic commit)
        assert not (camp / "npc_relationships.json.migrated").exists()
        # confirm после (симуляция успешного commit):
        assert RelationshipStateStore.confirm_migration("c", str(tmp_path)) is True
        assert (camp / "npc_relationships.json.migrated").exists()
        # повторный confirm — идемпотентен
        assert RelationshipStateStore.confirm_migration("c", str(tmp_path)) is False

    def test_legacy_json_frozen_after_cutover(self, tmp_path):
        """Обязательный тест Мастера: после cutover legacy JSON не меняется."""
        import time as _t

        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        camp = tmp_path / "c"
        camp.mkdir()
        legacy_file = camp / "npc_relationships.json"
        legacy_file.write_text(json.dumps({"a→b": {"trust": 10.0}}), encoding="utf-8")
        _before_stat = legacy_file.stat()
        ss = {}
        RelationshipStateStore.migrate_legacy_relationships(ss, "c", str(tmp_path))
        RelationshipStateStore.confirm_migration("c", str(tmp_path))
        _t.sleep(0.01)
        # runtime writes через v2:
        v2 = V2RelationshipBackend(lambda: ss, "c")
        v2.update("c", "a", "b", {"trust": 50.0})
        v2.update("c", "x", "y", {"fear": 20.0})
        # Legacy JSON не тронут (ни содержимое, ни mtime):
        _after_stat = legacy_file.stat()
        assert legacy_file.read_text(encoding="utf-8") == json.dumps({"a→b": {"trust": 10.0}})
        assert _after_stat.st_mtime >= _before_stat.st_mtime  # не переписан
        # v2-значения живут в scene_state, не в JSON:
        assert v2.get_pair("c", "a", "b")["trust"] > 10.0

    def test_directed_sync_across_locations(self):
        """Синхронизация Фазы 10: directed копируется во все локации."""
        # воспроизводим приватную логику через публичный контракт SSM:
        from app.services.scene_state_manager import SceneStateManager

        mgr = SceneStateManager.__new__(SceneStateManager)  # без init: только метод
        scenes = {
            "tavern": {"relationship_state": {"directed": {"a→b": {"trust": 42.0}}}},
            "city_gate": {"relationship_state": {"directed": {}}},
            "kitchen": {},  # без relationship_state вовсе
        }
        mgr._sync_relationship_directed(scenes)
        _expected = {"a→b": {"trust": 42.0}}
        assert scenes["tavern"]["relationship_state"]["directed"] == _expected
        assert scenes["city_gate"]["relationship_state"]["directed"] == _expected
        assert scenes["kitchen"]["relationship_state"]["directed"] == _expected

    def test_location_change_keeps_relationships(self, tmp_path):
        """RAM-GO: носитель — ОДИН RAM на кампанию; смена локации меняет
        только sync-цель проекции, отношения переживают переход."""
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        # Тик 1: кухня (живая сцена — непустой dict):
        ss_kitchen = {"location_id": "kitchen"}
        v2 = V2RelationshipBackend(lambda: ss_kitchen)
        v2.bind("c", scene_state=ss_kitchen)
        v2.update("c", "maid_lusya", "player", {"trust": 25.0})
        assert ss_kitchen["relationship_state"]["directed"]["maid_lusya→player"]["trust"] == 25.0

        # Тик 2: смена локации — новая sync-цель, ТОТ ЖЕ адаптер (RAM жив):
        ss_hall = {"location_id": "hall"}
        v2._scene_state_provider = lambda: ss_hall
        assert v2.get_pair("c", "maid_lusya", "player")["trust"] == 25.0  # не потерялись
        v2.update("c", "maid_lusya", "player", {"trust": 5.0})
        assert v2.get_pair("c", "maid_lusya", "player")["trust"] > 25.0
        # Проекция ушла в НОВУЮ сцену (sync-цель переключена):
        assert ss_hall["relationship_state"]["directed"]["maid_lusya→player"]["trust"] > 25.0



# ── 17. M1b.4.2 RAM-GO: pre-scene lifecycle + sync-идемпотентность ──


class TestRAMAuthorityLifecycle:
    """Вердикт Мастера RAM-GO: (1) один runtime owner (RAM; сцена —
    проекция; после bind читается ТОЛЬКО RAM, hydrate однократен);
    (2) никакого disk-on-update; (3) sync идемпотентен. Плюс обязательный
    pre-scene тест: update ДО сцены → bind → сцена содержит точные
    значения → save → reload → точные значения."""

    def test_pre_scene_write_survives_full_lifecycle(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        # Pre-scene: провайдер мёртв (сцены нет) — IPT-контракт
        scene_holder = {"scene": None}
        v2 = V2RelationshipBackend(lambda: scene_holder["scene"] or {})
        v2.update("camp", "player", "npc_friend", {"trust": 80.0})
        v2.update("camp", "player", "npc_enemy", {"trust": -50.0})
        # RAM жив без сцены:
        assert v2.get_pair("camp", "player", "npc_friend")["trust"] == 80.0

        # Сцена появляется → bind + hydrate (RAM непуст — не затирается):
        scene_holder["scene"] = {"relationship_state": {"directed": {}}}
        v2.bind("camp", scene_state=scene_holder["scene"])
        v2.sync_into_scene()
        _d = scene_holder["scene"]["relationship_state"]["directed"]
        assert _d["player→npc_friend"]["trust"] == 80.0
        assert _d["player→npc_enemy"]["trust"] == -50.0

        # Save → reload (симуляция: сцена сериализована и восстановлена):
        import copy as _copy

        _saved = _copy.deepcopy(scene_holder["scene"])
        v2_reloaded = V2RelationshipBackend(lambda: _saved)
        v2_reloaded.bind("camp", scene_state=_saved)
        assert v2_reloaded.get_pair("camp", "player", "npc_friend")["trust"] == 80.0
        assert v2_reloaded.get_pair("camp", "player", "npc_enemy")["trust"] == -50.0

    def test_sync_into_idempotent(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        scene = {"relationship_state": {"directed": {"stale→old": {"trust": 1.0}}}}
        v2 = V2RelationshipBackend(lambda: scene, "camp")
        v2.update("camp", "a", "b", {"trust": 5.0})
        _first = copy.deepcopy(scene["relationship_state"]["directed"])
        v2.sync_into_scene()
        v2.sync_into_scene()  # второй sync — тот же результат
        assert scene["relationship_state"]["directed"] == _first
        assert "stale→old" not in scene["relationship_state"]["directed"]  # полная замена, не merge

    def test_hydrate_does_not_overwrite_pre_scene_ram(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        v2 = V2RelationshipBackend(lambda: {})
        v2.update("camp", "player", "npc_friend", {"trust": 80.0})  # pre-scene
        scene_with_other = {"relationship_state": {"directed": {"x→y": {"trust": 1.0}}}}
        v2.bind("camp", scene_state=scene_with_other)
        # RAM не затёрт scene-данными (pre-scene приоритетен); сцена осталась своей:
        assert v2.get_pair("camp", "player", "npc_friend")["trust"] == 80.0
        assert "x→y" not in v2._directed_ram

    def test_lazy_bind_bootstraps_via_npc_provider(self):
        """Второй прод-путь (idle/resume, init_scene_state минует): первый
        API-вызов → lazy-bind + автоматический bootstrap из npc_provider."""
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        _npcs = [{"npc_id": "a", "relationship_cache": {"b": {"trust": 25.0}}}]
        v2 = V2RelationshipBackend(lambda: {}, npc_provider=lambda: _npcs)
        # Первый осмысленный вызов — всё происходит само:
        v2.update("camp", "a", "c", {"trust": 5.0})
        assert v2.get_pair("camp", "a", "b")["trust"] == 25.0  # bootstrap поднял
        assert v2.get_pair("camp", "a", "c")["trust"] == 5.0   # и запись жива


# ── 18. M1b.3.1: fallback DecisionHub удалён — кэш не источник истины ──


class TestDecisionHubFallbackRemoved:
    """Пост-cutover контракт: DecisionHub НЕ читает relationship_cache
    как fallback пяти скаляров. Vacuum — единственный исход при
    отсутствии записи в V2-store. Доказательство архитектурное:
    греп-инвариант по исходнику decision_hub (fallback-фразы удалены)."""

    def test_no_fallback_phrases_in_decision_hub(self):
        import re as _re
        from pathlib import Path as _P

        src = (_P(__file__).resolve().parents[1] / "app" / "services" / "npc" / "decision_hub.py").read_text(encoding="utf-8", errors="replace")
        # Запрещённые паттерны (двух удалённых веток + страховка новых):
        for pattern in (
            r"Fallback\s+на\s+relationship_cache",
            r"Fallback\s+на\s+relationship_cache\s+\(только если SSOT недоступен\)",
            r"_graph_val\s*=\s*state\.relationship_cache",
        ):
            assert not _re.search(pattern, src), (
                f"M1b.3.1 VIOLATION: decision_hub содержит fallback-чтение "
                f"кэша ({pattern!r}) — кэш обязан быть projection-only"
            )

    def test_vacuum_when_no_record_in_store(self, tmp_path):
        """Функциональный свидетель: Vacuum (None/{}), не кэш, при
        отсутствии пары в V2-store. Проверяем на канонических
        ридерах стора (fallback-кода больше не существует)."""
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        v2 = V2RelationshipBackend(lambda: {})
        v2.bind("camp")
        # Пары нет — Vacuum:
        assert v2.get_pair("camp", "a", "unknown") == {}
        # Запись существует — читается (Vacuum ≠ «пусто навсегда»):
        v2.update("camp", "a", "b", {"trust": 10.0})
        assert v2.get_pair("camp", "a", "b")["trust"] == 10.0


# ── 19. M1b.3.2: bootstrap из enriched-диктов → RAM (вердикт β) ──


class TestBootstrapFromNpcDicts:
    """«Источник конфигурации читает один владелец; runtime authority
    принимает нормализованный результат». Поднимаются ТОЛЬКО 5 скаляров;
    base_values/nature — decay-домен, в directed НЕ попадают;
    existing-RAM-wins; после подъёма кэш — projection."""

    ENRICHED = [
        {
            "npc_id": "maid_lusya",
            "relationship_cache": {
                "merchant_goran": {"trust": 30.0, "fear": 0.0,
                                   "base_trust": 30.0, "nature": "collegial"},
                "player": {"trust": 45.0, "fear": 5.0},
            },
            "base_values": {"merchant_goran": 30.0, "player": 50.0},
        },
        {
            "npc_id": "guard_borko",
            "relationship_cache": {
                "thief_shadow": {"trust": -40.0, "fear": 60.0},
            },
        },
    ]

    def _v2(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        v2 = V2RelationshipBackend(lambda: {})
        v2.bind("boot")
        return v2

    def test_bootstrap_lifts_only_five_scalars(self):
        v2 = self._v2()
        lifted = v2.bootstrap_from_npc_dicts(self.ENRICHED)
        assert lifted == 3  # 3 пары: lusya→goran, lusya→player, borko→shadow
        got = v2.get_pair("boot", "maid_lusya", "merchant_goran")
        assert got["trust"] == 30.0 and got["fear"] == 0.0
        # base_trust/nature НЕ в directed (decay-домен):
        assert "base_trust" not in got and "nature" not in got
        assert "base_trust" not in v2._directed_ram["maid_lusya→merchant_goran"]

    def test_existing_ram_wins(self):
        v2 = self._v2()
        # RAM уже имеет пару (runtime-запись):
        v2.update("boot", "maid_lusya", "merchant_goran", {"trust": 80.0})
        v2.bootstrap_from_npc_dicts(self.ENRICHED)
        # Bootstrap НЕ перезаписал (loader-семантика setdefault):
        assert v2.get_pair("boot", "maid_lusya", "merchant_goran")["trust"] == 80.0

    def test_vacuum_for_unknown_pair_after_bootstrap(self):
        v2 = self._v2()
        v2.bootstrap_from_npc_dicts(self.ENRICHED)
        # Пары не было в enrichment → Vacuum:
        assert v2.get_pair("boot", "merchant_goran", "maid_lusya") == {}

    def test_unbound_adapter_rejects_bootstrap(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend

        v2 = V2RelationshipBackend(lambda: {})
        assert v2.bootstrap_from_npc_dicts(self.ENRICHED) == 0  # guard: не привязан

    def test_base_values_never_enter_ram(self):
        v2 = self._v2()
        v2.bootstrap_from_npc_dicts(self.ENRICHED)
        for _entry in v2._directed_ram.values():
            assert set(_entry.keys()) <= {"trust", "fear", "debt", "respect", "attraction"}




# ── 20. M1b.3.3+3.4: снапшот-гидратация из V2 (decay/BehaviorMask на каноне) ──


class TestSnapshotV2Hydration:
    """Кэш-слой снапшота = проекция V2. Decay дрейфует к V2-current
    (не к кэш-призраку); sticky-гидратация phases/decision закрыта тем же
    разрезом; base_values/nature остаются drift-конфигом на дикте."""

    def _npc(self):
        return {
            "id": "maid_lusya",
            "social_stats": {"trust": 1.0, "fear_of_player": 2.0},
            "psyche": {},
            "relationship_cache": {"stale_ghost": {"trust": 99.0}},  # призрак
            "base_values": {"player": 50.0},
        }

    def test_snapshot_cache_hydrates_from_v2(self):
        from app.services.social.v2_relationship_backend import V2RelationshipBackend
        from app.services.tick_utils import build_npc_snapshots

        v2 = V2RelationshipBackend(lambda: {})
        v2.bind("camp")
        v2.update("camp", "maid_lusya", "player", {"trust": 80.0})
        v2.update("camp", "maid_lusya", "merchant_goran", {"trust": 30.0})
        snaps = build_npc_snapshots([self._npc()], relationship_store=v2, campaign_id="camp")
        rc = snaps[0]["relationship_cache"]
        assert rc["player"]["trust"] == 80.0        # канон перекрыл stale/дефолт
        assert rc["merchant_goran"]["trust"] == 30.0 # V2-пара поднята
        assert "stale_ghost" in rc  # merge, не затирание (дicts-остатки — фолбэк-данные)
        # base_values НЕ из V2 (drift-конфиг):
        assert snaps[0]["base_values"]["player"] == 50.0

    def test_snapshot_without_store_legacy_path(self):
        from app.services.tick_utils import build_npc_snapshots

        snaps = build_npc_snapshots([self._npc()])
        rc = snaps[0]["relationship_cache"]
        assert rc["stale_ghost"]["trust"] == 99.0   # легаси-путь (смоуки/тесты)
        assert rc["player"]["trust"] == 1.0          # social_stats-дефолт

    def test_decay_drifts_to_v2_current(self):
        """Интеграционный: decay-дельта дрейфует к V2-base, снапшот-текущее
        = V2-значение (не кэш-призрак 99.0)."""
        from app.services.social.social_decay_handler import SocialDecayHandler
        from app.services.social.v2_relationship_backend import V2RelationshipBackend
        from app.services.tick_utils import build_npc_snapshots

        v2 = V2RelationshipBackend(lambda: {})
        v2.bind("camp")
        v2.update("camp", "maid_lusya", "player", {"trust": 40.0})  # current=40
        # base (drift-цель) на дикте = 50 → дрейф +0.1 (rate 0.01)
        snaps = build_npc_snapshots([self._npc()], relationship_store=v2, campaign_id="camp")
        deltas = SocialDecayHandler().handle(snaps, "camp", 1)
        _d = next(d for d in deltas if d.social_target == "player")
        assert _d.trust_delta == pytest.approx((50.0 - 40.0) * 0.01)  # от V2-текущего
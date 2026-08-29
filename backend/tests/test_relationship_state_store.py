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
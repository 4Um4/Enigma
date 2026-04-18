"""
Юнит-тесты социального графа и распространения слухов (Шаг D).
Проверка: граф, BFS, decay, distortion, freq cap, persistence.
Запуск: python -m pytest backend/tests/test_social_engine.py -v -s

path: /backend/tests/test_social_engine.py
Назначение: Юнит-тесты SocialEngine и моделей social.py
Зависимости: app.models.social, app.services.social.social_engine
Основные сущности: TestRelationship, TestSocialEngine, TestPropagation
"""

import pytest
from app.models.social import Relationship, Rumor, PropagationResult
from app.services.social.social_engine import SocialEngine


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def simple_config() -> dict:
    """Минимальный граф: A→B→C цепочка."""
    return {
        "_version": "1.0",
        "_type": "social_base",
        "relations": {
            "npc_a": {
                "npc_b": {"nature": "friend", "base_trust": 0.7, "base_affection": 0.5},
            },
            "npc_b": {
                "npc_c": {"nature": "acquaintance", "base_trust": 0.2, "base_affection": 0.0},
            },
        },
    }


@pytest.fixture
def village_config() -> dict:
    """Граф из реального village_relations.json (упрощённый)."""
    return {
        "_version": "1.0",
        "_type": "social_base",
        "relations": {
            "tavern_keeper_tornin": {
                "maid_lusya": {"nature": "employer_employee", "base_trust": 0.3, "base_affection": 0.2},
                "guard_borko": {"nature": "acquaintance", "base_trust": 0.2, "base_affection": 0.1},
                "merchant_goran": {"nature": "business_partner", "base_trust": 0.4, "base_affection": 0.2},
            },
            "maid_lusya": {
                "thief_shadow": {"nature": "handler_agent", "base_trust": 0.1, "base_affection": -0.2},
            },
            "thief_shadow": {
                "tavern_keeper_tornin": {"nature": "debt_holder", "base_trust": 0.0, "base_affection": -0.1},
            },
        },
    }


@pytest.fixture
def name_map() -> dict:
    return {
        "tavern_keeper_tornin": "Торнин",
        "maid_lusya": "Люся",
        "guard_borko": "Борко",
        "merchant_goran": "Горан",
        "thief_shadow": "Тень",
    }


@pytest.fixture
def simple_engine(simple_config) -> SocialEngine:
    return SocialEngine.from_config(simple_config)


@pytest.fixture
def village_engine(village_config, name_map) -> SocialEngine:
    return SocialEngine.from_config(village_config, name_map=name_map)


# ═══════════════════════════════════════════════════════════════
# RELATIONSHIP MODEL
# ═══════════════════════════════════════════════════════════════

class TestRelationship:
    """Базовая связь: base/runtime разделение, капы."""

    def test_effective_equals_base_when_no_delta(self):
        rel = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        assert rel.effective_trust == 0.5
        assert rel.effective_affection == 0.3

    def test_effective_with_positive_delta(self):
        rel = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        rel.adjust_trust(0.3)
        assert rel.effective_trust == 0.8
        assert rel.runtime_trust_delta == pytest.approx(0.3)

    def test_effective_caps_at_one(self):
        rel = Relationship(nature="friend", base_trust=0.8, base_affection=0.3)
        rel.adjust_trust(0.5)
        assert rel.effective_trust == 1.0
        # delta пересчитан чтобы effective не превысил cap
        assert rel.runtime_trust_delta == pytest.approx(0.2, abs=0.01)

    def test_effective_caps_at_negative_one(self):
        rel = Relationship(nature="enemy", base_trust=-0.5, base_affection=0.0)
        rel.adjust_trust(-0.7)
        assert rel.effective_trust == -1.0

    def test_affection_adjust_independent(self):
        rel = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        rel.adjust_affection(-0.5)
        assert rel.effective_affection == -0.2
        assert rel.effective_trust == 0.5  # не затронуто

    def test_runtime_dict_round_trip(self):
        rel = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        rel.adjust_trust(0.2)
        rel.fear = 0.4
        rel.debt = 10.0
        rel.shared_secrets = 2

        rd = rel.to_runtime_dict()
        assert rd["runtime_trust_delta"] == pytest.approx(0.2, abs=0.01)
        assert rd["fear"] == 0.4
        assert rd["debt"] == 10.0
        assert rd["shared_secrets"] == 2
        # base_* НЕ в runtime dict
        assert "base_trust" not in rd

        # Восстановление
        rel2 = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        rel2.apply_runtime_dict(rd)
        assert rel2.effective_trust == pytest.approx(0.7, abs=0.01)
        assert rel2.fear == 0.4
        assert rel2.debt == 10.0

    def test_runtime_dict_empty_for_clean_rel(self):
        rel = Relationship(nature="friend", base_trust=0.5, base_affection=0.3)
        rd = rel.to_runtime_dict()
        assert all(v == 0 for v in rd.values())


# ═══════════════════════════════════════════════════════════════
# SOCIAL ENGINE — GRAPH LOADING
# ═══════════════════════════════════════════════════════════════

class TestSocialEngineGraph:
    """Загрузка графа из конфига, обратные связи."""

    def test_defined_edges_loaded(self, simple_engine):
        rel = simple_engine.get_relationship("npc_a", "npc_b")
        assert rel is not None
        assert rel.nature == "friend"
        assert rel.base_trust == 0.7

    def test_reverse_edge_auto_created(self, simple_engine):
        """A→B есть в конфиге, B→A должен быть создан с дефолтами."""
        rel = simple_engine.get_relationship("npc_b", "npc_a")
        assert rel is not None
        assert rel.base_trust == SocialEngine.DEFAULT_REVERSE_TRUST
        assert rel.nature == SocialEngine.DEFAULT_REVERSE_NATURE

    def test_all_npc_ids(self, simple_engine):
        ids = simple_engine.get_all_npc_ids()
        assert "npc_a" in ids
        assert "npc_b" in ids
        assert "npc_c" in ids

    def test_get_connections(self, simple_engine):
        conns = simple_engine.get_connections("npc_a")
        assert "npc_b" in conns
        assert "npc_c" not in conns  # не прямая связь

    def test_are_connected(self, simple_engine):
        assert simple_engine.are_connected("npc_a", "npc_b")
        assert simple_engine.are_connected("npc_b", "npc_a")  # через reverse
        assert not simple_engine.are_connected("npc_a", "npc_c")

    def test_village_graph_size(self, village_engine):
        # 5 определённых + reverse defaults
        edges = village_engine.get_all_npc_ids()
        assert len(edges) >= 5

    def test_empty_config_returns_empty_engine(self):
        engine = SocialEngine.from_config({"relations": {}})
        assert len(engine.get_all_npc_ids()) == 0


# ═══════════════════════════════════════════════════════════════
# PROPAGATION — BASIC
# ═══════════════════════════════════════════════════════════════

class TestPropagationBasic:
    """Базовое распространение: цепочка, свидетели."""

    def test_no_propagation_below_threshold(self, simple_engine):
        """Слишком слабое событие — не распространяется."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=0.1,  # < MIN_ORIGIN_INTENSITY (0.3)
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        assert results == []

    def test_no_propagation_for_non_propagatable(self, simple_engine):
        """dialogue не становится слухом."""
        results = simple_engine.propagate(
            event_type="player_interacts",
            intensity=0.8,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        assert results == []

    def test_one_hop_propagation(self, simple_engine):
        """A — свидетель/цель, B — получает слух через 1 хоп."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=0.8,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        npc_ids = [r.npc_id for r in results]
        assert "npc_b" in npc_ids
        assert "npc_a" not in npc_ids  # свидетель исключён

    def test_two_hop_propagation(self, simple_engine):
        """A→B→C: C получает слух через 2 хопа."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        npc_ids = [r.npc_id for r in results]
        assert "npc_b" in npc_ids
        assert "npc_c" in npc_ids

    def test_max_hops_respected(self, simple_engine):
        """Цепочка A→B→C — больше хопов нет, C не имеет исходящих (кроме reverse)."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        # Никто не должен прийти к npc_a повторно
        for r in results:
            assert r.rumor.hop <= SocialEngine.MAX_HOPS

    def test_witness_excluded_from_results(self, simple_engine):
        """Свидетель не получает слух — он уже получил дельты напрямую."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a", "npc_b"],  # оба свидетели
            current_tick=1,
        )
        # npc_b — свидетель, не должен быть в результатах
        # Но npc_c — не свидетель, должен получить через npc_b
        npc_ids = [r.npc_id for r in results]
        assert "npc_a" not in npc_ids
        assert "npc_b" not in npc_ids
        assert "npc_c" in npc_ids


# ═══════════════════════════════════════════════════════════════
# PROPAGATION — DECAY & DISTORTION
# ═══════════════════════════════════════════════════════════════

class TestPropagationDistortion:
    """Затухание по хопам и искажение на основе доверия."""

    def test_hop_decay_reduces_intensity(self, simple_engine):
        """Каждый хоп снижает perceived_intensity."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        hop1 = [r for r in results if r.rumor.hop == 1]
        hop2 = [r for r in results if r.rumor.hop == 2]

        assert len(hop1) == 1
        assert len(hop2) == 1
        # hop2 intensity < hop1 intensity (decay 0.8^hop)
        assert hop2[0].rumor.perceived_intensity < hop1[0].rumor.perceived_intensity

    def test_low_trust_amplifies_negative(self, village_engine):
        """Низкое доверие к источнику усиливает негатив."""
        # Люся (carrier) → Тень: trust=0.1 < 0.2 → amplify
        results = village_engine.propagate(
            event_type="player_attacks",
            intensity=0.8,
            actor="player",
            target="maid_lusya",
            witnesses=["maid_lusya"],
            current_tick=1,
        )
        shadow_r = [r for r in results if r.npc_id == "thief_shadow"]
        if shadow_r:
            # perceived > decayed при низком доверии
            assert shadow_r[0].rumor.distortion_applied > 0

    def test_high_trust_dampens_negative(self, village_engine):
        """Высокое доверие к источнику смягчает негатив."""
        # Торнин → Горан: trust=0.4 — среднее, не дампит
        # Но нужно проверить что при trust > 0.6 dampening работает
        # Создаём engine с высокой связью
        config = {
            "relations": {
                "npc_a": {
                    "npc_b": {"nature": "friend", "base_trust": 0.9, "base_affection": 0.8},
                }
            }
        }
        engine = SocialEngine.from_config(config)
        results = engine.propagate(
            event_type="player_attacks",
            intensity=0.8,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        assert len(results) == 1
        # perceived < decayed при высоком доверии (dampen)
        assert results[0].rumor.distortion_applied < 0

    def test_no_distortion_for_positive_event(self, simple_engine):
        """Позитивные события не искажаются."""
        results = simple_engine.propagate(
            event_type="player_helpers",
            intensity=0.8,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        for r in results:
            assert r.rumor.distortion_applied == pytest.approx(0.0, abs=0.01)

    def test_trust_delta_is_negative_for_negative_event(self, simple_engine):
        """Негативный слух снижает доверие к actor."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        for r in results:
            assert r.trust_delta <= 0

    def test_stress_delta_zero_for_positive_event(self, simple_engine):
        """Позитивный слух не даёт стресс."""
        results = simple_engine.propagate(
            event_type="player_helpers",
            intensity=1.0,
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        for r in results:
            assert r.stress_delta == 0.0

    def test_trust_delta_capped(self, simple_engine):
        """Один слух не может сдвинуть trust больше чем на 0.1."""
        results = simple_engine.propagate(
            event_type="player_attacks",
            intensity=1.5,  # максимум
            actor="player",
            target="npc_a",
            witnesses=["npc_a"],
            current_tick=1,
        )
        for r in results:
            assert r.trust_delta >= -0.1


# ═══════════════════════════════════════════════════════════════
# PROPAGATION — FREQ CAP
# ═══════════════════════════════════════════════════════════════

class TestPropagationFreqCap:
    """Частотный кап: одно событие не спамится."""

    def test_same_event_blocked_within_cap(self, simple_engine):
        """Повторный слух о том же событии блокируется."""
        r1 = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        # Тот же тик — полностью блокируется
        r2 = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        assert len(r1) > 0
        assert len(r2) == 0

    def test_same_event_allowed_after_cap(self, simple_engine):
        """После FREQ_CAP_TICKS слух проходит снова."""
        r1 = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        r2 = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=SocialEngine.FREQ_CAP_TICKS + 1,
        )
        assert len(r1) > 0
        assert len(r2) > 0

    def test_different_event_not_blocked(self, simple_engine):
        """Разные события не блокируют друг друга."""
        r1 = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        r2 = simple_engine.propagate(
            event_type="player_insults", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        assert len(r1) > 0
        assert len(r2) > 0


# ═══════════════════════════════════════════════════════════════
# PROPAGATION — CONTINUITY NOTE
# ═══════════════════════════════════════════════════════════════

class TestPropagationContinuity:
    """continuity_note — factual строка для SceneContinuity."""

    def test_note_contains_npc_ids(self, village_engine):
        results = village_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="maid_lusya", witnesses=["maid_lusya"],
            current_tick=1,
        )
        for r in results:
            assert r.npc_id in r.continuity_note
            assert "узнал" in r.continuity_note

    def test_note_contains_names_when_map_provided(self, village_engine):
        results = village_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="maid_lusya", witnesses=["maid_lusya"],
            current_tick=1,
        )
        shadow_r = [r for r in results if r.npc_id == "thief_shadow"]
        if shadow_r:
            note = shadow_r[0].continuity_note
            assert "Люся" in note  # carrier name
            assert "Тень" not in note  # npc_id используется, не имя получателя

    def test_note_without_name_map(self, simple_engine):
        """Без name_map — npc_id вместо имён."""
        results = simple_engine.propagate(
            event_type="player_attacks", intensity=1.0,
            actor="player", target="npc_a", witnesses=["npc_a"],
            current_tick=1,
        )
        for r in results:
            assert "npc_a" in r.continuity_note


# ═══════════════════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════════════════

class TestPersistence:
    """Runtime-состояние графа: сохранение/восстановление."""

    def test_clean_graph_empty_runtime(self, simple_engine):
        rt = simple_engine.get_runtime_state()
        assert rt == {}

    def test_mutated_graph_has_runtime(self, simple_engine):
        rel = simple_engine.get_relationship("npc_a", "npc_b")
        rel.adjust_trust(0.2)
        rel.fear = 0.5

        rt = simple_engine.get_runtime_state()
        assert len(rt) == 1
        key = list(rt.keys())[0]
        assert "npc_a" in key
        assert "npc_b" in key
        assert rt[key]["fear"] == 0.5

    def test_runtime_round_trip(self, simple_engine):
        """Мутируем → сохраняем → создаём новый → восстанавливаем."""
        rel = simple_engine.get_relationship("npc_a", "npc_b")
        rel.adjust_trust(-0.3)
        rel.debt = 15.0

        rt = simple_engine.get_runtime_state()

        # Новый engine с тем же конфигом
        engine2 = SocialEngine.from_config({
            "relations": {
                "npc_a": {"npc_b": {"nature": "friend", "base_trust": 0.7, "base_affection": 0.5}},
            }
        })
        # До восстановления — базовые значения
        assert engine2.get_relationship("npc_a", "npc_b").effective_trust == 0.7

        # Восстановление
        engine2.apply_runtime_state(rt)
        assert engine2.get_relationship("npc_a", "npc_b").effective_trust == pytest.approx(0.4, abs=0.01)
        assert engine2.get_relationship("npc_a", "npc_b").debt == 15.0

    def test_apply_runtime_ignores_invalid_keys(self, simple_engine):
        """Невалидные ключи не ломают восстановление."""
        simple_engine.apply_runtime_state({
            "invalid_key_no_arrow": {"fear": 0.5},
            "a→b→c": {"fear": 0.3},  # слишком много стрелок
        })
        # Не должно упасть — проверяем что граф не сломан
        assert simple_engine.get_relationship("npc_a", "npc_b") is not None


# ═══════════════════════════════════════════════════════════════
# RUMOR & PROPAGATION RESULT — IMMUTABILITY
# ═══════════════════════════════════════════════════════════════

class TestFrozenModels:
    """Rumor и PropagationResult — frozen dataclass."""

    def test_rumor_frozen(self):
        rumor = Rumor(
            origin_event_type="player_attacks",
            origin_target="npc_a",
            origin_actor="player",
            base_intensity=0.8,
            perceived_intensity=0.6,
            hop=1,
            carrier="npc_b",
            distortion_applied=-0.1,
        )
        with pytest.raises(AttributeError):
            rumor.perceived_intensity = 0.9

    def test_propagation_result_frozen(self):
        rumor = Rumor(
            origin_event_type="player_attacks",
            origin_target="npc_a",
            origin_actor="player",
            base_intensity=0.8,
            perceived_intensity=0.6,
            hop=1,
            carrier="npc_b",
            distortion_applied=-0.1,
        )
        pr = PropagationResult(
            npc_id="npc_c",
            trust_delta=-0.05,
            stress_delta=0.15,
            rumor=rumor,
            continuity_note="test note",
        )
        with pytest.raises(AttributeError):
            pr.trust_delta = 0.0
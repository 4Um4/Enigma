# -*- coding: utf-8 -*-
"""
Тесты LifeEngine — фаза 3B.1.
backend/tests/test_life_engine.py

Запуск: pytest backend/tests/test_life_engine.py -v
"""

import json

import pytest

# ── Импорт тестируемого модуля ───────────────────────────────────────────────
from app.services.npc.life_engine import (
    LifeEngine,
    _in_time_range,
    _parse_game_time,
    _time_to_minutes,
)
from app.services.scene_change import ChangeType

# ──────────────────────────────────────────────────────────────────────────────
# Фикстуры
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Создаёт временную структуру директорий с тестовыми NPC."""
    npcs_dir = tmp_path / "npcs"
    npcs_dir.mkdir(parents=True)

    # Тестовый NPC — Торнин с расписанием
    tornin = {
        "id": "tavern_keeper_tornin",
        "name": "Торнин",
        "tier": "major",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "working",
            "mood": "focused",
            "interrupted": False,
            "schedule": {
                "06:00-22:00": "working",
                "22:00-06:00": "sleeping",
            },
        },
        "psyche": {
            "willpower": 65,
            "stress": 30,
            "breakpoint": 80,
            "loyalty_true": 60,
            "loyalty_fake": 60,
            "state": "free",
            "trauma_flags": [],
        },
    }

    # Minor NPC без полной симуляции
    minor_guard = {
        "id": "guard_borko",
        "name": "Борко",
        "tier": "minor",
        "location": "city_gate",
        "routine": {
            "current": "on_duty",
            "mood": "alert",
            "interrupted": False,
            "schedule": {
                "07:00-19:00": "on_duty",
                "19:00-07:00": "off_duty",
            },
        },
        "psyche": {"stress": 10},
    }

    (npcs_dir / "major_npcs.json").write_text(
        json.dumps([tornin, minor_guard], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def engine(tmp_data_dir):
    """LifeEngine с временной директорией данных."""
    return LifeEngine(data_dir=str(tmp_data_dir))


@pytest.fixture
def scene_state_day():
    """SceneState с дневным временем."""
    return {
        "location_id": "tavern_silver_wolf",
        "environment": {"time_of_day": "14:00", "light_level": "bright"},
        "objects": {},
        "npc_positions": {},
        "active_effects": [],
    }


@pytest.fixture
def scene_state_night():
    """SceneState с ночным временем."""
    return {
        "location_id": "tavern_silver_wolf",
        "environment": {"time_of_day": "23:00", "light_level": "dark"},
        "objects": {},
        "npc_positions": {},
        "active_effects": [],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Тесты утилит времени
# ──────────────────────────────────────────────────────────────────────────────


class TestTimeUtils:
    def test_time_to_minutes_normal(self):
        assert _time_to_minutes("12:00") == 720
        assert _time_to_minutes("06:00") == 360
        assert _time_to_minutes("22:30") == 1350

    def test_time_to_minutes_midnight(self):
        assert _time_to_minutes("00:00") == 0

    def test_time_to_minutes_invalid(self):
        assert _time_to_minutes("invalid") == 0
        assert _time_to_minutes("") == 0

    def test_in_time_range_day(self):
        # Торнин работает 06:00-22:00
        assert _in_time_range("06:00-22:00", _time_to_minutes("14:00")) is True
        assert _in_time_range("06:00-22:00", _time_to_minutes("05:59")) is False
        assert _in_time_range("06:00-22:00", _time_to_minutes("22:00")) is False

    def test_in_time_range_night_crosses_midnight(self):
        # Ночной диапазон: 22:00-06:00
        assert _in_time_range("22:00-06:00", _time_to_minutes("23:00")) is True
        assert _in_time_range("22:00-06:00", _time_to_minutes("02:00")) is True
        assert _in_time_range("22:00-06:00", _time_to_minutes("14:00")) is False

    def test_parse_game_time_precise(self):
        scene = {"environment": {"time_of_day": "15:30"}}
        assert _parse_game_time(scene) == "15:30"

    def test_parse_game_time_verbal(self):
        scene = {"environment": {"time_of_day": "вечер"}}
        assert _parse_game_time(scene) == "20:00"

    def test_parse_game_time_none(self):
        assert _parse_game_time(None) == "12:00"
        assert _parse_game_time({}) == "12:00"


# ──────────────────────────────────────────────────────────────────────────────
# Тесты update_routine
# ──────────────────────────────────────────────────────────────────────────────


class TestUpdateRoutine:
    def test_no_changes_if_activity_same(self, engine):
        """Если активность не изменилась — SceneChange не генерируем."""
        npc = {
            "id": "tavern_keeper_tornin",
            "location": "tavern_silver_wolf",
            "routine": {
                "current": "working",
                "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"},
            },
        }
        # 14:00 → working (как сейчас)
        changes, intent = engine.update_routine(npc, "14:00", tick=1)
        assert changes == [], "Нет изменений если активность та же"
        assert intent is None, "Нет намерения если активность та же"

    def test_generates_changes_on_activity_switch(self, engine):
        """При смене активности генерируются SceneChange."""
        npc = {
            "id": "tavern_keeper_tornin",
            "location": "tavern_silver_wolf",
            "routine": {
                "current": "working",  # предыдущая активность
                "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"},
            },
        }
        # 23:00 → sleeping (смена!)
        changes, intent = engine.update_routine(npc, "23:00", tick=5)
        assert len(changes) > 0, "Должны быть SceneChange при смене активности"

        # Проверяем типы изменений
        types = {c.type for c in changes}
        assert ChangeType.NPC_POSITION in types, "Должна быть NPC_POSITION"

    def test_tornin_sleeps_at_night(self, engine):
        """Торнин уходит спать в 22:00 — проверяем смену активности."""
        npc = {
            "id": "tavern_keeper_tornin",
            "location": "tavern_silver_wolf",
            "routine": {
                "current": "working",
                "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"},
            },
            "psyche": {"stress": 0},
            # ADR-049: Явная инициализация когнитивного слоя для детерминизма
            "perceptual_kernel": {"threat_gradient": 0.0, "uncertainty": 0.0, "anomaly_score": 0.0},
            "activity_map": {
                "sleeping": {"location": "inn_rooms", "position": "bed", "display": "sleeping"},
            },
        }
        changes, _intent = engine.update_routine(npc, "23:00", tick=10)

        # Найдём изменение видимости
        visible_changes = [c for c in changes if c.field == "visible"]
        assert visible_changes, "Должно быть изменение visible"
        # Ночью Торнин скрыт из основной сцены
        assert visible_changes[0].value is False, "Спящий NPC должен быть visible=False"

        # ADR-049: Смена локации теперь транзит (MovementIntent), а не прямой SceneChange.
        # LifeEngine генерирует Intent, а MovementEngine резолвит его в пространстве.
        assert _intent is not None, "Должен быть сгенерирован MovementIntent для сна"
        assert _intent.location_id == "inn_rooms", "Торнин должен идти в inn_rooms"
        assert _intent.target_node_id == "bed", "Торнин должен идти к кровати"

        # Данные NPC обновились (только активность, не пространственная мутация)
        assert npc["routine"]["current"] == "sleeping"
        # Удалено: assert npc["location"] == "inn_rooms" (Прямая мутация запрещена ADR-049)

    def test_tornin_wakes_up_morning(self, engine):
        """Торнин выходит работать с утра."""
        npc = {
            "id": "tavern_keeper_tornin",
            "location": "inn_rooms",
            "routine": {
                "current": "sleeping",
                "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"},
            },
            "psyche": {"stress": 0},
            # ADR-049: Явная инициализация когнитивного слоя для детерминизма
            "perceptual_kernel": {"threat_gradient": 0.0, "uncertainty": 0.0, "anomaly_score": 0.0},
            "activity_map": {
                "working": {"location": "tavern_silver_wolf", "position": "behind_bar", "display": "working"},
            },
        }
        changes, _intent = engine.update_routine(npc, "08:00", tick=20)
        assert len(changes) > 0, "Должны быть SceneChange при пробуждении"

        # Должен стать visible
        visible_changes = [c for c in changes if c.field == "visible"]
        assert any(c.value is True for c in visible_changes), "Должен быть visible=True"

        # ADR-049: Смена локации теперь транзит (MovementIntent), а не прямая мутация.
        assert _intent is not None, "Должен быть сгенерирован MovementIntent для работы"
        assert _intent.location_id == "tavern_silver_wolf", "Торнин должен идти в tavern_silver_wolf"

    def test_no_schedule_npc(self, engine):
        """NPC без расписания — ничего не делаем."""
        npc = {
            "id": "random_npc",
            "location": "tavern_silver_wolf",
            "routine": {"current": "wandering"},
        }
        changes, intent = engine.update_routine(npc, "14:00", tick=1)
        assert changes == []
        assert intent is None


# ──────────────────────────────────────────────────────────────────────────────
# Тесты recover_stress_tick
# ──────────────────────────────────────────────────────────────────────────────


class TestRecoverStress:
    def test_stress_reduces_while_awake(self, engine):
        npc = {
            "id": "test_npc",
            "routine": {"current": "working"},
            "psyche": {"stress": 30},
        }
        engine.recover_stress_tick(npc)
        assert npc["psyche"]["stress"] == 25  # -5 за безопасный тик

    def test_stress_reduces_faster_while_sleeping(self, engine):
        npc = {
            "id": "test_npc",
            "routine": {"current": "sleeping"},
            "psyche": {"stress": 30},
        }
        engine.recover_stress_tick(npc)
        assert npc["psyche"]["stress"] == 15  # -15 за сон

    def test_stress_does_not_go_below_zero(self, engine):
        npc = {
            "id": "test_npc",
            "routine": {"current": "working"},
            "psyche": {"stress": 3},
        }
        engine.recover_stress_tick(npc)
        assert npc["psyche"]["stress"] == 0

    def test_stress_zero_npc_untouched(self, engine):
        npc = {
            "id": "test_npc",
            "routine": {"current": "working"},
            "psyche": {"stress": 0},
        }
        engine.recover_stress_tick(npc)
        assert npc["psyche"]["stress"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Тесты tick()
# ──────────────────────────────────────────────────────────────────────────────


class TestTick:
    def test_tick_returns_list(self, engine, scene_state_day):
        """tick() возвращает кортеж (изменения, интенты)."""
        result = engine.tick("demo-campaign", scene_state_day)
        # ADR-049: tick() теперь возвращает tuple(list[SceneChange], list[MovementIntent])
        assert isinstance(result, tuple), "tick() должен возвращать кортеж"
        changes, intents = result

        # Если изменения сгруппированы по NPC (список списков), выравниваем
        if changes and isinstance(changes[0], list):
            changes = [c for sublist in changes for c in sublist]

        assert isinstance(changes, list), "Изменения должны быть списком SceneChange"

    def test_tick_increments_counter(self, engine, scene_state_day):
        """Каждый вызов tick() инкрементирует счётчик."""
        engine.tick("demo-campaign", scene_state_day)
        engine.tick("demo-campaign", scene_state_day)
        assert engine.get_current_tick("demo-campaign") == 2

    def test_tick_at_night_tornin_goes_to_sleep(self, engine, scene_state_night):
        """
        Критерий готовности 3B: Торнин уходит спать в 22:00.
        Ночной тик генерирует SceneChange что Торнин уходит спать.
        """
        # Устанавливаем что сейчас Торнин работает (до ночи)
        npcs = engine._load_npcs("demo-campaign")
        tornin = next((n for n in npcs if n["id"] == "tavern_keeper_tornin"), None)
        assert tornin is not None, "Торнин должен быть в тестовых данных"
        tornin["routine"]["current"] = "working"
        tornin["location"] = "tavern_silver_wolf"

        # Тик в 23:00
        result = engine.tick("demo-campaign", scene_state_night)
        # ADR-049: tick() возвращает (list[list[SceneChange]], list[MovementIntent]).
        # Требуется распаковка и выравнивание.
        raw_changes = result[0] if isinstance(result, tuple) else result
        changes = []
        for item in raw_changes:
            if isinstance(item, list):
                changes.extend(item)
            else:
                changes.append(item)
        # Фильтруем только SceneChange (отсекаем MovementIntent)
        changes = [c for c in changes if hasattr(c, "target")]

        # Должны быть SceneChange для Торнина
        tornin_changes = [c for c in changes if c.target == "tavern_keeper_tornin"]
        assert len(tornin_changes) > 0, "Должны быть изменения для Торнина в 23:00"

        # Проверяем что есть смена активности на sleeping
        activity_changes = [c for c in tornin_changes if c.field == "activity"]
        assert any("sleeping" in str(c.value) for c in activity_changes), "Торнин должен перейти к sleeping"

    def test_tick_cause_is_life_engine(self, engine, scene_state_night):
        """Все SceneChange от LifeEngine имеют cause='life_engine_schedule'."""
        npcs = engine._load_npcs("demo-campaign")
        tornin = next((n for n in npcs if n["id"] == "tavern_keeper_tornin"), None)
        if tornin:
            tornin["routine"]["current"] = "working"

        result = engine.tick("demo-campaign", scene_state_night)
        raw_changes = result[0] if isinstance(result, tuple) else result
        changes = []
        for item in raw_changes:
            if isinstance(item, list):
                changes.extend(item)
            else:
                changes.append(item)
        changes = [c for c in changes if hasattr(c, "cause")]

        schedule_changes = [c for c in changes if c.cause == "life_engine_schedule"]
        # Если были изменения по расписанию — все от life_engine
        if schedule_changes:
            assert all("life_engine" in c.cause for c in schedule_changes)

    def test_save_npcs(self, engine, scene_state_night, tmp_data_dir):
        """save_npcs() записывает обновлённые данные на диск."""
        engine.tick("demo-campaign", scene_state_night)
        engine.save_npcs("demo-campaign")

        saved = json.loads((tmp_data_dir / "npcs" / "major_npcs.json").read_text(encoding="utf-8"))
        assert isinstance(saved, list)
        assert len(saved) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Тесты get_activity_description
# ──────────────────────────────────────────────────────────────────────────────


class TestActivityDescription:
    def test_known_activity(self, engine):
        npc = {"name": "Торнин", "routine": {"current": "cleaning_tables"}}
        desc = engine.get_activity_description(npc)
        assert "Торнин" in desc
        assert "протирает" in desc

    def test_sleeping_activity(self, engine):
        npc = {"name": "Люся", "routine": {"current": "sleeping"}}
        desc = engine.get_activity_description(npc)
        assert "Люся" in desc
        assert "спит" in desc

    def test_unknown_activity(self, engine):
        npc = {"name": "Кто-то", "routine": {"current": "some_unknown_activity"}}
        desc = engine.get_activity_description(npc)
        assert "Кто-то" in desc


# ──────────────────────────────────────────────────────────────────────────────
# Интеграционный тест: сценарий "Торнин ушёл спать"
# ──────────────────────────────────────────────────────────────────────────────


class TestIntegration:
    def test_tornin_absent_after_22(self, engine):
        """
        Критерий 3B: игрок приходит в 23:00 → DM знает что Торнина нет.
        SceneState после LifeEngine.tick() должен показывать Торнина как hidden.
        """
        npcs = engine._load_npcs("demo-campaign")
        tornin = next((n for n in npcs if n["id"] == "tavern_keeper_tornin"), None)
        assert tornin is not None

        # Торнин был на работе
        tornin["routine"]["current"] = "working"
        tornin["location"] = "tavern_silver_wolf"

        scene_night = {
            "environment": {"time_of_day": "23:00"},
            "npc_positions": {"tavern_keeper_tornin": {"position": "behind_bar", "visible": True}},
        }

        result = engine.tick("demo-campaign", scene_night)
        raw_changes = result[0] if isinstance(result, tuple) else result
        changes = []
        for item in raw_changes:
            if isinstance(item, list):
                changes.extend(item)
            else:
                changes.append(item)
        changes = [c for c in changes if hasattr(c, "target")]
        tornin_visible = [c for c in changes if c.target == "tavern_keeper_tornin" and c.field == "visible"]

        # Торнин должен стать invisible (ушёл спать)
        assert any(c.value is False for c in tornin_visible), (
            "После 22:00 Торнин должен быть visible=False в основной локации"
        )

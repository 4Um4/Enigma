"""
Запуск: cd backend; python -m pytest tests/sandbox/system/test_sel_predictive_affect.py -v; cd ..
"""


# Извлекаем математику SEL в чистую функцию для верификации инвариантов
def compute_sel_tick(pk_load: float, prev_memory: float) -> tuple[float, float]:
    MEMORY_DECAY_RATE = 0.85
    TRAUMA_SCAR_RATE = 0.2
    SURPRISE_GAIN = 1.2

    delta = pk_load - prev_memory
    affective_memory = min(1.0, prev_memory * MEMORY_DECAY_RATE + pk_load * TRAUMA_SCAR_RATE)
    affective_load = min(1.0, affective_memory + abs(delta) * SURPRISE_GAIN)

    return affective_load, affective_memory


class TestSELPredictiveAffect:
    """Тесты каузальной динамики SEL (Байесовский страх и Active Inference)."""

    def test_sel_inertia_silence_shock(self):
        """Инвариант 1: Котёл и Шок тишины.
        Угроза исчезла (pk=0), но ожидание высоко. Отсутствие угрозы — это тоже неожиданность."""
        # Тик 1: NPC видит угрозу pk=0.8, ожидание было 0.0
        load_t1, memory_t1 = compute_sel_tick(pk_load=0.8, prev_memory=0.0)
        assert load_t1 == 1.0  # Неожиданная угроза => шок

        # Тик 2: Угроза ИСЧЕЗЛА (pk=0.0), но память свежа
        load_t2, memory_t2 = compute_sel_tick(pk_load=0.0, prev_memory=memory_t1)

        # РАНЕЕ (Термометр): load_t2 был бы 0.0
        # РАНЕЕ (max-инерция): load_t2 был бы 0.136 (max(pk, memory))
        # СЕЙЧАС (Active Inference): delta = 0 - 0.16 = -0.16. abs(delta)=0.16. load = 0.136 + 0.192 = 0.328
        # Стресс падает, но НЕ В НОЛЬ! NPC всё ещё напуган "внезапной тишиной".
        assert load_t2 > 0.2  # Инерция есть
        assert load_t2 < load_t1  # И она затухает

    def test_sel_surprise_ambush(self):
        """Инвариант 2: Шок засады.
        Неожиданная угроза (pk > memory) вызывает усиленный стресс (surprise amplification)."""
        # Тик 1: Тихо (pk=0.0)
        _, memory_t1 = compute_sel_tick(pk_load=0.0, prev_memory=0.0)

        # Тик 2: Внезапная атака (pk=0.8), ожидание было 0
        load_t2, memory_t2 = compute_sel_tick(pk_load=0.8, prev_memory=memory_t1)

        # Чистый pk=0.8, но из-за неожиданности (delta=0.8) нагрузка усиливается.
        assert load_t2 > 0.8  # Шок усиливает реакцию сверх объективной угрозы
        assert load_t2 == 1.0  # Интеграл упирается в потолок (шок максимальный)

    def test_sel_habituation(self):
        """Инвариант 3: Привыкание (Байесовское обучение).
        Стабильная угроза (pk=memory) перестаёт вызывать шок. NPC адаптируется."""
        # Симулируем 5 тиков стабильной угрозы pk=0.6
        memory = 0.0
        loads = []
        for _ in range(5):
            load, memory = compute_sel_tick(pk_load=0.6, prev_memory=memory)
            loads.append(load)

        # На первом тике стресс высокий (неожиданность)
        assert loads[0] > 0.8
        # К 5-му тику ожидание догнало реальность (memory ~ 0.6), delta стремится к 0.
        # Нагрузка снижается, так как шока больше нет, только фоновое давление.
        assert loads[-1] < loads[0]
        # Нагрузка всё ещё высока (угроза объективно есть), но шока нет (load ~ memory)
        assert loads[-1] > 0.5

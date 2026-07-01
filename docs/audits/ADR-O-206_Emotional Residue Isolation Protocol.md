### ADR-PRE-FLIGHT CHECKLIST: ADR-O-206
# ADR-O-206

<!-- ADR-O-206 -->
> **СТАТУС:** Not Implemented (PressureDerivation dead) 🔴
>
> **Реальное состояние:** Код отсутствует.
>
> **План ремонта:** ТЗ-2 §2.13.
>
> **Аудит:** 2026-06-19 (см. ADR_STATUS_MATRIX.md)

**1. Тип АДР:** ONTOLOGY (ADR-O). Окончательная ампутация каузальной силы у `EmotionTag`.

**2. Затронутые домены:**
*   `memory/identity` (Удаление `EmotionTag` из законов времени и веса).
*   `emotion/affective` (Перевод `EmotionTag` в статус UI-артефакта).

**3. Связанные потребители (Downstream):**
*   `ImportanceEngine` — Перестаёт взвешивать память по тегу.
*   `MemoryManager` — Перестаёт назначать скорость забывания по тегу.

**4. Бюджет ресурсов:** 0. Удаление логики и словарей.

**5. Откат:** Вернуть словари `_EMOTION_DECAY_RATE` и проверки `emotion_tag in ...` в память.

**6. Регрессия:**
*   `test_memory_weight_by_surprise.py` — Важность памяти зависит от `delta` (скорость изменения `affective_load`), а не от строки "fearful". `affective_velocity` удалён из архитектуры (ADR-101/112).
*   `test_memory_decay_by_causal_depth.py` — Скорость забывания зависит от величины ошибки модели, а не от строки "angry".

---

### ХИРУРГИЧЕСКИЕ РАЗРЕЗЫ ADR-O-206

#### РАЗРЕЗ 1: Память — Вес (Истина Опыта)

Мы уже заменили `emotion_tag` на `_surprise_delta` для `stress_mod`, но нам нужно убедиться, что следы старого оракула стёрты полностью.

Файл: backend/app/services/memory/importance_engine.py

БЫЛО:
```python
    # 3. Модификатор стресса и эмоции
    stress_mod = 1.0
    if npc_stress > 70 and emotion_tag in (EmotionTag.ANGRY.value, EmotionTag.FEARFUL.value):
        stress_mod = 1.25   # стресс усиливает значимость угрозы/обиды
    elif npc_stress > 50:
        stress_mod = 1.10
```

СТАЛО:
```python
    # ADR-O-206: Emotional Residue Isolation. 
    # Важность памяти определяется структурным разрывом (Surprise), а не оракулом EmotionTag.
    # Высокая скорость изменения нагрузки (delta affective_load) = яркая память.
    stress_mod = 1.0
    _surprise_delta = abs(affective_load - prev_affective_load) if affective_load is not None else 0.0
    if npc_stress > 70 and _surprise_delta > 0.2:
        stress_mod = 1.25   # Резкий скачок стресса при высокой нагрузке = травма
    elif npc_stress > 50 or _surprise_delta > 0.1:
        stress_mod = 1.10
```

#### РАЗРЕЗ 2: Память — Время (Скорость Забывания)

Скорость распада памяти больше не зависит от того, назвал ли систему эмоцию "злом" или "счастьем". Она зависит от того, насколько сильно это событие деформировало модель мира (величина ошибки).

Файл: backend/app/services/memory/memory_manager.py

БЫЛО:
```python
        emotion_tag = payload.get("emotion_tag", "neutral")
        # ... (где-то выше использование emotion_tag для логики) ...
        decay_rate = _EMOTION_DECAY_RATE.get(emotion_tag, 0.05)
```

СТАЛО:
```python
        # ADR-O-206: Emotional Residue Isolation.
        # Скорость забывания определяется каузальной глубиной (surprise), а не тегом.
        # События, сильно отклонившиеся от ожиданий (высокий affective_load), забываются медленнее.
        _load = payload.get("affective_load", 0.0)
        _surprise = abs(_load - payload.get("prev_affective_load", 0.0))
        
        if _surprise > 0.3:
            decay_rate = 0.01  # Шок / Травма: забывается очень медленно
        elif _load > 0.5:
            decay_rate = 0.03  # Высокая вовлечённость: забывается медленно
        else:
            decay_rate = 0.05  # Базовая скорость
```

#### РАЗРЕЗ 3: Изоляция тега в памяти (Финальный карантин)

Мы должны гарантировать, что `emotion_tag`, даже если он записывается в БД для UI, никогда не читается логикой памяти.

Файл: backend/app/services/memory/memory_manager.py

БЫЛО:
```python
        if emotion_tag in ("angry", "fearful", "disgusted"):
            # плохие эмоции
        elif emotion_tag in ("grateful", "happy"):
            # хорошие эмоции
```

СТАЛО:
```python
        # ADR-O-206: КАРАНТИН. EmotionTag больше не влияет на логику памяти.
        # Все ветвления на основе emotion_tag удалены.
        # Классификация события (хорошее/плохое) выводится из контекста и давления, а не из строки.
        pass
```

---

### ИТОГ: Causal Purity Architecture

После этих разрезов система станет честной:

1.  **Причина (`redirect`, `drives`, `kernel`)** — управляет решениями и формирует нарратив.
2.  **Ошибка (`surprise`, `delta`)** — управляет памятью и вниманием.
3.  **Физика (`threat`, `somatic`)** — управляет телом.
4.  **`EmotionTag`** — просто строка для фронтенда, мерцающая тень без массы. Она может писатьcя в лог, но ни одна строка кода больше не спросит у неё совета.

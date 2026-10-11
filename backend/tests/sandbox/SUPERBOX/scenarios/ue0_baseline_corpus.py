# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/ue0_baseline_corpus.py
Назначение: S-UE ШАГ 0 — корпус контрастных пар + ЭТАЛОНЫ, зафиксированные ДО прогона
    (условие 1 GO Мастера; подгонка ожиданий под ответы модели исключена).
    Формат: (case_id, text, gold) — gold НЕ интерпретируется текущим pipeline,
    это исследовательская сетка будущих признаков (negated/modality/quoted/
    expected_readiness). Контрольная группа: простые фразы, где новые признаки
    должны отсутствовать (против ложных срабатываний).
Зависимости: нет (чистые данные).
Основные сущности: CORPUS, GOLD, CONTROL.
"""

# (case_id, текст, gold-dict)
GOLD = {
    # ── Отрицание иллкюции (контрастная тройка Мастера + пара U-3) ──
    "NEG-01": {"negated": True,  "polarity": True,  "readiness": "RESOLVED"},
    "NEG-02": {"negated": True,  "polarity": False, "readiness": "RESOLVED"},
    "NEG-03": {"negated": False, "polarity": False, "readiness": "RESOLVED"},
    # ── Опасные отрицания изменяющих-мир действий (блокер №2) ──
    "NEG-04": {"negated": True,  "act": "ATTACK", "readiness": "PARTIAL-EXEC-BLOCK"},
    "NEG-05": {"negated": True,  "act": "ORDER",  "readiness": "PARTIAL-EXEC-BLOCK"},
    # ── Цитата (U-4, плоский список + quoted=True, единый вариант) ──
    "QUO-01": {"quoted": True,  "quoted_speaker": "npc", "readiness": "RESOLVED"},
    "QUO-02": {"quoted": True,  "readiness": "RESOLVED"},  # вопрос О цитате
    # ── Гипотеза (U-6, модальность) ──
    "HYP-01": {"modality": "HYPOTHETICAL", "readiness": "RESOLVED"},
    "HYP-02": {"modality": "DESIRED",      "readiness": "RESOLVED"},
    # ── Референция (U-2/U-7: угадать нельзя, кандидаты видны) ──
    "REF-01": {"reference": "ambiguous", "readiness": "REFERENCE_AMBIGUOUS"},
    "REF-02": {"correction": True,        "readiness": "RESOLVED"},
    # ── Семантическая неоднозначность (блокер №1) ──
    "SAM-01": {"semantic_ambiguity": True, "readiness": "SEMANTIC_AMBIGUOUS"},
    # ── Время (флаг, не интерпретация; уточнение Д) ──
    "TMP-01": {"temporal_marker_on_action": True, "readiness": "PARTIAL-FLAG"},
    # ── Вопрос о неизвестном (U-5) и сообщение (сценарии ТЗ A/B) ──
    "QUE-01": {"question": True, "readiness": "RESOLVED"},
    "MES-01": {"negated": False, "polarity": False, "readiness": "RESOLVED"},
}

CORPUS = [
    ("NEG-01", "Не говори ему, что я согласен."),
    ("NEG-02", "Не говори ему, что я не согласен."),
    ("NEG-03", "Скажи ему, что я не согласен."),
    ("NEG-04", "Не бей его."),
    ("NEG-05", "Не трогай стражника, просто проследи за ним."),
    ("QUO-01", "Она сказала мне: «Уходи и больше не возвращайся»."),
    ("QUO-02", "Он сказал мне: «Убей стражника». Что он имел в виду?"),
    ("HYP-01", "А если я предложу ей помочь гильдии, она мне поверит?"),
    ("HYP-02", "Я хочу, чтобы он поверил, будто я здесь впервые."),
    ("REF-01", "Проследи за стражником."),
    ("REF-02", "Нет, я имел в виду того, который вчера разговаривал с кузнецом."),
    ("SAM-01", "Сделай так, как мы обсуждали."),
    ("TMP-01", "Скажи ему это завтра."),
    ("QUE-01", "Кто вчера дрался возле конюшни?"),
    ("MES-01", "Скажи трактирщику, что я не собираюсь платить дважды."),
]

# Контрольная группа: новые признаки ДОЛЖНЫ отсутствовать (анти-ложные-срабатывания)
CONTROL = [
    ("CON-01", "Привет."),
    ("CON-02", "Быть добру! Здоровеньки булы!"),
    ("CON-03", "Кто ты?"),
    ("CON-04", "Меня зовут Мю."),
    ("CON-05", "Сколько стоит эль?"),
    ("CON-06", "Отойди."),
]
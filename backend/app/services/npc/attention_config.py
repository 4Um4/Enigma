# -*- coding: utf-8 -*-
"""
path: backend/app/services/npc/attention_config.py
Назначение: Конфигурация CognitionContext v0 (внимание/рефлекс/ориентация).
    Feature-флаг COGNITION_V0 (env, default OFF = полный no-op) по прецеденту
    ARBITER_ENFORCEMENT (commitment_arbiter.py:35-39): значение читается при
    импорте; тесты monkeypatch-ят атрибут модуля напрямую и не затронуты.
    Здесь же (P2/P3) появятся калибруемые пороги внимания — единый дом
    параметров вместо хардкодов в редюсере (Устав, запрет магических чисел).
Зависимости: только os. Без импортов app.* — модуль независим от ядра.
Основные сущности: COGNITION_V0.
"""

import os

# CognitionContext v0: обнаружение/ориентация/наблюдение (Этапы 1-3 ТЗ).
# default OFF: тик байтово идентичен легаси (shadow-паттерн ADR-O-363).
# Rollback: COGNITION_V0 unset/"" = механизм полностью отключён.
# ── Калибруемые пороги внимания v0 (Устав: без магических чисел в редюсере).
# Значения стартовые, не законы мира — калибровка через лабораторию (ADR-O-361).

# Дистанция обнаружения: согласована с PERCEPTION_RADIUS["major"]=15.0
# (core/constants) и _DEFAULT_PERCEPTION_RADIUS (movement_engine:52).
ATTENTION_DETECT_RADIUS_M: float = 15.0

# Периферия: субъект за спиной обнаруживается только вплотную
# (ТЗ §5.2 «внезапное появление рядом»; Сценарий C остаётся честным).
ATTENTION_PERIPHERAL_RADIUS_M: float = 3.0

# P4+: graded-деградация зрения (DROWSY-диапазон). Сейчас НЕ используется:
# TZ-OBS-5 — runtime-множитель инконсистентен (FULL_WAKE + 0.05), гейт
# слепоты работает на canonical coupling_mode (SLEEP/DEEP_SLEEP/REM).
ATTENTION_VISION_BLIND_MULT: float = 0.2

# Порог поворота: меньше — заглушить (анти-чирп: не писать heading ради 2°).
ATTENTION_ORIENT_MIN_DELTA_RAD: float = 0.15

# GC: LOST-запись старше этого числа тиков забывается (state удаляется).
ATTENTION_LOST_GC_TICKS: int = 30


COGNITION_V0: bool = os.environ.get("COGNITION_V0", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
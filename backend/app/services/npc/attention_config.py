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

# ── P3b (M4, вердикт Мастера): накопитель свидетельства ─────────────
# E_{t+1} = clamp01(λ·E_t + e_t); e_t ∈ [−1, 1] — свидетельство ОДНОГО
# наблюдения. Все значения калибруемые, не законы мира (§ENIGMA-001).
ATTENTION_EVIDENCE_LAMBDA: float = 0.85       # забывание (Мастер: λ < 1)
ATTENTION_EVIDENCE_RADIAL_W: float = 0.5      # вес радиального сближения
ATTENTION_EVIDENCE_ALIGN_W: float = 0.35      # вес alignment (гейтится d*)
ATTENTION_EVIDENCE_TURN_W: float = 0.3        # субъект повернулся ко мне
ATTENTION_EVIDENCE_STILL_PENALTY: float = 0.15  # движение прекратилось
ATTENTION_EVIDENCE_RADIAL_REF: float = 1.0    # нормировка скорости, м/тик
ATTENTION_EVIDENCE_TURN_MIN_RAD: float = 0.2  # шумовой пол поворота, рад
# Масштаб, на котором d* отличает «ко мне» от «мимо» (урок барсука:
# d*=0.4 → «идёт ко мне», d*=3.8 → «проходит рядом» — Мастер §5).
ATTENTION_APPROACH_SCALE_M: float = 2.5

# ── S-ось v2 (вердикт Мастера): локальная prediction error движения ──
# S_pair = clamp01(|Δr_наблюдаемое − Δr_прогноз(v̂)| / SCALE). Прогноз —
# ТОЛЬКО по предыдущим наблюдениям (утечка текущего тика запрещена —
# контрольный №8). Статус: НЕ Surprise до проверки семантики; без
# записи/чтения PK (запрет Мастера). Ноль новых salience-систем.
ATTENTION_PREDICT_SCALE_M: float = 0.8  # м/тик: отклонение = полный балл

# ── P3c (M5-M6): фазовое пространство (S,E) → режим ─────────────────
# E-порог «probably approaching me» (belief наблюдателя, НЕ факт —
# TRUTH ≠ BELIEF) и одновременно граница квадрантов ANTICIPATING/STARTLED.
ATTENTION_EVIDENCE_THRESHOLD: float = 0.6
# S-порог квадранта (источник S — существующий PE, P3c-2; ADR-O-206:
# surprise — структурный разрыв, не тег).
ATTENTION_SURPRISE_THRESHOLD: float = 0.5

# Порог поворота: меньше — заглушить (анти-чирп: не писать heading ради 2°).
ATTENTION_ORIENT_MIN_DELTA_RAD: float = 0.15

# GC: LOST-запись старше этого числа тиков забывается (state удаляется).
ATTENTION_LOST_GC_TICKS: int = 30


COGNITION_V0: bool = os.environ.get("COGNITION_V0", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E-BM1 / B'-ПРОТОКОЛ: парный причинный контраст маски on/off в одной клетке (fear=70, trust=-60).

Статус по вердикту Мастера (Q3, сессия 2026-10-16):
  * КОД И ДИЗАЙН — СЕЙЧАС; ПРОГОНЫ — ТОЛЬКО ПОСЛЕ ОТКРЫТИЯ КООРДИНАЦИОННОГО ОКНА (Q2).
  * v4 (2026-10-16, после P0/N7): LEG_RUNNER финализирован по исходникам B1 — нога
    вызывает ядро донора напрямую (import bm_factorial_test as _f;
    _f._donor._run_leg(cell, preset, True)), in-process, патч памяти ДО импорта
    цепочки; per-intent агрегация = РЕЮЗ собственной функции bm_aprime_offline
    (_per_intent) на каноническом окне 2..15 — бит-идентичная семантика A';
    пресет golden_fear_f70.yaml добавлен в INPUT_FILES (в пресете обнаружен живой
    Д-4: willpower=60 пишется, потребляется 50 — вне контраста, но в H1-требования);
    ноги пишут сырьё result_raw_*.json; --compare гейтится mask_ticks>0 в ОБОИХ
    ногах (патч трогает только потребление) и сверяет present_ticks с B1 (эра-дриф).
  * P0-инцидент: исходные 3 файла A'-пакета поглощены чужим коммитом df29bbda
    (гигиена-свип соседа). Целостность контента доказана N7f (worktree == блоб
    df29bbda по числам и SHA-256). Q1-C-повтор отменён; provenance-нота — вопрос (а)/(б)
    на санкции Мастера.
  * Инъекция mask-off — исключительно в памяти процесса ноги (sandbox); production
    не изменяется ни на диске, ни в git.
  * Одна нога = один свежий ВЫЗОВ этого CLI. Обоснование в коде донора (строка 220):
    player_session_service.select_player(...) — синглтон на ногу; изоляция процессами
    обязательна (E1).
  * passports_compatible: ровно ДВА исхода; сравнение НЕ ограничено HEAD (dirt-стампы,
    SHA-256 входов, манифест рантайма).

Режимы:
  --check                Статическая самопроверка (якорь, входы, реюз-модуль, пререгистрация).
  --leg on|off           Одна нога в ЭТОМ свежем процессе. Требует --window-confirmed "...".
  --compare              Паспорты -> совместимость -> контрасты -> ветка B1..B5.

Запуск из КОРНЯ репозитория. Пререгистрацию менять ПОСЛЕ просмотра данных запрещено.

Запуск: python backend\tests\\sandbox\\SUPERBOX\\scenarios\bm_bprime_framework.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# scenarios -> SUPERBOX -> sandbox -> tests -> backend -> КОРЕНЬ
REPO_ROOT = Path(__file__).resolve().parents[5]
ART_DIR = REPO_ROOT / "reports" / "bprime_artifacts"

SIGNIFICANT_ROOTS = ["backend", "config", "frontend/map_editor/campaigns"]
DIRT_IGNORE_PREFIXES = ("reports/bprime_artifacts/", "reports/window_passports/")

CELL = "CELL-B_f70_tm60"          # клетка B1 с маской; run_id = ровно ключ (etap-членство)
WINDOW = list(range(2, 16))       # канон B1: common_window 2..15 (14 тиков; тик 1 = до _apply_initial_social)
B1_PRESENT_TICKS = {"attack": 14, "intimidate": 14, "warn": 8,   # покрытие клетки B в B1/A'
                    "observe": 14, "talk": 8, "idle": 14}

INPUT_FILES = [
    "backend/tests/sandbox/SUPERBOX/scenarios/bm_factorial_test.py",       # раннер факториала: клетки, окно, метрики
    "backend/tests/sandbox/SUPERBOX/scenarios/bm_factorial_isolation.py",  # изоляционный паттерн (основа ноги)
    "backend/tests/sandbox/SUPERBOX/scenarios/bm_aprime_offline.py",       # реюз _per_intent (семантика A')
    "config/calibration/test_presets/golden_fear_f70.yaml",                # пресет клетки B (N7d; содержит willpower=60 — живой Д-4)
    "backend/app/services/npc/decision_hub.py",                            # якорь инъекции
]

LEG_RUNNER = {
    "cell_key": "CELL-B_f70_tm60",
    "preset_rel": "config/calibration/test_presets/golden_fear_f70.yaml",
    "donor_module": "bm_factorial_test",   # импорт патчит _SCORE_LEGS донора (execute-tap)
}

# H1b-mini (E-BM1 B'): in-memory patch для захвата base до/после mask.
# In-memory patch: объединяет OFF-инъекцию и H1b-mini захват (замена MASK_OFF_PATCH).
# mode="on": base *= mask_mod (применяется), mask_application_enabled=True
# mode="off": base *= 1.0 (инъекция), mask_application_enabled=False
# Якорь: 4-строчный блок в decision_hub.py _score_all (N5d, ~строки 1114-1117).
H1B_MINI_PATCH = {
    "enabled": True,
    "file": "backend/app/services/npc/decision_hub.py",
    "old_block": (
        "            mask_mod = self._behavior_mask_modifier(intent_str, state)\n"
        "            if mask_mod != 1.0:\n"
        "                base *= mask_mod\n"
        "                components[\"mask\"] = round(mask_mod, 3)\n"
    ),
    "on_block": (
        "            mask_mod = self._behavior_mask_modifier(intent_str, state)\n"
        "            _h1b_base_before = base\n"
        "            if mask_mod != 1.0:\n"
        "                base *= mask_mod\n"
        "                components[\"mask\"] = round(mask_mod, 3)\n"
        "            components[\"_h1b_base_before_mask\"] = round(_h1b_base_before, 4)\n"
        "            components[\"_h1b_mask_mod\"] = round(mask_mod, 4)\n"
        "            components[\"_h1b_base_after_mask\"] = round(base, 4)\n"
        "            components[\"_h1b_mask_application_enabled\"] = True\n"
    ),
    "off_block": (
        "            mask_mod = self._behavior_mask_modifier(intent_str, state)\n"
        "            _h1b_base_before = base\n"
        "            if mask_mod != 1.0:\n"
        "                base *= 1.0  # E-BM1 B-prime mask-off (in-memory)\n"
        "                components[\"mask\"] = round(mask_mod, 3)\n"
        "            components[\"_h1b_base_before_mask\"] = round(_h1b_base_before, 4)\n"
        "            components[\"_h1b_mask_mod\"] = round(mask_mod, 4)\n"
        "            components[\"_h1b_base_after_mask\"] = round(base, 4)\n"
        "            components[\"_h1b_mask_application_enabled\"] = False\n"
    ),
    # H1b-mini2: захват входов risk_penalty (без повторного вычисления)
    "old_block_2": (
        "        return {\n"
        "            \"drive\": round(drive_score, 4),\n"
        "            \"emotion\": round(emotion_mod, 4),\n"
        "            \"relationship\": round(rel_mod, 4),\n"
        "            \"risk_penalty\": risk_penalty,\n"
    ),
    "new_block_2": (
        "        return {\n"
        "            \"drive\": round(drive_score, 4),\n"
        "            \"emotion\": round(emotion_mod, 4),\n"
        "            \"relationship\": round(rel_mod, 4),\n"
        "            \"risk_penalty\": risk_penalty,\n"
        "            # H1b-mini2: входы risk_penalty (строки — не входят в sum)\n"
        "            \"_h1b2_fear_rel\": f\"{round(fear, 4)}\",\n"
        "            \"_h1b2_drives_fear\": f\"{round(drives.get('fear', 0.0), 4)}\" if drives else None,\n"
        "            \"_h1b2_drives_control\": f\"{round(drives.get('control', 0.0), 4)}\" if drives else None,\n"
        "            \"_h1b2_perceived_risk\": f\"{round(risk, 4)}\",\n"
        "            \"_h1b2_event_distance\": f\"{getattr(event, 'distance', None)}\",\n"
        "            \"_h1b2_event_witness_count\": f\"{getattr(event, 'witness_count', None)}\",\n"
        "            \"_h1b2_event_success\": f\"{getattr(event, 'success', None)}\",\n"
        "            \"_h1b2_event_visible_threat_markers\": f\"{list(getattr(event, 'visible_threat_markers', []))}\",\n"
        "            \"_h1b2_event_scene_flags\": f\"{list(getattr(event, 'scene_flags', set())) if hasattr(event, 'scene_flags') else None}\",\n"
        "            \"_h1b2_recent_pressure\": f\"{(state.relationship_cache.get('player', {}) if isinstance(getattr(state, 'relationship_cache', None), dict) else {}).get('recent_pressure', None)}\",\n"
        "            \"_h1b3_pressure_events\": (state.relationship_cache.get('player', {}) if isinstance(getattr(state, 'relationship_cache', None), dict) else {}).get('_h1b3_pressure_events', []),\n"
    ),
    "file_3": "backend/app/services/memory/memory_manager.py",
    "old_block_3": (
        "            graph_weights[tid] = {\n"
        "                \"trust\": rel.get(\"trust\", 0.0),\n"
        "                \"fear\": rel.get(\"fear\", 0.0),\n"
        "                \"debt\": rel.get(\"debt\", 0.0),\n"
        "                \"recent_pressure\": min(recent_pressure, 100.0),\n"
        "            }\n"
    ),
    "new_block_3": (
        "            _h1b3_pe = []\n"
        "            for e in recent:\n"
        "                if isinstance(e, dict):\n"
        "                    if e.get(\"actor\") == tid or e.get(\"target\") == tid:\n"
        "                        _h1b3_pe.append({\"type\": e.get(\"type\") or e.get(\"event_type\"), \"actor\": e.get(\"actor\"), \"target\": e.get(\"target\"), \"importance\": e.get(\"importance\", 0.0)})\n"
        "                elif (hasattr(e, \"target_id\") and e.target_id == tid) or (hasattr(e, \"actor_id\") and e.actor_id == tid):\n"
        "                        _h1b3_pe.append({\"type\": getattr(e, \"event_type\", None), \"actor\": getattr(e, \"actor_id\", None), \"target\": getattr(e, \"target_id\", None), \"importance\": getattr(e, \"importance\", 0.0)})\n"
        "            graph_weights[tid] = {\n"
        "                \"trust\": rel.get(\"trust\", 0.0),\n"
        "                \"fear\": rel.get(\"fear\", 0.0),\n"
        "                \"debt\": rel.get(\"debt\", 0.0),\n"
        "                \"recent_pressure\": min(recent_pressure, 100.0),\n"
        "                \"_h1b3_pressure_events\": _h1b3_pe,\n"
        "            }\n"
    ),
}


def discover_hub_file() -> Path:
    hits = sorted(set(REPO_ROOT.glob("backend/**/decision_hub.py")))
    if not hits:
        raise SystemExit("[FAIL] decision_hub.py не найден — проверь структуру репозитория.")
    if len(hits) > 1:
        raise SystemExit(f"[FAIL] Найдено несколько decision_hub.py (неоднозначный якорь): {hits}")
    return hits[0]


def discover_anchor_lines(hub: Path) -> dict:
    text = hub.read_text(encoding="utf-8", errors="replace")
    out = {"suppression": [], "consumption": []}
    for n, line in enumerate(text.splitlines(), 1):
        if re.search(r"0\.8\s*-\s*0\.7", line):
            out["suppression"].append((n, line.strip()))
        elif re.search(r"suppression|mask", line) and "*" in line:
            out["consumption"].append((n, line.strip()))
    return out


def install_h1b_mini_capture(mode: str) -> str:
    """In-memory H1b-mini patch: захват base до/после mask + OFF-инъекция.

    mode="on": base *= mask_mod (применяется), mask_application_enabled=True
    mode="off": base *= 1.0 (инъекция), mask_application_enabled=False

    Обе ноги: захват _h1b_base_before_mask, _h1b_mask_mod, _h1b_base_after_mask.
    mask_application_enabled — из режима (ON/OFF), не из diff.

    Production-код на диске не меняется. exec в namespace модуля."""
    if not H1B_MINI_PATCH["enabled"]:
        raise SystemExit("[BLOCK] H1B_MINI_PATCH не финализирован.")
    if mode not in ("on", "off"):
        raise SystemExit(f"[FAIL] mode должен быть 'on' или 'off', получил {mode!r}")

    hub = REPO_ROOT / H1B_MINI_PATCH["file"]
    src = hub.read_text(encoding="utf-8")
    old_block = H1B_MINI_PATCH["old_block"]
    new_block = H1B_MINI_PATCH["on_block"] if mode == "on" else H1B_MINI_PATCH["off_block"]

    occurrences = src.count(old_block)
    if occurrences != 1:
        raise SystemExit(
            f"[FAIL] old_block дал {occurrences} совпадений (ожидалось ровно 1). "
            "Якорь сдвинулся (decision_hub рефакторили?) — обновить old_block ДО прогона.")

    patched_src = src.replace(old_block, new_block, 1)

    # H1b-mini2: второй блок — захват входов risk_penalty
    old_block_2 = H1B_MINI_PATCH["old_block_2"]
    new_block_2 = H1B_MINI_PATCH["new_block_2"]
    occ2 = patched_src.count(old_block_2)
    if occ2 != 1:
        raise SystemExit(
            f"[FAIL] old_block_2 дал {occ2} совпадений (ожидалось ровно 1). "
            "Якорь return-блока _score_components сдвинулся — обновить old_block_2."
        )
    patched_src = patched_src.replace(old_block_2, new_block_2, 1)

    # H1b-mini3: третий блок — захват pressure events из get_weights_for_decision
    # Патчит memory_manager.py (отдельный файл от decision_hub.py)
    mm_file = REPO_ROOT / H1B_MINI_PATCH["file_3"]
    mm_src = mm_file.read_text(encoding="utf-8")
    old_block_3 = H1B_MINI_PATCH["old_block_3"]
    new_block_3 = H1B_MINI_PATCH["new_block_3"]
    occ3 = mm_src.count(old_block_3)
    if occ3 != 1:
        raise SystemExit(
            f"[FAIL] old_block_3 дал {occ3} совпадений (ожидалось ровно 1). "
            "Якорь get_weights_for_decision return сдвинулся — обновить old_block_3."
        )
    patched_mm_src = mm_src.replace(old_block_3, new_block_3, 1)

    # P1/D-1: каноническое имя цепочки (ленивые импорты, walk-имена НЕ работают)
    dotted = ".".join(hub.relative_to(REPO_ROOT / "backend").with_suffix("").parts)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    mod = importlib.import_module(dotted)
    exec(compile(patched_src, f"{hub} (in-memory h1b-mini {mode})", "exec"), mod.__dict__)

    # H1b-mini3: применить патч к memory_manager.py
    mm_dotted = ".".join(mm_file.relative_to(REPO_ROOT / "backend").with_suffix("").parts)
    mm_mod = importlib.import_module(mm_dotted)
    exec(compile(patched_mm_src, f"{mm_file} (in-memory h1b-mini3)", "exec"), mm_mod.__dict__)

    return (
        f"h1b-mini in-memory patch ({mode}):\n"
        f"  file: {hub}\n  module: {dotted}\n"
        f"  mode: {mode} → mask_application_enabled={'True' if mode == 'on' else 'False'}\n"
        f"  capture: _h1b_base_before_mask, _h1b_mask_mod, _h1b_base_after_mask, _h1b_mask_application_enabled\n"
        f"  off-injection: {'applied (base *= 1.0)' if mode == 'off' else 'not applied (base *= mask_mod)'}"
    )


def _git(args: list) -> str:
    r = subprocess.run(["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"[FAIL] git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _significant_porcelain(porcelain_raw: str) -> str:
    """D-3 (самострел B5): вырезать СВОИ артефакты из status --porcelain.

    DIRT_IGNORE_PREFIXES уже фильтрует untracked_significant (ls-files), но не
    применяется к porcelain — и первая пара ног детерминированно даёт B5:
    OFF-нога создаёт reports/bprime_artifacts/ ПОСЛЕ своего паспорта, и
    ON-паспорт видит собственный мусор как «дерево изменилось между ногами».
    Чужие строки (M/D/?? вне префиксов) остаются: для компарабельности важна
    идентичность между ногами, а не отсутствие."""
    path_at = 3  # «XY » — два статус-символа + пробел (формат git porcelain)
    keep = []
    for l in porcelain_raw.splitlines():
        path = (l[path_at:] if len(l) > path_at else "").strip().strip('"')
        if path and any(path.startswith(pfx) for pfx in DIRT_IGNORE_PREFIXES):
            continue  # свой артефакт — не дрейф дерева; в сравнение не входит
        keep.append(l)
    return "\n".join(keep)


def capture_passport(tag: str) -> dict:
    """Паспорт ДО начала ноги: HEAD + dirt-стамп + untracked значимых корней + рантайм + входы."""
    porcelain = _significant_porcelain(_git(["status", "--porcelain"]))
    diff_hash = hashlib.sha256(_git(["diff"]).encode("utf-8")).hexdigest() if porcelain else "clean"
    untracked_significant = [
        l for l in _git(["ls-files", "--others", "--exclude-standard"] + SIGNIFICANT_ROOTS).splitlines()
        if l and not any(l.startswith(pfx) for pfx in DIRT_IGNORE_PREFIXES)
    ]
    inputs = {}
    for rel in INPUT_FILES:
        p = REPO_ROOT / rel
        inputs[rel] = sha256_file(p) if p.exists() else "MISSING"
    return {
        "tag": tag,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "head": _git(["rev-parse", "HEAD"]),
        "status_porcelain": porcelain,
        "diff_hash": diff_hash,
        "untracked_significant_roots": untracked_significant,
        "runtime_manifest": {"python": sys.version, "platform": sys.platform, "argv0": sys.argv[0]},
        "input_sha256": inputs,
    }


def passports_compatible(p_on: dict, p_off: dict) -> tuple:
    """Ровно ДВА исхода (вердикт Q3). Сравнение НЕ ограничено HEAD (вердикт Q3)."""
    d = []
    if p_on["head"] != p_off["head"]:
        d.append(f"HEAD различается: on={p_on['head'][:12]} off={p_off['head'][:12]} (сосед коммитил между ногами)")
    if p_on["status_porcelain"] != p_off["status_porcelain"]:
        d.append("status_porcelain различается: дерево изменилось между ногами")
    if p_on["diff_hash"] != p_off["diff_hash"]:
        d.append("diff_hash различается: локальные модификации изменились между ногами (HEAD может совпадать!)")
    if p_on["runtime_manifest"]["python"] != p_off["runtime_manifest"]["python"]:
        d.append("версия python различается между ногами")
    for rel in p_on["input_sha256"]:
        if p_on["input_sha256"][rel] != p_off["input_sha256"][rel]:
            d.append(f"вход изменился между ногами: {rel} "
                     f"(on={p_on['input_sha256'][rel][:12]} off={p_off['input_sha256'][rel][:12]})")
    for name, p in (("on", p_on), ("off", p_off)):
        for u in p["untracked_significant_roots"]:
            d.append(f"[{name}] необъяснённый untracked под значимым корнем: {u}")
    return ("COMPATIBLE", []) if not d else ("INCOMPATIBLE", d)


PRE_REGISTERED = {
    "cell": CELL,
    "source": "N4-таблица per_intent_common (reports/bm_aprime_offline.json), верификация: scripts/n4_verify.py",
    "mask_off_mean_prediction": {   # B'_off = A + F (эра-чувствительная проверка, НЕ причинная)
        "attack": -1.702422, "intimidate": -1.598872, "warn": -0.485929,
        "observe": 0.681829, "talk": -0.402914, "idle": -0.592443,
    },
    "on_off_contrast_prediction": {  # ГЛАВНАЯ причинная пререгистрация: ON - OFF по интентам
        "attack": 1.361308, "intimidate": 1.361329, "warn": 0.427116,
        "observe": 0.105778, "talk": -0.062936, "idle": -0.122964,
    },
    "tolerance": 0.10,   # max|остаток реконструкции| = 0.077 + запас; warn/talk — полувыборка
    "y1_direction": "y1(ON) - y1(OFF) ожидается сильно положительным (порядка +1.0..+1.3, из Δ_int=+1.209)",
    "formulation": "результат формулируется как причинный эффект ПОТРЕБЛЕНИЯ МНОЖИТЕЛЯ маски "
                   "(decision_hub:1116), не «полного эффекта маски»: контур deformation (600-628) "
                   "идентичен в обеих ногах (N7e).",
    "assumptions": [
        "эра не взаимодействует с трактом потребления маски (оба плеча в одной эре)",
        "сид/пресет клетки битово совпадают с B1 (иначе ON не обязан воспроизвести B)",
    ],
    "outcome_branches": {
        "B1": "ON == B1(B) численно, |OFF-(A+F)|<=tol, |(ON-OFF)-PRED|<=tol: причинный эффект "
              "потребления множителя подтверждён; реконструкция N4 закрыта каузально (клетка/эра).",
        "B2": "ON != B1(B) (сдвиг эры/базовой линии), НО |(ON-OFF)-PRED|<=tol: причинный контраст "
              "внутри эры подтверждён; абсолютные сравнения с B1 — условные (эра).",
        "B3": "|(ON-OFF)-PRED|>tol по attack/intimidate при остальных в допуске: остаточная "
              "асимметрия больше предсказанной -> components_trace (H1; туда же willpower — живой Д-4).",
        "B4": "ON ~ OFF (контраст ~ 0 по всем интентам): инъекция НЕ сработала (мёртвый путь класса "
              "Д-8) -> НЕТ выводов о маске; дефект фреймворка.",
        "B5": "паспорты INCOMPATIBLE: ноги некомпаративны -> блокировка результата, повтор при "
              "стабильном дереве.",
    },
}


def _per_intent_common(rec: dict):
    """Пер-интентные средние общего окна — РЕЮЗ bm_aprime_offline._per_intent (N7c).

    Та же функция, что произвела числа A'/пререгистрации -> ноль риска трансляции.
    Возвращает {intent: {mean, present_ticks}} или None, если сырьё отсутствует.
    """
    raw = rec.get("scores_raw") or rec.get("scores_per_tick")  # P2/D-2: ключ сырья — scores_per_tick (донор :66); 'scores_raw' — алиас ВЫХОДА _cell_metrics (:108)
    if not raw:
        return None
    import bm_aprime_offline as _aprime  # noqa: E402 (scenarios/ уже в sys.path к этому моменту)
    return _aprime._per_intent(raw, WINDOW)


def mode_check() -> int:
    print("== B' --check (статический, без симуляции) ==")
    here = Path(__file__).resolve().parent
    hub = discover_hub_file()
    print(f"[OK] decision_hub: {hub.relative_to(REPO_ROOT)}")
    print(f"[OK] имя модуля для инъекции (= имя цепочки): {'.'.join(hub.relative_to(REPO_ROOT / 'backend').with_suffix('').parts)}")
    anchors = discover_anchor_lines(hub)
    print(f"[INFO] строк формулы suppression: {len(anchors['suppression'])}")
    for n, l in anchors["suppression"]:
        print(f"   {n}: {l}")
    print(f"[INFO] кандидатов строки потребления ('*' + hint): {len(anchors['consumption'])}")
    for n, l in anchors["consumption"][:40]:
        print(f"   {n}: {l}")
    if H1B_MINI_PATCH["enabled"]:
        src = (REPO_ROOT / H1B_MINI_PATCH["file"]).read_text(encoding="utf-8", errors="replace")
        n1 = src.count(H1B_MINI_PATCH["old_block"])
        n2 = src.count(H1B_MINI_PATCH["old_block_2"])
        s1 = "OK" if n1 == 1 else "FAIL"
        s2 = "OK" if n2 == 1 else "FAIL"
        print(f"[{s1}] H1B_MINI_PATCH: old_block даёт {n1} совпадений (нужно ровно 1)")
        print(f"[{s2}] H1B_MINI_PATCH: old_block_2 даёт {n2} совпадений (нужно ровно 1)")
        # H1b-mini3: memory_manager.py — отдельный файл
        mm_src = (REPO_ROOT / H1B_MINI_PATCH["file_3"]).read_text(encoding="utf-8", errors="replace")
        n3 = mm_src.count(H1B_MINI_PATCH["old_block_3"])
        s3 = "OK" if n3 == 1 else "FAIL"
        print(f"[{s3}] H1B_MINI_PATCH: old_block_3 (memory_manager) даёт {n3} совпадений (нужно ровно 1)")
        if n1 != 1 or n2 != 1 or n3 != 1:
            print("        -> якорь сдвинулся; обновить old_block / old_block_2 / old_block_3 ДО прогона; --leg не запускать.")
    else:
        print("[BLOCK] H1B_MINI_PATCH не финализирован.")
    print(f"[OK] LEG_RUNNER: клетка {LEG_RUNNER['cell_key']}, пресет {LEG_RUNNER['preset_rel']}; "
          "нога = ядро донора in-process, патч до импорта цепочки (паттерн bm_factorial_isolation.py).")
    aprime = here / "bm_aprime_offline.py"
    print("[OK] bm_aprime_offline.py доступен для реюза _per_intent" if aprime.exists()
          else "[BLOCK] bm_aprime_offline.py не найден рядом — реюз per-intent невозможен.")
    print(f"[OK] INPUT_FILES: {len(INPUT_FILES)} (в т.ч. пресет клетки B и якорный decision_hub).")
    print(f"[OK] WINDOW: {WINDOW[0]}..{WINDOW[-1]} (канон B1, {len(WINDOW)} тиков); "
          f"B1 present_ticks референс: {B1_PRESENT_TICKS}")
    print("\n== Паспорт текущего состояния ==")
    print(json.dumps(capture_passport("check"), ensure_ascii=False, indent=2))
    print("\n== Пререгистрация (числа менять ПОСЛЕ просмотра данных запрещено) ==")
    print(json.dumps(PRE_REGISTERED, ensure_ascii=False, indent=2))
    return 0


def mode_leg(mode: str, window_confirmed: str) -> int:
    if not window_confirmed:
        raise SystemExit("[BLOCK] --window-confirmed обязателен (вердикт Q2). Без окна прогоны запрещены.")
    if not LEG_RUNNER.get("cell_key"):
        raise SystemExit("[BLOCK] LEG_RUNNER.cell_key не задан.")
    passport = capture_passport(f"leg-{mode}")
    print(f"[PASSPORT-{mode}]\n" + json.dumps(passport, ensure_ascii=False, indent=2))
    ART_DIR.mkdir(parents=True, exist_ok=True)
    (ART_DIR / f"passport_{mode}.json").write_text(
        json.dumps(passport, ensure_ascii=False, indent=2), encoding="utf-8")
    # sys.path зеркально bm_factorial_isolation.py — ДО инъекции (ей нужен импорт app.*):
    here = Path(__file__).resolve().parent
    backend_root = here.parents[3]
    for p in (str(here), str(backend_root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    if mode == "off":
        print(install_h1b_mini_capture("off"))
    else:
        print(install_h1b_mini_capture("on"))
    # Импорт цепочки раннера — ПОСЛЕ патча (патч действует в памяти ЭТОГО процесса).
    import bm_factorial_test as _f  # noqa: E402
    key = LEG_RUNNER["cell_key"]
    if key not in _f._CELLS:
        raise SystemExit(f"[FAIL] ключ клетки '{key}' отсутствует в bm_factorial_test._CELLS — "
                         "fail-loud вместо тихого no-op (урок Д-8).")
    # Ядро изоляционного раннера B1: run_id = ровно ключ клетки (etap-членство).
    rec, _fin = _f._donor._run_leg(key, _f._CELLS[key], True)
    metrics = {k: v for k, v in _f._cell_metrics(rec).items() if k != "scores_raw"}
    # Сырьё — ВСЕГДА (данные ноги не теряются даже при пустой per-intent агрегации):
    (ART_DIR / f"result_raw_{mode}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    per_intent = _per_intent_common(rec)
    coverage = {i: v.get("present_ticks") for i, v in per_intent.items()} if per_intent else None
    mt = metrics.get("mask_ticks")
    if not (isinstance(mt, (int, float)) and mt > 0):
        print(f"[WARN-{mode}] mask_ticks={mt} (ожидалось >0: маска обязана ЗАПИСЫВАТЬСЯ в обеих ногах; "
              "патч трогает только потребление). --compare заблокируется.")
    result = {
        "leg": mode,
        "cell": key,
        "preset": _f._CELLS[key],
        "preset_sha256": sha256_file(REPO_ROOT / _f._CELLS[key]),
        "metrics": metrics,
        "window": WINDOW,
        "per_intent_common": per_intent,
        "present_ticks": coverage,
        "present_ticks_b1_reference": B1_PRESENT_TICKS,
        "present_ticks_match_b1": (coverage == B1_PRESENT_TICKS) if coverage else None,
    }
    (ART_DIR / f"result_{mode}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE-{mode}] metrics={json.dumps(metrics, ensure_ascii=False)}")
    if per_intent:
        print(f"[DONE-{mode}] per_intent_common="
              + json.dumps({i: round(v['mean'], 6) for i, v in per_intent.items()}, ensure_ascii=False))
        if coverage != B1_PRESENT_TICKS:
            print(f"[WARN-{mode}] present_ticks отличается от B1 ({coverage} vs {B1_PRESENT_TICKS}) — "
                  "индикатор эра/сид-дрифа (кормит ветку B2).")
    else:
        print(f"[WARN-{mode}] per-intent агрегация пуста (scores_raw отсутствует?); сырьё в "
              f"result_raw_{mode}.json; --compare заблокируется.")
    print(f"[ART-{mode}] {ART_DIR}")
    return 0


def mode_compare() -> int:
    p_on = json.loads((ART_DIR / "passport_on.json").read_text(encoding="utf-8"))
    p_off = json.loads((ART_DIR / "passport_off.json").read_text(encoding="utf-8"))
    verdict, discrepancies = passports_compatible(p_on, p_off)
    print(f"== passports_compatible: {verdict} ==")
    for dsc in discrepancies:
        print(f"  - {dsc}")
    if verdict == "INCOMPATIBLE":
        print("[B5] Ноги некомпаративны. Каузальные выводы ЗАПРЕЩЕНЫ. Повтор при стабильном дереве.")
        return 2
    on = json.loads((ART_DIR / "result_on.json").read_text(encoding="utf-8"))
    off = json.loads((ART_DIR / "result_off.json").read_text(encoding="utf-8"))
    # Гейт 1: маска ЗАПИСАНА в обеих ногах (патч трогает только потребление):
    mt_on = (on.get("metrics") or {}).get("mask_ticks")
    mt_off = (off.get("metrics") or {}).get("mask_ticks")
    if not (isinstance(mt_on, (int, float)) and mt_on > 0
            and isinstance(mt_off, (int, float)) and mt_off > 0):
        print(f"[BLOCK] mask_ticks ног ненадёжен (on={mt_on}, off={mt_off}) — каузальные выводы запрещены.")
        return 2
    # Гейт 2: per-intent агрегация присутствует:
    if not on.get("per_intent_common") or not off.get("per_intent_common"):
        print("[BLOCK] per_intent_common отсутствует в ноге/ногах — сравнение невозможно (сырьё в result_raw_*).")
        return 2
    tol = PRE_REGISTERED["tolerance"]
    coverage_drift = []
    for i in PRE_REGISTERED["on_off_contrast_prediction"]:
        pt_on = on["per_intent_common"][i].get("present_ticks")
        pt_off = off["per_intent_common"][i].get("present_ticks")
        if pt_on != B1_PRESENT_TICKS.get(i) or pt_off != B1_PRESENT_TICKS.get(i):
            coverage_drift.append(f"{i}: on={pt_on} off={pt_off} (B1={B1_PRESENT_TICKS.get(i)})")
    report = {"verdict_passports": verdict, "preregistration": PRE_REGISTERED,
              "mask_ticks": {"on": mt_on, "off": mt_off},
              "coverage_drift": coverage_drift, "contrasts": {}, "branch_assignment": None}
    for intent, pred in PRE_REGISTERED["on_off_contrast_prediction"].items():
        m_on = on["per_intent_common"][intent]["mean"]
        m_off = off["per_intent_common"][intent]["mean"]
        obs = m_on - m_off
        dev = obs - pred
        report["contrasts"][intent] = {"on": m_on, "off": m_off, "observed_contrast": obs,
                                       "predicted": pred, "deviation": dev,
                                       "within_tol": abs(dev) <= tol}
    all_attackish = all(report["contrasts"][i]["within_tol"] for i in ("attack", "intimidate"))
    all_zero = all(abs(c["observed_contrast"]) < 0.01 for c in report["contrasts"].values())
    if all_zero:
        report["branch_assignment"] = "B4 (инъекция не сработала — выводов о маске НЕТ)"
    elif all_attackish and all(c["within_tol"] for c in report["contrasts"].values()):
        report["branch_assignment"] = "B1/B2 (причинный контраст подтверждён; B1 vs B2 — по совпадению ON с B1(B))"
    elif all_attackish:
        report["branch_assignment"] = "B3' (промах вне attack/intimidate -> components_trace)"
    else:
        report["branch_assignment"] = "B3 (промах по attack/intimidate -> components_trace)"
    if coverage_drift:
        report["branch_assignment"] += " + coverage-drift (эра-чувствительность: см. ветку B2)"
    (ART_DIR / "compare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n[INTERPRETATION-блок — отдельно от сырых данных; см. compare_report.json; "
          "формулировка: эффект ПОТРЕБЛЕНИЯ МНОЖИТЕЛЯ маски (decision_hub:1116).]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="E-BM1 B' paired on/off protocol (window-gated)")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--leg", choices=["on", "off"])
    ap.add_argument("--window-confirmed", default="")
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    if a.check:
        return mode_check()
    if a.leg:
        return mode_leg(a.leg, a.window_confirmed)
    if a.compare:
        return mode_compare()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
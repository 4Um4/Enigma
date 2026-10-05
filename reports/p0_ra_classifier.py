"""path: /project/reports/p0_ra_classifier.py

Назначение: P0-4 (SR-1, Phase 0 GO): R-a LLM-router — измерение точности
    дешёвого LLM-классификатора семейств на probe-корпусе. INV-SR-1
    (вердикт Мастера): выход СТРОГО {"module": "dialogue_provenance" |
    "dialogue_identity" | "none"} — никогда акты/типы; парс-отказ/ошибка
    вызова -> none (∅) + громкий лог. Промпт строится ТОЛЬКО из
    контраст-блоков модулей (verbatim, corpus-foreign by design);
    определительные предложения enum-tail НЕ включены (гигиена замера:
    они содержат корпусную фразу AB-PROV[0] дословно и near-dupe
    PROV-негатива; стволовое покрытие уже измерено R-c baseline).
    Ground truth — единый источник: p0_rc_baseline (аудит P0-1).
    Детерминизм: temperature=0.0 + seed=KernelRNG(salt=фраза) — контракт
    компрессора; A/A второй проход = гварь (S316: warm-протокол).
Зависимости: llama-server через scripts.llm_server_manager (прецедент
    corpus script), app-модули read-only (loader, KernelRNG),
    p0_rc_baseline, stdlib. app/ не изменяется.
Запуск: python reports/p0_ra_classifier.py (сервер стартует скриптом;
    ENIGMA_DET_KEEP_SERVER=1 — оставить тёплый сервер для повторов).
"""

import atexit
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))              # scripts.llm_server_manager
sys.path.insert(0, str(_ROOT / "backend"))  # app.* — read-only

from p0_rc_baseline import (  # единый источник ground truth
    _ID_CONTROL_TEXTS,
    _PROV_CONTROL_TEXTS,
    _assert_invariants,
    _gold,
    _load_corpus,
)

from app.services.input.semantic_library import load_module
from app.services.npc.kernel_rng import KernelRNG

# Выравнивание с production call-surface (урок INVALID RUN: хардкод 127.0.0.1
# отвергался — llama-server слушает на settings.llama_cpp_server_url; менеджер
# health-ждёт именно его, харнесс-проба ходит на localhost; прецедент импорта
# settings внутри клиента — llm_compressor_client.__init__):
from app.core.config import settings

_BASE_URL = settings.llama_cpp_server_url
_BOUNDARY = "BOUNDARY"
_GROUPS = ("PROV", "ID", "EMPTY")


def _build_system_prompt() -> str:
    """Промпт из контраст-блоков модулей (единственный источник
    семействных знаний). Гигиена: корпусные фразы исключены — потому
    enum-tail (содержит AB-PROV[0] дословно) не включён."""
    prov = load_module("dialogue_provenance")
    ident = load_module("dialogue_identity")
    return (
        "Ты — маршрутизатор семантических модулей. Игрок вводит фразу; "
        "выбери ОДИН семантический модуль, знание которого нужно для "
        "разбора этой фразы, или none, если ни один не нужен. Ты НЕ "
        "разбираешь фразу по актам и не определяешь её смысл — это "
        "делает другой обработчик. Выбирай строго по границам, заданным "
        "контрастными парами ниже.\n\n"
        "Модуль dialogue_provenance — граница «источник знания "
        "собеседника vs событие мира»:\n"
        + prov.contrast_block.strip()
        + "\n\nМодуль dialogue_identity — граница «имя собеседника vs "
        "имя третьего лица»:\n"
        + ident.contrast_block.strip()
        + "\n\nПравила: фраза спрашивает об ИСТОЧНИКЕ знания собеседника "
        "(кто ему сообщил, откуда он знает) — dialogue_provenance; фраза "
        "спрашивает об имени/идентичности СОБЕСЕДНИКА игрока — "
        "dialogue_identity; вопросы о третьих лицах (кто что сделал, "
        "как кого зовут) и все прочие фразы — none.\n\n"
        "Ответ строго JSON без markdown: "
        '{"module": "dialogue_provenance"} или '
        '{"module": "dialogue_identity"} или {"module": "none"}.'
    )


def _call(system_prompt: str, user_text: str) -> Tuple[Optional[str], int]:
    """Один вызов классификатора. Контракт детерминизма компрессора:
    temperature=0.0, seed=KernelRNG(salt=фраза). Отказ -> (None, seed):
    роутер падает в ∅, измерение не падает (INV-SR-1)."""
    import urllib.request

    seed = KernelRNG(tick=0, npc_id="p0_ra_router", salt=user_text).randint(0, 2**31 - 1)
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
        "seed": seed,
        "response_format": {"type": "json_object"},
    }
    try:
        req = urllib.request.Request(
            f"{_BASE_URL}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=60.0) as response:
            resp = json.loads(response.read().decode("utf-8"))
            return str(resp["choices"][0]["message"]["content"]), seed
    except Exception as e:  # L4: причина видима; отказ -> ∅ (INV-SR-1)
        print(f"[ROUTER-ERROR] {type(e).__name__}: {e}")
        return None, seed


def _parse_route(content: Optional[str]) -> Tuple[str, bool]:
    """Ответ -> (семья, parse_error). Любой отказ -> EMPTY (∅)."""
    if content is None:
        return "EMPTY", True
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return "EMPTY", True
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "EMPTY", True
    module = str(data.get("module", "")).strip()
    if module == "dialogue_provenance":
        return "PROV", False
    if module == "dialogue_identity":
        return "ID", False
    if module == "none":
        return "EMPTY", False
    return "EMPTY", True


def main() -> None:
    try:
        from scripts.llm_server_manager import kill_llama_server, start_llama_server
        print("Запускаю LLM-сервер для R-a classifier...")
        llm_ok = start_llama_server()
        if os.environ.get("ENIGMA_DET_KEEP_SERVER") != "1":
            atexit.register(kill_llama_server)
    except Exception as e:
        print(f"ВНИМАНИЕ: менеджер LLM недоступен ({e}).")
        llm_ok = False
    if not llm_ok:
        print("ИТОГО P0-4: INVALID RUN (LLM недоступна) — не является измерением.")
        return

    entries = _load_corpus()
    _assert_invariants(entries)
    texts = [t for _, t, _ in entries]
    golds = [_gold(cls, text) for cls, text, _ in entries]
    system_prompt = _build_system_prompt()

    # Прогрев (нейтральная фраза — НЕ корпусная)
    for _attempt in range(12):
        content, _ = _call(system_prompt, "привет")
        if content is not None:
            break
        time.sleep(5.0)
    else:
        print("ИТОГО P0-4: INVALID RUN (модель не прогрелась).")
        return

    print("=== P0-4: R-a LLM ROUTER (INV-SR-1: module_id|none, никогда акты) ===")
    print("--- SYSTEM PROMPT (a priori; контраст-пары verbatim, корпусные фразы исключены) ---")
    print(system_prompt)
    print("--- конец промпта ---")

    def _run_pass(tag: str) -> Tuple[List[str], List[float]]:
        routes: List[str] = []
        lats: List[float] = []
        for i, (cls, text, _expected) in enumerate(entries):
            t0 = time.monotonic()
            content, seed = _call(system_prompt, text)
            lats.append(time.monotonic() - t0)
            route, parse_err = _parse_route(content)
            routes.append(route)
            print(
                f"[{tag}] {cls:9} {text!r} -> {route:5} (gold={golds[i]:7}) "
                f"lat={lats[-1]:.2f}s seed={seed} err={int(parse_err)}"
            )
            if parse_err and content is not None:
                print(f"    RAW: {content[:160]!r}")
        return routes, lats

    routes_a, lats_a = _run_pass("A1")
    routes_b, _ = _run_pass("A2")
    mismatches = [
        (texts[i], routes_a[i], routes_b[i])
        for i in range(len(entries))
        if routes_a[i] != routes_b[i]
    ]

    # Метрики — по проходу A1 (A/A = гварь детерминизма)
    confusion = {}
    prov_misses: List[str] = []
    id_misses: List[str] = []
    id_fps: List[str] = []
    boundary_routes: List[Tuple[str, str]] = []
    prov_fp_controls = 0
    prov_fp_other = 0
    cross_family = 0
    for i, (cls, text, _) in enumerate(entries):
        gold, route = golds[i], routes_a[i]
        if gold == _BOUNDARY:
            boundary_routes.append((text, route))
            continue
        confusion[(gold, route)] = confusion.get((gold, route), 0) + 1
        if gold == "PROV" and route != "PROV":
            prov_misses.append(text)
            if route == "ID":
                cross_family += 1
        if gold == "EMPTY" and route == "PROV":
            if text in _PROV_CONTROL_TEXTS:
                prov_fp_controls += 1
            else:
                prov_fp_other += 1
        if gold == "ID" and route != "ID":
            id_misses.append(text)
        if gold == "EMPTY" and route == "ID":
            id_fps.append(text)

    prov_total = sum(v for (g, _), v in confusion.items() if g == "PROV")
    id_total = sum(v for (g, _), v in confusion.items() if g == "ID")
    empty_total = sum(v for (g, _), v in confusion.items() if g == "EMPTY")

    print()
    print(f"gold: PROV={prov_total} ID={id_total} EMPTY={empty_total} boundary={len(boundary_routes)}")
    print()
    print("--- Конфьюжн (gold -> route), проход A1 ---")
    for gold in _GROUPS:
        cells = "  ".join(f"{r}:{confusion.get((gold, r), 0):3}" for r in _GROUPS)
        print(f"{gold:6} {cells}")
    print()
    print("--- PROV routing (основная количественная метрика SR-1) ---")
    print(f"PROV recall: {prov_total - len(prov_misses)}/{prov_total}")
    for m in prov_misses:
        print(f"  MISS: {m!r}")
    print(f"PROV FP: контрольные PROV-негативы: {prov_fp_controls} | прочие EMPTY: {prov_fp_other}")
    print(f"cross-family PROV->ID: {cross_family}")
    print()
    print("--- Identity (diagnostic arm) ---")
    print(f"ID recall: {id_total - len(id_misses)}/{id_total}")
    for m in id_misses:
        print(f"  MISS: {m!r}")
    print(f"ID FP (EMPTY->ID): {len(id_fps)}")
    for m in id_fps:
        print(f"  FP: {m!r}")
    kto_route = routes_a[texts.index("Кто ты?")]
    print(f"F5: 'Кто ты?' -> {kto_route} (обязательство: ID)")
    print()
    print("--- Boundary (диагностика, НЕ ground truth; Q-1) ---")
    for text, route in boundary_routes:
        print(f"  {text!r} -> {route}")
    print()
    print("--- Детерминизм A/A и latency ---")
    print(f"A/A mismatches: {len(mismatches)}")
    for t, r1, r2 in mismatches:
        print(f"  {t!r}: A1={r1} A2={r2}")
    lat_mean = sum(lats_a) / len(lats_a) if lats_a else 0.0
    print(f"latency A1: mean={lat_mean:.2f}s max={max(lats_a):.2f}s (90 вызовов)")
    print()
    print(
        f"ИТОГО P0-4: PROV recall {prov_total - len(prov_misses)}/{prov_total}, "
        f"PROV-FP {prov_fp_controls + prov_fp_other}, "
        f"ID recall {id_total - len(id_misses)}/{id_total}, ID-FP {len(id_fps)}, "
        f"cross-family {cross_family}, F5 {'PASS' if kto_route == 'ID' else 'FAIL'}, "
        f"A/A={len(mismatches)}, boundary {len(boundary_routes)} логировано"
    )


if __name__ == "__main__":
    main()
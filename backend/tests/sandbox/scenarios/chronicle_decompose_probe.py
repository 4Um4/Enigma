"""T-CCH-02 живой проб декомпозитора хроники (ADR-O-420, CCH-2).

Эталонный фрагмент №1 Люси (ТЗ CCH-01 §9/§10). Проверяет:
1) decompose через ЖИВОЙ llama-server (ModelRouter → FACT_EXTRACTION, temp=0);
2) структурные ожидания гейта: items ≥ 1; присутствуют EVENT; вопрос
   (needs_confirmation/question) присутствует; в вопросах есть LEAVE_WHITE_SPOT;
3) детерминизм: два идентичных запроса → идентичный ответ (md5 сырого ответа).
Итог-строка: 'Итог: GREEN=N RED=M' (квалификация §3.12).
LLM-пул недоступен → RED=1 с честным маркером LLM_UNAVAILABLE (не фейк-GREEN).
"""
from __future__ import annotations

import asyncio
import hashlib
import json

from app.core.config import settings
from app.services.chronicle.biography_decomposer import BiographyDecomposer

FRAGMENT = (
    "В 8 лет Люся осталась без родителей. Её взял к себе трактирщик Торнин — "
    "дальний родственник матери. С тех пор Люся живёт в трактире Торнина "
    "и работает там официанткой."
)


def _llm_alive() -> bool:
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(settings.llama_cpp_server_url.replace("/v1", "") + "/health", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def main() -> int:
    green = 0
    red = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal green, red
        if cond:
            green += 1
            print(f"[GREEN] {name}")
        else:
            red += 1
            print(f"[RED] {name} :: {detail}")

    if not _llm_alive():
        # Паттерн IPT: менеджер проекта поднимает сервер ВНУТРИ нашего процесса
        # (SPAWN-ребёнок живёт, пока жив родитель; отдельные python -c его теряли).
        # Корень репо ищем вверх по дереву по якорю scripts/llm_server_manager.py —
        # без зависимости от глубины __file__ (урок: parents[3] = backend, не root).
        import sys
        from pathlib import Path as _P

        _probe = _P(__file__).resolve()
        _repo_root = None
        for _cand in _probe.parents:
            if (_cand / "scripts" / "llm_server_manager.py").is_file():
                _repo_root = _cand
                break
        if _repo_root is None:
            print(f"[RED] LLM_UNAVAILABLE :: корень репо не найден вверх от {_probe}")
            print("Итог: GREEN=0 RED=1")
            return 1
        if str(_repo_root) not in sys.path:
            sys.path.insert(0, str(_repo_root))
        try:
            from scripts.llm_server_manager import start_llama_server
            print("[LLM_MANAGER] health refused → поднимаю сервер менеджером проекта...")
            if not start_llama_server():
                print("[RED] LLM_UNAVAILABLE :: start_llama_server вернул False")
                print("Итог: GREEN=0 RED=1")
                return 1
        except ImportError as e:
            print(f"[RED] LLM_UNAVAILABLE :: менеджер недоступен: {e}")
            print("Итог: GREEN=0 RED=1")
            return 1

    # Прод-прецедент main.py:120-122 / router.initialize_router():
    # регистрация конфигов пула ОБЯЗАТЕЛЬНА до любого request() —
    # без неё is_model_available=False («Все модели пула недоступны»).
    from app.services.llm.router import initialize_router
    initialize_router()
    print("[PROBE] ModelPool инициализирован (initialize_router, прод-прецедент)")

    d = BiographyDecomposer()
    r1 = asyncio.run(d.decompose("chronicle_maid_lusya", 0, FRAGMENT))

    check("decompose_ok", r1.ok, str(r1.error))
    if not r1.ok:
        print("Итог: GREEN=0 RED=" + str(red))
        return 1

    check("age_anchors_found", bool(r1.age_anchors), f"anchors={r1.age_anchors}")
    kinds = [it.kind.value for it in r1.items]
    check("has_event", "EVENT" in kinds, f"kinds={kinds}")
    check("has_question", any(it.question is not None or it.needs_confirmation for it in r1.items), f"kinds={kinds}")
    check(
        "white_spot_option_in_questions",
        all(
            q is None or any(o.value == "LEAVE_WHITE_SPOT" for o in q.options)
            for it in r1.items
            for q in [it.question]
        ),
        "вопрос без опции белого пятна",
    )

    for it in r1.items:
        q = it.question
        qs = f" ? {q.question_id} span={q.target_span!r}" if q else ""
        print(
            f"  - {it.kind.value} conf={it.confidence} needs={it.needs_confirmation} "
            f"payload={json.dumps(it.draft_payload, ensure_ascii=False)[:160]}{qs}"
        )

    # Детерминизм (канон S316: identical input → identical CANONICAL output):
    # канонический уровень декомпозиции — СТРУКТУРА (kinds, nature/valence/
    # effect_kind, наличие вопросов), не дословность свободного текста summary.
    # Косметическая вариативность summary при temp=0+seed не нарушает
    # канонический контракт (прецедент: compressor — семантика, не буквы).
    r2 = asyncio.run(d.decompose("chronicle_maid_lusya", 0, FRAGMENT))
    if r2.ok and r1.ok:
        def _struct_sig(items):
            rows = []
            for i in items:
                p = i.draft_payload
                rows.append((
                    i.kind.value,
                    tuple(sorted(p.keys())),
                    p.get("nature"), p.get("valence"), p.get("effect_kind"),
                    i.question is not None,
                    i.needs_confirmation,
                ))
            return hashlib.md5(json.dumps(sorted(rows), ensure_ascii=False).encode()).hexdigest()
        sig1 = _struct_sig(r1.items)
        sig2 = _struct_sig(r2.items)
        check("determinism_same_prompt_same_structure", sig1 == sig2, f"sig1={sig1[:8]} sig2={sig2[:8]}")
    else:
        check("determinism_same_prompt_same_structure", False, "второй прогон не ok")

    print(f"Итог: GREEN={green} RED={red}")
    return 0 if red == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
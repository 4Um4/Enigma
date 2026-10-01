"""path: /project/backend/tests/sandbox/SUPERBOX/scenarios/m1_self_intro_probe.py

Назначение: P1 (вердикт Мастера) — M1-проба вариативности SELF_INTRODUCTION.
    Батч поверхностей одной семантики -> доля распознанных
    SELF_INTRODUCTION{name непустое}. БЕЙЗЛАЙН до few-shot-патча и
    ПОСТ-ПАТЧ — тем же батчем, дельта = эффект few-shot.
    Контрасты (К1/К2) защищают от ложно-сработавших.
Зависимости: app.services.input.intent_compressor.
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.m1_self_intro_probe; cd ..
"""

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.intent_profile import IntentSemanticField

BATCH = [
    # (фраза, ожидаем SELF_INTRODUCTION)
    ("Я Мю.", True),
    ("Меня зовут Мю.", True),
    ("Имя мне Мю.", True),
    ("Я — Мю.", True),
    ("Привет, я Мю.", True),
    ("Здравствуй, меня зовут Мю.", True),
    ("Кстати, я Мю.", True),
    ("Я — Мю, а ты кто?", True),
    ("Меня зовут Мю. Кто здесь главный?", True),
    # Контрасты: имя НЕ представление игрока
    ("Я слуга этого дома десять лет.", False),
    ("Я устал.", False),
]


def _acts_of(field: IntentSemanticField) -> list:
    return list(getattr(field, "semantic_acts", []) or [])


def _intro_name(field: IntentSemanticField) -> str:
    for a in _acts_of(field):
        if isinstance(a, dict) and a.get("type") == "SELF_INTRODUCTION":
            params = a.get("params") or {}
            return str(params.get("name") or "")
    return ""


async def main() -> None:
    from app.services.input.intent_compressor import IntentCompressor
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient

    compressor = IntentCompressor(LlamaCppCompressorClient())
    ok = 0
    false_positive = 0
    total = len(BATCH)
    print("=== M1 SELF_INTRO PROBE ===")
    for phrase, expect_intro in BATCH:
        field = await compressor.compress(phrase, {})
        name = _intro_name(field)
        got = bool(name)
        status = "OK"
        if expect_intro and got:
            ok += 1
        elif not expect_intro and not got:
            pass
        elif not expect_intro and got:
            false_positive += 1
            status = "FALSE-POSITIVE"
        else:
            status = "MISS"
        print(
            f"[{status}] {phrase!r} -> name={name!r} "
            f"acts={[a.get('type') for a in _acts_of(field)]}"
        )
    print(
        f"\nИТОГО M1: recognition={ok}/9, false_positives={false_positive}/2, "
        f"target recognition>=8/9 (~89%)"
    )


if __name__ == "__main__":
    asyncio.run(main())
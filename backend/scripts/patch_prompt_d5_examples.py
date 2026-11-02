#!/usr/bin/env python3
"""CCH-12 Fix 3: позитивные примеры EFFECT/LOCATION/EVENT в D5.

Добавляет в существующий блок D5 (refined) конкретные примеры из
биографии Орма, чтобы LLM не путала:
  - EFFECT (последствие) vs TRAIT_SEED vs PORTRET
  - LOCATION (место) vs PORTRET
  - EVENT (действие-причина) vs PORTRET

Идемпотентный: проверяет маркер D5-EXAMPLES перед применением.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROMPT_PATH = Path("backend/prompts/chronicle_decompose_system.txt")
MARKER = "D5-EXAMPLES"

EXAMPLES_BLOCK = """\
Позитивные примеры (из биографии Орма — для калибровки):

ПРИМЕР D5-EFFECT (физическое последствие):
  Фрагмент: «Обожжённые руки в старых ожогах — рукопожатие, которого
            избегают.»
  ВЕРНО: { kind: EFFECT,
           summary: "обожжённые руки в старых ожогах",
           effect_kind: "custom",
           target_hint: null }
  НЕВЕРНО: { kind: TRAIT_SEED, trait: "обожжённые руки" }
  НЕВЕРНО: { kind: PORTRET, statement: "обожжённые руки" }
  Основание: это физическое последствие работы кузнеца, не черта
  характера и не внутреннее состояние.

ПРИМЕР D5-LOCATION (место):
  Фрагмент: «Кузня — пристройка таверны: над головой гнома кровля,
            по сути принадлежащая Торнину.»
  ВЕРНО: { kind: LOCATION,
           summary: "кузня — пристройка таверны",
           name_hint: "кузня" }
  НЕВЕРНО: { kind: PORTRET, statement: "кузня — пристройка таверны" }
  Основание: это место, не характеристика персонажа.

ПРИМЕР D5-EVENT (действие-причина):
  Фрагмент: «146 лет, из которых он кузнец в городе уже 57 лет.»
  ВЕРНО: { kind: EVENT,
           summary: "стал кузнецом в городе",
           day: null,
           duration_years: 57 }
  НЕВЕРНО: { kind: PORTRET, statement: "стал кузнецом" }
  НЕВЕРНО: { kind: EFFECT, effect_kind: "occupation" } (если есть
            явное событие «стал» — это EVENT, не EFFECT)
  Основание: «стал кузнецом» — это действие-событие с duration_years
  (57 лет). EFFECT для occupation используется, когда профессия —
  состояние без явного события.

ПРИМЕР D5-EFFECT-OCCUPATION (занятие как состояние):
  Фрагмент: «кузнец Орм: гном» (шапка, без события «стал»)
  ВЕРНО: { kind: EFFECT,
           summary: "кузнец по профессии",
           effect_kind: "occupation",
           target_hint: null }
  НЕВЕРНО: { kind: TRAIT_SEED, trait: "кузнец" }
  Основание: «кузнец» в шапке — это занятие-состояние (EFFECT с
  effect_kind=occupation), не черта характера. Но если в тексте есть
  «стал кузнецом» — это EVENT, не EFFECT.

<!-- D5-EXAMPLES -->
"""


def main() -> int:
    if not PROMPT_PATH.exists():
        print(f"ERROR: {PROMPT_PATH} not found", file=sys.stderr)
        return 2

    text = PROMPT_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print(f"[skip] D5 examples already applied (marker {MARKER} found)")
        return 0

    # Вставляем перед D6 (D5 → D6 → D7 → D8). D6 начинается с "D6. ЛИМИТ"
    anchor = "D6. ЛИМИТ НА ФРАГМЕНТ (hard cap)"
    if anchor not in text:
        print(
            f"ERROR: anchor '{anchor}' not found — D5 block structure changed",
            file=sys.stderr,
        )
        return 3

    new_text = text.replace(anchor, EXAMPLES_BLOCK + "\n" + anchor)
    PROMPT_PATH.write_text(new_text, encoding="utf-8")
    print(f"[ok] D5 examples inserted before D6")
    print(f"     size: {len(text)} -> {len(new_text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
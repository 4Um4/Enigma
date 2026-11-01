# backend/scripts/patch_prompt_d5_refinement.py
# Идемпотентное уточнение D5: анти-регрессия EFFECT/LOCATION/DESIRE
import sys, pathlib

PROMPT_PATH = pathlib.Path("backend/prompts/chronicle_decompose_system.txt")
MARKER = "D5-REFINED"

# Заменяем существующий блок D5 целиком
OLD_D5 = """D5. PORTRET приоритет над TRAIT_SEED для характерологических описаний

Если утверждение описывает «какой персонаж» / «как его оценивают» /
«какую роль играет» — это PORTRET, не TRAIT_SEED.

Признаки PORTRET-утверждения:
  - оценка/мнение («не опасен», «не амбициозен», «удобный»)
  - метафора-описание («мебель города», «инструмент»)
  - социальная роль («кузнец», «информатор», «старейшина»)
  - демографический факт («гном», «живёт здесь 57 лет»)
  - мотив-объяснение («не из хитрости, из привычки»)
  - утверждение о балансе/стратегии («стратегия выживания»)

PORTRET.statement = исходная фраза целиком (дословно).
PORTRET.traits = массив слов-характеристик (0..5); может быть ПУСТЫМ,
если в тексте нет полноценного поведенческого паттерна.

TRAIT_SEED — это УСТОЙЧИВАЯ ЧЕРТА ПОВЕДЕНИЯ, наблюдаемая в паттернах
действий: «привык держать всё в себе», «не объясняет мотивов»,
«избегает толпы». Это можно ПОКАЗАТЬ в действии, а не просто
УТВЕРДИТЬ.

АНТИПРИМЕР D5 (характерология как TRAIT_SEED):
  items: [
    { kind: TRAIT_SEED, trait: "не опасен", evidence: "..." },
    { kind: TRAIT_SEED, trait: "не амбициозен", evidence: "..." },
    { kind: TRAIT_SEED, trait: "мебель города", evidence: "..." },
    { kind: TRAIT_SEED, trait: "из привычки", evidence: "..." }
  ]
  ← НЕВЕРНО: это всё STATE-описания, не черты поведения.
  ВЕРНО: собрать их в ОДИН PORTRET с statement = фраза целиком,
  traits: [] (пусто, т.к. паттернов поведения тут нет)."""

NEW_D5 = """D5. PORTRET vs TRAIT_SEED vs другие kind

PORTRET — внутреннее состояние, мировоззрение, самоинтерпретация,
психологическая характеристика. Это НЕ механический приоритет над
другими kind: PORTRET поглощает утверждение ТОЛЬКО если оно не
подходит под EFFECT / LOCATION / EVENT / DESIRE_SEED / TRAIT_SEED.

Иерархия выбора kind (проверяй сверху вниз):
  1. EVENT — действие или изменение во времени. Маркеры: глагол
     совершенного вида («умер», «стал», «предупредил»), временной
     якорь (years_ago / duration_years / at_age).
  2. EFFECT — последствие для тела, личности или статуса.
     draft_payload: effect_kind (trauma|loss|gain|secret|skill|
     residence|guardianship|occupation|custom).
     Маркеры: «травма», «потерял», «приобрёл», занятие как результат
     («стал кузнецом» — если это событие-причина), физическое
     последствие («обожжённые руки»).
  3. LOCATION — место или пространственный объект.
     draft_payload: name_hint.
     Маркеры: «кузня», «таверна», «город», топоним.
  4. DESIRE_SEED — желаемое будущее состояние, намерение, мечта.
     Маркеры: «хочет», «мечтает», «планирует», «думает получить».
     Граница: случилось → EVENT; мечтается → DESIRE_SEED.
  5. RELATIONSHIP — устойчивое отношение к другому (человеку или
     организации). Маркеры: «друг», «враг», «терпит», «боится».
  6. BELIEF_SEED — реактивное убеждение о мире (belief_type=danger
     или player_hostile). Маркеры: правило-из-опыта, обобщение.
  7. TRAIT_SEED — устойчивая характеристика или привычка,
     наблюдаемая в паттернах действий: «привык держать всё в себе»,
     «не объясняет мотивов». Можно ПОКАЗАТЬ в действии.
  8. PORTRET — внутреннее состояние / оценка / метафора, не
     подходящее под пункты 1–7. statement = фраза целиком.

PORTRET.statement = исходная фраза целиком (дословно).
PORTRET.traits = массив слов-характеристик (0..5); может быть ПУСТЫМ.

АНТИПРИМЕР D5-EFFECT (последствие как PORTRET):
  items: [
    { kind: PORTRET, statement: "обожжённые руки в старых ожогах" }
  ]
  ← НЕВЕРНО: это физическое последствие (EFFECT, effect_kind=custom
  или skill), не внутреннее состояние.
  ВЕРНО: { kind: EFFECT, summary: "обожжённые руки в старых ожогах",
           effect_kind: "custom" }

АНТИПРИМЕР D5-LOCATION (место как PORTRET):
  items: [
    { kind: PORTRET, statement: "кузня — пристройка таверны" }
  ]
  ← НЕВЕРНО: это место (LOCATION), не характеристика.
  ВЕРНО: { kind: LOCATION, summary: "кузня — пристройка таверны",
           name_hint: "кузня" }

АНТИПРИМЕР D5-DESIRE (мечта как PORTRET):
  items: [
    { kind: PORTRET, statement: "Орм думает открыть кузню" }
  ]
  ← НЕВЕРНО: это DESIRE_SEED (намерение на будущее).
  ВЕРНО: { kind: DESIRE_SEED,
           statement: "открыть нормальную личную кузню",
           about_hint: "собственная кузня" }

АНТИПРИМЕР D5-TRAIT (характерология как TRAIT_SEED — сохраняется
из старого D5):
  items: [
    { kind: TRAIT_SEED, trait: "не опасен", evidence: "..." },
    { kind: TRAIT_SEED, trait: "мебель города", evidence: "..." }
  ]
  ← НЕВЕРНО: это STATE-описания, не черты поведения.
  ВЕРНО: PORTRET со statement = фраза целиком.

АНТИ-РЕГРЕССИЯ: характерологические утверждения НЕ должны массово
возвращаться из PORTRET в TRAIT_SEED. PORTRET остаётся правильным
kind для STATE-описаний («не опасен», «мебель города»). Уточнение
D5 касается только того, что PORTRET НЕ поглощает EFFECT, LOCATION,
EVENT, DESIRE_SEED.

Маркер для проверки: ключевое слово НЕ является достаточным
основанием для классификации. «Кузнец» может быть:
  - EFFECT (effect_kind=occupation) — если это результат действия
  - LOCATION (name_hint) — если это место работы
  - PORTRET (характеристика) — если это самоидентификация
  - TRAIT_SEED — если это паттерн поведения
Смотри на синтаксис и контекст, не на отдельное слово."""

def main():
    if not PROMPT_PATH.exists():
        print(f"ERROR: {PROMPT_PATH} not found", file=sys.stderr)
        sys.exit(2)

    text = PROMPT_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print(f"[skip] D5 refinement already applied")
        return

    if OLD_D5 not in text:
        print(f"ERROR: OLD D5 block not found — check prompt state", file=sys.stderr)
        sys.exit(3)

    # Заменяем старый D5 на новый + маркер
    new_text = text.replace(OLD_D5, NEW_D5 + "\n\n<!-- " + MARKER + " -->")

    PROMPT_PATH.write_text(new_text, encoding="utf-8")
    print(f"[ok] D5 refinement applied")
    print(f"     size: {len(text)} -> {len(new_text)} bytes")

if __name__ == "__main__":
    main()
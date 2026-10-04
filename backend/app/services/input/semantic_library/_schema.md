# Semantic Library — Schema v0 (Э0)

> path: backend/app/services/input/semantic_library/_schema.md
> Статус: ACTIVE (Э0) | Вердикт Мастера: D1/D2 GO, production migration NO, router absent by design

## Принцип
Библиотека — модульное семантическое знание на диске. Активный промпт получает
ограниченный срез. Production source of truth — inline-сборка
(llm_compressor_client); библиотека при ON обязана воспроизводить целевое
состояние БАЙТ-В-БАЙТ (golden-lock). Миграция источника истины — отдельный
вердикт.

## Формат модуля (.md)
- Первая значащая строка: `# semantic-module: <name>` — name == stem файла, иначе громкий отказ.
- Метаданные: строки `> key: value` до первой секции.
- Секции: `## <name>`; контент verbatim между заголовками. Хвостовые пустые
  строки секции срезаются; ВЕДУЩИЕ пустые строки сохраняются (несут ведущий
  `\n` блока контрастов). Чтение utf-8-sig (BOM-уроки серии S317).

## Реестр секций (ЗАКРЫТ, v1 — Э2)
- `enum-tail` — verbatim-замена хвоста перечисления semantic_acts (ОПЦИОНАЛЬНАЯ:
  модуль без неё = add-only; два enum-tail-модуля в одном срезе = отказ сборки).
- `contrast-block` — verbatim-блок контрастных пар, вкл. ведущий `\n` (обязательная).
- `notes` — свободные примечания, loader'ом не используется (опциональная).
Неизвестная секция = SemanticLibraryError. Расширение реестра = правка схемы +
лоадера + вердикт Мастера.

## Флаг и приоритеты
- `ENIGMA_SEM_LIB=1` — ON; отсутствует/иное — OFF (путь мёртв: import внутри ветки).
- ON: библиотека — ЕДИНСТВЕННЫЙ владелец provenance-региона; ENIGMA_PROV_X2 /
  XCLEAN / B / B2 игнорируются (замок test_semlib_on). ENIGMA_RC8_STATE не
  зависит (другой регион, legacy).
- Отказ библиотеки при ON — громкий (SemanticLibraryError); fallback на inline запрещён (L4).

## Router seam
Router отсутствует by design (Э0-Э2). Точка будущей вставки: выбор модуля
между `list_modules()` и `load_module()`; сигнатуры менять не предполагается.

## Приёмка Э0
1. schema работает (закрытый реестр, громкие откази) — test_semlib_loader.
2. loader детерминирован — test_semlib_loader (×2 equal, sorted list).
3. модуль воспроизводит контракт состояния B — test_semlib_on (bytewise).
4. OFF = байт-в-байт production — test_semlib_off (golden A).
5. ON = ожидаемый промпт — test_semlib_on (golden B).
6. consumer/recovery/corpus не тронуты — patch scope: только точка сборки.
7. один флаг — ENIGMA_SEM_LIB.

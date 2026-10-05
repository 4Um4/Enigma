"""path: /project/backend/app/services/input/semantic_router.py

Назначение: экспериментальный semantic-slice router (SR-1 Phase 1, GO
    Мастера, вариант A). Единственный режим — oracle: выбор 0..1 модуля
    по gold-меткам корпуса (измерительный прибор; реальных роутеров здесь
    нет и не появится до завершения oracle-isolation — принцип Мастера:
    «не ремонтируем и не строим router до oracle»). INV-SR-1: выход =
    имена модулей (0..1), НИКОГДА акты/типы; промах/неизвестная фраза ->
    пустой срез (ноль модулей = байт-состояние A, замок
    test_semlib_router). Шов зафиксирован _schema.md: выбор между
    list_modules() и load_module(); сигнатуры loader'а не меняются.
    ENIGMA_SEM_ROUTER (default: отсутствует) — путь мёртв; включается
    ТОЛЬКО измерительным контуром. Метки живут ВНЕ app/ (экспериментальная
    зона reports/) — app/ корпусных данных не содержит.
Зависимости: app.services.input.semantic_library (read-only), stdlib.
Основные сущности: select_modules(), _route_oracle(), _load_labels().
Запуск: не запускается напрямую — вызывается из ON-ветки
    llm_compressor_client._build_prompts (import внутри ветки, как Э0).
"""

import json
import os
from typing import Dict, Tuple

from app.services.input.semantic_library import SemanticModule, load_module

_LABELS_PATH_ENV = "ENIGMA_SEM_ROUTER_ORACLE_LABELS"
_FAMILIES_ENV = "ENIGMA_SEM_ROUTER_ORACLE_FAMILIES"
# Кэш по пути (не глобальный): микро-тесты подают разные tmp-файлы меток.
_LABELS_CACHE: Dict[str, Dict[str, str]] = {}

_FAMILY_TO_MODULE = {"PROV": "dialogue_provenance", "ID": "dialogue_identity"}


def select_modules(raw_text: str, csv_names: str) -> Tuple[SemanticModule, ...]:
    """Шов роутера — единственная точка выбора среза. При ENIGMA_SEM_ROUTER
    != 'oracle' — легаси CSV-путь Э0/Э1/Э2 байт-в-байт (изменений ноль)."""
    if os.environ.get("ENIGMA_SEM_ROUTER", "") == "oracle":
        return _route_oracle(raw_text)
    from app.services.input.semantic_library import load_modules

    return load_modules(csv_names)


def _load_labels() -> Dict[str, str]:
    """Gold-метки (аудит P0-1; генерируются reports/p0_gen_oracle_labels.py
    из ЕДИНОГО источника p0_rc_baseline). Отказ громкий (L4): oracle без
    меток — INVALID измерения, не тихий пустой срез."""
    path = os.environ.get(_LABELS_PATH_ENV, "")
    if not path:
        raise RuntimeError(
            f"{_LABELS_PATH_ENV} не задан: oracle-режим без меток — INVALID"
        )
    cached = _LABELS_CACHE.get(path)
    if cached is not None:
        return cached
    with open(path, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    labels = {str(key): str(value) for key, value in data.items()}
    _LABELS_CACHE[path] = labels
    return labels


def _route_oracle(raw_text: str) -> Tuple[SemanticModule, ...]:
    """Oracle: gold-семья -> её модуль; EMPTY/BOUNDARY/неизвестно -> пустой
    срез. Оружие рук — ENIGMA_SEM_ROUTER_ORACLE_FAMILIES (default
    'PROV,ID'): рука активирует только перечисленные семьи (ORC-B='PROV',
    ORC-I='ID'). [SLICE] — fingerprint выбора (NONE = пустой срез = ноль
    модулей; ASCII-маркер: U+2205 отсутствует в cp1251 артефактов)."""
    labels = _load_labels()
    family = labels.get(raw_text)
    enabled = {
        item.strip().upper()
        for item in os.environ.get(_FAMILIES_ENV, "PROV,ID").split(",")
        if item.strip()
    }
    names: Tuple[str, ...] = ()
    if family in _FAMILY_TO_MODULE and family in enabled:
        names = (_FAMILY_TO_MODULE[family],)
    print(
        f"[SLICE] router=oracle text={raw_text!r} family={family!r} "
        f"modules={names[0] if names else 'NONE'}"
    )
    return tuple(load_module(name) for name in names)

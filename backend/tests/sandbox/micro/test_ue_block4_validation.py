# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_block4_validation.py
Назначение: S-UE Блок 4 — валидатор per-act ключей: легитимные проходят
    (модальность UPPER-нормализуется), мусорные значения = ключ ОТБРАСЫВАЕТСЯ
    (не None), отсутствующие остаются отсутствующими, чужой type фильтруется.
Зависимости: app.services.input.intent_compressor
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_block4_validation.py -q; cd ..
"""
from app.services.input.intent_compressor import _validate_acts


def test_per_act_keys_pass_and_normalize():
    acts = _validate_acts([{
        "type": "ORDER", "params": {}, "negated": True,
        "modality": "hypothetical", "quoted": False, "quoted_speaker_hint": "Люся",
    }])
    a = acts[0]
    assert a["negated"] is True and a["modality"] == "HYPOTHETICAL"
    assert a["quoted"] is False and a["quoted_speaker_hint"] == "Люся"


def test_garbage_keys_dropped():
    acts = _validate_acts([{
        "type": "ORDER", "params": {}, "negated": "yes",
        "modality": "MAYBE", "quoted": 1, "quoted_speaker_hint": "   ",
    }])
    for k in ("negated", "modality", "quoted", "quoted_speaker_hint"):
        assert k not in acts[0]


def test_absent_keys_stay_absent():
    assert _validate_acts([{"type": "GREETING", "params": {}}]) == [{"type": "GREETING", "params": {}}]


def test_bad_type_still_filtered():
    assert _validate_acts([{"type": "QUOTED_COMMAND", "params": {}, "quoted": True}]) == []
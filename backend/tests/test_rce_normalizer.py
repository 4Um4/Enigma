# backend/tests/test_rce_normalizer.py
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.memory.rce import extract_speech_events
from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer


def test_dm_response_normalizer_markdown():
    # 1. Снятие markdown с пробелами и регистром
    raw1 = '  ```JSON\n{"dm_response": "Торнин хмурится."}\n```  '
    out1 = DMResponseNormalizer.normalize(raw1)
    assert out1.schema_type == "dm_response", f"Fail 1: {out1.schema_type}"
    assert out1.dm_text == "Торнин хмурится.", f"Fail 1 text: {out1.dm_text}"


def test_dm_response_normalizer_plain_text():
    # 2. Обычный текст (не JSON)
    raw2 = "Просто текст без JSON."
    out2 = DMResponseNormalizer.normalize(raw2)
    assert out2.schema_type == "unknown", f"Fail 2: {out2.schema_type}"
    assert out2.dm_text == "Просто текст без JSON.", f"Fail 2 text: {out2.dm_text}"


def test_rce_blocks_json_artifact():
    npcs = [{"npc_id": "tavern_keeper_tornin", "name": "Торнин"}]
    # 3. Fallback с JSON-артефактом (должен вернуть пустой список)
    dm_text_artifact = '{"dm_response": "Торнин хмурится."}'
    reactions = extract_speech_events(dm_text=dm_text_artifact, target_npc_id="tavern_keeper_tornin", all_npcs_raw=npcs)
    assert reactions == [], f"Fail 3: Должен быть пустой список, но получилось {reactions}"


def test_rce_allows_normal_fallback():
    npcs = [{"npc_id": "tavern_keeper_tornin", "name": "Торнин"}]
    # 4. Нормальный Fallback без кавычек (должен записать речь)
    dm_text_normal = "Торнин молча смотрит на тебя."
    reactions2 = extract_speech_events(dm_text=dm_text_normal, target_npc_id="tavern_keeper_tornin", all_npcs_raw=npcs)
    assert len(reactions2) == 1, f"Fail 4: Должна быть 1 реакция, но получилось {reactions2}"
    assert "Торнин:" in reactions2[0], f"Fail 4 text: {reactions2[0]}"

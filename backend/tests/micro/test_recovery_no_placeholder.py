"""path: /project/backend/tests/micro/test_recovery_no_placeholder.py

Назначение: замок V.3-вердикта (unspecified-дефект): recovery/enrichment
    НЕ подставляет выдуманный topic-плейсхолдер, когда модель не дала
    requested_outcome. Честное UNKNOWN = акт без topic (§ENIGMA-003:
    отсутствие проекции ≠ нейтральное значение). Provenance синтеза — в
    source_fields. Заглушка маскировала реальный сигнал модели в
    det-замерах (19-29 фраз из 90 несли фиктивный topic).
Зависимости: app.services.input.intent_compressor, app.domain.intent_profile
Основные сущности: IntentCompressor._recover_acts

Запуск: cd backend; python -m pytest tests/micro/test_recovery_no_placeholder.py -v; cd ..
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

from app.domain.intent_profile import ActionType, IntentSemanticField, SpeechAct
from app.services.input.intent_compressor import IntentCompressor


def _compressor(llm_response):
    client = MagicMock()
    client.compress_intent = AsyncMock(return_value=llm_response)
    return IntentCompressor(llm_client=client)


def test_recover_acts_no_placeholder_topic():
    """Recovery: question без requested_outcome → акт БЕЗ topic, не 'unspecified'."""
    comp = _compressor(None)
    field = IntentSemanticField(
        action=ActionType.DIALOGUE,
        raw_text="Кто рассказал?",
        speech_act=SpeechAct.QUESTION,
    )
    result = asyncio.run(comp._recover_acts(field, None, {}))
    acts = result.semantic_acts
    assert acts, "recovery обязан канонизировать speech_act=question в акт"
    assert acts[0]["type"] == "QUESTION"
    assert "topic" not in (acts[0].get("params") or {}), f"выдуманный topic вернулся: {acts[0]}"
    assert "unspecified" not in str(acts)
    # Provenance синтеза сохранён (canonical-vs-recovery различимы)
    assert "source_fields" in acts[0]


def test_recover_acts_real_topic_kept():
    """Recovery: requested_outcome присутствует → topic = реальные данные модели."""
    comp = _compressor(None)
    field = IntentSemanticField(
        action=ActionType.DIALOGUE,
        raw_text="Кто рассказал?",
        speech_act=SpeechAct.QUESTION,
        requested_outcome="узнать источник",
    )
    result = asyncio.run(comp._recover_acts(field, None, {}))
    acts = result.semantic_acts
    assert acts[0]["params"].get("topic") == "узнать источник"


def test_no_unspecified_placeholder_left_in_source():
    """AST-гвард: заглушка удалена из ОБЕИХ точек вставки (enrich + recovery)."""
    from app.services.input import intent_compressor

    src = inspect.getsource(intent_compressor)
    assert 'or "unspecified"' not in src, "заглушка unspecified жива в intent_compressor"
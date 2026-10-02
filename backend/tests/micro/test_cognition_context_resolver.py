"""path: /project/backend/tests/micro/test_cognition_context_resolver.py

Назначение: Step 5 Этап 1-замок — CognitionContextResolver: read-only
    проекция claims/вопросов сессии в cognition-блок. Формулировка
    «представился как» (не «знает имя»); пусто при пустой сессии;
    ошибки чтения не крашат (warning + "").
Зависимости: app.services.npc.cognition_context, app.services.memory.dialogue_session.
Запуск: cd backend; python -m pytest tests/micro/test_cognition_context_resolver.py -v; cd ..
"""


from app.services.memory.dialogue_session import DialogueSession
from app.services.npc.cognition_context import CognitionContextResolver


class _SessionMemory:
    def __init__(self) -> None:
        self._sessions: dict = {}

    def get_dialogue_session(
        self, campaign_id: str, npc_id: str, partner_id: str = "player"
    ) -> DialogueSession:
        key = (campaign_id, npc_id, partner_id)
        if key not in self._sessions:
            self._sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._sessions[key]


def test_claims_projected_with_heard_framing():
    mem = _SessionMemory()
    r = CognitionContextResolver(mem, campaign_id_provider=lambda: "T")
    s = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    s.add_claim(
        text="представился как «Мю»", speaker="player", confidence=0.9, tick=1,
    )
    block = r.resolve_block("merchant_goran")
    assert "Мю" in block
    assert "представился как" in block
    # Граница: формулировка НЕ утверждает «знает имя»
    assert "знает имя" not in block
    assert "знает, что игрока зовут" not in block


def test_empty_session_empty_block():
    mem = _SessionMemory()
    r = CognitionContextResolver(mem, campaign_id_provider=lambda: "T")
    assert r.resolve_block("merchant_goran") == ""


def test_open_questions_projected():
    mem = _SessionMemory()
    r = CognitionContextResolver(mem, campaign_id_provider=lambda: "T")
    s = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    s.add_open_question(
        text="кто ты?", asked_by="player", addressed_to="merchant_goran", tick=2,
    )
    block = r.resolve_block("merchant_goran")
    assert "кто ты?" in block


def test_memory_failure_degrades_not_crashes():
    class _Boom:
        def get_dialogue_session(self, *a, **k):
            raise RuntimeError("boom")

    r = CognitionContextResolver(_Boom(), campaign_id_provider=lambda: "T")
    assert r.resolve_block("merchant_goran") == ""
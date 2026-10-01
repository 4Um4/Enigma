"""path: /project/backend/tests/micro/test_lang_leak_provenance.py

Назначение: A1-регрессия (RE-D2, вердикт Мастера). LANG_LEAK-гейт
    применяется ТОЛЬКО к тексту LLM-происхождения (_text_source=="llm").
    T1-фальсификатор: детерминированная материализация warn (machine-id
    латиницей BY DESIGN, share=0.60) публикуется БЕЗ единого вызова
    router — до фикса ретрай звал LLM с потока петли, RE-D2.
    T2-замок: LLM-текст с утечкой по-прежнему гейтится (S292 не
    ослаблен): initial + reinforced retry = ровно 2 вызова router.

Зависимости: app.domain.communication, app.domain.execution,
    app.services.execution.dialogue_executor.

Основные сущности: test_deterministic_warn_published_without_llm_call,
    test_llm_text_still_gated_by_lang_leak.
"""


from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.execution import QueuedTask, TaskKind
from app.services.execution.dialogue_executor import DialogueExecutor


class _ReDF2Router:
    """Фальсификатор: любой вызов request_for_agent = RE-D2-класс.
    Считает вызовы — контракт A1: deterministic-путь не зовёт вовсе."""

    def __init__(self) -> None:
        self.calls = 0

    def request_for_agent(self, **kwargs):
        self.calls += 1
        raise RuntimeError(
            "RE-D2 probe: LLM вызван из deterministic-пути (A1 нарушен)"
        )

    def _abort_generation(self) -> None:  # контракт threading.Timer
        pass


class _OkRouter(_ReDF2Router):
    """LLM-роутер: отдаёт латинский текст (leak) на каждый вызов."""

    def request_for_agent(self, **kwargs):
        self.calls += 1
        return "hello world my friend"


class _PassValidator:
    """Стаб валидатора (структуру ResponseValidator не угадываем —
    подменяем контракт после конструктора, инъекция атрибута)."""

    class _Result:
        is_fallback = False

        def __init__(self, text: str) -> None:
            self.text = text

    def validate(self, raw: str):
        return self._Result(raw)


def _warn_task() -> QueuedTask:
    req = DialogueRequest(
        topic="власть",
        target_id="thief_shadow",
        exposure=ExposureLevel.from_semantic("normal"),
        intent_type="warn",
    )
    return QueuedTask(
        task_id="t-a1",
        tick=1,
        counter=1,
        kind=TaskKind.DIALOGUE,
        owner_id="guard_borko",
        campaign_id="T",
        payload=req,
    )


def test_deterministic_warn_published_without_llm_call():
    router = _ReDF2Router()
    executor = DialogueExecutor(router=router)
    artifacts = list(executor.execute(_warn_task()))

    assert router.calls == 0, (
        f"A1 нарушен: deterministic-текст породил {router.calls} LLM-вызовов "
        "(LANG_LEAK гейтит не-LLM текст — источник RE-D2 в WARN-path)"
    )
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art.success is True
    assert art.result_type == "dialogue_line"
    # machine-id публикуется как есть (A2 — отдельный дефект presentation)
    assert "guard_borko" in art.data["text"]
    assert "thief_shadow" in art.data["text"]


def test_llm_text_still_gated_by_lang_leak():
    router = _OkRouter()
    executor = DialogueExecutor(router=router)
    executor._validator = _PassValidator()  # инъекция стаба валидатора
    req = DialogueRequest(
        topic="власть",
        target_id="thief_shadow",
        exposure=ExposureLevel.from_semantic("normal"),
        intent_type="talk",  # requires_llm=True -> LLM-ветка
        prepared_prompt="скажи свою реплику",
    )
    task = QueuedTask(
        task_id="t-a1-llm",
        tick=1,
        counter=2,
        kind=TaskKind.DIALOGUE,
        owner_id="guard_borko",
        campaign_id="T",
        payload=req,
    )
    artifacts = list(executor.execute(task))

    # Замок S292 жив: initial + reinforced retry = ровно 2 вызова.
    assert router.calls == 2, (
        f"LANG_LEAK-гейт ослаблен: ожидалось 2 вызова (initial+retry), "
        f"получено {router.calls}"
    )
    assert len(artifacts) == 1
    assert artifacts[0].success is True
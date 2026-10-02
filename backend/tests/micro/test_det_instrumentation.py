"""path: /project/backend/tests/micro/test_det_instrumentation.py

Назначение: замок инструментализации DEBT-INFERENCE-NONDET (вердикт Мастера):
    (1) временный [DIAG-PROMPT]-зонд удалён из _build_prompts (замер выполнен,
    F-B применён — зонд не имеет права мусорить det-вывод);
    (2) [DET-TRACE] в компрессоре существует ТОЛЬКО за env-флагом
    ENIGMA_DET_TRACE (default OFF — production-эффект нулевой);
    (3) менеджер llama-server честно маркирует REUSE (identity NOT verified)
    и PID-контракт свободного порта — 'unknown', не краш.
Зависимости: app.services.input.llm_compressor_client, scripts.llm_server_manager
Основные сущности: LlamaCppCompressorClient._build_prompts, _port_owner_pid

Запуск: cd backend; python -m pytest tests/micro/test_det_instrumentation.py -v; cd ..
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_build_prompts_no_diag_prompt_probe():
    """[DIAG-PROMPT] удалён: stdout промпт-сборки чист (behavioral lock)."""
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient

    client = LlamaCppCompressorClient()
    buf = io.StringIO()
    with redirect_stdout(buf):
        client._build_prompts("тестовая фраза", {"npc_positions": {}})
    out = buf.getvalue()
    assert "[DIAG-PROMPT]" not in out, f"зонд жив в _build_prompts: {out[:200]}"


def test_det_trace_gated_by_env_flag():
    """[DET-TRACE] закрыт env-флагом (source lock — default OFF)."""
    import inspect

    from app.services.input import llm_compressor_client

    src = inspect.getsource(llm_compressor_client)
    assert "ENIGMA_DET_TRACE" in src, "det-зонд исчез из компрессора"
    assert 'os.environ.get("ENIGMA_DET_TRACE")' in src, "det-зонд не закрыт env-флагом"


def test_reuse_marker_and_port_pid_contract():
    """REUSE-маркировка менеджера + честный PID-контракт свободного порта."""
    import inspect

    import scripts.llm_server_manager as mgr

    assert "REUSE — identity NOT verified" in inspect.getsource(mgr)
    # свободный порт: 'unknown' (честный ответ), не исключение и не ноль
    result = mgr._port_owner_pid(59999)
    assert result == "unknown" or result.isdigit(), f"нечестный PID-контракт: {result}"
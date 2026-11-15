"""A6 S3 proxy logger tests — verify precision + restore + delegation."""
import pytest


def test_s3_proxy_raises_on_4_causal_warnings():
    """All 4 causal producer messages trigger RuntimeError."""
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    causal_msgs = [
        "[CAUSAL_SLICE] producer failed (no-op) for guard_borko: boom",
        "[CAUSAL_SLICE_HUNGER] producer failed (no-op) for merchant_goran: boom",
        "[CAUSAL_SLICE_GRIEVANCE] producer failed (no-op) for maid_lusya: boom",
        "[CAUSAL_SLICE_AFFECTION] producer failed (no-op) for blacksmith_orm: boom",
    ]

    with s3_fail_loud_logger() as proxy:
        for msg in causal_msgs:
            with pytest.raises(RuntimeError, match="A6-S3-FAIL-LOUD"):
                proxy.warning(msg)
        assert len(proxy.failures) == 4


def test_s3_proxy_delegates_non_causal_warnings():
    """Other 13 pipeline warnings pass through to real logger, no raise."""
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    non_causal_msgs = [
        "[MEMORY] perception apply failed for guard_borko: x",
        "[BELIEF] belief update failed for merchant_goran: x",
        "[NEED_MODIFIERS] failed to read NeedLevel for maid_lusya: x",
        "[MEM-3] npc_memory_modifiers failed for blacksmith_orm: x",
        "[MEMORY_EVENT] create_memory_event failed for tavern_keeper_tornin: x",
        "[APPROACH_NAV] target=X not found in npc_positions! Movement blocked.",
        "[FLEE_NAV] threat=Y not found in npc_positions! Flee blocked.",
    ]

    with s3_fail_loud_logger() as proxy:
        # No assertion — if any raises, test fails
        for msg in non_causal_msgs:
            proxy.warning(msg)
        assert proxy.failures == []


def test_s3_proxy_raises_only_when_both_prefix_and_marker_present():
    """Prefix without 'producer failed' → delegate. Marker without prefix → delegate."""
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    with s3_fail_loud_logger() as proxy:
        # Prefix present, marker absent
        proxy.warning("[CAUSAL_SLICE] some other message entirely")
        # Marker present, no causal prefix
        proxy.warning("unrelated message says producer failed (no-op) outside context")
        assert proxy.failures == []


def test_s3_proxy_restores_original_logger():
    """Restore module-level logger binding on CM exit, by identity."""
    import app.services.npc.npc_tick_pipeline as _ntp
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    original = _ntp.logger
    with s3_fail_loud_logger():
        assert _ntp.logger is not original
    assert _ntp.logger is original


def test_s3_proxy_restores_on_exception():
    """Restore on exception in CM body."""
    import app.services.npc.npc_tick_pipeline as _ntp
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    original = _ntp.logger
    with pytest.raises(RuntimeError):
        with s3_fail_loud_logger():
            raise RuntimeError("boom")
    assert _ntp.logger is original


def test_s3_proxy_delegates_info_debug_error():
    """Delegation through __getattr__ — info/debug/error/exception still callable."""
    from tests.sandbox.a6_ablation.s3_proxy import s3_fail_loud_logger

    with s3_fail_loud_logger() as proxy:
        # If delegation broken, AttributeError/TypeError raised here
        proxy.info("[CAUSAL_SLICE] info is fine")
        proxy.debug("[CAUSAL_SLICE] debug is fine")
        proxy.error("[CAUSAL_SLICE] error is fine")
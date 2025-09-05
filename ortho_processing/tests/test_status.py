import inspect

from services.status import recompute_overall, reconcile_state

HAS_FAILED_NOW = "failed_now" in inspect.signature(recompute_overall).parameters


def call_recompute(odm, oi, prev, failed_now=False):
    if HAS_FAILED_NOW:
        return recompute_overall(odm, oi, prev, failed_now=failed_now)  # type: ignore[call-arg]
    return recompute_overall(odm, oi, prev)  # type: ignore[call-arg]


def test_reconcile_state_tail_precedence():
    s, why = reconcile_state(
        prev="processing", ok_by_artifacts=False, tail_state="succeeded", tail_reason="footer"
    )

    assert s == "succeeded"
    s2, _ = reconcile_state(
        prev="succeeded", ok_by_artifacts=False, tail_state="failed", tail_reason="exit"
    )
    assert s2 == "failed"


def test_reconcile_state_artifacts_imply_success_when_no_tail():
    s, why = reconcile_state(prev=None, ok_by_artifacts=True, tail_state=None, tail_reason=None)
    assert s == "succeeded"


def test_reconcile_state_sticky_terminal_without_new_evidence():
    s, why = reconcile_state(
        prev="failed", ok_by_artifacts=False, tail_state=None, tail_reason=None
    )
    assert s == "failed"
    s2, _ = reconcile_state(
        prev="succeeded", ok_by_artifacts=False, tail_state=None, tail_reason=None
    )
    assert s2 == "succeeded"


def test_recompute_overall_processed_is_terminal():
    # Even if new inputs suggest failure/success, processed stays processe

    out = call_recompute(odm="failed", oi="failed", prev="processed", failed_now=True)
    assert out == "processed"


def test_recompute_overall_success_paths():
    assert call_recompute(odm="succeeded", oi="succeeded", prev="processing") == "processed"
    assert call_recompute(odm="succeeded", oi="processing", prev="processing") == "ortho generated"


def test_recompute_overall_failure_rule():
    if HAS_FAILED_NOW:
        # Only fails when fresh failure is indicated
        assert (
            call_recompute(odm="succeeded", oi="failed", prev="processing", failed_now=True)
            == "failed"
        )
        assert (
            call_recompute(odm="succeeded", oi="failed", prev="processing", failed_now=False)
            == "processing"
        )
    else:
        # Legacy behavior: any failed stage yields failed
        assert call_recompute(odm="succeeded", oi="failed", prev="processing") == "failed"


def test_recompute_no_promotion_on_stale_oi_failure():
    # Do not promote to 'ortho generated' if OI is marked failed but there's no fresh failure
    assert (
        call_recompute(odm="succeeded", oi="failed", prev="processing", failed_now=False)
        == "processing"
    )
    # If we were already at 'ortho generated', keep it (no demotion)
    assert (
        call_recompute(odm="succeeded", oi="failed", prev="ortho generated", failed_now=False)
        == "ortho generated"
    )


def test_recompute_no_demote_from_ortho_generated_on_stale_failure():
    # When we were already "ortho generated",
    # and OI is marked failed but there's no fresh tail failure,
    # do not demote overall back to "processing".
    import inspect

    from services.status import recompute_overall

    HAS_FAILED_NOW = "failed_now" in inspect.signature(recompute_overall).parameters

    def call(odm, oi, prev, failed_now=False):
        return (
            recompute_overall(odm, oi, prev, failed_now=failed_now)
            if HAS_FAILED_NOW
            else recompute_overall(odm, oi, prev)  # type: ignore[call-arg]
        )

    assert (
        call(odm="succeeded", oi="failed", prev="ortho generated", failed_now=False)
        == "ortho generated"
    )

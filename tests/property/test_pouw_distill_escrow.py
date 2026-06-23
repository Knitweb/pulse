"""IL-105: distill registered as PoUW job class; settlement escrow refund claims."""

from __future__ import annotations

import pytest

from knitweb.pouw.escrow import (
    ClaimRefund,
    EscrowRelease,
    RefundClaims,
    settle_on_verify,
)
from knitweb.pouw.job import (
    DISTILL_JOB_CLASS,
    VERIFICATION_SPLIT,
    job_class,
    verification_policy,
)


# ---------------------------------------------------------------------------
# IL-105: distill job class registration
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_distill_job_class_registered():
    jc = job_class("distill")
    assert jc.name == "distill"


@pytest.mark.property
def test_distill_verification_is_split():
    assert verification_policy("distill") == VERIFICATION_SPLIT


@pytest.mark.property
def test_distill_job_class_constant():
    assert DISTILL_JOB_CLASS.name == "distill"
    assert DISTILL_JOB_CLASS == job_class("distill")


# ---------------------------------------------------------------------------
# Settlement escrow: RefundClaims
# ---------------------------------------------------------------------------


def _claim(suffix: str = "1") -> ClaimRefund:
    return ClaimRefund(
        claimant=f"pub{suffix}",
        result_cid=f"cid{suffix}",
        reason="work not delivered",
    )


@pytest.mark.property
def test_escrow_amount_must_be_integer():
    rc = RefundClaims()
    with pytest.raises(ValueError, match="integer"):
        rc.submit(_claim(), amount_pls=1.5)  # type: ignore[arg-type]


@pytest.mark.property
def test_escrow_negative_amount_raises():
    rc = RefundClaims()
    with pytest.raises(ValueError):
        rc.submit(_claim(), amount_pls=-1)


@pytest.mark.property
def test_escrow_approve_returns_release():
    rc = RefundClaims()
    eid = rc.submit(_claim(), amount_pls=100)
    release = rc.approve(eid)
    assert isinstance(release, EscrowRelease)
    assert release.payee == "pub1"
    assert release.amount_pls == 100
    assert isinstance(release.amount_pls, int)


@pytest.mark.property
def test_escrow_reject_removes_claim():
    rc = RefundClaims()
    eid = rc.submit(_claim(), amount_pls=50)
    rc.reject(eid)
    with pytest.raises(KeyError):
        rc.approve(eid)


@pytest.mark.property
def test_escrow_duplicate_submit_raises():
    rc = RefundClaims()
    claim = _claim()
    rc.submit(claim, amount_pls=10)
    with pytest.raises(ValueError, match="duplicate"):
        rc.submit(claim, amount_pls=10)

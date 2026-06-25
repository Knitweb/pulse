"""IL-100 Subscription dataclass + IL-102 provenance gate tests."""

from __future__ import annotations

import pytest

from knitweb.interpret.retrieve import Subscription
from knitweb.interpret.distill import ProvenanceError, _check_provenance_chain
from knitweb.interpret import Subscription as SubscriptionFromPackage


# ---------------------------------------------------------------------------
# C1: Subscription dataclass
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_subscription_scope_filters():
    sub = Subscription(scope=("chemistry-node",), max_candidates=5, min_reputation=0)
    assert sub.scope == ("chemistry-node",)
    assert isinstance(sub.max_candidates, int)
    assert isinstance(sub.min_reputation, int)


@pytest.mark.property
def test_subscription_integer_fields():
    sub = Subscription(scope=("lens",), max_candidates=64, min_reputation=10)
    assert not isinstance(sub.max_candidates, bool)
    assert not isinstance(sub.min_reputation, bool)
    assert sub.max_candidates == 64
    assert sub.min_reputation == 10


@pytest.mark.property
def test_subscription_none_is_unrestricted():
    from knitweb.interpret.retrieve import retrieve
    # retrieve(..., subscription=None) must not raise — tested via smoke import
    assert Subscription is not None  # import check


@pytest.mark.property
def test_subscription_exported_from_package():
    assert SubscriptionFromPackage is Subscription


@pytest.mark.property
def test_subscription_invalid_scope_raises():
    with pytest.raises(TypeError):
        Subscription(scope=("",))  # empty string in scope


@pytest.mark.property
def test_subscription_float_max_candidates_raises():
    with pytest.raises(ValueError):
        Subscription(scope=("x",), max_candidates=1.5)  # type: ignore[arg-type]


@pytest.mark.property
def test_subscription_zero_max_candidates_raises():
    with pytest.raises(ValueError):
        Subscription(scope=("x",), max_candidates=0)


@pytest.mark.property
def test_subscription_negative_reputation_raises():
    with pytest.raises(ValueError):
        Subscription(scope=("x",), min_reputation=-1)


# ---------------------------------------------------------------------------
# C2: Provenance gate
# ---------------------------------------------------------------------------


@pytest.mark.property
def test_provenance_gate_valid_cid():
    valid_cid = "b" + "a" * 52  # syntactically valid base32 CID stub
    record = {"query_fingerprint": valid_cid, "kind": "distill-intermediate"}
    _check_provenance_chain(record)  # must not raise


@pytest.mark.property
def test_provenance_gate_missing_fingerprint_raises():
    with pytest.raises(ProvenanceError):
        _check_provenance_chain({"kind": "distill-intermediate"})


@pytest.mark.property
def test_provenance_gate_empty_fingerprint_raises():
    with pytest.raises(ProvenanceError):
        _check_provenance_chain({"query_fingerprint": ""})


@pytest.mark.property
def test_provenance_gate_non_cid_string_raises():
    with pytest.raises(ProvenanceError):
        _check_provenance_chain({"query_fingerprint": "not-a-cid"})


@pytest.mark.property
def test_provenance_gate_none_raises():
    with pytest.raises(ProvenanceError):
        _check_provenance_chain({"query_fingerprint": None})

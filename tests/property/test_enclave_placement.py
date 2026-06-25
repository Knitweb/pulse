"""P7b: Central Computation Enclave — placement policy + attestation seam.

Acceptance criteria
-------------------
AC1  fail closed: a required-attestation policy with NO verifier yields no
     eligible nodes, even when nodes loudly claim the attestation.
AC2  with a verifier, only nodes whose attestation actually verifies are eligible.
AC3  a claimed-but-rejected attestation (verifier returns False) is excluded.
AC4  geo bound: nodes outside the geohash prefix are excluded; empty prefix =
     no geographic restriction.
AC5  required_attestation="" means no TEE required (geo-only placement).
AC6  combined geo + attestation: both must hold.
AC7  the AttestationVerifier base class is abstract (.verify raises).
AC8  determinism: order-preserving; empty input → empty output; is_eligible
     agrees with eligible_nodes.
"""

from __future__ import annotations

import pytest

from knitweb.privacy.enclave import (
    AttestationVerifier,
    EnclaveError,
    EnclavePolicy,
    NodeAttestation,
    NodeProfile,
    TrustedAllowlistVerifier,
    eligible_nodes,
    is_eligible,
)

_SGX = "sgx"


def _node(node_id, geo="u15", kinds=(_SGX,)):
    return NodeProfile(
        node_id=node_id,
        geohash=geo,
        attestations=tuple(NodeAttestation(kind=k, evidence=b"quote") for k in kinds),
    )


# ── AC1: fail closed without a verifier ───────────────────────────────────────
@pytest.mark.property
def test_no_verifier_fails_closed():
    nodes = [_node("a"), _node("b")]
    policy = EnclavePolicy(required_attestation=_SGX)
    assert eligible_nodes(nodes, policy) == []  # claims alone prove nothing


# ── AC2 / AC3: verifier decides ───────────────────────────────────────────────
@pytest.mark.property
def test_verifier_admits_only_verified_nodes():
    nodes = [_node("a"), _node("b"), _node("c")]
    v = TrustedAllowlistVerifier({("a", _SGX), ("c", _SGX)})
    policy = EnclavePolicy(required_attestation=_SGX)
    got = [n.node_id for n in eligible_nodes(nodes, policy, verifier=v)]
    assert got == ["a", "c"]  # b is claimed-but-not-allowed → excluded (AC3)


@pytest.mark.property
def test_wrong_attestation_kind_excluded():
    nodes = [_node("a", kinds=("sev-snp",))]
    v = TrustedAllowlistVerifier({("a", "sev-snp")})
    policy = EnclavePolicy(required_attestation=_SGX)  # asks for sgx, node has sev
    assert eligible_nodes(nodes, policy, verifier=v) == []


# ── AC4: geo bound ────────────────────────────────────────────────────────────
@pytest.mark.property
def test_geo_prefix_filters():
    nodes = [_node("near", geo="u15xx"), _node("far", geo="gbsuv")]
    v = TrustedAllowlistVerifier({("near", _SGX), ("far", _SGX)})
    policy = EnclavePolicy(required_attestation=_SGX, geo_prefix="u15")
    got = [n.node_id for n in eligible_nodes(nodes, policy, verifier=v)]
    assert got == ["near"]


@pytest.mark.property
def test_empty_geo_prefix_no_restriction():
    nodes = [_node("a", geo=""), _node("b", geo="zzz")]
    v = TrustedAllowlistVerifier({("a", _SGX), ("b", _SGX)})
    policy = EnclavePolicy(required_attestation=_SGX, geo_prefix="")
    assert len(eligible_nodes(nodes, policy, verifier=v)) == 2


# ── AC5: no TEE required ──────────────────────────────────────────────────────
@pytest.mark.property
def test_no_attestation_required_is_geo_only():
    nodes = [_node("a", geo="u15", kinds=()), _node("b", geo="gb", kinds=())]
    policy = EnclavePolicy(required_attestation="", geo_prefix="u")
    got = [n.node_id for n in eligible_nodes(nodes, policy)]
    assert got == ["a"]  # no verifier needed, only geo applies


# ── AC6: combined ─────────────────────────────────────────────────────────────
@pytest.mark.property
def test_geo_and_attestation_both_required():
    nodes = [
        _node("right_geo_no_att", geo="u15", kinds=()),
        _node("wrong_geo_att", geo="gb", kinds=(_SGX,)),
        _node("right_both", geo="u15", kinds=(_SGX,)),
    ]
    v = TrustedAllowlistVerifier(
        {("wrong_geo_att", _SGX), ("right_both", _SGX)}
    )
    policy = EnclavePolicy(required_attestation=_SGX, geo_prefix="u15")
    got = [n.node_id for n in eligible_nodes(nodes, policy, verifier=v)]
    assert got == ["right_both"]


# ── AC7: abstract seam ────────────────────────────────────────────────────────
@pytest.mark.property
def test_base_verifier_is_abstract():
    with pytest.raises(NotImplementedError):
        AttestationVerifier().verify("a", NodeAttestation(kind=_SGX))


# ── AC8: determinism & helpers ────────────────────────────────────────────────
@pytest.mark.property
def test_empty_nodes_and_order_preserved():
    assert eligible_nodes([], EnclavePolicy()) == []
    nodes = [_node(x, kinds=()) for x in ("z", "a", "m")]
    policy = EnclavePolicy()  # no att, no geo → all pass, order kept
    assert [n.node_id for n in eligible_nodes(nodes, policy)] == ["z", "a", "m"]


@pytest.mark.property
def test_is_eligible_agrees_with_eligible_nodes():
    v = TrustedAllowlistVerifier({("a", _SGX)})
    policy = EnclavePolicy(required_attestation=_SGX)
    a, b = _node("a"), _node("b")
    assert is_eligible(a, policy, verifier=v) is True
    assert is_eligible(b, policy, verifier=v) is False
    assert eligible_nodes([a, b], policy, verifier=v) == [a]


@pytest.mark.property
def test_validation_guards():
    with pytest.raises(EnclaveError):
        NodeAttestation(kind="")
    with pytest.raises(EnclaveError):
        NodeProfile(node_id="")

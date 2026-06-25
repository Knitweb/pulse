"""Central Computation Enclave — placement policy + attestation seam.

The goal: run *sensitive* compute only on nodes that (a) prove they sit inside a
hardware-protected enclave (TEE — SGX / SEV-SNP / TDX) and (b) are bound to an
allowed geographic region (the "localized at p2p locations" requirement).  This
is the gate that decides **which candidate nodes are eligible** to receive an
encrypted/sensitive job before the scheduler ever hands them anything.

What is **real** here and what is a **seam**:

* **Real, pure, tested** — :func:`eligible_nodes`: the placement policy.  Given
  candidate node profiles and an :class:`EnclavePolicy`, it returns exactly the
  nodes that satisfy the geo bound *and* hold a *verified* attestation of the
  required type.  Deterministic, order-preserving, no I/O.
* **Honest seam** — :class:`AttestationVerifier`: verifying a TEE quote requires
  vendor PKI / DCAP collateral the dependency-free core cannot ship.  So the
  base verifier is abstract and the policy **fails closed**: with *no* verifier
  installed, a node's attestation claim counts for nothing and the node is
  excluded.  A real verifier (Intel DCAP, AMD SEV-SNP report check) plugs in
  here.  We never treat an unverified claim as proof.

The :class:`TrustedAllowlistVerifier` is a **dev/test stand-in, NOT real
attestation** — it trusts a static allowlist so the policy is exercisable
without TEE hardware.  Its name and docstring say so loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class EnclaveError(RuntimeError):
    """An enclave placement / attestation failure."""


@dataclass(frozen=True)
class NodeAttestation:
    """A node's *claim* to run inside a TEE of ``kind`` — awaiting verification.

    ``evidence`` is the opaque attestation quote/report bytes a real
    :class:`AttestationVerifier` would check against vendor collateral.  A claim
    is never proof until a verifier says so.
    """

    kind: str
    evidence: bytes = b""

    def __post_init__(self) -> None:
        if not self.kind:
            raise EnclaveError("attestation kind must be non-empty")


@dataclass(frozen=True)
class NodeProfile:
    """A candidate compute node.

    ``geohash`` binds the node to a physical region (empty = location unknown).
    ``attestations`` are its *claimed* TEE attestations, each still to be
    verified by the policy's verifier.
    """

    node_id: str
    geohash: str = ""
    attestations: tuple[NodeAttestation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.node_id:
            raise EnclaveError("node_id must be non-empty")


@dataclass(frozen=True)
class EnclavePolicy:
    """Where a sensitive job is allowed to run.

    ``required_attestation``  TEE kind a node must *prove* (``""`` = no TEE
                              required; geo-only placement).
    ``geo_prefix``            geohash prefix the node must fall under
                              (``""`` = no geographic restriction).
    """

    required_attestation: str = ""
    geo_prefix: str = ""


class AttestationVerifier:
    """Seam to real TEE quote verification.

    A concrete verifier validates ``att.evidence`` for ``node_id`` against
    vendor PKI / DCAP collateral and returns whether the node genuinely runs the
    attested enclave.  The base class is abstract — :func:`eligible_nodes` with
    no verifier fails closed rather than trusting claims.
    """

    def verify(self, node_id: str, att: NodeAttestation) -> bool:
        raise NotImplementedError


class TrustedAllowlistVerifier(AttestationVerifier):
    """Dev/test stand-in — **NOT real attestation.**

    Trusts a static allowlist of ``(node_id, kind)`` pairs so the placement
    policy can be exercised without TEE hardware.  Never use in production: it
    verifies nothing cryptographically.
    """

    def __init__(self, allowed: set[tuple[str, str]] | None = None) -> None:
        self._allowed = set(allowed or ())

    def allow(self, node_id: str, kind: str) -> None:
        self._allowed.add((node_id, kind))

    def verify(self, node_id: str, att: NodeAttestation) -> bool:
        return (node_id, att.kind) in self._allowed


def _geo_ok(node: NodeProfile, geo_prefix: str) -> bool:
    if not geo_prefix:
        return True
    return bool(node.geohash) and node.geohash.startswith(geo_prefix)


def _attestation_ok(
    node: NodeProfile,
    required: str,
    verifier: AttestationVerifier | None,
) -> bool:
    if not required:
        return True  # no TEE required for this policy
    if verifier is None:
        return False  # fail closed: no verifier ⇒ no claim can be proven
    return any(
        att.kind == required and verifier.verify(node.node_id, att)
        for att in node.attestations
    )


def eligible_nodes(
    nodes: list[NodeProfile],
    policy: EnclavePolicy,
    *,
    verifier: AttestationVerifier | None = None,
) -> list[NodeProfile]:
    """Return the candidate ``nodes`` that may run a job under ``policy``.

    A node is eligible iff it satisfies the geo bound **and** holds a *verified*
    attestation of the required kind.  Fails closed: an attestation claim with no
    verifier (or a verifier that rejects it) does not make a node eligible.
    Order-preserving and deterministic.
    """
    return [
        node
        for node in nodes
        if _geo_ok(node, policy.geo_prefix)
        and _attestation_ok(node, policy.required_attestation, verifier)
    ]


def is_eligible(
    node: NodeProfile,
    policy: EnclavePolicy,
    *,
    verifier: AttestationVerifier | None = None,
) -> bool:
    """Whether a single ``node`` satisfies ``policy`` (see :func:`eligible_nodes`)."""
    return _geo_ok(node, policy.geo_prefix) and _attestation_ok(
        node, policy.required_attestation, verifier
    )

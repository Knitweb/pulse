"""WeightAssertion — convergent G-Counter for fabric edge weights.

Design rationale
----------------
An Edge's CID commits to its full record including ``weight``, so two peers that
independently increment a weight produce different edge CIDs that gossip keeps as
separate edges — they never merge.  A G-Counter side-channel fixes this without
touching the Edge canonical format:

  * Edges stay ``weight=1`` in the fabric; the field encodes topology, not magnitude.
  * WeightAssertion records accumulate alongside: one per (edge_cid, source).
    ``source`` is a personhood-scope nullifier or PoUW collateral address — one per
    independent contributor, so Sybil inflation is blocked at the assertion layer.
  * ``converged_weight(edge_cid, assertions)`` folds them:
        W = sum(max(a.count for a in group) for group in by_source)
    This is strong-eventual-consistent: the fold is commutative, associative, and
    idempotent (union of assertion sets, not re-counts).  Partial sync gives a
    monotone lower bound that can only increase — gossip converges without barriers.
  * ``weight_root(assertions)`` produces a hex commitment over the full assertion
    set, suitable for inclusion in a FabricCheckpoint.

Security boundary
-----------------
WeightAssertions are NOT on the canonical value path (no Knit signs them, no
ledger records them).  They are operator-local diagnostic / reputation signals,
the same tier as p2p/metrics.py.  A Lens reads ``converged_weight`` as a ranking
signal; it never crosses the Mining→Settlement boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core import canonical, crypto

__all__ = [
    "WeightAssertion",
    "converged_weight",
    "weight_root",
]


def _require_str(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty str")


def _require_pos_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"{name} must be a positive int")


# ---------------------------------------------------------------------------
# WeightAssertion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WeightAssertion:
    """One source's integer count contribution for an edge.

    ``edge_cid``  — CID of the Edge this assertion applies to.
    ``source``    — personhood-scope nullifier or PoUW collateral address of the
                    contributor.  One independent actor → one source → one
                    assertion in the fold; Sybil inflation is blocked because two
                    assertions with the same source collapse to the higher count.
    ``count``     — positive integer; the contributor's current running count.
                    A later assertion with a higher count supersedes an earlier one
                    from the same source (last-write-wins within a source, G-Counter
                    across sources).
    """

    edge_cid: str
    source: str
    count: int

    def __post_init__(self) -> None:
        _require_str("edge_cid", self.edge_cid)
        _require_str("source", self.source)
        _require_pos_int("count", self.count)

    def to_record(self) -> dict:
        return {
            "kind": "weight-assertion",
            "edge_cid": self.edge_cid,
            "source": self.source,
            "count": self.count,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


# ---------------------------------------------------------------------------
# G-Counter fold
# ---------------------------------------------------------------------------

def converged_weight(
    edge_cid: str,
    assertions: Iterable[WeightAssertion],
) -> int:
    """Return the converged integer weight for *edge_cid*.

    Algorithm (G-Counter join-semilattice fold):
      1. Filter to assertions for *edge_cid*.
      2. Group by source; take max(count) per group.
      3. Sum the per-source maxima.

    Properties:
      * Monotone — adding more assertions never decreases the result.
      * Idempotent — re-delivering the same assertion set is a no-op.
      * Order-independent — any gossip delivery order converges to the same value.
      * Sybil-bounded — two assertions from the same source collapse; only distinct
        sources can increase the total.

    Returns 0 when no assertions exist for *edge_cid* (the edge has weight 0 in the
    convergent sense, distinct from the structural weight=1 stored on the Edge itself).
    """
    per_source: dict[str, int] = {}
    for a in assertions:
        if a.edge_cid != edge_cid:
            continue
        if a.source not in per_source or a.count > per_source[a.source]:
            per_source[a.source] = a.count
    return sum(per_source.values())


# ---------------------------------------------------------------------------
# Checkpoint commitment
# ---------------------------------------------------------------------------

def weight_root(assertions: Iterable[WeightAssertion]) -> str:
    """Hex SHA-256 commitment over a set of WeightAssertions.

    Leaves are the canonical CBOR bytes of each assertion's to_record(), sorted
    for determinism, then reduced via the same Merkle-root function used by
    web_state_root.  An empty assertion set returns the SHA-256 of b"" (the
    canonical empty-set sentinel) as 64 hex chars.

    Suitable for inclusion in a FabricCheckpoint so verifiers can audit the
    full assertion corpus offline.
    """
    recs = sorted(
        {canonical.encode(a.to_record()) for a in assertions}
    )
    leaves = [crypto.sha256(r) for r in recs]
    return crypto.merkle_root(leaves).hex()

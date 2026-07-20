"""Property tests for fabric.weight — G-Counter WeightAssertion convergence."""

import pytest

from knitweb.fabric.weight import WeightAssertion, converged_weight, weight_root
from knitweb.fabric.web import Edge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wa(edge_cid: str, source: str, count: int) -> WeightAssertion:
    return WeightAssertion(edge_cid=edge_cid, source=source, count=count)


def _edge_cid(src="A", dst="B", rel="supports") -> str:
    return Edge(src=src, dst=dst, rel=rel).cid


# ---------------------------------------------------------------------------
# WeightAssertion construction
# ---------------------------------------------------------------------------

class TestWeightAssertionConstruction:
    def test_round_trip_canonical(self):
        from knitweb.core import canonical
        a = _wa("cid1", "src1", 3)
        assert canonical.cid(a.to_record()) == a.cid

    def test_rejects_zero_count(self):
        with pytest.raises(TypeError):
            _wa("cid1", "src1", 0)

    def test_rejects_negative_count(self):
        with pytest.raises(TypeError):
            _wa("cid1", "src1", -1)

    def test_rejects_float_count(self):
        with pytest.raises(TypeError):
            _wa("cid1", "src1", 1.5)  # type: ignore[arg-type]

    def test_rejects_empty_edge_cid(self):
        with pytest.raises(TypeError):
            _wa("", "src1", 1)

    def test_rejects_empty_source(self):
        with pytest.raises(TypeError):
            _wa("cid1", "", 1)

    def test_frozen(self):
        a = _wa("cid1", "src1", 3)
        with pytest.raises(Exception):
            a.count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# converged_weight — core G-Counter properties
# ---------------------------------------------------------------------------

class TestConvergedWeight:
    def test_empty_returns_zero(self):
        assert converged_weight("cid-x", []) == 0

    def test_no_matching_assertions_returns_zero(self):
        a = _wa("other-cid", "src1", 5)
        assert converged_weight("cid-x", [a]) == 0

    def test_single_assertion(self):
        cid = _edge_cid()
        a = _wa(cid, "src1", 3)
        assert converged_weight(cid, [a]) == 3

    def test_two_distinct_sources_sum(self):
        cid = _edge_cid()
        a1 = _wa(cid, "alice", 3)
        a2 = _wa(cid, "bob", 5)
        assert converged_weight(cid, [a1, a2]) == 8

    def test_same_source_takes_max_not_sum(self):
        """Two assertions from the same source — only the higher count counts."""
        cid = _edge_cid()
        a_old = _wa(cid, "alice", 2)
        a_new = _wa(cid, "alice", 7)
        assert converged_weight(cid, [a_old, a_new]) == 7

    def test_idempotent_duplicate_delivery(self):
        """Re-delivering the same assertion is a no-op."""
        cid = _edge_cid()
        a = _wa(cid, "alice", 4)
        assert converged_weight(cid, [a, a, a]) == 4

    def test_order_independent(self):
        """Fold result is the same regardless of delivery order."""
        cid = _edge_cid()
        assertions = [
            _wa(cid, "alice", 3),
            _wa(cid, "bob", 5),
            _wa(cid, "alice", 4),
        ]
        import itertools
        results = {
            converged_weight(cid, list(perm))
            for perm in itertools.permutations(assertions)
        }
        assert len(results) == 1  # all orderings give 4 + 5 = 9
        assert results.pop() == 9

    def test_monotone_adding_assertion_never_decreases(self):
        """Adding more assertions never decreases the weight."""
        cid = _edge_cid()
        base = [_wa(cid, "alice", 3)]
        w1 = converged_weight(cid, base)
        base_plus = base + [_wa(cid, "bob", 1)]
        w2 = converged_weight(cid, base_plus)
        assert w2 >= w1

    def test_sybil_same_source_does_not_amplify(self):
        """N assertions from the same source = 1 contribution, not N×count."""
        cid = _edge_cid()
        sybil = [_wa(cid, "attacker", 10)] * 100
        assert converged_weight(cid, sybil) == 10

    def test_independent_sources_required_for_growth(self):
        """Only distinct sources can increase the total weight."""
        cid = _edge_cid()
        one_source = [_wa(cid, "solo", 999)]
        two_sources = one_source + [_wa(cid, "peer", 1)]
        assert converged_weight(cid, two_sources) == 1000
        assert converged_weight(cid, one_source) == 999

    def test_partial_sync_monotone_lower_bound(self):
        """A peer with a subset of assertions gets a lower bound, not a wrong answer."""
        cid = _edge_cid()
        full = [_wa(cid, "a", 3), _wa(cid, "b", 5), _wa(cid, "c", 2)]
        subset = [_wa(cid, "a", 3), _wa(cid, "b", 5)]
        assert converged_weight(cid, subset) <= converged_weight(cid, full)

    def test_multiple_edges_isolated(self):
        """Assertions for different edges don't bleed into each other."""
        cid1 = _edge_cid("A", "B")
        cid2 = _edge_cid("C", "D")
        assertions = [_wa(cid1, "x", 10), _wa(cid2, "x", 7)]
        assert converged_weight(cid1, assertions) == 10
        assert converged_weight(cid2, assertions) == 7


# ---------------------------------------------------------------------------
# weight_root — deterministic commitment
# ---------------------------------------------------------------------------

class TestWeightRoot:
    def test_deterministic(self):
        cid = _edge_cid()
        assertions = [_wa(cid, "a", 1), _wa(cid, "b", 2)]
        r1 = weight_root(assertions)
        r2 = weight_root(reversed(assertions))
        assert r1 == r2

    def test_hex_64_chars(self):
        r = weight_root([_wa(_edge_cid(), "src", 1)])
        assert len(r) == 64
        int(r, 16)  # must be valid hex

    def test_empty_returns_sentinel(self):
        import hashlib
        expected = hashlib.sha256(b"").hexdigest()
        # merkle_root of empty list → sha256(b"") → 64 hex
        r = weight_root([])
        assert r == expected

    def test_different_assertions_different_root(self):
        cid = _edge_cid()
        r1 = weight_root([_wa(cid, "a", 1)])
        r2 = weight_root([_wa(cid, "a", 2)])
        assert r1 != r2

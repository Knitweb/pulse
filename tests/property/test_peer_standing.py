"""Proofs for peer standing — the positive, reward-side counterpart to reputation.

Reputation accrues misbehavior toward a ban; standing accrues *sustained* clean epochs toward a
bounded reward bonus. The streak grows one per clean epoch and resets to zero on any fault, so only
uninterrupted service accumulates standing. Deterministic and integer-only — epoch advancement is
explicit, never wall-clock; the reward weight is basis points so no float touches a settled value.
"""

import pytest

from knitweb.p2p.standing import (
    BASE_WEIGHT_BPS,
    DEFAULT_MAX_BONUS_BPS,
    DEFAULT_MAX_STREAK,
    PeerStanding,
)

A = "did:key:peerA"
B = "did:key:peerB"
C = "did:key:peerC"


# ── 1. Accrual ────────────────────────────────────────────────────────────────

def test_unknown_peer_is_at_par():
    s = PeerStanding()
    assert s.streak(A) == 0
    assert s.reward_weight_bps(A) == BASE_WEIGHT_BPS      # 1.0x, no bonus
    assert s.tier(A) == 0
    assert s.standing() == []
    assert s.tracked() == 0


def test_credit_accumulates_streak():
    s = PeerStanding()
    assert s.credit(A) == 1
    assert s.credit(A) == 2
    assert s.credit(A) == 3
    assert s.streak(A) == 3
    assert s.reward_weight_bps(A) > BASE_WEIGHT_BPS       # a bonus has accrued


def test_streak_saturates_at_max():
    s = PeerStanding(max_streak=10)
    for _ in range(25):
        s.credit(A)
    assert s.streak(A) == 10                              # capped, not 25
    assert s.reward_weight_bps(A) == BASE_WEIGHT_BPS + s.max_bonus_bps


# ── 2. A fault forfeits sustained standing ───────────────────────────────────

def test_fault_resets_streak_to_zero():
    s = PeerStanding()
    for _ in range(20):
        s.credit(A)
    assert s.streak(A) == 20
    s.fault(A)
    assert s.streak(A) == 0
    assert s.reward_weight_bps(A) == BASE_WEIGHT_BPS      # bonus forfeited
    assert s.tier(A) == 0


def test_cannot_farm_by_alternating():
    """Alternating good/bad epochs never accumulates standing — stability must be sustained."""
    s = PeerStanding()
    for _ in range(50):
        s.credit(A)
        s.fault(A)
    assert s.streak(A) == 0
    assert s.reward_weight_bps(A) == BASE_WEIGHT_BPS


# ── 3. Reward weight: bounded, monotonic, integer ────────────────────────────

def test_weight_is_monotonic_in_streak():
    s = PeerStanding(max_streak=52)
    prev = s.reward_weight_bps(A)
    for _ in range(52):
        s.credit(A)
        now = s.reward_weight_bps(A)
        assert now >= prev                                # never decreases as streak grows
        prev = now


def test_weight_is_bounded():
    s = PeerStanding(max_streak=52, max_bonus_bps=2500)
    for _ in range(1000):
        s.credit(A)
    # Even after far more than max_streak epochs, the bonus is capped.
    assert s.reward_weight_bps(A) == BASE_WEIGHT_BPS + 2500


def test_apply_weight_par_peer_is_identity():
    s = PeerStanding()
    assert s.apply_weight(A, 1_000_000) == 1_000_000      # streak 0 → exactly base reward


def test_apply_weight_scales_and_never_cuts():
    s = PeerStanding(max_streak=10, max_bonus_bps=2500)
    for _ in range(10):
        s.credit(A)
    # Fully-standing peer: +25% on a 1_000_000-wei base reward.
    assert s.apply_weight(A, 1_000_000) == 1_250_000
    # Never reduces below the base for any streak.
    s.fault(A)
    s.credit(A)
    assert s.apply_weight(A, 1_000_000) >= 1_000_000


def test_apply_weight_rejects_negative_reward():
    s = PeerStanding()
    with pytest.raises((TypeError, ValueError)):
        s.apply_weight(A, -1)


# ── 4. Tiers ──────────────────────────────────────────────────────────────────

def test_tier_spans_zero_to_max():
    s = PeerStanding(max_streak=40, tiers=5)
    assert s.tier(A) == 0
    for _ in range(40):
        s.credit(A)
    assert s.tier(A) == 4                                 # top tier == tiers-1
    # Tiers are non-decreasing along the streak.
    s2 = PeerStanding(max_streak=40, tiers=5)
    seen = []
    for _ in range(40):
        s2.credit(B)
        seen.append(s2.tier(B))
    assert seen == sorted(seen)


# ── 5. Deterministic ordering ────────────────────────────────────────────────

def test_standing_orders_by_streak_then_peer():
    s = PeerStanding()
    for _ in range(3):
        s.credit(A)
    for _ in range(5):
        s.credit(B)
    s.credit(C)                                           # streak 1
    # B(5) > A(3) > C(1)
    assert s.standing() == [B, A, C]


def test_standing_excludes_zero_streak_peers():
    s = PeerStanding()
    s.credit(A)
    s.fault(A)                                            # back to 0 → dropped from listing
    s.credit(B)
    assert s.standing() == [B]


def test_determinism_same_stream_same_state():
    """Two ledgers replaying the same call stream reach identical state — no wall-clock/randomness."""
    stream = [("credit", A), ("credit", B), ("fault", A), ("credit", B), ("credit", A)]
    s1, s2 = PeerStanding(), PeerStanding()
    for ledger in (s1, s2):
        for op, peer in stream:
            getattr(ledger, op)(peer)
    assert s1.streak(A) == s2.streak(A)
    assert s1.streak(B) == s2.streak(B)
    assert s1.reward_weight_bps(B) == s2.reward_weight_bps(B)
    assert s1.standing() == s2.standing()


# ── 6. Validation ─────────────────────────────────────────────────────────────

def test_rejects_empty_peer():
    s = PeerStanding()
    for bad in ("", None, 123):
        with pytest.raises(TypeError):
            s.credit(bad)


def test_constructor_rejects_bad_bounds():
    with pytest.raises((TypeError, ValueError)):
        PeerStanding(max_streak=0)
    with pytest.raises((TypeError, ValueError)):
        PeerStanding(max_bonus_bps=-1)
    with pytest.raises((TypeError, ValueError)):
        PeerStanding(tiers=0)

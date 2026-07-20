"""Peer standing — reward *sustained* good performance, the positive counterpart to reputation.

:mod:`knitweb.p2p.reputation` is deliberately punitive: it accrues misbehavior points and bans a
peer that crosses a threshold. That is the *consequence* layer. But a credibly-neutral DePIN web
also needs the *incentive* layer — a reason for an honest operator to keep a node up and serving
pulses week after week. Detection-and-ban tells a peer what NOT to do; it never rewards the peer
who quietly does the right thing for a year. This module is that missing positive signal.

The quantity rewarded is **stability**, not raw volume. A peer earns standing by stringing together
consecutive clean Pulse epochs — an epoch in which it served its obligations and committed no
provable offense. One fault resets the streak to zero: stable performance must be *sustained*, so a
peer cannot farm standing by alternating good and bad epochs. Sustained streaks convert to a
**bounded integer reward weight** (basis points) that the issuance/settlement layer
(:mod:`knitweb.token.mint`, :mod:`knitweb.pouw.marketplace`) can multiply into a worker's reward,
and to a coarse **tier** that gating layers (votebank weight, committee-selection priority) can read.

Determinism is the whole point, exactly as in reputation: **no wall-clock and no randomness**. Epoch
advancement is driven by explicit ``credit``/``fault`` calls a caller makes per Pulse epoch, so two
honest nodes replaying the same performance stream compute byte-identical standing — the reward
weight is reproducible, not node-local guesswork. Every quantity is an integer; the reward weight is
basis points (10000 = 1.0x) so no float ever touches a hashed, signed, or settled value. Standing is
bounded above (a cap on the streak) so the weight can never inflate a reward without limit.
"""

from __future__ import annotations

from typing import Dict, List

__all__ = [
    "BASE_WEIGHT_BPS",
    "DEFAULT_MAX_STREAK",
    "DEFAULT_MAX_BONUS_BPS",
    "DEFAULT_TIERS",
    "PeerStanding",
]

# A peer with no streak earns the base reward weight: 10000 bps == 1.0x, i.e. no bonus and no
# penalty. Standing only ever *adds* a bounded bonus on top of this floor; it never cuts a reward
# below par (cutting bad work is reputation's job, via slashing/bans).
BASE_WEIGHT_BPS = 10_000

# Streak length (in Pulse epochs) at which the bonus saturates. ~52 weekly epochs ≈ one year of
# uninterrupted service to reach the maximum loyalty bonus.
DEFAULT_MAX_STREAK = 52

# The most a fully-saturated streak can add: +2500 bps == +25% reward. Bounded so issuance stays
# demand-gated — a long-standing peer earns a premium, never an unbounded multiplier.
DEFAULT_MAX_BONUS_BPS = 2_500

# Number of coarse standing tiers (0..DEFAULT_TIERS-1) for eligibility/weight gating.
DEFAULT_TIERS = 5


def _require_int(name: str, value: int, *, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int, not {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got {value})")


def _require_peer(peer: str) -> None:
    if not isinstance(peer, str) or not peer:
        raise TypeError("peer must be a non-empty str")


class PeerStanding:
    """Tracks per-peer stable-performance streaks and converts them to a bounded reward weight.

    All quantities are integers; a peer never seen has streak 0 and earns exactly the base weight
    (:data:`BASE_WEIGHT_BPS`, i.e. 1.0x — no bonus). The streak grows by one for each clean Pulse
    epoch (:meth:`credit`) and is reset to zero by any fault (:meth:`fault`), so only *sustained*
    good performance accumulates standing. The streak is capped at ``max_streak``, which bounds the
    reward weight at ``BASE_WEIGHT_BPS + max_bonus_bps``.
    """

    def __init__(
        self,
        max_streak: int = DEFAULT_MAX_STREAK,
        max_bonus_bps: int = DEFAULT_MAX_BONUS_BPS,
        tiers: int = DEFAULT_TIERS,
    ) -> None:
        _require_int("max_streak", max_streak, minimum=1)
        _require_int("max_bonus_bps", max_bonus_bps, minimum=0)
        _require_int("tiers", tiers, minimum=1)
        self.max_streak = max_streak
        self.max_bonus_bps = max_bonus_bps
        self.tiers = tiers
        self._streak: Dict[str, int] = {}

    # ── Mutations (one call per peer per Pulse epoch) ────────────────────────

    def credit(self, peer: str) -> int:
        """Record a clean epoch for ``peer``; returns the new (capped) streak.

        Idempotency is the caller's responsibility: call this exactly once per peer per epoch for an
        epoch the peer served without a provable offense. The streak saturates at ``max_streak`` —
        crediting beyond that is a no-op on the streak (the peer simply holds the maximum bonus).
        """
        _require_peer(peer)
        current = self._streak.get(peer, 0)
        if current < self.max_streak:
            self._streak[peer] = current + 1
        return self._streak[peer]

    def fault(self, peer: str) -> None:
        """Reset ``peer``'s streak to zero — a fault breaks sustained standing.

        Call this when the peer commits a provable offense or misses an epoch obligation. Standing is
        about *uninterrupted* service, so a single fault forfeits the accumulated bonus; the peer
        must rebuild from zero. (The punitive ban-score lives in :mod:`reputation`; this only zeroes
        the positive bonus, it does not itself ban.)
        """
        _require_peer(peer)
        self._streak.pop(peer, None)

    # ── Queries ──────────────────────────────────────────────────────────────

    def streak(self, peer: str) -> int:
        """The peer's current clean-epoch streak (0 if never seen)."""
        _require_peer(peer)
        return self._streak.get(peer, 0)

    def reward_weight_bps(self, peer: str) -> int:
        """The peer's reward weight in basis points (10000 == 1.0x, no bonus).

        Climbs linearly from :data:`BASE_WEIGHT_BPS` at streak 0 to
        ``BASE_WEIGHT_BPS + max_bonus_bps`` at ``streak >= max_streak``. Integer floor division
        keeps it exact and reproducible — a settlement layer multiplies a base reward by this and
        divides by :data:`BASE_WEIGHT_BPS`, all in integer PLS-wei.
        """
        _require_peer(peer)
        streak = min(self._streak.get(peer, 0), self.max_streak)
        bonus = (self.max_bonus_bps * streak) // self.max_streak
        return BASE_WEIGHT_BPS + bonus

    def apply_weight(self, peer: str, base_reward: int) -> int:
        """Scale an integer ``base_reward`` by the peer's standing weight (integer PLS-wei in/out).

        ``base_reward * reward_weight_bps // BASE_WEIGHT_BPS``. A peer at par (streak 0) gets exactly
        ``base_reward`` back; a fully-standing peer gets up to ``+max_bonus_bps`` more. Never reduces
        the reward below ``base_reward``.
        """
        _require_int("base_reward", base_reward, minimum=0)
        return base_reward * self.reward_weight_bps(peer) // BASE_WEIGHT_BPS

    def tier(self, peer: str) -> int:
        """A coarse standing tier in ``0..tiers-1`` for eligibility/weight gating.

        Tier 0 is a fresh or just-faulted peer; the top tier is a fully-saturated streak. Useful for
        votebank vote-weighting or committee-selection priority without exposing the raw streak.
        """
        _require_peer(peer)
        streak = min(self._streak.get(peer, 0), self.max_streak)
        # Map streak in [0, max_streak] onto [0, tiers-1] by integer scaling.
        return (streak * (self.tiers - 1)) // self.max_streak

    def standing(self) -> List[str]:
        """All peers with a positive streak, ordered by descending streak then peer id.

        Ordering is fully deterministic (streak desc, then lexicographic peer id) so any listing —
        e.g. picking the top-standing peers for a committee — is reproducible across nodes.
        """
        return [
            peer
            for peer, _ in sorted(
                self._streak.items(), key=lambda kv: (-kv[1], kv[0])
            )
            if self._streak[peer] > 0
        ]

    def tracked(self) -> int:
        """How many peers currently hold a non-zero streak record."""
        return len(self._streak)

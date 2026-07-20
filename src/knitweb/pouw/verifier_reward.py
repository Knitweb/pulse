"""Verifier kickback ledger — track earned rewards for committee participants.

A PoUW committee verifier re-executes a sampled job slice and casts a CONFIRM/MISMATCH
verdict. Without an economic incentive, a rational verifier has no reason to do this
work honestly or at all — "why verify when you earn nothing either way?"

This module is the accounting half of the kickback: an integer accumulator that records
how much each verifier has earned across all confirmed jobs it was part of. The actual
PLS transfer is left to the caller (e.g. a marketplace ``claim`` call that drives a
ledger transfer from a fee pool). Keeping accounting separate from settlement lets the
ledger be used in read-only audit paths and keeps the integer invariants clean.

Design invariants (same as SpiderQualityReputation and PeerStanding):
  * All quantities are integers (PLS-wei). No floats, ever.
  * No wall-clock. Epoch advancement is explicit.
  * Per-verifier balances are additive and non-negative.
  * "Already claimed" is tracked so callers can implement idempotent ``claim`` flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

__all__ = [
    "DEFAULT_VERIFIER_FEE_BPS",
    "VerifierEarning",
    "VerifierRewardLedger",
    "verifier_fee_split",
]

# Default fraction of the spider's mint that is shared with the committee.
# 200 bps = 2% split equally among k verifiers — large enough to be meaningful
# on modest mints, small enough not to significantly reduce the spider's reward.
DEFAULT_VERIFIER_FEE_BPS: int = 200


def _require_int(name: str, value: int, *, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int, not {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got {value})")


def _require_peer(name: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty str")


def verifier_fee_split(spider_reward: int, fee_bps: int, k: int) -> int:
    """The integer PLS-wei each of ``k`` committee members earns from ``spider_reward``.

    ``fee_bps`` is the fraction of the spider's mint shared with the full committee
    (in basis points, 10000 = 100%). The per-verifier share is floor division — the
    remainder stays with the spider (unaccounted surplus, always < k wei).

    Returns 0 when ``spider_reward`` is 0, ``fee_bps`` is 0, or ``k`` is 0.
    """
    _require_int("spider_reward", spider_reward)
    _require_int("fee_bps", fee_bps, minimum=0)
    if fee_bps > 10_000:
        raise ValueError("fee_bps must be <= 10000 (100%)")
    _require_int("k", k)
    if spider_reward == 0 or fee_bps == 0 or k == 0:
        return 0
    total_fee = spider_reward * fee_bps // 10_000
    return total_fee // k


@dataclass
class VerifierEarning:
    """Running totals for one verifier across all jobs it has been on."""

    verifier: str
    credited: int = 0    # total PLS-wei earned (credited by the marketplace)
    claimed: int = 0     # total PLS-wei already settled out to the verifier
    jobs: int = 0        # how many confirmed jobs this verifier participated in

    @property
    def claimable(self) -> int:
        """PLS-wei that has been credited but not yet claimed."""
        return self.credited - self.claimed


class VerifierRewardLedger:
    """Accumulates verifier kickback earnings across confirmed PoUW jobs.

    Usage pattern (in a marketplace ``run_job`` loop)::

        per_v = verifier_fee_split(spider_reward, fee_bps=200, k=len(committee))
        for v in committee:
            ledger.credit(v, per_v)

    Then later, when a verifier wants to claim::

        claimable = ledger.balance(verifier_addr)
        ledger.mark_claimed(verifier_addr, claimable)
        # caller drives the actual PLS transfer

    All arithmetic is integer PLS-wei. No wall-clock, no floats.
    """

    def __init__(self, fee_bps: int = DEFAULT_VERIFIER_FEE_BPS) -> None:
        _require_int("fee_bps", fee_bps, minimum=0)
        if fee_bps > 10_000:
            raise ValueError("fee_bps must be <= 10000 (100%)")
        self.fee_bps = fee_bps
        self._earnings: Dict[str, VerifierEarning] = {}

    def _get_or_create(self, verifier: str) -> VerifierEarning:
        _require_peer("verifier", verifier)
        if verifier not in self._earnings:
            self._earnings[verifier] = VerifierEarning(verifier=verifier)
        return self._earnings[verifier]

    def credit(self, verifier: str, amount: int) -> int:
        """Credit ``amount`` PLS-wei to ``verifier``'s earned balance. Returns new total."""
        _require_int("amount", amount, minimum=0)
        rec = self._get_or_create(verifier)
        rec.credited += amount
        rec.jobs += 1
        return rec.credited

    def mark_claimed(self, verifier: str, amount: int) -> int:
        """Record that ``amount`` PLS-wei has been settled to ``verifier``. Returns remaining."""
        _require_int("amount", amount, minimum=0)
        rec = self._get_or_create(verifier)
        if amount > rec.claimable:
            raise ValueError(
                f"claim {amount} exceeds claimable balance {rec.claimable} for {verifier!r}"
            )
        rec.claimed += amount
        return rec.claimable

    def balance(self, verifier: str) -> int:
        """Unclaimed (claimable) PLS-wei for ``verifier`` (0 if never seen)."""
        _require_peer("verifier", verifier)
        rec = self._earnings.get(verifier)
        return rec.claimable if rec is not None else 0

    def earning(self, verifier: str) -> VerifierEarning | None:
        """Full earning record for ``verifier``, or None if never seen."""
        return self._earnings.get(verifier)

    def credit_committee(self, committee: List[str], spider_reward: int) -> int:
        """Credit each member of ``committee`` their share of ``spider_reward``.

        Uses :func:`verifier_fee_split` with this ledger's ``fee_bps``. Returns
        the per-verifier amount credited (0 if reward is 0 or committee is empty).
        """
        per_v = verifier_fee_split(spider_reward, self.fee_bps, len(committee))
        if per_v > 0:
            for v in committee:
                self.credit(v, per_v)
        return per_v

    def all_earners(self) -> List[Tuple[str, int]]:
        """All verifiers with a non-zero credited balance, sorted by total earned desc."""
        return sorted(
            [(v, r.credited) for v, r in self._earnings.items() if r.credited > 0],
            key=lambda item: (-item[1], item[0]),
        )

    def tracked(self) -> int:
        """Number of verifiers with any earning record."""
        return len(self._earnings)

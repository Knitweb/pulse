"""Demand-gated settlement: pay a spider only for verified useful work.

The consumer commits pulses to a job; the spider does the work; a verifier
re-executes a sample (``pouw.job.verify``); only on success do the pulses settle
from consumer to worker. A fraudulent proof settles nothing — and is slashable.

Settlement is a conservation-preserving Knit transfer (no new issuance here), so
total PLS is unchanged: this is the sound subset of the economic loop we can prove
today, independent of the deferred mint/bootstrap-emission policy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from ..ledger.node import AccountNode
from .job import SynapticCompileJob, WorkProof, verify

__all__ = [
    "settle_on_verify",
    "ClaimRefund",
    "EscrowRelease",
    "EscrowState",
    "RefundClaims",
]

EscrowState = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class ClaimRefund:
    """A consumer's refund claim for a failed or disputed job."""
    claimant: str
    result_cid: str
    reason: str


@dataclass(frozen=True)
class EscrowRelease:
    """The release record emitted when a refund claim is approved."""
    escrow_id: str
    payee: str
    amount_pls: int  # always integer, never float


class RefundClaims:
    """In-memory registry of pending refund claims.

    ``submit`` → ``approve``/``reject`` lifecycle.  Amounts are enforced as
    integers at submit time.  Duplicate result_cid+claimant raises.
    """

    def __init__(self) -> None:
        self._claims: dict[str, tuple[ClaimRefund, EscrowState]] = {}
        self._amounts: dict[str, int] = {}

    def submit(self, claim: ClaimRefund, *, amount_pls: int) -> str:
        """Register a new claim.  Returns the escrow ID.  Raises on duplicate."""
        if not isinstance(amount_pls, int) or isinstance(amount_pls, bool):
            raise ValueError("amount_pls must be an integer")
        if amount_pls < 0:
            raise ValueError("amount_pls must be non-negative")
        eid = _escrow_id(claim)
        if eid in self._claims:
            raise ValueError(f"duplicate claim for escrow_id {eid!r}")
        self._claims[eid] = (claim, "pending")
        self._amounts[eid] = amount_pls
        return eid

    def approve(self, escrow_id: str) -> EscrowRelease:
        """Approve a pending claim; returns the release record."""
        if escrow_id not in self._claims:
            raise KeyError(escrow_id)
        claim, state = self._claims[escrow_id]
        if state != "pending":
            raise ValueError(f"claim {escrow_id!r} is already {state!r}")
        self._claims[escrow_id] = (claim, "approved")
        return EscrowRelease(
            escrow_id=escrow_id,
            payee=claim.claimant,
            amount_pls=self._amounts[escrow_id],
        )

    def reject(self, escrow_id: str) -> None:
        """Reject a pending claim; removes it from the registry."""
        if escrow_id not in self._claims:
            raise KeyError(escrow_id)
        self._claims.pop(escrow_id)
        self._amounts.pop(escrow_id, None)


def _escrow_id(claim: ClaimRefund) -> str:
    digest = hashlib.sha256(
        f"{claim.claimant}:{claim.result_cid}:{claim.reason}".encode()
    ).hexdigest()[:16]
    return f"escrow:{digest}"


def settle_on_verify(
    consumer: AccountNode,
    worker: AccountNode,
    pulses: int,
    job: SynapticCompileJob,
    proof: WorkProof,
    timestamp: int,
) -> bool:
    """Pay ``pulses`` (PLS) from ``consumer`` to ``worker`` iff ``proof`` verifies.

    Returns True when the work was confirmed and paid, False when the proof failed
    verification (no payment occurs, so a bad spider earns nothing).
    """
    if not verify(job, proof):
        return False
    consumer.transfer_to(worker, "PLS", pulses, timestamp)
    return True

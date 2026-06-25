"""Quorum-aware settlement for proof-of-useful-work.

A single verifier can be wrong or colluding.  This module closes the economic
loop by requiring a k-of-n quorum of independent re-executions before the
consumer's escrowed pulses are released to the worker.  The quorum logic lives
in :mod:`knitweb.pouw.quorum`; this layer maps job proofs to verifier verdicts
and settles only when the quorum outcome is ``CONFIRMED``.

The design keeps the heavy work (resolve + compile + verify) off the ledger:
verdicts are computed locally by peers, and only the boolean settlement result
touches the account state.
"""

from __future__ import annotations

from ..ledger.node import AccountNode
from ..p2p.standing import PeerStanding
from .escrow import settle_on_verify
from .job import SynapticCompileJob, WorkProof, verify
from .quorum import Outcome, QuorumResult, Verdict, tally

__all__ = ["proofs_to_verdicts", "settle_on_quorum"]


def proofs_to_verdicts(
    job: SynapticCompileJob,
    proofs: list[WorkProof],
) -> list[Verdict]:
    """Map each independent proof to a verifier verdict.

    A proof is either ``CONFIRM`` (re-execution matches and the originator
    signature is valid) or ``MISMATCH`` (anything else).  There is no abstention
    here; each verifier either produces a matching re-execution or does not.
    """
    return [
        Verdict.CONFIRM if verify(job, proof) else Verdict.MISMATCH
        for proof in proofs
    ]


def settle_on_quorum(
    consumer: AccountNode,
    worker: AccountNode,
    pulses: int,
    job: SynapticCompileJob,
    proofs: list[WorkProof],
    timestamp: int,
    *,
    worker_declared_fault: bool = False,
    threshold: int | None = None,
    standing: PeerStanding | None = None,
) -> tuple[bool, QuorumResult]:
    """Pay ``pulses`` from ``consumer`` to ``worker`` only after a confirming quorum.

    Parameters
    ----------
    consumer:
        Account that escrowed the pulses.
    worker:
        Account that performed the useful work.
    pulses:
        Integer PLS amount to transfer on confirmation.
    job:
        The work description peers re-execute.
    proofs:
        Independent proofs from distinct verifier peers.
    timestamp:
        Ledger timestamp for the Knit transfer.
    worker_declared_fault:
        If True, the worker itself admitted a fault and the outcome becomes
        ``DECLARED_FAULT`` (consumer is refunded).
    threshold:
        Optional explicit quorum threshold.  Defaults to a strict supermajority.
    standing:
        Optional :class:`~knitweb.p2p.standing.PeerStanding` ledger. When
        supplied, a confirmed-and-paid settlement calls ``credit(worker.address)``
        and a ``DECLARED_FAULT`` or ``DETECTED_FAULT`` calls
        ``fault(worker.address)``. ``INCONCLUSIVE`` and defensive-path outcomes
        leave standing unchanged. ``None`` (default) preserves the prior
        behaviour — no standing side-effect.

    Returns
    -------
    ``(paid, result)`` — ``paid`` is True only when the quorum confirmed and the
    ledger transfer succeeded.  On ``DETECTED_FAULT`` or ``DECLARED_FAULT`` no
    payment occurs and the consumer keeps the escrow.
    """
    verdicts = proofs_to_verdicts(job, proofs)
    result = tally(
        verdicts,
        worker_declared_fault=worker_declared_fault,
        threshold=threshold,
    )
    if not result.releases:
        # result.outcome is already final here (DECLARED_FAULT / DETECTED_FAULT /
        # INCONCLUSIVE) — tally() set it before returning, so we can act on it
        # directly. The _inconclusive_from() helper further below is only reached
        # via the confirmed branch where a proof later fails, overriding outcome.
        if standing is not None and result.outcome in (
            Outcome.DECLARED_FAULT, Outcome.DETECTED_FAULT
        ):
            standing.fault(worker.address)
        return False, result

    def _inconclusive_from(result: QuorumResult) -> QuorumResult:
        """Return a result with the same tallies but an INCONCLUSIVE outcome."""
        return QuorumResult(
            outcome=Outcome.INCONCLUSIVE,
            confirms=result.confirms,
            mismatches=result.mismatches,
            abstains=result.abstains,
            n=result.n,
            threshold=result.threshold,
        )

    # Quorum confirmed: settle using any confirmed proof.  settle_on_verify
    # performs the final local verification before touching ledger state.
    for proof in proofs:
        if verify(job, proof):
            try:
                paid = settle_on_verify(consumer, worker, pulses, job, proof, timestamp)
            except ValueError:
                # Ledger transfer failed (e.g. insufficient escrow).  Downgrade to
                # INCONCLUSIVE so callers never see releases=True while paid=False.
                return False, _inconclusive_from(result)
            if paid:
                if standing is not None:
                    standing.credit(worker.address)
                return True, result
            # Proof failed final verification; fall through to defensive path.
            return False, _inconclusive_from(result)

    # Defensive: tally said confirmed, yet no individual proof verified.
    # Treat as inconclusive and refuse payment.
    return False, _inconclusive_from(result)


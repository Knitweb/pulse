"""Quantum-circuit proof-of-useful-work — the compute-marketplace seam.

Registers a ``"quantum-circuit"`` PoUW job class so "run this circuit, return
verified measurement counts" becomes a unit of useful work a peer can be rewarded
for (à la Quip.Network). Because a seeded statevector simulation is
byte-reproducible, it settles under ``VERIFICATION_UNIFORM``: a verifier re-runs
the job and confirms byte-identical counts.

This is the SEAM — it does the work and proves it deterministically, but wiring
the reward to live escrow (``token.mint.Treasury.reward_verified_work``) is left
to the marketplace layer. The job carries the QASM directly (or a circuit_cid the
caller resolves from the artifact store first).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..core import canonical
from .pouw_register import ensure_registered
from .simulator import simulate_counts

__all__ = [
    "QuantumCircuitJob",
    "QuantumWorkProof",
    "execute",
    "verify",
    "counts_digest",
]

QUANTUM_JOB_CLASS = "quantum-circuit"


@dataclass(frozen=True)
class QuantumCircuitJob:
    """A unit of useful work: run *qasm* for *shots* shots seeded by *seed*.

    ``circuit_cid`` is optional provenance (the ``lcid:`` id of the artifact the
    QASM came from); it does not affect execution but binds the proof to a circuit.
    """

    qasm: str
    shots: int = 1024
    seed: int = 0
    circuit_cid: str = ""


@dataclass(frozen=True)
class QuantumWorkProof:
    """What a worker emits: the canonical counts bytes and their digest."""

    counts: bytes     # canonical-CBOR of the {bitstring: int} histogram
    digest: str       # sha256 hex of the canonical counts bytes


def counts_digest(counts: dict[str, int]) -> str:
    """Deterministic digest over an integer counts histogram."""
    return hashlib.sha256(canonical.encode(_canonical_counts(counts))).hexdigest()


def _canonical_counts(counts: dict[str, int]) -> dict[str, int]:
    # sorted keys, integer values only — canonical-CBOR clean, no floats
    return {k: int(counts[k]) for k in sorted(counts)}


def execute(job: QuantumCircuitJob) -> QuantumWorkProof:
    """Do the work: simulate the circuit and emit a reproducible proof."""
    ensure_registered()
    counts = simulate_counts(job.qasm, job.shots, job.seed)
    canon = _canonical_counts(counts)
    body = canonical.encode(canon)
    return QuantumWorkProof(counts=body, digest=hashlib.sha256(body).hexdigest())


def verify(job: QuantumCircuitJob, proof: QuantumWorkProof) -> bool:
    """Sampled re-execution: independently redo the job and confirm the proof.

    Deterministic booleans only:
      1. the claimed digest matches the claimed counts bytes, and
      2. re-running the seeded simulation reproduces byte-identical counts.
    Either failure ⇒ the proof is fraudulent and must not settle (slashable).
    """
    if hashlib.sha256(proof.counts).hexdigest() != proof.digest:
        return False
    recomputed = canonical.encode(_canonical_counts(simulate_counts(job.qasm, job.shots, job.seed)))
    return recomputed == proof.counts

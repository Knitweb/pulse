"""Phase C — quantum-circuit PoUW job: determinism, verification, registration."""

import pytest

from knitweb.pouw.job import VERIFICATION_UNIFORM, verification_policy
from knitweb.quantum import (
    QuantumCircuitJob, execute, verify, simulate_counts, QUANTUM_JOB_CLASS,
)
from knitweb.quantum.job import QuantumWorkProof


BELL = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0],q[1];
"""

GHZ3 = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
h q[0];
cx q[0],q[1];
cx q[1],q[2];
"""


# ── registration ─────────────────────────────────────────────────────────
def test_job_class_registered_uniform():
    # importing knitweb.quantum registers the class
    assert verification_policy(QUANTUM_JOB_CLASS) == VERIFICATION_UNIFORM


# ── determinism ──────────────────────────────────────────────────────────
def test_execute_is_deterministic():
    job = QuantumCircuitJob(qasm=BELL, shots=2048, seed=42)
    p1 = execute(job)
    p2 = execute(job)
    assert p1.digest == p2.digest
    assert p1.counts == p2.counts


def test_different_seed_changes_sampling_not_support():
    a = execute(QuantumCircuitJob(qasm=BELL, shots=4096, seed=1))
    b = execute(QuantumCircuitJob(qasm=BELL, shots=4096, seed=2))
    # different seeds → generally different histograms (digests differ)…
    assert a.digest != b.digest
    # …but a Bell state only ever produces 00 / 11, whatever the seed
    import knitweb.core.canonical as canonical
    for proof in (a, b):
        hist = canonical.decode(proof.counts)
        assert set(hist) <= {"00", "11"}


# ── verification ─────────────────────────────────────────────────────────
def test_verify_accepts_honest_proof():
    job = QuantumCircuitJob(qasm=GHZ3, shots=1024, seed=7)
    assert verify(job, execute(job)) is True


def test_verify_rejects_tampered_counts():
    job = QuantumCircuitJob(qasm=BELL, shots=1024, seed=7)
    proof = execute(job)
    tampered = QuantumWorkProof(counts=proof.counts + b"\x00", digest=proof.digest)
    assert verify(job, tampered) is False


def test_verify_rejects_wrong_digest():
    job = QuantumCircuitJob(qasm=BELL, shots=1024, seed=7)
    proof = execute(job)
    forged = QuantumWorkProof(counts=proof.counts, digest="0" * 64)
    assert verify(job, forged) is False


def test_verify_rejects_different_shots():
    job = QuantumCircuitJob(qasm=BELL, shots=1024, seed=7)
    proof = execute(job)
    # a proof for 1024 shots must not verify against a 2048-shot job
    assert verify(QuantumCircuitJob(qasm=BELL, shots=2048, seed=7), proof) is False


# ── simulator physical sanity ────────────────────────────────────────────
def test_bell_only_correlated_outcomes():
    counts = simulate_counts(BELL, shots=4000, seed=123)
    assert set(counts) <= {"00", "11"}
    # both outcomes appear with a fair coin (loose bounds, deterministic seed)
    assert counts.get("00", 0) > 500 and counts.get("11", 0) > 500


def test_ghz_only_all_zero_or_all_one():
    counts = simulate_counts(GHZ3, shots=3000, seed=99)
    assert set(counts) <= {"000", "111"}


def test_x_gate_flips():
    qasm = 'OPENQASM 2.0;\nqreg q[1];\nx q[0];\n'
    counts = simulate_counts(qasm, shots=100, seed=0)
    assert counts == {"1": 100}

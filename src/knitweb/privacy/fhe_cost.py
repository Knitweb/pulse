"""Honest cost/time model for FHE workloads across the compute swarm.

This module estimates **wall-clock time, total node-work and a PLS price** for a
fully-homomorphic-encryption job *without* running (or even installing) FHE.  It
is a planning tool: given an op-count and the number of peers available to
compute, it answers "how long, how much".

Honesty
-------
The per-op latencies are **order-of-magnitude estimates** drawn from published
CKKS benchmarks (Microsoft SEAL / OpenFHE, single modern CPU core, RNS-CKKS).
They are deliberately coarse and labelled as such — do not read them as a
guarantee.  Re-measure on real hardware before pricing a production job.

Parallelism
-----------
FHE over a swarm is only *partly* parallel: independent ciphertexts / SIMD
batches spread across nodes, but a multiplicative-depth chain is sequential.  We
model this with **Amdahl's law** so the estimate respects a sequential floor —
throwing more nodes at a deep circuit cannot beat its critical path.

    wall = serial * ((1 - f) + f / nodes)        # f = parallel fraction

Everything that touches a settlement price is integer (PLS); only the timing
analytics are floats.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Supported schemes (only CKKS is modelled for now — the common ML/aggregation
# choice; BFV/BGV would need their own table).
SCHEME_CKKS = "CKKS"
SUPPORTED_SCHEMES = frozenset({SCHEME_CKKS})

# Per-op latency table, milliseconds per op, single CPU core.
# Keyed by (scheme, ring_degree).  Honest order-of-magnitude figures from
# published RNS-CKKS benchmarks; "bootstrap" is the expensive refresh op.
#   add    : ciphertext + ciphertext
#   mul    : ciphertext * ciphertext incl. relinearisation
#   rotate : Galois rotation (for SIMD slot shifts)
#   bootstrap : noise refresh (only some ring sizes support it)
_LATENCY_MS: dict[tuple[str, int], dict[str, float]] = {
    (SCHEME_CKKS, 8192): {"add": 0.05, "mul": 6.0, "rotate": 5.0, "bootstrap": math.inf},
    (SCHEME_CKKS, 16384): {"add": 0.1, "mul": 20.0, "rotate": 18.0, "bootstrap": math.inf},
    (SCHEME_CKKS, 32768): {"add": 0.2, "mul": 70.0, "rotate": 60.0, "bootstrap": 10000.0},
    (SCHEME_CKKS, 65536): {"add": 0.4, "mul": 240.0, "rotate": 210.0, "bootstrap": 30000.0},
}

SUPPORTED_RING_DEGREES = frozenset(deg for _, deg in _LATENCY_MS)


@dataclass(frozen=True)
class FHEParams:
    """Cryptographic parameters that drive the latency table."""

    ring_degree: int  # poly modulus degree N (a power of two)
    scheme: str = SCHEME_CKKS

    def __post_init__(self) -> None:
        if self.scheme not in SUPPORTED_SCHEMES:
            raise ValueError(f"unsupported scheme {self.scheme!r}")
        if (self.scheme, self.ring_degree) not in _LATENCY_MS:
            raise ValueError(
                f"no benchmark for {self.scheme} ring_degree={self.ring_degree}; "
                f"supported: {sorted(SUPPORTED_RING_DEGREES)}"
            )


@dataclass(frozen=True)
class Workload:
    """The homomorphic op-counts of a job (all integers)."""

    adds: int = 0
    mults: int = 0
    rotations: int = 0
    bootstraps: int = 0

    def __post_init__(self) -> None:
        for name, v in (
            ("adds", self.adds),
            ("mults", self.mults),
            ("rotations", self.rotations),
            ("bootstraps", self.bootstraps),
        ):
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"{name} must be int")
            if v < 0:
                raise ValueError(f"{name} must be >= 0")

    @property
    def total_ops(self) -> int:
        return self.adds + self.mults + self.rotations + self.bootstraps


@dataclass(frozen=True)
class Estimate:
    """Result of :func:`estimate`."""

    wall_time_s: float
    node_seconds: float
    serial_time_s: float
    total_ops: int
    cost_pls: int
    notes: tuple[str, ...] = field(default_factory=tuple)


def op_latencies_ms(params: FHEParams) -> dict[str, float]:
    """Return the per-op latency table (ms) for the given parameters."""
    return dict(_LATENCY_MS[(params.scheme, params.ring_degree)])


def serial_time_ms(workload: Workload, params: FHEParams) -> float:
    """Total single-core time (ms) to run the whole workload sequentially."""
    lat = _LATENCY_MS[(params.scheme, params.ring_degree)]
    if workload.bootstraps and not math.isfinite(lat["bootstrap"]):
        raise ValueError(
            f"ring_degree={params.ring_degree} does not support bootstrapping; "
            "pick a larger ring or remove bootstraps"
        )
    total = (
        workload.adds * lat["add"]
        + workload.mults * lat["mul"]
        + workload.rotations * lat["rotate"]
        + workload.bootstraps * lat["bootstrap"]
    )
    return total


def estimate(
    workload: Workload,
    params: FHEParams,
    *,
    nodes_available: int,
    parallel_fraction: float = 0.9,
    pls_per_node_second: int = 1,
) -> Estimate:
    """Estimate wall-time, node-work and PLS price for ``workload``.

    Parameters
    ----------
    nodes_available:
        Number of swarm peers that can compute in parallel (>= 1).
    parallel_fraction:
        Amdahl ``f`` in ``[0, 1]`` — the share of work that parallelises across
        nodes.  The remaining ``1 - f`` is the sequential critical path that more
        nodes cannot speed up.  Default 0.9 (mostly-batched workload).
    pls_per_node_second:
        Integer settlement rate; ``cost_pls = ceil(node_seconds * rate)``.
    """
    if not isinstance(nodes_available, int) or isinstance(nodes_available, bool):
        raise TypeError("nodes_available must be int")
    if nodes_available < 1:
        raise ValueError("nodes_available must be >= 1")
    if not (0.0 <= parallel_fraction <= 1.0):
        raise ValueError("parallel_fraction must be in [0, 1]")
    if not isinstance(pls_per_node_second, int) or isinstance(pls_per_node_second, bool):
        raise TypeError("pls_per_node_second must be int")
    if pls_per_node_second < 0:
        raise ValueError("pls_per_node_second must be >= 0")

    serial_s = serial_time_ms(workload, params) / 1000.0
    # Amdahl: sequential floor + parallel part divided over nodes.
    f = parallel_fraction
    wall_s = serial_s * ((1.0 - f) + f / nodes_available)
    node_seconds = serial_s  # total CPU-seconds of useful work is node-count-invariant
    cost_pls = math.ceil(node_seconds * pls_per_node_second)

    notes: list[str] = [
        "latencies are order-of-magnitude CKKS estimates; re-measure for production"
    ]
    if workload.bootstraps:
        notes.append("bootstrap dominates cost; minimise multiplicative depth")
    if f < 1.0 and nodes_available > 1:
        notes.append(
            f"sequential floor: wall cannot drop below {serial_s * (1.0 - f):.3f}s"
        )

    return Estimate(
        wall_time_s=wall_s,
        node_seconds=node_seconds,
        serial_time_s=serial_s,
        total_ops=workload.total_ops,
        cost_pls=cost_pls,
        notes=tuple(notes),
    )

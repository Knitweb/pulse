"""Knitweb privacy layer.

Modules
-------
``fhe_cost``  honest wall-time / node-work / PLS estimator for FHE workloads.

Future (separate PRs): ``fhe`` (real optional CKKS backend behind ``knitweb[fhe]``),
``additive`` (Paillier — *partially* homomorphic, never labelled FHE),
``zerotrust`` (authorize policy), ``enclave`` (TEE placement seam).
"""

from .fhe_cost import (
    SCHEME_CKKS,
    SUPPORTED_RING_DEGREES,
    SUPPORTED_SCHEMES,
    Estimate,
    FHEParams,
    Workload,
    estimate,
    op_latencies_ms,
    serial_time_ms,
)

__all__ = [
    "SCHEME_CKKS",
    "SUPPORTED_RING_DEGREES",
    "SUPPORTED_SCHEMES",
    "Estimate",
    "FHEParams",
    "Workload",
    "estimate",
    "op_latencies_ms",
    "serial_time_ms",
]

"""Knitweb privacy layer.

Modules
-------
``fhe``       real FHE seam; optional CKKS backend behind ``knitweb[fhe]``.
``additive``  Paillier — *partially* homomorphic (add-only), never FHE.
``fhe_cost``  honest wall-time / node-work / PLS estimator for FHE workloads.
``zerotrust`` "never trust, always verify" authorize policy over existing gates.
``enclave``   Central Computation Enclave placement policy + TEE attestation seam.
"""

from .additive import (
    PaillierPrivateKey,
    PaillierPublicKey,
    generate_keypair,
)
from .enclave import (
    AttestationVerifier,
    EnclaveError,
    EnclavePolicy,
    NodeAttestation,
    NodeProfile,
    TrustedAllowlistVerifier,
    eligible_nodes,
    is_eligible,
)
from .fhe import (
    SCHEME_CKKS,
    Ciphertext,
    FHEBackendUnavailable,
    FHEContext,
    available_backends,
    create_context,
)
from .fhe_cost import (
    SUPPORTED_RING_DEGREES,
    SUPPORTED_SCHEMES,
    Estimate,
    FHEParams,
    Workload,
    estimate,
    op_latencies_ms,
    serial_time_ms,
)
from .zerotrust import (
    ACTION_MIN_TIER,
    ACTIONS_REQUIRING_PROVEN_ID,
    Action,
    Decision,
    authorize,
)

__all__ = [
    # FHE seam (real FHE via optional backend)
    "SCHEME_CKKS",
    "Ciphertext",
    "FHEBackendUnavailable",
    "FHEContext",
    "available_backends",
    "create_context",
    # additive (Paillier — partially homomorphic, NOT FHE)
    "PaillierPublicKey",
    "PaillierPrivateKey",
    "generate_keypair",
    # cost model
    "SUPPORTED_RING_DEGREES",
    "SUPPORTED_SCHEMES",
    "Estimate",
    "FHEParams",
    "Workload",
    "estimate",
    "op_latencies_ms",
    "serial_time_ms",
    # zero-trust authorization
    "Action",
    "Decision",
    "authorize",
    "ACTION_MIN_TIER",
    "ACTIONS_REQUIRING_PROVEN_ID",
    # enclave placement (TEE attestation seam)
    "AttestationVerifier",
    "EnclaveError",
    "EnclavePolicy",
    "NodeAttestation",
    "NodeProfile",
    "TrustedAllowlistVerifier",
    "eligible_nodes",
    "is_eligible",
]

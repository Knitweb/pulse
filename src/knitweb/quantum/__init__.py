"""knitweb.quantum — the fabric bridge for quantum artifacts.

Publishes content-addressed quantum circuits, results and system descriptors onto
the Knitweb P2P fabric as first-class typed records, indexes them for the
read-only ``/interpret`` lens gateway, and estimates query size before retrieval.

The full artifacts (QASM, float error-rates) are minted and stored by the
``knitweb-lens`` SDK under the ``lcid:``/``lres:``/``lqpu:`` namespaces; this
module carries the lean, canonical, queryable descriptors on the fabric.
"""

from .records import (
    QuantumCircuitRecord,
    QuantumResultRecord,
    QuantumSystemRecord,
)
from .index import atoms_for, index_into
from .publish import publish, weave_into, link_provenance
from .estimate import estimate_circuits, estimate_bytes
from .lens_gateway import build_lens, query_space
from .job import (
    QuantumCircuitJob, QuantumWorkProof, execute, verify, counts_digest,
    QUANTUM_JOB_CLASS,
)
from .simulator import simulate_counts

__all__ = [
    "QuantumCircuitRecord", "QuantumResultRecord", "QuantumSystemRecord",
    "atoms_for", "index_into",
    "publish", "weave_into", "link_provenance",
    "estimate_circuits", "estimate_bytes",
    "build_lens", "query_space",
    "QuantumCircuitJob", "QuantumWorkProof", "execute", "verify", "counts_digest",
    "QUANTUM_JOB_CLASS", "simulate_counts",
]

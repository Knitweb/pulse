"""Quantum artifact records — first-class fabric nodes for circuits, results
and quantum systems.

These mirror :mod:`knitweb.fabric.items`: frozen dataclasses that round-trip
through canonical CBOR, so their CIDs are deterministic and collision-free across
peers, and that ``weave()`` themselves into a :class:`~knitweb.fabric.web.Web`.

They are LEAN, queryable *descriptors* that reference the full artifact by its
content id (``lcid:`` circuit / ``lres:`` result / ``lqpu:`` system) minted by the
``knitweb-lens`` SDK. The heavy bytes (QASM source, full float error-rates) live in
the artifact store the relay syncs; the fabric record carries only canonical-safe,
integer/string fields so every peer hashes it identically. No floats ever enter a
record (canonical-CBOR determinism), matching the rest of the fabric.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import canonical
from ..fabric.items import ResourceItem
from ..fabric.web import Web

__all__ = [
    "QuantumCircuitRecord",
    "QuantumResultRecord",
    "QuantumSystemRecord",
]


def _require_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int")


# ---------------------------------------------------------------------------
# QuantumCircuitRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuantumCircuitRecord:
    """A content-addressed quantum circuit descriptor on the fabric.

    ``circuit_cid`` is the ``lcid:`` id of the full circuit artifact (QASM); the
    record itself is a queryable summary. Tags are stored sorted so the canonical
    encoding is insertion-order independent.
    """

    circuit_cid: str        # lcid:... — the full-artifact content id
    name: str
    qubits: int
    author: str = ""        # PLS address of the publishing spider
    domain: str = "fundamental"
    depth: int = 0
    source_lang: str = "qasm2"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.circuit_cid.startswith("lcid:"):
            raise ValueError("circuit_cid must be an lcid: content id")
        _require_int("qubits", self.qubits)
        _require_int("depth", self.depth)
        if self.qubits < 0 or self.depth < 0:
            raise ValueError("qubits and depth must be non-negative")

    def to_record(self) -> dict:
        return {
            "kind": "quantum-circuit",
            "circuit_cid": self.circuit_cid,
            "name": self.name,
            "qubits": self.qubits,
            "author": self.author,
            "domain": self.domain,
            "depth": self.depth,
            "source_lang": self.source_lang,
            "tags": sorted(self.tags),
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def weave(self, web: Web) -> str:
        return web.weave(self.to_record())


# ---------------------------------------------------------------------------
# QuantumResultRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuantumResultRecord:
    """A content-addressed execution-result descriptor on the fabric.

    ``counts`` is a bitstring -> shot-count histogram (all integer values, so it
    is canonical-CBOR safe). ``result_cid`` is the ``lres:`` id of the full result
    artifact; ``circuit_cid`` / ``backend_cid`` link provenance.
    """

    result_cid: str         # lres:...
    circuit_cid: str        # lcid:... the circuit that was executed
    counts: dict[str, int]
    shots: int = 0
    backend_cid: str = ""   # lqpu:... the system it ran on, if known
    author: str = ""

    def __post_init__(self) -> None:
        if not self.result_cid.startswith("lres:"):
            raise ValueError("result_cid must be an lres: content id")
        if not self.circuit_cid.startswith("lcid:"):
            raise ValueError("circuit_cid must be an lcid: content id")
        if self.backend_cid and not self.backend_cid.startswith("lqpu:"):
            raise ValueError("backend_cid must be an lqpu: content id")
        if not self.counts:
            raise ValueError("counts histogram must be non-empty")
        for k, v in self.counts.items():
            if not isinstance(k, str):
                raise TypeError("counts keys must be bitstrings (str)")
            _require_int(f"counts[{k}]", v)
            if v < 0:
                raise ValueError("counts must be non-negative")
        if not self.shots:
            object.__setattr__(self, "shots", sum(self.counts.values()))
        _require_int("shots", self.shots)

    def to_record(self) -> dict:
        return {
            "kind": "quantum-result",
            "result_cid": self.result_cid,
            "circuit_cid": self.circuit_cid,
            "counts": {k: self.counts[k] for k in sorted(self.counts)},
            "shots": self.shots,
            "backend_cid": self.backend_cid,
            "author": self.author,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    @property
    def most_frequent(self) -> str:
        return max(sorted(self.counts), key=lambda k: self.counts[k])

    def weave(self, web: Web) -> str:
        return web.weave(self.to_record())


# ---------------------------------------------------------------------------
# QuantumSystemRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuantumSystemRecord:
    """A content-addressed quantum-system (QPU / simulator) capability descriptor.

    A near-cousin of :class:`~knitweb.fabric.items.ResourceItem` — a bounded
    compute resource — specialised for quantum backends. ``kind_`` is
    ``"simulator"`` or ``"hardware"`` (a string, never a bool, to stay canonical).
    Float error-rates live in the full ``lqpu:`` artifact, not in this record.
    """

    backend_cid: str        # lqpu:...
    name: str
    n_qubits: int
    provider: str = ""
    kind_: str = "simulator"      # "simulator" | "hardware"
    native_gates: tuple[str, ...] = field(default_factory=tuple)
    price_per_epoch: int = 0      # PLS-wei; 0 = free/self-hosted

    def __post_init__(self) -> None:
        if not self.backend_cid.startswith("lqpu:"):
            raise ValueError("backend_cid must be an lqpu: content id")
        _require_int("n_qubits", self.n_qubits)
        _require_int("price_per_epoch", self.price_per_epoch)
        if self.n_qubits < 0 or self.price_per_epoch < 0:
            raise ValueError("n_qubits and price_per_epoch must be non-negative")
        if self.kind_ not in ("simulator", "hardware"):
            raise ValueError('kind_ must be "simulator" or "hardware"')

    def to_record(self) -> dict:
        return {
            "kind": "quantum-system",
            "backend_cid": self.backend_cid,
            "name": self.name,
            "n_qubits": self.n_qubits,
            "provider": self.provider,
            "system_kind": self.kind_,
            "native_gates": sorted(self.native_gates),
            "price_per_epoch": self.price_per_epoch,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def weave(self, web: Web) -> str:
        return web.weave(self.to_record())

    def as_resource_item(self) -> ResourceItem:
        """Expose this system as a marketplace ResourceItem (capacity = qubits).

        Lets quantum backends appear in the same resource-offer market as GPU/CPU
        without duplicating the offer logic.
        """
        return ResourceItem(
            resource_kind="qpu",
            capacity=self.n_qubits,
            price_per_epoch=self.price_per_epoch,
            provider=self.provider,
        )

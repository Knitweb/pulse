"""Specify-before-retrieve — estimate a query's size before fetching anything.

The World-Narrow-Web contract: a peer first *specifies* what it wants and gets a
bounded plan (which CIDs match, and roughly how many bytes they are) so it can
decide before pulling. This operates over the lean fabric records; the real bytes
are pulled from the artifact store only once the caller accepts the estimate.
"""

from __future__ import annotations

from collections.abc import Iterable

from .records import QuantumCircuitRecord

__all__ = ["estimate_circuits", "estimate_bytes"]

# QASM 2.0 size heuristic: fixed header + per-gate line + per-qubit decl/measure.
_HEADER_BYTES = 60          # "OPENQASM 2.0;" + include + qreg/creg lines
_PER_GATE_BYTES = 18        # an average gate line, e.g. "cx q[0],q[1];\n"
_PER_QUBIT_BYTES = 16       # qreg/creg width + a measure line


def estimate_bytes(qubits: int, depth: int) -> int:
    """Estimate the on-wire QASM byte size of a circuit from qubits + depth."""
    return _HEADER_BYTES + max(0, depth) * _PER_GATE_BYTES + max(0, qubits) * _PER_QUBIT_BYTES


def estimate_circuits(records: Iterable[QuantumCircuitRecord], *,
                      domain: str = "", max_qubits: int | None = None,
                      tags: Iterable[str] | None = None) -> dict:
    """Return a fetch plan for circuit records matching the query.

    The result is a dict::

        {
          "count": int,
          "est_total_bytes": int,
          "matches": [{"cid","name","qubits","domain","est_bytes"}, ...],
        }

    Nothing is fetched — the caller inspects ``est_total_bytes`` and only then
    pulls the CIDs it wants from the artifact store.
    """
    want_tags = set(tags or [])
    matches = []
    total = 0
    for r in records:
        if domain and r.domain != domain:
            continue
        if max_qubits is not None and r.qubits > max_qubits:
            continue
        if want_tags and not want_tags.intersection(r.tags):
            continue
        est = estimate_bytes(r.qubits, r.depth)
        total += est
        matches.append({
            "cid": r.circuit_cid,
            "name": r.name,
            "qubits": r.qubits,
            "domain": r.domain,
            "est_bytes": est,
        })
    matches.sort(key=lambda m: (m["qubits"], m["name"]))
    return {"count": len(matches), "est_total_bytes": total, "matches": matches}

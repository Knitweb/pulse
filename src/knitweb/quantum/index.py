"""Index quantum artifact records into a LensSpace so ``/interpret`` can query
them by content, domain, qubit count, or provenance.

Each record becomes a small set of MeTTa-style expression atoms:

    (QuantumCircuit (CID lcid:...) (name grover_2q) (domain algorithms) (qubits 2))
    (QuantumResult  (CID lres:...) (of lcid:...) (shots 1024) (ran-on lqpu:...))
    (QuantumSystem  (CID lqpu:...) (name aer) (qubits 32) (kind simulator))

A caller can then match e.g. ``(QuantumCircuit (CID $c) (domain algorithms) ...)``
against the space to enumerate every algorithm circuit the node knows about.
"""

from __future__ import annotations

from ..lens.atom import Atom, ExpressionAtom, GroundedAtom, SymbolAtom
from ..lens.space import LensSpace
from .records import QuantumCircuitRecord, QuantumResultRecord, QuantumSystemRecord

__all__ = ["atoms_for", "index_into"]


def _kv(key: str, value, typename: str) -> ExpressionAtom:
    return ExpressionAtom(SymbolAtom(key), GroundedAtom(value, typename, str(value)))


def atoms_for(record) -> list[Atom]:
    """Build the queryable atoms for a quantum artifact record."""
    if isinstance(record, QuantumCircuitRecord):
        head = SymbolAtom("QuantumCircuit")
        atoms: list[Atom] = [
            ExpressionAtom(head, _kv("CID", record.circuit_cid, "CID")),
            ExpressionAtom(head, _kv("CID", record.circuit_cid, "CID"), _kv("name", record.name, "Str")),
            ExpressionAtom(head, _kv("CID", record.circuit_cid, "CID"), _kv("domain", record.domain, "Str")),
            ExpressionAtom(head, _kv("CID", record.circuit_cid, "CID"), _kv("qubits", record.qubits, "Int")),
        ]
        atoms += [
            ExpressionAtom(head, _kv("CID", record.circuit_cid, "CID"), _kv("tag", t, "Str"))
            for t in sorted(record.tags)
        ]
        return atoms

    if isinstance(record, QuantumResultRecord):
        head = SymbolAtom("QuantumResult")
        atoms = [
            ExpressionAtom(head, _kv("CID", record.result_cid, "CID"), _kv("of", record.circuit_cid, "CID")),
            ExpressionAtom(head, _kv("CID", record.result_cid, "CID"), _kv("shots", record.shots, "Int")),
            ExpressionAtom(head, _kv("CID", record.result_cid, "CID"), _kv("top", record.most_frequent, "Str")),
        ]
        if record.backend_cid:
            atoms.append(
                ExpressionAtom(head, _kv("CID", record.result_cid, "CID"),
                               _kv("ran-on", record.backend_cid, "CID"))
            )
        return atoms

    if isinstance(record, QuantumSystemRecord):
        head = SymbolAtom("QuantumSystem")
        atoms = [
            ExpressionAtom(head, _kv("CID", record.backend_cid, "CID"), _kv("name", record.name, "Str")),
            ExpressionAtom(head, _kv("CID", record.backend_cid, "CID"), _kv("qubits", record.n_qubits, "Int")),
            ExpressionAtom(head, _kv("CID", record.backend_cid, "CID"), _kv("kind", record.kind_, "Str")),
        ]
        atoms += [
            ExpressionAtom(head, _kv("CID", record.backend_cid, "CID"), _kv("gate", g, "Str"))
            for g in sorted(record.native_gates)
        ]
        return atoms

    raise TypeError(f"not a quantum artifact record: {type(record).__name__}")


def index_into(space: LensSpace, record) -> None:
    """Add a record's atoms to *space* (idempotent — LensSpace dedups by key)."""
    space.add_all(atoms_for(record))

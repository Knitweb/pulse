"""A read-only Lens gateway that answers quantum-artifact queries against a
LensSpace of indexed records.

Wire it into an app with ``App.set_lens(build_lens(space))``; it then answers
``/interpret`` queries like::

    circuits domain=algorithms
    circuits qubits<=3
    systems kind=simulator
    cid lcid:abcd...

without ever mutating the Web (it only reads the indexed atom space).
"""

from __future__ import annotations

from collections.abc import Mapping

from ..lens.atom import ExpressionAtom, SymbolAtom, VariableAtom
from ..lens.space import LensSpace

__all__ = ["build_lens", "query_space"]


def _cids_for(space: LensSpace, head: str, key: str, value: str) -> list[str]:
    """Return CID strings of ``head`` atoms whose (key value) pair matches.

    The value position is matched with a variable and compared by its rendered
    string, so matching does not depend on reconstructing the grounded atom's
    typename (an int ``2`` renders "2" and matches the query "2" alike).
    """
    pattern = ExpressionAtom(
        SymbolAtom(head),
        ExpressionAtom(SymbolAtom("CID"), VariableAtom("cid")),
        ExpressionAtom(SymbolAtom(key), VariableAtom("val")),
    )
    out = []
    for _atom, binding in space.query(pattern):
        val = binding.get("val")
        cid = binding.get("cid")
        if cid is not None and val is not None and str(val) == value:
            out.append(str(cid))
    return sorted(set(out))


def _all_cids(space: LensSpace, head: str) -> list[str]:
    pattern = ExpressionAtom(
        SymbolAtom(head),
        ExpressionAtom(SymbolAtom("CID"), VariableAtom("cid")),
    )
    out = [str(b.get("cid")) for _a, b in space.query(pattern) if b.get("cid") is not None]
    return sorted(set(out))


def query_space(space: LensSpace, query: str) -> dict:
    """Answer a structured query string against the indexed space."""
    q = (query or "").strip()
    if not q:
        return {"error": "empty query"}
    parts = q.split()
    head_word = parts[0].lower()

    # cid <id> -> everything the space asserts about a content id
    if head_word == "cid" and len(parts) >= 2:
        cid = parts[1]
        facts = []
        for atom in space.atoms():
            if cid in str(atom):
                facts.append(str(atom))
        return {"cid": cid, "facts": facts, "count": len(facts)}

    head = {"circuits": "QuantumCircuit", "results": "QuantumResult",
            "systems": "QuantumSystem"}.get(head_word)
    if head is None:
        return {"error": f"unknown query head: {head_word}"}

    # optional  key=value  or  qubits<=N  filter
    for tok in parts[1:]:
        if "<=" in tok:
            key, val = tok.split("<=", 1)
            if key == "qubits" and val.isdigit():
                keep = set()
                for n in range(int(val) + 1):
                    keep.update(_cids_for(space, head, "qubits", str(n)))
                return {"head": head, "filter": tok, "cids": sorted(keep), "count": len(keep)}
        if "=" in tok:
            key, val = tok.split("=", 1)
            cids = _cids_for(space, head, key, val)
            return {"head": head, "filter": tok, "cids": cids, "count": len(cids)}

    cids = _all_cids(space, head)
    return {"head": head, "cids": cids, "count": len(cids)}


def build_lens(space: LensSpace):
    """Return a Lens callable ``(query, snapshot, params) -> dict`` over *space*.

    The snapshot/params are accepted for the ``App.set_lens`` contract but the
    gateway is pure-read over the indexed atom space, so it never touches live
    Web state.
    """
    def _lens(query: str, snapshot: Mapping | None = None, params: Mapping | None = None) -> dict:
        return query_space(space, query)
    return _lens

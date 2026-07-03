"""Property tests for the knitweb.quantum fabric bridge (offline, no network)."""

import pytest

from knitweb.core import canonical
from knitweb.fabric.web import Web
from knitweb.lens.atom import ExpressionAtom, SymbolAtom, VariableAtom
from knitweb.lens.space import LensSpace
from knitweb.quantum import (
    QuantumCircuitRecord, QuantumResultRecord, QuantumSystemRecord,
    atoms_for, index_into, weave_into, link_provenance,
    estimate_circuits, estimate_bytes, query_space, build_lens,
)


# ── records: CID determinism + validation ────────────────────────────────
def test_circuit_record_cid_deterministic():
    a = QuantumCircuitRecord(circuit_cid="lcid:abc", name="grover_2q", qubits=2,
                             domain="algorithms", tags=("grover", "search"))
    b = QuantumCircuitRecord(circuit_cid="lcid:abc", name="grover_2q", qubits=2,
                             domain="algorithms", tags=("search", "grover"))  # reordered tags
    assert a.cid == b.cid
    assert a.cid == canonical.cid(a.to_record())


def test_result_record_defaults_shots_and_validates_cids():
    r = QuantumResultRecord(result_cid="lres:r", circuit_cid="lcid:c",
                            counts={"00": 500, "11": 524})
    assert r.shots == 1024
    assert r.most_frequent == "11"
    with pytest.raises(ValueError):
        QuantumResultRecord(result_cid="nope", circuit_cid="lcid:c", counts={"0": 1})
    with pytest.raises(ValueError):
        QuantumResultRecord(result_cid="lres:r", circuit_cid="bad", counts={"0": 1})


def test_system_record_kind_and_resource_item():
    s = QuantumSystemRecord(backend_cid="lqpu:s", name="aer", n_qubits=32,
                            provider="local", kind_="simulator",
                            native_gates=("h", "cx", "rz"))
    assert isinstance(s.cid, str) and s.cid
    ri = s.as_resource_item()
    assert ri.resource_kind == "qpu" and ri.capacity == 32
    with pytest.raises(ValueError):
        QuantumSystemRecord(backend_cid="lqpu:s", name="x", n_qubits=1, kind_="weird")


def test_no_floats_in_records():
    # error-rates / probabilities never enter a fabric record (canonical safety).
    rec = QuantumSystemRecord(backend_cid="lqpu:s", name="aer", n_qubits=5).to_record()
    assert all(not isinstance(v, float) for v in rec.values())


# ── weave into a Web + provenance links ──────────────────────────────────
def test_weave_and_link_provenance():
    web = Web()
    circ = QuantumCircuitRecord(circuit_cid="lcid:c", name="bell", qubits=2, domain="fundamental")
    sysd = QuantumSystemRecord(backend_cid="lqpu:s", name="aer", n_qubits=32)
    res = QuantumResultRecord(result_cid="lres:r", circuit_cid="lcid:c",
                              counts={"00": 512, "11": 512}, backend_cid="lqpu:s")
    c_cid = weave_into(web, circ)
    s_cid = weave_into(web, sysd)
    r_cid = weave_into(web, res)
    assert {c_cid, s_cid, r_cid} <= set(web.nodes.keys())
    link_provenance(web, res, c_cid, s_cid)
    # edges result -> circuit (result-of) and result -> system (ran-on)
    rels = {(e.rel, e.dst) for e in web._out.get(r_cid, [])}
    assert ("result-of", c_cid) in rels
    assert ("ran-on", s_cid) in rels


# ── indexing + lens query ─────────────────────────────────────────────────
def test_index_and_query_by_domain_and_qubits():
    space = LensSpace()
    index_into(space, QuantumCircuitRecord(circuit_cid="lcid:g2", name="grover_2q",
               qubits=2, domain="algorithms", tags=("grover",)))
    index_into(space, QuantumCircuitRecord(circuit_cid="lcid:g3", name="grover_3q",
               qubits=3, domain="algorithms", tags=("grover",)))
    index_into(space, QuantumCircuitRecord(circuit_cid="lcid:bell", name="bell",
               qubits=2, domain="fundamental"))

    by_domain = query_space(space, "circuits domain=algorithms")
    assert set(by_domain["cids"]) == {"lcid:g2", "lcid:g3"}

    by_qubits = query_space(space, "circuits qubits<=2")
    assert "lcid:g2" in by_qubits["cids"] and "lcid:bell" in by_qubits["cids"]
    assert "lcid:g3" not in by_qubits["cids"]


def test_lens_callable_contract():
    space = LensSpace()
    index_into(space, QuantumSystemRecord(backend_cid="lqpu:aer", name="aer",
               n_qubits=32, kind_="simulator"))
    lens = build_lens(space)
    out = lens("systems kind=simulator", {}, {})
    assert out["cids"] == ["lqpu:aer"]


def test_cid_lookup_returns_facts():
    space = LensSpace()
    index_into(space, QuantumCircuitRecord(circuit_cid="lcid:bell", name="bell",
               qubits=2, domain="fundamental"))
    out = query_space(space, "cid lcid:bell")
    assert out["count"] >= 2
    assert any("bell" in f for f in out["facts"])


# ── specify-before-retrieve estimate ─────────────────────────────────────
def test_estimate_plan_before_fetch():
    recs = [
        QuantumCircuitRecord(circuit_cid="lcid:a", name="a", qubits=2, depth=4, domain="algorithms"),
        QuantumCircuitRecord(circuit_cid="lcid:b", name="b", qubits=5, depth=40, domain="algorithms"),
        QuantumCircuitRecord(circuit_cid="lcid:c", name="c", qubits=2, depth=2, domain="fundamental"),
    ]
    plan = estimate_circuits(recs, domain="algorithms")
    assert plan["count"] == 2
    assert plan["est_total_bytes"] == estimate_bytes(2, 4) + estimate_bytes(5, 40)
    # sorted by qubits then name; nothing fetched, only a plan returned
    assert [m["cid"] for m in plan["matches"]] == ["lcid:a", "lcid:b"]

    capped = estimate_circuits(recs, max_qubits=2)
    assert {m["cid"] for m in capped["matches"]} == {"lcid:a", "lcid:c"}

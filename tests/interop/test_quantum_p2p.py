"""2-node interop: publish quantum artifacts on A, converge to B, query on B.

Proves the fabric bridge end-to-end over the real P2P broadcast path: a circuit,
a system and a result woven on node A cross to node B content-identically, and B
can then index + query them and produce a specify-before-retrieve estimate.
"""

import asyncio

import pytest

from knitweb.fabric.node import FabricNode
from knitweb.lens.space import LensSpace
from knitweb.quantum import (
    QuantumCircuitRecord, QuantumResultRecord, QuantumSystemRecord,
    index_into, query_space, estimate_circuits,
)


def run(coro):
    return asyncio.run(coro)


def _circuit_from_record(rec: dict) -> QuantumCircuitRecord:
    """Rebuild a circuit record from the dict B received over P2P."""
    return QuantumCircuitRecord(
        circuit_cid=rec["circuit_cid"], name=rec["name"], qubits=rec["qubits"],
        author=rec.get("author", ""), domain=rec.get("domain", "fundamental"),
        depth=rec.get("depth", 0), source_lang=rec.get("source_lang", "qasm2"),
        tags=tuple(rec.get("tags", [])),
    )


@pytest.mark.interop
def test_quantum_artifacts_converge_and_are_queryable_on_peer():
    async def scenario():
        a = FabricNode()
        b = FabricNode()
        async with a, b:
            a.add_peer("b", b.address)

            circ = QuantumCircuitRecord(circuit_cid="lcid:grover2", name="grover_2q",
                                        qubits=2, domain="algorithms",
                                        depth=12, tags=("grover", "search"), author=a.pub)
            sysd = QuantumSystemRecord(backend_cid="lqpu:aer", name="aer",
                                       n_qubits=32, kind_="simulator", provider=a.pub)
            res = QuantumResultRecord(result_cid="lres:r1", circuit_cid="lcid:grover2",
                                      counts={"00": 20, "11": 1004}, backend_cid="lqpu:aer",
                                      author=a.pub)

            c_cid = await a.weave(circ.to_record())
            s_cid = await a.weave(sysd.to_record())
            r_cid = await a.weave(res.to_record())

            # All three crossed to B, content-identical (content-addressed CIDs match).
            for cid, rec in ((c_cid, circ), (s_cid, sysd), (r_cid, res)):
                assert b.web.get(cid) is not None, f"{cid} did not converge to B"
                assert b.web.nodes[cid] == rec.to_record()

            # B links provenance in its own converged Web and it holds.
            b.web.link(r_cid, c_cid, "result-of", 1)
            assert ("result-of", c_cid) in {(e.rel, e.dst) for e in b.web._out.get(r_cid, [])}

            # B indexes the received circuit + system and answers /interpret-style queries.
            space = LensSpace()
            received_circuit = _circuit_from_record(b.web.nodes[c_cid])
            index_into(space, received_circuit)
            index_into(space, sysd)

            assert query_space(space, "circuits domain=algorithms")["cids"] == ["lcid:grover2"]
            assert query_space(space, "systems kind=simulator")["cids"] == ["lqpu:aer"]
            assert query_space(space, "circuits qubits<=2")["cids"] == ["lcid:grover2"]

            # B can plan a fetch (specify-before-retrieve) without pulling QASM bytes.
            plan = estimate_circuits([received_circuit], domain="algorithms")
            assert plan["count"] == 1
            assert plan["est_total_bytes"] > 0

    run(scenario())

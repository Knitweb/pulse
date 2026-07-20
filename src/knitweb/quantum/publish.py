"""Publish quantum artifact records onto the fabric.

``publish`` weaves a record into a live :class:`~knitweb.fabric.node.FabricNode`
(which announces its CID to peers for P2P convergence) and, for results, links
provenance edges result -> circuit and result -> system so the fabric graph
records what produced what. ``weave_into`` is the synchronous, node-free variant
used in tests and offline indexing.
"""

from __future__ import annotations

from ..fabric.web import Web
from .records import QuantumCircuitRecord, QuantumResultRecord, QuantumSystemRecord

__all__ = ["weave_into", "publish", "link_provenance"]


def weave_into(web: Web, record) -> str:
    """Weave a record into a local Web; return its fabric CID. Synchronous."""
    return record.weave(web)


def link_provenance(web: Web, result: QuantumResultRecord,
                    circuit_fabric_cid: str,
                    system_fabric_cid: str | None = None) -> None:
    """Link a result's fabric node to the circuit (and system) it came from.

    ``circuit_fabric_cid`` / ``system_fabric_cid`` are the CIDs the circuit and
    system records got when they were woven (i.e. their ``.cid``), which must
    already exist in *web*.
    """
    result_cid = result.cid
    web.link(result_cid, circuit_fabric_cid, "result-of", 1)
    if system_fabric_cid:
        web.link(result_cid, system_fabric_cid, "ran-on", 1)


async def publish(node, record) -> str:
    """Weave a record into ``node``'s Web and announce it to peers.

    Returns the record's fabric CID. Use :func:`link_provenance` afterwards (via
    ``node.link``) once the referenced circuit/system records are also woven.
    """
    return await node.weave(record.to_record())

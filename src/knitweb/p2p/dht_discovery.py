"""Kademlia ↔ flat-PEX bridge (knitweb/molgang#88).

``discovery.py`` is flat peer-exchange: it merges every peer it hears into an
unbounded :class:`~knitweb.p2p.discovery.PeerDirectory` and shares a bounded
sample. ``kademlia.py`` is the structured successor: a 256-bucket XOR routing
table with an iterative, ``alpha``-bounded ``find_node`` lookup. They already
share the peer-record wire shape (a Kademlia contact record is a discovery peer
record plus an ``id`` hex) — but nothing ties them together.

This adapter is that tie, added **without editing discovery.py, kademlia.py or
node.py** (per the two-track coordination plan): every DHT-learned contact drops
into BOTH the routing table (so lookups can route *toward* a target) and the flat
directory (so existing dial/dedup/eviction is untouched), and the flat
peer-exchange gains an optional ``target`` that asks for peers *closest to* an id.

Byte-identity guarantee (#88 acceptance): a bare peer-exchange with **no**
``target`` is produced by delegating verbatim to
:func:`knitweb.p2p.discovery.peer_exchange_message`, so today's frames are
unchanged to the byte. Everything here is pure logic — no sockets, no clock, no
RNG, no float, no new dependency; the ``serve()`` wiring is deferred to the node
layer exactly like the other activation adapters.
"""
from __future__ import annotations

from . import discovery, kademlia
from .discovery import PeerDirectory
from .kademlia import (
    Contact,
    RoutingTable,
    contacts_from_records,
    contacts_to_records,
    iterative_lookup,
    node_id,
)
from .transport import PeerAddress

__all__ = [
    "PEER_EXCHANGE_TARGET_FIELD",
    "DhtDiscovery",
    "peer_exchange_query",
    "handle_peer_exchange",
]

# The additive field name a target-aware peer-exchange carries. Absent ⇒ the
# frame is the legacy flat peer-exchange, byte-for-byte.
PEER_EXCHANGE_TARGET_FIELD = "target"


class DhtDiscovery:
    """A node's structured peer discovery: a routing table beside the flat directory.

    ``self_pubkey_hex`` fixes ``self_id = sha256(pubkey)``. ``directory`` is the
    existing address store (created fresh if omitted). DHT-learned contacts feed
    both; flat-PEX-learned addresses (which carry no node id) still merge into the
    directory alone, so they remain dialable seeds even though they cannot be
    routed toward.
    """

    def __init__(
        self,
        self_pubkey_hex: str,
        *,
        directory: "PeerDirectory | None" = None,
        k: int = kademlia.DEFAULT_K,
        source_cap: "int | None" = None,
    ) -> None:
        self.self_id = node_id(self_pubkey_hex)
        self.table = RoutingTable(self.self_id, k=k, source_cap=source_cap)
        self.directory = directory if directory is not None else PeerDirectory()
        self._k = k

    # -- learning ----------------------------------------------------------
    def learn_contacts(self, records) -> int:
        """Admit DHT contact records (id + host/port) into the table AND directory.

        Returns the number of contacts newly admitted to the routing table. The
        matching :class:`PeerAddress` is merged into the flat directory too, so
        the existing dial path sees the peer with no change to its dedup/eviction.
        Malformed records raise ``ValueError`` (same strictness as the wire layer).
        """
        contacts = contacts_from_records(records)
        added = 0
        for c in contacts:
            if c.node_id == self.self_id:
                continue                       # a node never routes to itself
            if self.table.add(c):
                added += 1
        # feed the flat directory from the same contacts (addresses only)
        self.directory.merge([c.address for c in contacts])
        return added

    def learn_addresses(self, peers) -> None:
        """Merge flat-PEX addresses (no node id) into the directory only."""
        self.directory.merge(list(peers))

    # -- serving -----------------------------------------------------------
    def closest_contacts(self, target, count: "int | None" = None) -> list[Contact]:
        return self.table.closest(target, count if count is not None else self._k)

    def closest_records(self, target, count: "int | None" = None) -> list[dict]:
        return contacts_to_records(self.closest_contacts(target, count))

    # -- iterative lookup --------------------------------------------------
    def find_node(self, target, responder, **kw) -> list[Contact]:
        """Drive an iterative Kademlia lookup for ``target`` seeded from our table.

        ``responder(contact, target) -> Iterable[Contact]`` is injected (in
        production: the decoded ``nodes`` reply to a ``find_node`` frame), so this
        stays socket-free and cannot stall. Returns the ``k`` closest contacts.
        Discovered contacts are folded back into the table + directory.
        """
        seeds = self.table.closest(target)
        state = iterative_lookup(target, seeds, responder, k=self._k, **kw)
        result = state.result()
        for c in state.known.values():
            if c.node_id != self.self_id:
                self.table.add(c)
        self.directory.merge([c.address for c in state.known.values()])
        return result


def peer_exchange_query(
    directory: PeerDirectory,
    target,
    *,
    k: "int | None" = discovery.DEFAULT_SHARE_K,
) -> dict:
    """A peer-exchange that additionally asks for peers *closest to* ``target``.

    Same shape as :func:`discovery.peer_exchange_message` plus a ``target``
    node-id-hex field. The responder (:func:`handle_peer_exchange`) reads that
    field to reply with routing-table-closest contacts; a peer that does not
    understand it simply ignores the extra key and answers a flat sample.
    """
    msg = discovery.peer_exchange_message(directory, k)
    msg[PEER_EXCHANGE_TARGET_FIELD] = kademlia._as_id_bytes(target).hex()
    return msg


def handle_peer_exchange(
    dht: DhtDiscovery,
    msg: dict,
    *,
    share_k: "int | None" = discovery.DEFAULT_SHARE_K,
) -> dict:
    """Answer a (possibly target-aware) peer-exchange.

    - **No ``target``**: delegate verbatim to
      :func:`discovery.peer_exchange_message` — the reply is byte-identical to the
      legacy flat path (#88 acceptance).
    - **With ``target``**: reply with the routing table's ``k`` closest contacts
      (each record carries its ``id`` so the asker can route the next hop), under
      the same peer-exchange kind so the carrier is unchanged.
    """
    target = msg.get(PEER_EXCHANGE_TARGET_FIELD) if isinstance(msg, dict) else None
    if target is None:
        return discovery.peer_exchange_message(dht.directory, share_k)
    if not isinstance(target, str):
        raise ValueError("peer-exchange target must be a node-id hex str")
    return {
        "kind": discovery.PEER_EXCHANGE_KIND,
        "peers": dht.closest_records(target, share_k),
        PEER_EXCHANGE_TARGET_FIELD: kademlia._as_id_bytes(target).hex(),
    }

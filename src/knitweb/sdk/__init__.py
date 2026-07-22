"""Knitweb SDK — a small, friendly facade over the PLS web primitives.

Wraps the ledger and synaptic layers into a developer-facing API so apps don't
touch the low-level Knitweb/Knit machinery directly:

  * ``Wallet``            — a PLS account: keygen, address, balance, pay()
  * ``compile_asset``     — resolve an OriginTrail asset → signed synaptic bytecode
  * ``verify_bundle`` / ``decode_bundle`` — the edge-side verify + read flow
  * ``import_geoweave_findings`` — verified PAR findings → attested field
    observations woven into a Web (the dapp-facing GeoWeave crossing)

You pay in **PLS** ("pulses") for activity; a *fiber* carries data, a *pulse* is
the metered unit you spend. The native base token has no premine — wallets earn
PLS via proof-of-useful-work. ``Wallet.create(genesis_pulses=...)`` seeds a
balance for **local/dev/testing only**, never for production issuance.
"""

from __future__ import annotations

import hashlib

from ..core import canonical, crypto
from ..ledger.knit import Knit
from ..ledger.node import AccountNode
from ..fabric import items
from ..fabric.web import Web
from ..interpret import distill as _distill
from ..interpret import retrieve as _retrieve
from ..synaptic import bytecode as _bc
from ..synaptic.origintrail import resolve_asset

__all__ = [
    "Wallet",
    "compile_asset",
    "distill_bundle",
    "verify_bundle",
    "decode_bundle",
    "import_geoweave_findings",
    "TOKEN",
]

TOKEN = "PLS"


class Wallet:
    """A friendly handle on a PLS account."""

    def __init__(self, account: AccountNode) -> None:
        self._node = account

    # -- construction ------------------------------------------------------

    @classmethod
    def create(cls, genesis_pulses: int = 0) -> "Wallet":
        """Create a fresh wallet. ``genesis_pulses`` seeds a balance (dev/test only)."""
        balances = {"PLS": genesis_pulses} if genesis_pulses else None
        return cls(AccountNode(genesis_balances=balances))

    @classmethod
    def from_key(cls, priv_hex: str) -> "Wallet":
        """Load a wallet from a private-key hex (no balance restore — local only)."""
        pub = crypto.public_from_private(priv_hex)
        return cls(AccountNode(priv=priv_hex, pub=pub))

    # -- identity ----------------------------------------------------------

    @property
    def address(self) -> str:
        return self._node.address

    @property
    def public_key(self) -> str:
        return self._node.pub

    @property
    def private_key(self) -> str:
        return self._node.priv

    # -- value -------------------------------------------------------------

    def balance(self, symbol: str = "PLS") -> int:
        return self._node.balance(symbol)

    def pay(self, to: "Wallet", pulses: int, timestamp: int) -> Knit:
        """Pay ``pulses`` (PLS) to another wallet. Returns the settled Knit."""
        return self._node.transfer_to(to._node, "PLS", pulses, timestamp)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Wallet({self.address}, {self.balance()} PLS)"


def compile_asset(asset: dict, originator_priv: str) -> tuple[bytes, str]:
    """Resolve an OriginTrail Knowledge Asset and compile it to *signed* bytecode.

    Returns ``(bytecode, signature_hex)``. The signature lets any edge device
    verify the originator before executing the bundle.
    """
    asset_id, originator, relations = resolve_asset(asset)
    data = _bc.compile_bundle(asset_id, originator, relations)
    signature = _bc.sign_bundle(originator_priv, data)
    return data, signature


def distill_bundle(
    query: str | dict,
    subscription: list[str] | tuple[str, ...] | None,
    originator_priv: str,
    *,
    web: Web | None = None,
    depth: int = 2,
    max_iters: int = 8,
    mode: str = "reflect",
) -> tuple[bytes, str]:
    """Run the read-path interpretation lobe and return a signed distill bundle.

    The answer-space identifier is content-derived from the query, subscription and
    query-bearing web state so identical reads compile to identical bundle ids.
    """
    web = web or Web()
    # web_state_cid is part of the read-path manifest: identical query and web
    # produce identical assets; stale reads cannot be replayed without that state.
    web_state_cid = items.web_state_root(web)
    candidate_set = _retrieve(query, subscription, web, depth=depth, web_state_cid=web_state_cid)
    selection = _distill(
        candidate_set,
        query,
        web=web,
        max_iters=max_iters,
        mode=mode,
    )

    # Deterministic content identifier for this question/context query.
    manifest = {
        "query": query,
        "subscription": sorted(subscription) if subscription is not None else None,
        "web_state_cid": web_state_cid,
    }
    asset_id = f"distill:{hashlib.sha256(canonical.encode(manifest)).hexdigest()}"

    originator_pub = crypto.public_from_private(originator_priv)
    originator = crypto.address(originator_pub)

    data = _bc.compile_bundle(
        asset_id,
        originator,
        list(selection.relations),
    )
    return data, _bc.sign_bundle(originator_priv, data)


def verify_bundle(originator_pub: str, data: bytes, signature_hex: str) -> bool:
    """Verify a synaptic bytecode bundle against the claimed originator key."""
    return _bc.verify_bundle(originator_pub, data, signature_hex)


def decode_bundle(data: bytes) -> dict:
    """Decode a synaptic bytecode bundle back into {asset_cid, originator, relations}."""
    return _bc.decode_bundle(data)


def import_geoweave_findings(
    envelopes,
    *,
    web: Web,
    importer_priv: str,
    beat: int,
    target_map: dict | None = None,
    precision: int = 9,
) -> dict:
    """Import verified GeoWeave finding envelopes into ``web`` — one call.

    The dapp-facing wrapper over :mod:`knitweb.geoweave.bridge` +
    :mod:`knitweb.edge.labelmap`: when ``target_map`` is omitted it is built
    from ``web`` itself (every titled knowledge node — e.g. MOLGANG molecules
    and apparatus — becomes a target). Per envelope: verify (a failing
    envelope raises, import refused), convert, weave record + spatial anchor,
    attest with ``importer_priv``.

    Returns ``{"imported": [(observation_cid, anchor_cid, attestation), ...],
    "skipped_unmapped": [label, ...]}``. Unmapped labels are *verified but
    skipped* — nothing to bind is not a forgery, and a forgery is never a
    skip.
    """
    from ..edge.labelmap import target_map_from_web
    from ..geoweave import bridge as _gw

    targets = target_map_from_web(web) if target_map is None else dict(target_map)
    imported: list[tuple] = []
    skipped: list[str] = []
    for envelope in envelopes:
        if not _gw.verify_finding(envelope):
            raise _gw.BridgeVerifyError(
                "finding envelope failed verification — refusing import"
            )
        label = envelope["body"]["label"]
        if label not in targets:
            skipped.append(label)
            continue
        observation, attestation = _gw.finding_to_observation(
            envelope, target_map=targets, importer_priv=importer_priv,
            beat=beat, precision=precision,
        )
        observation_cid, anchor_cid = observation.weave(web)
        imported.append((observation_cid, anchor_cid, attestation))
    return {"imported": imported, "skipped_unmapped": skipped}

"""WebID link — bind a Solid pod identity to a ``pls1`` key, verifiably.

A wearer has two identities: the ``pls1`` address their glass signs
observations with, and the WebID (an HTTPS URL) their Solid pod answers to. A
:class:`WebIdLink` is the small, float-free fabric record that says *"this
WebID and this address are the same wearer"* — signed by the key itself via
the standard :class:`~knitweb.fabric.attest.Attestation` envelope, so nobody
can claim someone else's pod (or hang their pod on someone else's key).

With a verified link in the local Web, a peer holding a shared observation can
resolve ``observer → WebID`` and ask that pod for the original capture — which
the pod owner grants or refuses through their own access control. The fabric
never carries the original; it carries who to ask.

Lookups here are *plain reads*; trust comes from checking the attestation
(:func:`verify_link`) before acting on a link, exactly like every other
fabric item.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import canonical, crypto
from ..fabric.attest import Attestation, attest, verify_record

__all__ = [
    "WEBID_LINK_KIND",
    "WebIdLink",
    "link_webid",
    "verify_link",
    "webid_for",
    "observers_for",
]

WEBID_LINK_KIND = "webid-link"


@dataclass(frozen=True)
class WebIdLink:
    """A signed claim: this WebID and this pls1 address are the same wearer."""

    webid: str
    observer: str   # pls1 address of the linking key
    beat: int       # integer Pulse time; latest beat wins on re-link

    def __post_init__(self) -> None:
        if not isinstance(self.webid, str) or not self.webid:
            raise TypeError("webid must be a non-empty str")
        if not (self.webid.startswith("https://") or self.webid.startswith("http://")):
            raise ValueError("webid must be an http(s) URL")
        if not isinstance(self.observer, str) or not crypto.is_valid_address(self.observer):
            raise ValueError("observer must be a valid pls1 address")
        if isinstance(self.beat, bool) or not isinstance(self.beat, int):
            raise TypeError("beat must be an integer")
        if self.beat < 0:
            raise ValueError("beat must be non-negative")

    def to_record(self) -> dict:
        return {
            "kind": WEBID_LINK_KIND,
            "webid": self.webid,
            "observer": self.observer,
            "beat": self.beat,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def weave(self, web) -> str:
        return web.weave(self.to_record())


def link_webid(webid: str, observer_priv: str, beat: int) -> tuple[WebIdLink, Attestation]:
    """Create + sign a link with the wearer's own key.

    The record's ``observer`` is derived from ``observer_priv``, and the
    attestation is over the record's canonical bytes — a key can only link a
    WebID to *itself*.
    """
    observer = crypto.address(crypto.public_from_private(observer_priv))
    link = WebIdLink(webid=webid, observer=observer, beat=beat)
    return link, attest(link.to_record(), observer_priv, author_field="observer")


def verify_link(record: dict, author_pub: str, sig: str) -> bool:
    """True iff ``record`` is a well-formed webid-link the key really signed."""
    if not isinstance(record, dict) or record.get("kind") != WEBID_LINK_KIND:
        return False
    try:
        WebIdLink(
            webid=record.get("webid"),
            observer=record.get("observer"),
            beat=record.get("beat"),
        )
    except (TypeError, ValueError):
        return False
    return verify_record(record, author_pub, sig, author_field="observer")


def _links(web) -> list[dict]:
    return [
        record for record in web.nodes.values()
        if isinstance(record, dict) and record.get("kind") == WEBID_LINK_KIND
    ]


def webid_for(web, observer: str) -> str | None:
    """The WebID linked to ``observer`` (latest beat wins), or None.

    Plain read — check the link's attestation with :func:`verify_link` before
    acting on the answer.
    """
    best: tuple[int, str] | None = None
    for record in _links(web):
        if record.get("observer") != observer:
            continue
        beat = record.get("beat", 0)
        if best is None or beat > best[0]:
            best = (beat, record["webid"])
    return best[1] if best else None


def observers_for(web, webid: str) -> list[str]:
    """Every pls1 address that woven links claim for ``webid`` (sorted)."""
    return sorted({
        record["observer"] for record in _links(web)
        if record.get("webid") == webid
    })

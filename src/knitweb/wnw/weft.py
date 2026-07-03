"""Spherical WNW weft addresses.

The geohash spatial layer binds facts to physical places.  A ``WeftAddress``
binds a fact or circuit relation to a deterministic spherical shell position:
layer/radius, angular theta/phi bins, beat time, frequency band, and relation
digest.  The compact 12-byte encoding carries the routing coordinates used by
tiny relays; the textual record carries the human-readable band and digest.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from knitweb.core import canonical, crypto

LAYER_BITS = 4
NODE_INDEX_BITS = 20
BEAT_BITS = 40
THETA_BITS = 8
PHI_BITS = 9

MAX_LAYER = (1 << LAYER_BITS) - 1
MAX_NODE_INDEX = (1 << NODE_INDEX_BITS) - 1
MAX_BEAT = (1 << BEAT_BITS) - 1
MAX_THETA = (1 << THETA_BITS) - 1
MAX_PHI = (1 << PHI_BITS) - 1
WEFT_ADDRESS_BYTES = 12
FIBONACCI_NODE_COUNT = 1 << 20
_RESERVED_BITS = 15
_TAU = 2.0 * math.pi
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
_BAND_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_int(name: str, value: int, *, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} out of range [0, {maximum}]")


def relation_digest(relation: str) -> str:
    """Return the SHA-256 digest used to bind a relation into a weft address."""
    if not isinstance(relation, str):
        raise TypeError("relation must be a string")
    if not relation:
        raise ValueError("relation must not be empty")
    return crypto.sha256_hex(relation.encode("utf-8"))


def fibonacci_sphere(layer: int, node_index: int) -> tuple[int, int]:
    """Map ``(layer, node_index)`` to quantized ``(theta, phi)`` bins.

    The angular lattice is shared by all layers so a node can traverse inward or
    outward on the same angular column.  The layer is still validated here
    because it is part of the addressable spherical coordinate.
    """
    _require_int("layer", layer, maximum=MAX_LAYER)
    _require_int("node_index", node_index, maximum=MAX_NODE_INDEX)
    z = 1.0 - (2.0 * (node_index + 0.5) / FIBONACCI_NODE_COUNT)
    theta_rad = (node_index * _GOLDEN_ANGLE) % _TAU
    theta = int((theta_rad / _TAU) * (MAX_THETA + 1)) % (MAX_THETA + 1)
    phi = int((math.acos(z) / math.pi) * (MAX_PHI + 1))
    return theta, min(MAX_PHI, phi)


@dataclass(frozen=True)
class WeftAddress:
    """Canonical spherical address for WNW fact and circuit relations."""

    layer: int
    node_index: int
    theta: int
    phi: int
    beat: int
    band: str
    relation_digest: str

    def __post_init__(self) -> None:
        _require_int("layer", self.layer, maximum=MAX_LAYER)
        _require_int("node_index", self.node_index, maximum=MAX_NODE_INDEX)
        _require_int("theta", self.theta, maximum=MAX_THETA)
        _require_int("phi", self.phi, maximum=MAX_PHI)
        _require_int("beat", self.beat, maximum=MAX_BEAT)
        if not isinstance(self.band, str) or not _BAND_RE.match(self.band):
            raise ValueError("band must be a lowercase ASCII label")
        if not isinstance(self.relation_digest, str) or not _HEX64_RE.match(
            self.relation_digest
        ):
            raise ValueError("relation_digest must be 64 lowercase hex characters")

    @classmethod
    def from_node(
        cls,
        layer: int,
        node_index: int,
        beat: int,
        band: str,
        relation_digest: str,
    ) -> "WeftAddress":
        """Build an address from a shell layer and Fibonacci node index."""
        theta, phi = fibonacci_sphere(layer, node_index)
        return cls(
            layer=layer,
            node_index=node_index,
            theta=theta,
            phi=phi,
            beat=beat,
            band=band,
            relation_digest=relation_digest,
        )

    @classmethod
    def from_bytes12(
        cls,
        data: bytes,
        *,
        band: str,
        relation_digest: str,
    ) -> "WeftAddress":
        """Decode the 12-byte routing coordinate plus textual band/digest."""
        if len(data) != WEFT_ADDRESS_BYTES:
            raise ValueError("weft address encoding must be exactly 12 bytes")
        raw = int.from_bytes(data, "big")
        if raw & ((1 << _RESERVED_BITS) - 1):
            raise ValueError("reserved weft address bits must be zero")
        value = raw >> _RESERVED_BITS
        phi = value & MAX_PHI
        value >>= PHI_BITS
        theta = value & MAX_THETA
        value >>= THETA_BITS
        beat = value & MAX_BEAT
        value >>= BEAT_BITS
        node_index = value & MAX_NODE_INDEX
        value >>= NODE_INDEX_BITS
        layer = value & MAX_LAYER
        return cls(
            layer=layer,
            node_index=node_index,
            theta=theta,
            phi=phi,
            beat=beat,
            band=band,
            relation_digest=relation_digest,
        )

    def validate(self, *, previous_beat: int | None = None) -> None:
        """Validate range constraints and optional monotonic beat ordering."""
        self.__post_init__()
        if previous_beat is not None:
            _require_int("previous_beat", previous_beat, maximum=MAX_BEAT)
            if self.beat < previous_beat:
                raise ValueError("beat must be monotonic")

    def to_bytes12(self) -> bytes:
        """Return the fixed 12-byte coordinate encoding.

        Layout, from most significant bit: ``r:4 | node_index:20 | beat:40 |
        theta:8 | phi:9 | reserved:15``.  Reserved low bits are zeroed so future
        narrow-web versions can add flags without changing the byte width.
        """
        value = self.layer
        value = (value << NODE_INDEX_BITS) | self.node_index
        value = (value << BEAT_BITS) | self.beat
        value = (value << THETA_BITS) | self.theta
        value = (value << PHI_BITS) | self.phi
        value <<= _RESERVED_BITS
        return value.to_bytes(WEFT_ADDRESS_BYTES, "big")

    def to_record(self) -> dict:
        return {
            "kind": "wnw.weft_address.v1",
            "layer": self.layer,
            "node_index": self.node_index,
            "theta": self.theta,
            "phi": self.phi,
            "beat": self.beat,
            "band": self.band,
            "relation_digest": self.relation_digest,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


WeftEndpoint = WeftAddress | str


def _endpoint_record(endpoint: WeftEndpoint) -> dict:
    if isinstance(endpoint, WeftAddress):
        return endpoint.to_record()
    if isinstance(endpoint, str) and endpoint:
        return {"kind": "cid-ref", "cid": endpoint}
    raise TypeError("weft endpoint must be a WeftAddress or non-empty CID string")


@dataclass(frozen=True)
class WeftPick:
    """A relation pick whose subject and object may be spherical addresses."""

    subject: WeftEndpoint
    relation: str
    object: WeftEndpoint
    beat: int

    def __post_init__(self) -> None:
        _require_int("beat", self.beat, maximum=MAX_BEAT)
        if not isinstance(self.relation, str) or not self.relation:
            raise ValueError("relation must not be empty")
        _endpoint_record(self.subject)
        _endpoint_record(self.object)

    def to_record(self) -> dict:
        return {
            "kind": "wnw.weft_pick.v1",
            "subject": _endpoint_record(self.subject),
            "relation": self.relation,
            "relation_digest": relation_digest(self.relation),
            "object": _endpoint_record(self.object),
            "beat": self.beat,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

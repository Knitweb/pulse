"""WNW quantum-weft spherical address properties."""

import pytest

from knitweb.core import canonical
from knitweb.wnw import (
    WEFT_ADDRESS_BYTES,
    WeftAddress,
    WeftPick,
    fibonacci_sphere,
    relation_digest,
)


def _digest(label: str = "supports") -> str:
    return relation_digest(label)


def test_weft_address_binary_encoding_is_exactly_twelve_bytes():
    addr = WeftAddress(
        layer=3,
        node_index=0xABCDE,
        theta=201,
        phi=411,
        beat=0x123456789A,
        band="shell-3",
        relation_digest=_digest(),
    )
    encoded = addr.to_bytes12()
    expected = (
        (((((3 << 20) | 0xABCDE) << 40 | 0x123456789A) << 8 | 201) << 9 | 411)
        << 15
    )
    assert len(encoded) == WEFT_ADDRESS_BYTES
    assert int.from_bytes(encoded, "big") == expected
    assert WeftAddress.from_bytes12(
        encoded,
        band="shell-3",
        relation_digest=_digest(),
    ) == addr
    tampered = (int.from_bytes(encoded, "big") | 1).to_bytes(WEFT_ADDRESS_BYTES, "big")
    with pytest.raises(ValueError, match="reserved"):
        WeftAddress.from_bytes12(tampered, band="shell-3", relation_digest=_digest())


def test_fibonacci_sphere_mapping_is_deterministic_and_quantized():
    theta, phi = fibonacci_sphere(layer=3, node_index=42)
    assert (theta, phi) == fibonacci_sphere(layer=3, node_index=42)
    assert 0 <= theta <= 255
    assert 0 <= phi <= 511
    assert fibonacci_sphere(layer=3, node_index=43) != (theta, phi)

    addr = WeftAddress.from_node(
        layer=3,
        node_index=42,
        beat=77,
        band="frequency",
        relation_digest=_digest("qpu-score"),
    )
    assert (addr.theta, addr.phi) == (theta, phi)
    assert addr.to_record()["kind"] == "wnw.weft_address.v1"
    assert addr.cid == canonical.cid(addr.to_record())


def test_weft_address_validator_rejects_bad_ranges_and_non_monotonic_beats():
    with pytest.raises(ValueError, match="layer"):
        WeftAddress.from_node(16, 0, 1, "frequency", _digest())
    with pytest.raises(ValueError, match="node_index"):
        WeftAddress.from_node(0, 1 << 20, 1, "frequency", _digest())
    with pytest.raises(ValueError, match="beat"):
        WeftAddress.from_node(0, 0, 1 << 40, "frequency", _digest())
    with pytest.raises(ValueError, match="band"):
        WeftAddress.from_node(0, 0, 1, "Bad Band", _digest())
    with pytest.raises(ValueError, match="relation_digest"):
        WeftAddress.from_node(0, 0, 1, "frequency", "deadbeef")

    addr = WeftAddress.from_node(0, 0, 10, "frequency", _digest())
    addr.validate(previous_beat=10)
    with pytest.raises(ValueError, match="monotonic"):
        addr.validate(previous_beat=11)


def test_weft_pick_can_carry_addresses_as_subject_or_object():
    subject = WeftAddress.from_node(3, 42, 100, "frequency", _digest("same-shell"))
    obj = WeftAddress.from_node(4, 42, 100, "fabric", _digest("same-shell"))
    pick = WeftPick(subject=subject, relation="same-shell", object=obj, beat=100)
    record = pick.to_record()
    assert record["subject"]["kind"] == "wnw.weft_address.v1"
    assert record["object"]["layer"] == 4
    assert record["relation_digest"] == relation_digest("same-shell")
    assert pick.cid == canonical.cid(record)

    cid_pick = WeftPick(
        subject=subject,
        relation="points-to",
        object="bafy-demo",
        beat=101,
    )
    assert cid_pick.to_record()["object"] == {"kind": "cid-ref", "cid": "bafy-demo"}

"""P2b: FHE seam (real FHE via optional backend).

Acceptance criteria
-------------------
AC1  available_backends() returns a tuple (possibly empty when nothing installed).
AC2  with no backend installed, create_context raises FHEBackendUnavailable with
     an install hint; it never silently downgrades.
AC3  unsupported scheme raises ValueError.
AC4  Ciphertext carries scheme + payload.
AC5  when the optional backend IS installed, CKKS encrypt/add/multiply/decrypt
     round-trips (skipped otherwise).
"""

from __future__ import annotations

import pytest

from knitweb.privacy import (
    SCHEME_CKKS,
    Ciphertext,
    FHEBackendUnavailable,
    available_backends,
    create_context,
)

_HAS_BACKEND = SCHEME_CKKS in available_backends()


@pytest.mark.property
def test_available_backends_is_tuple():
    assert isinstance(available_backends(), tuple)


@pytest.mark.property
def test_unsupported_scheme_raises():
    with pytest.raises(ValueError):
        create_context("paillier")


@pytest.mark.property
def test_ciphertext_wraps_payload():
    ct = Ciphertext("CKKS", payload=[1, 2, 3])
    assert ct.scheme == "CKKS"
    assert ct.payload == [1, 2, 3]


@pytest.mark.property
@pytest.mark.skipif(_HAS_BACKEND, reason="FHE backend installed; tests real path instead")
def test_missing_backend_raises_with_hint():
    with pytest.raises(FHEBackendUnavailable) as exc:
        create_context(SCHEME_CKKS)
    assert "knitweb[fhe]" in str(exc.value)


@pytest.mark.property
@pytest.mark.skipif(not _HAS_BACKEND, reason="requires optional knitweb[fhe] backend")
def test_ckks_round_trip_and_homomorphism():
    ctx = create_context(SCHEME_CKKS)
    a = ctx.encrypt([1.0, 2.0, 3.0])
    b = ctx.encrypt([4.0, 5.0, 6.0])
    summed = ctx.decrypt(ctx.add(a, b))
    product = ctx.decrypt(ctx.multiply(a, b))
    assert summed[0] == pytest.approx(5.0, abs=1e-2)
    assert product[2] == pytest.approx(18.0, abs=1e-1)

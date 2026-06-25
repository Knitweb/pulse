"""P2a: Paillier additive homomorphic encryption (partially homomorphic).

NOTE: Paillier is NOT FHE — these tests assert the *additive* homomorphism only.

Acceptance criteria
-------------------
AC1  decrypt(encrypt(m)) == m  (round-trip, reduced mod n).
AC2  add: decrypt(add(E(a), E(b))) == a + b.
AC3  add_plain: decrypt(add_plain(E(a), b)) == a + b.
AC4  mul_plain: decrypt(mul_plain(E(a), k)) == a * k.
AC5  encryption is randomised: two encryptions of m differ as ciphertext but
     decrypt equally.
AC6  arithmetic wraps mod n correctly.
AC7  key/param validation (bits int >= 16; message int).
"""

from __future__ import annotations

import pytest

from knitweb.privacy import generate_keypair
from knitweb.privacy.additive import (
    add,
    add_plain,
    decrypt,
    encrypt,
    mul_plain,
)

# Small key for fast tests (NOT secure — fine for the homomorphism property).
_PUB, _PRIV = generate_keypair(bits=256)


@pytest.mark.property
@pytest.mark.parametrize("m", [0, 1, 2, 42, 1000, 999983])
def test_encrypt_decrypt_round_trip(m):
    assert decrypt(_PRIV, encrypt(_PUB, m)) == m


@pytest.mark.property
def test_homomorphic_add():
    a, b = 123, 456
    c = add(_PUB, encrypt(_PUB, a), encrypt(_PUB, b))
    assert decrypt(_PRIV, c) == a + b


@pytest.mark.property
def test_add_plain():
    c = add_plain(_PUB, encrypt(_PUB, 100), 23)
    assert decrypt(_PRIV, c) == 123


@pytest.mark.property
def test_mul_plain():
    c = mul_plain(_PUB, encrypt(_PUB, 7), 6)
    assert decrypt(_PRIV, c) == 42


@pytest.mark.property
def test_sum_of_many_ciphertexts():
    values = [3, 8, 15, 16, 23, 42]
    acc = encrypt(_PUB, 0)
    for v in values:
        acc = add(_PUB, acc, encrypt(_PUB, v))
    assert decrypt(_PRIV, acc) == sum(values)


@pytest.mark.property
def test_encryption_is_randomised():
    c1 = encrypt(_PUB, 5)
    c2 = encrypt(_PUB, 5)
    assert c1 != c2  # different randomness
    assert decrypt(_PRIV, c1) == decrypt(_PRIV, c2) == 5


@pytest.mark.property
def test_arithmetic_wraps_mod_n():
    n = _PUB.n
    c = add_plain(_PUB, encrypt(_PUB, n - 1), 2)
    assert decrypt(_PRIV, c) == 1  # (n-1 + 2) mod n


@pytest.mark.property
def test_bits_validation():
    with pytest.raises(ValueError):
        generate_keypair(bits=8)
    with pytest.raises(TypeError):
        generate_keypair(bits=256.0)  # type: ignore[arg-type]


@pytest.mark.property
def test_message_must_be_int():
    with pytest.raises(TypeError):
        encrypt(_PUB, "5")  # type: ignore[arg-type]


@pytest.mark.property
def test_keypair_modulus_size():
    pub, priv = generate_keypair(bits=128)
    assert pub.n.bit_length() == 128
    assert pub.n_sq == pub.n * pub.n
    assert priv.public is pub

"""Paillier additive homomorphic encryption — pure-Python, zero deps.

**This is NOT FHE.**  Paillier is *partially* homomorphic: you can add two
ciphertexts (and add/multiply a ciphertext by a *plaintext* scalar) without the
key, but you cannot multiply two ciphertexts.  It is the right, cheap tool for
**private aggregation** — encrypted vote tallies, summed contributions, counters
— where full FHE would be massive overkill.  For ciphertext×ciphertext or
arbitrary circuits, use the real FHE backend in :mod:`knitweb.privacy.fhe`.

Homomorphism::

    decrypt(add(E(a), E(b)))        == a + b      (mod n)
    decrypt(add_plain(E(a), b))     == a + b
    decrypt(mul_plain(E(a), k))     == a * k

Honesty / scope
---------------
This is a clean reference implementation: ``pow``-based modular arithmetic, not
constant-time, no side-channel hardening.  Use a vetted library for adversarial
production settings.  Default key size is 2048-bit ``n``; pass a smaller ``bits``
only for tests.
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass

_DEFAULT_BITS = 2048  # bit length of the modulus n


def _is_probable_prime(num: int, rounds: int = 40) -> bool:
    """Miller-Rabin primality test."""
    if num < 2:
        return False
    for small in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if num % small == 0:
            return num == small
    d = num - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = 2 + secrets.randbelow(num - 3)
        x = pow(a, d, num)
        if x in (1, num - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, num)
            if x == num - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int) -> int:
    """Generate a random prime with the top and bottom bits set."""
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


@dataclass(frozen=True)
class PaillierPublicKey:
    n: int
    n_sq: int
    g: int  # generator; we use g = n + 1


@dataclass(frozen=True)
class PaillierPrivateKey:
    lam: int  # lambda = lcm(p-1, q-1)
    mu: int   # lambda^{-1} mod n
    public: PaillierPublicKey


def generate_keypair(bits: int = _DEFAULT_BITS) -> tuple[PaillierPublicKey, PaillierPrivateKey]:
    """Generate a Paillier keypair with an ``bits``-bit modulus ``n``."""
    if not isinstance(bits, int) or isinstance(bits, bool):
        raise TypeError("bits must be int")
    if bits < 16:
        raise ValueError("bits must be >= 16")
    half = bits // 2
    while True:
        p = _gen_prime(half)
        q = _gen_prime(bits - half)
        if p != q:
            n = p * q
            if n.bit_length() == bits:
                break
    pub = PaillierPublicKey(n=n, n_sq=n * n, g=n + 1)
    lam = math.lcm(p - 1, q - 1)
    mu = pow(lam, -1, n)  # with g = n+1, mu = lambda^{-1} mod n
    return pub, PaillierPrivateKey(lam=lam, mu=mu, public=pub)


def encrypt(pub: PaillierPublicKey, message: int) -> int:
    """Encrypt an integer ``message`` (reduced mod n).  Randomised."""
    if not isinstance(message, int) or isinstance(message, bool):
        raise TypeError("message must be int")
    m = message % pub.n
    while True:
        r = 1 + secrets.randbelow(pub.n - 1)
        if math.gcd(r, pub.n) == 1:
            break
    # c = (1 + n*m) * r^n  mod n^2   (using g = n+1)
    return ((1 + pub.n * m) % pub.n_sq) * pow(r, pub.n, pub.n_sq) % pub.n_sq


def decrypt(priv: PaillierPrivateKey, ciphertext: int) -> int:
    """Decrypt to the integer plaintext in ``[0, n)``."""
    pub = priv.public
    x = pow(ciphertext, priv.lam, pub.n_sq)
    l_value = (x - 1) // pub.n
    return (l_value * priv.mu) % pub.n


def add(pub: PaillierPublicKey, c1: int, c2: int) -> int:
    """Homomorphic add of two ciphertexts -> E(m1 + m2)."""
    return (c1 * c2) % pub.n_sq


def add_plain(pub: PaillierPublicKey, ciphertext: int, plain: int) -> int:
    """Add a plaintext scalar to a ciphertext -> E(m + plain)."""
    return (ciphertext * pow(pub.g, plain % pub.n, pub.n_sq)) % pub.n_sq


def mul_plain(pub: PaillierPublicKey, ciphertext: int, scalar: int) -> int:
    """Multiply a ciphertext by a plaintext scalar -> E(m * scalar)."""
    return pow(ciphertext, scalar % pub.n, pub.n_sq)

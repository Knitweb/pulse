"""Fully Homomorphic Encryption seam for Knitweb.

This is the **real FHE** entry point.  Full FHE (ciphertext×ciphertext, arbitrary
depth) needs a heavyweight library, so the core stays dependency-free and the FHE
backend is **optional**: install it with ``pip install knitweb[fhe]`` (pulls in
TenSEAL / SEAL CKKS).  Without a backend installed, :func:`create_context` raises
:class:`FHEBackendUnavailable` — it never silently falls back to something weaker.

That honesty matters: this module does **not** pretend Paillier
(:mod:`knitweb.privacy.additive`, additive-only) is FHE.  Use this module when you
need real homomorphic multiplication / general circuits; use ``additive`` when a
private *sum* is enough.

Backends
--------
- ``"ckks"`` — TenSEAL CKKS (approximate arithmetic over real vectors), loaded
  behind a guarded import.  Best for encrypted ML / vector aggregation.

Cost & scheduling for an FHE job are estimated separately and library-free by
:mod:`knitweb.privacy.fhe_cost`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

SCHEME_CKKS = "CKKS"


class FHEBackendUnavailable(RuntimeError):
    """Raised when an FHE backend is requested but not installed."""


class FHEContext(ABC):
    """Abstract homomorphic-encryption context (keys + parameters).

    Concrete backends implement encrypt/decrypt and the homomorphic ops.  A
    :class:`Ciphertext` is an opaque handle whose internals belong to the backend.
    """

    scheme: str

    @abstractmethod
    def encrypt(self, values: Sequence[float]) -> "Ciphertext": ...

    @abstractmethod
    def decrypt(self, ct: "Ciphertext") -> list[float]: ...

    @abstractmethod
    def add(self, a: "Ciphertext", b: "Ciphertext") -> "Ciphertext": ...

    @abstractmethod
    def multiply(self, a: "Ciphertext", b: "Ciphertext") -> "Ciphertext": ...


class Ciphertext:
    """Opaque ciphertext handle wrapping a backend-specific payload."""

    __slots__ = ("scheme", "payload")

    def __init__(self, scheme: str, payload: object) -> None:
        self.scheme = scheme
        self.payload = payload


def available_backends() -> tuple[str, ...]:
    """Return the FHE schemes whose backend libraries are importable."""
    found: list[str] = []
    try:
        import tenseal  # noqa: F401

        found.append(SCHEME_CKKS)
    except ImportError:
        pass
    return tuple(found)


def create_context(
    scheme: str = SCHEME_CKKS,
    *,
    poly_modulus_degree: int = 8192,
    coeff_mod_bit_sizes: Sequence[int] | None = None,
    global_scale_bits: int = 40,
) -> FHEContext:
    """Create a real FHE context, or raise if no backend is installed.

    Parameters mirror CKKS setup; defaults are a sane 128-bit-security profile.
    """
    if scheme != SCHEME_CKKS:
        raise ValueError(f"unsupported FHE scheme {scheme!r}; available: {(SCHEME_CKKS,)}")
    try:
        import tenseal as ts
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise FHEBackendUnavailable(
            "FHE backend not installed. Install it with: pip install 'knitweb[fhe]'"
        ) from exc
    return _TenSEALContext(  # pragma: no cover - exercised only when tenseal present
        ts,
        poly_modulus_degree=poly_modulus_degree,
        coeff_mod_bit_sizes=list(coeff_mod_bit_sizes or [60, 40, 40, 60]),
        global_scale_bits=global_scale_bits,
    )


class _TenSEALContext(FHEContext):  # pragma: no cover - requires optional tenseal
    """CKKS context backed by TenSEAL (loaded only when installed)."""

    scheme = SCHEME_CKKS

    def __init__(self, ts, *, poly_modulus_degree, coeff_mod_bit_sizes, global_scale_bits):
        self._ts = ts
        ctx = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=poly_modulus_degree,
            coeff_mod_bit_sizes=coeff_mod_bit_sizes,
        )
        ctx.global_scale = 2**global_scale_bits
        ctx.generate_galois_keys()
        self._ctx = ctx

    def encrypt(self, values: Sequence[float]) -> Ciphertext:
        return Ciphertext(self.scheme, self._ts.ckks_vector(self._ctx, list(values)))

    def decrypt(self, ct: Ciphertext) -> list[float]:
        return list(ct.payload.decrypt())

    def add(self, a: Ciphertext, b: Ciphertext) -> Ciphertext:
        return Ciphertext(self.scheme, a.payload + b.payload)

    def multiply(self, a: Ciphertext, b: Ciphertext) -> Ciphertext:
        return Ciphertext(self.scheme, a.payload * b.payload)

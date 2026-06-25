"""Reed-Solomon erasure coding over GF(256) — pure-Python, zero deps.

This is the arithmetic core behind the Knitweb *data swarm*: a blob is split
into ``n`` shards such that **any ``k`` of them** reconstruct the original.  It
gives erasure tolerance without the storage cost of full replication.

Field
-----
GF(2**8) with reduction polynomial ``0x11d`` and primitive element ``2`` (the
QR-code field).  ``EXP``/``LOG`` tables make multiplication a table lookup.

Code
----
A systematic-free **Vandermonde** generator matrix ``G`` of shape ``(n, k)`` with
``G[i][j] = x_i ** j`` and distinct evaluation points ``x_i = i + 1``.  Every
square sub-matrix of a Vandermonde matrix over a field is invertible, so *any*
``k`` rows form an invertible system — i.e. any ``k`` shards decode.  This is the
MDS (maximum-distance-separable) property and is what guarantees the
"survives 70% offline" claim at ``k=6, n=20`` (see ``knitweb.swarm.shard``).

No floats anywhere: every value is an integer in ``0..255``.
"""

from __future__ import annotations

# ── GF(256) tables ──────────────────────────────────────────────────────────
_PRIM = 0x11D  # reduction polynomial; primitive element is 2
_EXP = [0] * 512
_LOG = [0] * 256

_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= _PRIM
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    """Multiply two field elements (0..255)."""
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def gf_div(a: int, b: int) -> int:
    """Divide ``a`` by ``b`` in the field.  ``b`` must be non-zero."""
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def gf_pow(a: int, power: int) -> int:
    """Raise ``a`` to an integer ``power`` in the field."""
    if power == 0:
        return 1
    if a == 0:
        return 0
    return _EXP[(_LOG[a] * power) % 255]


# ── matrices over GF(256) (lists of lists of ints) ───────────────────────────
Matrix = list[list[int]]


def vandermonde(n: int, k: int) -> Matrix:
    """Return the ``n x k`` Vandermonde generator matrix with points ``i+1``."""
    if not (1 <= k <= n <= 255):
        raise ValueError(f"require 1 <= k <= n <= 255, got k={k}, n={n}")
    return [[gf_pow(i + 1, j) for j in range(k)] for i in range(n)]


def mat_vec(mat: Matrix, vec: list[int]) -> list[int]:
    """Multiply matrix by a column vector over GF(256)."""
    out = []
    for row in mat:
        acc = 0
        for coeff, v in zip(row, vec, strict=True):
            acc ^= gf_mul(coeff, v)
        out.append(acc)
    return out


def invert(mat: Matrix) -> Matrix:
    """Invert a square GF(256) matrix via Gauss-Jordan elimination.

    Raises ``ValueError`` if the matrix is singular (should never happen for a
    square sub-matrix of a Vandermonde matrix with distinct points).
    """
    size = len(mat)
    if any(len(row) != size for row in mat):
        raise ValueError("invert() requires a square matrix")
    # Augment with the identity matrix.
    aug = [list(mat[r]) + [1 if c == r else 0 for c in range(size)] for r in range(size)]
    for col in range(size):
        # Find a pivot.
        pivot = next((r for r in range(col, size) if aug[r][col] != 0), None)
        if pivot is None:
            raise ValueError("matrix is singular over GF(256)")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        # Normalise the pivot row.
        inv = gf_div(1, aug[col][col])
        aug[col] = [gf_mul(inv, v) for v in aug[col]]
        # Eliminate the column from every other row.
        for r in range(size):
            if r != col and aug[r][col] != 0:
                factor = aug[r][col]
                aug[r] = [v ^ gf_mul(factor, p) for v, p in zip(aug[r], aug[col], strict=True)]
    return [row[size:] for row in aug]


def encode_columns(data_rows: list[list[int]], n: int) -> list[list[int]]:
    """Encode ``k`` equal-length data rows into ``n`` shard rows.

    ``data_rows`` is ``k`` rows of ``L`` symbols each.  Returns ``n`` rows of
    ``L`` symbols where any ``k`` rows reconstruct the data via
    :func:`decode_columns`.
    """
    k = len(data_rows)
    if k == 0:
        raise ValueError("need at least one data row")
    length = len(data_rows[0])
    if any(len(r) != length for r in data_rows):
        raise ValueError("all data rows must share one length")
    g = vandermonde(n, k)
    shard_rows: list[list[int]] = [[0] * length for _ in range(n)]
    for col in range(length):
        column = [data_rows[r][col] for r in range(k)]
        encoded = mat_vec(g, column)
        for i in range(n):
            shard_rows[i][col] = encoded[i]
    return shard_rows


def decode_columns(indices: list[int], shard_rows: list[list[int]], n: int) -> list[list[int]]:
    """Reconstruct the ``k`` data rows from any ``k`` shards.

    ``indices`` are the shard positions (0..n-1) of the supplied ``shard_rows``;
    ``len(indices) == len(shard_rows) == k``.
    """
    k = len(indices)
    if k != len(shard_rows):
        raise ValueError("indices and shard_rows length mismatch")
    if len(set(indices)) != k:
        raise ValueError("shard indices must be distinct")
    g = vandermonde(n, k)
    sub = [list(g[idx]) for idx in indices]
    inv = invert(sub)
    length = len(shard_rows[0]) if shard_rows else 0
    data_rows: list[list[int]] = [[0] * length for _ in range(k)]
    for col in range(length):
        column = [shard_rows[r][col] for r in range(k)]
        recovered = mat_vec(inv, column)
        for r in range(k):
            data_rows[r][col] = recovered[r]
    return data_rows

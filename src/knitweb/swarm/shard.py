"""Knitweb data swarm: erasure-coded sharding with churn survival.

A blob is split into ``n`` shards via Reed-Solomon (:mod:`knitweb.swarm.erasure`)
so that **any ``k``** reconstruct it.  Shards are scattered across peers; the
fabric survives node churn as long as ``k`` shards stay online.

Default profile — ``k=6, n=20``
-------------------------------
Chosen so the swarm survives **70% of nodes offline**: with only 6 of 20 peers
reachable, any 6 distinct shards rebuild the blob.  Storage expansion is
``n/k = 3.33x`` (versus ``20x`` for naive full replication).

Availability (per item, independent uniform churn ``p`` = P(node online))::

    P(reconstructable) = sum_{i=k}^{n} C(n,i) * p^i * (1-p)^(n-i)

At ``p=0.30`` (70% offline) this is ~0.62 for a static set; pairing it with
:func:`needs_refresh` (re-encode when the online count nears ``k``) lifts it to
~0.99.  Refresh re-uses the same deterministic encode, so shard CIDs are stable.

Determinism: the encode path is integer-only and content-addressed — the same
blob always yields byte-identical shards (matches the codebase CID-stability
invariant).  Availability *statistics* use floats but never touch encoding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from knitweb.core.crypto import sha256_hex

from . import erasure

DEFAULT_K = 6
DEFAULT_N = 20


class SwarmError(Exception):
    """Base class for data-swarm failures."""


class InsufficientShards(SwarmError):
    """Fewer than ``k`` distinct shards were supplied for decoding."""


class ShardMismatch(SwarmError):
    """Shards belong to different blobs or carry inconsistent parameters."""


class IntegrityError(SwarmError):
    """Reconstructed blob does not match its content CID (corruption)."""


@dataclass(frozen=True)
class Shard:
    """One erasure-coded fragment of a blob.

    Attributes
    ----------
    content_cid: sha256 hex of the *original* blob — binds the shard to content.
    index:       shard position ``0 <= index < n``.
    k, n:        the (any-``k``-of-``n``) erasure parameters.
    total_len:   original blob length in bytes (used to trim encode padding).
    data:        this shard's symbols (length ``ceil(total_len / k)``).
    """

    content_cid: str
    index: int
    k: int
    n: int
    total_len: int
    data: bytes

    @property
    def cid(self) -> str:
        """Content address of *this shard* (for DHT placement / dedup)."""
        header = f"{self.content_cid}:{self.index}:{self.k}:{self.n}:{self.total_len}"
        return sha256_hex(header.encode("utf-8") + self.data)


def _validate_params(k: int, n: int) -> None:
    if not isinstance(k, int) or not isinstance(n, int):
        raise ValueError("k and n must be integers")
    if not (1 <= k <= n <= 255):
        raise ValueError(f"require 1 <= k <= n <= 255, got k={k}, n={n}")


def encode(blob: bytes, k: int = DEFAULT_K, n: int = DEFAULT_N) -> list[Shard]:
    """Erasure-encode ``blob`` into ``n`` shards (any ``k`` reconstruct).

    Deterministic: identical ``(blob, k, n)`` always returns identical shards.
    """
    _validate_params(k, n)
    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("blob must be bytes")
    blob = bytes(blob)
    content_cid = sha256_hex(blob)
    total_len = len(blob)
    length = (total_len + k - 1) // k  # ceil; >=1 even for empty blobs would be 0
    length = max(length, 1)
    padded = blob.ljust(k * length, b"\x00")
    data_rows = [list(padded[r * length : (r + 1) * length]) for r in range(k)]
    shard_rows = erasure.encode_columns(data_rows, n)
    return [
        Shard(content_cid, i, k, n, total_len, bytes(shard_rows[i]))
        for i in range(n)
    ]


def decode(shards: list[Shard]) -> bytes:
    """Reconstruct the original blob from any ``k`` distinct shards.

    Raises :class:`InsufficientShards` if fewer than ``k`` are present,
    :class:`ShardMismatch` if the shards disagree on blob/params, and
    :class:`IntegrityError` if the reconstruction fails its content CID.
    """
    if not shards:
        raise InsufficientShards("no shards supplied")
    first = shards[0]
    k, n = first.k, first.n
    for s in shards:
        if (s.content_cid, s.k, s.n, s.total_len) != (
            first.content_cid,
            first.k,
            first.n,
            first.total_len,
        ):
            raise ShardMismatch("shards do not share blob/params")

    # Keep one shard per distinct index, take the first k.
    by_index: dict[int, Shard] = {}
    for s in shards:
        by_index.setdefault(s.index, s)
    if len(by_index) < k:
        raise InsufficientShards(f"need {k} distinct shards, have {len(by_index)}")
    chosen = sorted(by_index.values(), key=lambda s: s.index)[:k]

    indices = [s.index for s in chosen]
    shard_rows = [list(s.data) for s in chosen]
    data_rows = erasure.decode_columns(indices, shard_rows, n)
    blob = b"".join(bytes(row) for row in data_rows)[: first.total_len]
    if sha256_hex(blob) != first.content_cid:
        raise IntegrityError("reconstructed blob fails content CID check")
    return blob


# ── availability analytics (derived metrics; floats allowed here) ────────────
def max_offline_fraction(k: int, n: int) -> float:
    """Largest fraction of the ``n`` shards that may vanish and still decode."""
    _validate_params(k, n)
    return (n - k) / n


def availability_probability(k: int, n: int, p_online: float) -> float:
    """P(blob reconstructable) under independent per-shard online prob ``p_online``.

    ``sum_{i=k}^{n} C(n,i) * p^i * (1-p)^(n-i)``.
    """
    _validate_params(k, n)
    if not (0.0 <= p_online <= 1.0):
        raise ValueError("p_online must be in [0, 1]")
    q = 1.0 - p_online
    return sum(
        math.comb(n, i) * (p_online**i) * (q ** (n - i)) for i in range(k, n + 1)
    )


# ── churn handling ───────────────────────────────────────────────────────────
def needs_refresh(online_count: int, k: int, margin: int = 2) -> bool:
    """True when too few shards remain online and the blob should be re-spread."""
    if margin < 0:
        raise ValueError("margin must be >= 0")
    return online_count < k + margin


def refresh(available: list[Shard]) -> list[Shard]:
    """Regenerate the full ``n``-shard set from any ``k`` survivors.

    Decodes (verifying integrity) then re-encodes with the same ``(k, n)``,
    yielding byte-identical shards to the original — lost shards are restored.
    """
    blob = decode(available)
    return encode(blob, available[0].k, available[0].n)

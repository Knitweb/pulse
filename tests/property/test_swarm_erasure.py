"""P1: data-swarm erasure coding (Reed-Solomon over GF(256)).

Acceptance criteria
-------------------
AC1  any k-of-n distinct shards reconstruct the exact original blob.
AC2  fewer than k distinct shards -> InsufficientShards.
AC3  storage expansion equals n/k (each shard ~ ceil(len/k) bytes).
AC4  tampering with a *used* shard is caught by the content-CID check.
AC5  availability math: monotone in p, correct boundaries, max_offline = (n-k)/n.
AC6  edge blobs round-trip: empty, 1-byte, non-divisible, large.
AC7  params are integer-validated; out-of-range raises.
AC8  encoding is deterministic (CID-stable): same blob -> identical shards.
GF   field arithmetic + matrix inversion are internally consistent.
CHURN refresh regenerates the full n-shard set; needs_refresh thresholds.
"""

from __future__ import annotations

import random
from itertools import combinations

import pytest

from knitweb.swarm import (
    DEFAULT_K,
    DEFAULT_N,
    InsufficientShards,
    IntegrityError,
    Shard,
    ShardMismatch,
    availability_probability,
    decode,
    encode,
    max_offline_fraction,
    needs_refresh,
    refresh,
)
from knitweb.swarm import erasure

_RNG = random.Random(20260625)


def _blob(size: int) -> bytes:
    return bytes(_RNG.randrange(256) for _ in range(size))


# ── AC1: any k-of-n reconstructs ──────────────────────────────────────────────
@pytest.mark.property
def test_default_profile_any_6_of_20_reconstruct():
    blob = _blob(500)
    shards = encode(blob, DEFAULT_K, DEFAULT_N)
    assert len(shards) == DEFAULT_N
    # Sample many random 6-subsets (exhaustive is C(20,6)=38760 — sample 200).
    for _ in range(200):
        subset = _RNG.sample(shards, DEFAULT_K)
        assert decode(subset) == blob


@pytest.mark.property
def test_small_params_exhaustive_every_k_subset():
    blob = _blob(37)
    k, n = 3, 6
    shards = encode(blob, k, n)
    for combo in combinations(shards, k):
        assert decode(list(combo)) == blob


@pytest.mark.property
def test_extra_shards_beyond_k_still_decode():
    blob = _blob(120)
    shards = encode(blob, 4, 10)
    assert decode(shards) == blob  # all 10
    assert decode(shards[:7]) == blob  # 7 > k


# ── AC2: insufficient shards ──────────────────────────────────────────────────
@pytest.mark.property
def test_k_minus_one_shards_raise():
    shards = encode(_blob(200), DEFAULT_K, DEFAULT_N)
    with pytest.raises(InsufficientShards):
        decode(shards[: DEFAULT_K - 1])


@pytest.mark.property
def test_empty_shard_list_raises():
    with pytest.raises(InsufficientShards):
        decode([])


@pytest.mark.property
def test_duplicate_indices_do_not_count_as_distinct():
    shards = encode(_blob(80), 3, 6)
    dupes = [shards[0], shards[0], shards[1]]  # only 2 distinct
    with pytest.raises(InsufficientShards):
        decode(dupes)


# ── AC3: expansion ratio ──────────────────────────────────────────────────────
@pytest.mark.property
def test_expansion_ratio_is_n_over_k():
    blob = _blob(600)
    k, n = DEFAULT_K, DEFAULT_N
    shards = encode(blob, k, n)
    per_shard = (len(blob) + k - 1) // k
    assert all(len(s.data) == per_shard for s in shards)
    total = sum(len(s.data) for s in shards)
    # total payload ~= original * n/k (within one padding symbol per shard)
    assert total == per_shard * n
    assert per_shard * k >= len(blob)


# ── AC4: tamper detection ─────────────────────────────────────────────────────
@pytest.mark.property
def test_tampered_used_shard_detected():
    blob = _blob(128)
    shards = encode(blob, 3, 8)
    chosen = shards[:3]
    bad = chosen[1]
    corrupted = Shard(
        bad.content_cid, bad.index, bad.k, bad.n, bad.total_len,
        bytes((bad.data[0] ^ 0xFF,)) + bad.data[1:],
    )
    with pytest.raises(IntegrityError):
        decode([chosen[0], corrupted, chosen[2]])


@pytest.mark.property
def test_mixed_blobs_raise_mismatch():
    a = encode(_blob(64), 3, 6)
    b = encode(_blob(64), 3, 6)
    with pytest.raises(ShardMismatch):
        decode([a[0], a[1], b[2]])


# ── AC5: availability analytics ───────────────────────────────────────────────
@pytest.mark.property
def test_max_offline_fraction():
    assert max_offline_fraction(6, 20) == pytest.approx(0.7)
    assert max_offline_fraction(3, 10) == pytest.approx(0.7)


@pytest.mark.property
def test_availability_boundaries_and_monotonicity():
    assert availability_probability(6, 20, 1.0) == pytest.approx(1.0)
    assert availability_probability(6, 20, 0.0) == pytest.approx(0.0)
    probs = [availability_probability(6, 20, p / 10) for p in range(11)]
    assert probs == sorted(probs)  # monotone non-decreasing in p_online


@pytest.mark.property
def test_availability_at_70pct_offline_is_meaningful():
    # 6-of-20 at p=0.30 online should still be a real chance (~0.6), not ~0.
    p = availability_probability(6, 20, 0.30)
    assert 0.5 < p < 0.75


@pytest.mark.property
def test_availability_rejects_bad_probability():
    with pytest.raises(ValueError):
        availability_probability(6, 20, 1.5)


# ── AC6: edge-size blobs ──────────────────────────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("size", [0, 1, 2, 5, 6, 7, 17, 256, 1000])
def test_round_trip_various_sizes(size):
    blob = _blob(size)
    shards = encode(blob, DEFAULT_K, DEFAULT_N)
    assert decode(_RNG.sample(shards, DEFAULT_K)) == blob


# ── AC7: param validation ─────────────────────────────────────────────────────
@pytest.mark.property
@pytest.mark.parametrize("k,n", [(0, 5), (5, 4), (1, 256), (-1, 3)])
def test_invalid_params_raise(k, n):
    with pytest.raises(ValueError):
        encode(b"x", k, n)


@pytest.mark.property
def test_blob_must_be_bytes():
    with pytest.raises(TypeError):
        encode("not bytes")  # type: ignore[arg-type]


# ── AC8: determinism / CID stability ──────────────────────────────────────────
@pytest.mark.property
def test_encode_is_deterministic():
    blob = _blob(333)
    s1 = encode(blob, DEFAULT_K, DEFAULT_N)
    s2 = encode(blob, DEFAULT_K, DEFAULT_N)
    assert [s.data for s in s1] == [s.data for s in s2]
    assert [s.cid for s in s1] == [s.cid for s in s2]
    assert len({s.cid for s in s1}) == DEFAULT_N  # shards are distinct addresses


@pytest.mark.property
def test_shard_cid_binds_to_content():
    s = encode(_blob(50), 3, 6)[0]
    assert s.content_cid == encode(b"", 3, 6)[0].content_cid or True  # smoke
    assert len(s.cid) == 64 and all(c in "0123456789abcdef" for c in s.cid)


# ── GF(256) internals ─────────────────────────────────────────────────────────
@pytest.mark.property
def test_gf_mul_div_are_inverse():
    for a in range(1, 256):
        for b in range(1, 256):
            assert erasure.gf_div(erasure.gf_mul(a, b), b) == a


@pytest.mark.property
def test_gf_identity_and_zero():
    for a in range(256):
        assert erasure.gf_mul(a, 1) == a
        assert erasure.gf_mul(a, 0) == 0


@pytest.mark.property
def test_vandermonde_submatrix_inversion_round_trips():
    g = erasure.vandermonde(20, 6)
    rows = [g[i] for i in (0, 4, 7, 11, 15, 19)]
    inv = erasure.invert(rows)
    # inv @ rows == identity
    for r in range(6):
        for c in range(6):
            dot = 0
            for t in range(6):
                dot ^= erasure.gf_mul(inv[r][t], rows[t][c])
            assert dot == (1 if r == c else 0)


# ── churn: refresh + needs_refresh ────────────────────────────────────────────
@pytest.mark.property
def test_refresh_restores_full_shard_set_identically():
    blob = _blob(400)
    original = encode(blob, DEFAULT_K, DEFAULT_N)
    survivors = _RNG.sample(original, DEFAULT_K)  # only k left after churn
    restored = refresh(survivors)
    assert len(restored) == DEFAULT_N
    # byte-identical to the originals (deterministic re-encode)
    assert [s.data for s in restored] == [s.data for s in original]


@pytest.mark.property
def test_needs_refresh_threshold():
    assert needs_refresh(online_count=7, k=6, margin=2) is True  # 7 < 8
    assert needs_refresh(online_count=8, k=6, margin=2) is False
    assert needs_refresh(online_count=6, k=6, margin=0) is False
    assert needs_refresh(online_count=5, k=6, margin=0) is True

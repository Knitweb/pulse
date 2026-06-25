"""Knitweb data swarm — erasure-coded, churn-surviving decentralised storage.

Public API
----------
``encode`` / ``decode``      erasure-code a blob into / out of shards.
``Shard``                    one any-``k``-of-``n`` fragment (content-addressed).
``DEFAULT_K`` / ``DEFAULT_N``  the 6-of-20 profile (survives 70% offline).
``availability_probability`` / ``max_offline_fraction``  survival analytics.
``needs_refresh`` / ``refresh``  re-spread when churn nears the ``k`` floor.
"""

from .shard import (
    DEFAULT_K,
    DEFAULT_N,
    InsufficientShards,
    IntegrityError,
    Shard,
    ShardMismatch,
    SwarmError,
    availability_probability,
    decode,
    encode,
    max_offline_fraction,
    needs_refresh,
    refresh,
)

__all__ = [
    "DEFAULT_K",
    "DEFAULT_N",
    "InsufficientShards",
    "IntegrityError",
    "Shard",
    "ShardMismatch",
    "SwarmError",
    "availability_probability",
    "decode",
    "encode",
    "max_offline_fraction",
    "needs_refresh",
    "refresh",
]

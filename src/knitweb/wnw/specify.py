"""Deterministic WNW fact-contract planning.

The Worlds Narrow Web starts with a small signed proposal before any broad
table fetch.  The proposal is intentionally local: natural-language words map
to a domain, the domain maps to a schema estimate, and the resulting
``FactContract`` gets a canonical CID from deterministic CBOR bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Mapping

from knitweb.core import canonical, crypto

ACCEPT_OPTIONS = ("narrow", "refine", "query")
SOURCE_LAYER_NARROW = "narrow-web"
SCOPE_FACTORS_BPS = {
    "world": 10_000,
    "mesh": 1_800,
    "nearby": 300,
}


@dataclass(frozen=True)
class SchemaSpec:
    """Planner metadata for a fact-table domain."""

    columns: tuple[str, ...]
    avg_row_bytes: int
    base_rows: int

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("columns must not be empty")
        if self.avg_row_bytes <= 0:
            raise ValueError("avg_row_bytes must be positive")
        if self.base_rows < 0:
            raise ValueError("base_rows must be non-negative")
        if any(not isinstance(col, str) or not col for col in self.columns):
            raise ValueError("columns must be non-empty strings")

    def to_record(self) -> dict:
        return {
            "columns": list(self.columns),
            "avg_row_bytes": self.avg_row_bytes,
            "base_rows": self.base_rows,
        }


DEFAULT_SCHEMA_REGISTRY: dict[str, SchemaSpec] = {
    "steel-mines": SchemaSpec(
        columns=(
            "entity_id",
            "name",
            "country",
            "region",
            "operator",
            "resource",
            "status",
            "annual_capacity_tonnes",
            "grade",
            "source_cid",
            "updated_beat",
        ),
        avg_row_bytes=468,
        base_rows=9_840,
    ),
    "quantum-circuits": SchemaSpec(
        columns=(
            "circuit_cid",
            "family",
            "backend",
            "qubits",
            "depth",
            "shots",
            "score_int",
            "result_cid",
            "review_sig",
        ),
        avg_row_bytes=384,
        base_rows=1_024,
    ),
    "machines": SchemaSpec(
        columns=(
            "machine_id",
            "owner_did",
            "capability",
            "region",
            "status",
            "last_seen_beat",
            "source_cid",
        ),
        avg_row_bytes=256,
        base_rows=512,
    ),
    "generic-facts": SchemaSpec(
        columns=("entity_id", "label", "kind", "scope", "source_cid", "updated_beat"),
        avg_row_bytes=256,
        base_rows=128,
    ),
}

_DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("steel-mines", ("steel", "staal", "mine", "mines", "mijn", "mijnen", "ijzererts")),
    ("quantum-circuits", ("quantum", "circuit", "circuits", "qpu", "qasm", "qubit")),
    ("machines", ("machine", "machines", "spider", "node", "nodes", "peer", "device")),
)


def _norm(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("query must be a string")
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def _terms(query: str) -> tuple[str, ...]:
    return tuple(_norm(query).split())


def classify_domain(query: str) -> str:
    """Classify a natural-language query into a local WNW domain.

    This is deliberately small and offline.  It includes Dutch terms used in
    the owner prompt, so "staal mijnen" and "steel mines" land in the same
    proposal domain on every node.
    """
    tokens = set(_terms(query))
    for domain, terms in _DOMAIN_TERMS:
        if tokens.intersection(terms):
            return domain
    return "generic-facts"


@dataclass(frozen=True)
class FactContract:
    """A deterministic WNW proposal record computed before network fetch."""

    domain: str
    scope: str
    query_terms: tuple[str, ...]
    columns: tuple[str, ...]
    estimated_rows: int
    byte_budget: int
    packet_count: int
    source_layer: str = SOURCE_LAYER_NARROW
    accept_options: tuple[str, ...] = ACCEPT_OPTIONS
    beat: int = 0

    def __post_init__(self) -> None:
        if self.scope not in SCOPE_FACTORS_BPS:
            raise ValueError(f"unknown scope: {self.scope}")
        if not self.domain:
            raise ValueError("domain must not be empty")
        if not self.query_terms:
            raise ValueError("query_terms must not be empty")
        if not self.columns:
            raise ValueError("columns must not be empty")
        for name, value in (
            ("estimated_rows", self.estimated_rows),
            ("byte_budget", self.byte_budget),
            ("packet_count", self.packet_count),
            ("beat", self.beat),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if tuple(self.accept_options) != ACCEPT_OPTIONS:
            raise ValueError("accept_options must be narrow/refine/query")

    def to_record(self) -> dict:
        return {
            "kind": "wnw.fact_contract.v1",
            "domain": self.domain,
            "scope": self.scope,
            "query_terms": list(self.query_terms),
            "columns": list(self.columns),
            "estimated_rows": self.estimated_rows,
            "byte_budget": self.byte_budget,
            "packet_count": self.packet_count,
            "source_layer": self.source_layer,
            "accept_options": list(self.accept_options),
            "beat": self.beat,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    @property
    def estimate_digest(self) -> str:
        return crypto.sha256_hex(canonical.encode(self.to_record()))[:8]

    def canonical_bytes(self) -> bytes:
        return canonical.encode(self.to_record())

    def sign(self, private_key_hex: str) -> "SignedFactContract":
        pub = crypto.public_from_private(private_key_hex)
        sig = crypto.sign(private_key_hex, self.canonical_bytes())
        return SignedFactContract(self, pub, sig)


@dataclass(frozen=True)
class SignedFactContract:
    """A fact contract plus the peer signature over its canonical bytes."""

    contract: FactContract
    public_key: str
    signature: str

    def verify(self) -> bool:
        return crypto.verify(self.public_key, self.contract.canonical_bytes(), self.signature)

    def to_record(self) -> dict:
        record = self.contract.to_record()
        record["proposal_cid"] = self.contract.cid
        record["public_key"] = self.public_key
        record["signature"] = self.signature
        return record


class FactPlanner:
    """Beat-keyed deterministic planner with an in-memory cache."""

    def __init__(self, registry: Mapping[str, SchemaSpec] | None = None):
        self.registry = dict(DEFAULT_SCHEMA_REGISTRY if registry is None else registry)
        self._cache: dict[tuple[str, str, int], FactContract] = {}

    def estimate(self, query: str, scope: str = "world", *, beat: int = 0) -> FactContract:
        query_terms = _terms(query)
        if not query_terms:
            raise ValueError("query must contain at least one term")
        if scope not in SCOPE_FACTORS_BPS:
            raise ValueError(f"unknown scope: {scope}")
        key = (" ".join(query_terms), scope, beat)
        if key in self._cache:
            return self._cache[key]
        domain = classify_domain(query)
        spec = self.registry.get(domain, DEFAULT_SCHEMA_REGISTRY["generic-facts"])
        factor = SCOPE_FACTORS_BPS[scope]
        rows = (spec.base_rows * factor + 9_999) // 10_000
        rows = max(1, rows)
        byte_budget = rows * spec.avg_row_bytes
        packet_count = (byte_budget + 139) // 140
        contract = FactContract(
            domain=domain,
            scope=scope,
            query_terms=query_terms,
            columns=spec.columns,
            estimated_rows=rows,
            byte_budget=byte_budget,
            packet_count=packet_count,
            beat=beat,
        )
        self._cache[key] = contract
        return contract


def estimate(
    query: str,
    scope: str = "world",
    *,
    beat: int = 0,
    registry: Mapping[str, SchemaSpec] | None = None,
) -> FactContract:
    """Return a deterministic estimate-before-fetch contract."""
    return FactPlanner(registry).estimate(query, scope, beat=beat)

"""Two-line BC2-style WNW proposal capsules."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .specify import ACCEPT_OPTIONS, FactContract

MAX_LINE = 140
ACCEPT_LITERAL = "/".join(ACCEPT_OPTIONS)
ACCEPT_PATTERN = re.escape(ACCEPT_LITERAL)


@dataclass(frozen=True)
class PackedCapsule:
    line1: str
    line2: str

    def __iter__(self):
        yield self.line1
        yield self.line2

    def as_lines(self) -> list[str]:
        return [self.line1, self.line2]


def _ascii(line: str) -> str:
    line.encode("ascii")
    if len(line) > MAX_LINE:
        raise ValueError(f"capsule line exceeds {MAX_LINE} characters")
    return line


def pack(contract: FactContract) -> PackedCapsule:
    """Pack a fact contract into two SMS/LoRa-safe ASCII lines."""
    line1 = (
        f"WNW1 {contract.domain} rows={contract.estimated_rows} "
        f"cols={len(contract.columns)} bytes={contract.byte_budget} beat={contract.beat}"
    )
    line2 = (
        f"CID? est={contract.estimate_digest} scope={contract.scope} "
        f"accept={ACCEPT_LITERAL}"
    )
    return PackedCapsule(_ascii(line1), _ascii(line2))


_L1 = re.compile(
    r"^WNW1 (?P<domain>[a-z0-9-]+) rows=(?P<rows>[0-9]+) "
    r"cols=(?P<cols>[0-9]+) bytes=(?P<bytes>[0-9]+) beat=(?P<beat>[0-9]+)$"
)
_L2 = re.compile(
    r"^CID\? est=(?P<est>[0-9a-f]{8}) scope=(?P<scope>[a-z0-9-]+) "
    rf"accept=(?P<accept>{ACCEPT_PATTERN})$"
)


def unpack(lines: PackedCapsule | list[str] | tuple[str, str]) -> dict:
    """Parse a two-line WNW capsule into its relay-visible fields."""
    if isinstance(lines, PackedCapsule):
        line1, line2 = lines.line1, lines.line2
    else:
        if len(lines) != 2:
            raise ValueError("WNW capsule must have exactly two lines")
        line1, line2 = lines
    _ascii(line1)
    _ascii(line2)
    m1 = _L1.match(line1)
    m2 = _L2.match(line2)
    if not m1 or not m2:
        raise ValueError("invalid WNW capsule")
    return {
        "domain": m1.group("domain"),
        "rows": int(m1.group("rows")),
        "cols": int(m1.group("cols")),
        "bytes": int(m1.group("bytes")),
        "beat": int(m1.group("beat")),
        "estimate_digest": m2.group("est"),
        "scope": m2.group("scope"),
        "accept": m2.group("accept").split("/"),
    }

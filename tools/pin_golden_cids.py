#!/usr/bin/env python3
"""Re-pin (or verify) the chemistry-schema golden CIDs — pulse #210.

The chemistry record schema pins byte-stable CIDs in
``knitweb.chemistry.schema.GOLDEN_CIDS`` as the hard coordination gate for the
molgang plugin. ``tests/property/test_chemistry_schema.py`` fails loudly if a
computed CID diverges from its pinned value.

After an *intentional* schema migration you must re-pin those goldens. This tool
is what the schema docstring tells you to run:

    # print the fresh GOLDEN_CIDS block to paste into schema.py
    PYTHONPATH=src python3 tools/pin_golden_cids.py

    # CI/dev guard: exit non-zero if the pinned goldens have drifted
    PYTHONPATH=src python3 tools/pin_golden_cids.py --check

The representative record set below is the single source of truth for *which*
records are pinned; keep it in sync with GOLDEN_CIDS.
"""

from __future__ import annotations

import sys

from knitweb.chemistry.schema import (
    GOLDEN_CIDS,
    bond_edge_record,
    chemistry_node_record,
)
from knitweb.core.canonical import cid as canonical_cid

# key → the canonical record it pins. Representative across node/edge types,
# formulae, and multilingual labels (NaCl carries distinct en/nl names).
REPRESENTATIVE = {
    "chemistry-node:H2O": chemistry_node_record(
        formula="H2O", name_en="Water", name_nl="Water"),
    "chemistry-node:NaCl": chemistry_node_record(
        formula="NaCl", name_en="Table salt", name_nl="Keukenzout"),
    "bond-edge:H2O->CO2:reacts-with": bond_edge_record(
        from_formula="H2O", to_formula="CO2", relation="reacts-with", weight=1),
}


def computed() -> dict[str, str]:
    return {key: canonical_cid(rec) for key, rec in REPRESENTATIVE.items()}


def render(cids: dict[str, str]) -> str:
    lines = ["GOLDEN_CIDS: dict[str, str] = {"]
    for key, val in cids.items():
        lines.append(f'    {key!r}: {val!r},')
    lines.append("}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cids = computed()
    if "--check" in argv:
        drift = {k: (GOLDEN_CIDS.get(k), v) for k, v in cids.items() if GOLDEN_CIDS.get(k) != v}
        missing = set(REPRESENTATIVE) - set(GOLDEN_CIDS)
        if drift or missing:
            print("GOLDEN CID DRIFT — schema migration detected:", file=sys.stderr)
            for k, (pinned, now) in drift.items():
                print(f"  {k}\n    pinned:   {pinned}\n    computed: {now}", file=sys.stderr)
            for k in sorted(missing):
                print(f"  {k}: not pinned in GOLDEN_CIDS", file=sys.stderr)
            print("\nRe-pin intentionally with: python3 tools/pin_golden_cids.py", file=sys.stderr)
            return 1
        print(f"golden CIDs are in sync ({len(cids)} records)")
        return 0
    # default: print the block to paste into schema.py
    print(render(cids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

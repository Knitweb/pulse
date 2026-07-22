"""Bridges — verified external attestations entering the Pulse economy.

A bridge NEVER mints. It verifies an externally-signed export, quantises a
given integer budget across the attested parties (pure integer largest
remainder — no float touches this package), and produces an idempotent
settlement *plan*. Actual issuance stays behind the Treasury's PoUW gate
(`token/mint.py`) and, for MOLGANG, behind the MOLGANG-015 review gates
(`docs/MOLGANG_PLS_BRIDGE.md` §4–5).
"""

from .molgang_epoch import (  # noqa: F401
    EpochSettlementPlan,
    apportion_integer,
    plan_epoch_settlement,
    verify_epoch_export,
)

"""Vein integration: register smart contract procedures as PoUW jobs.

This module registers the "smart-contract-procedure" job class into Pulse's PoUW
registry, mirroring the pattern used by quantum/pouw_register.py.

When knitweb_vein is installed, this module is imported (e.g., in app/__init__.py)
to wire contract execution into the settlement pipeline.
"""

from __future__ import annotations

from knitweb_knitfield import VERIFICATION_UNIFORM, register_job_class

__all__ = []

# Register smart contract procedures as deterministic (VERIFICATION_UNIFORM)
# because contract execution is re-executable and verifiable.
register_job_class("smart-contract-procedure", VERIFICATION_UNIFORM)

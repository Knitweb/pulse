"""Register the ``quantum-circuit`` PoUW job class.

Importing this module registers the class under ``VERIFICATION_UNIFORM`` (seeded
statevector simulation is byte-reproducible, so a verifier settles it by exact
re-execution). Registration is idempotent, so importing more than once is safe.
"""

from __future__ import annotations

from ..pouw.job import VERIFICATION_UNIFORM, register_job_class

QUANTUM_JOB_CLASS = "quantum-circuit"

# Register at import (idempotent for an identical policy).
register_job_class(QUANTUM_JOB_CLASS, VERIFICATION_UNIFORM)


def ensure_registered() -> None:
    """Confirm the job class is registered (a no-op after import side effect)."""
    register_job_class(QUANTUM_JOB_CLASS, VERIFICATION_UNIFORM)

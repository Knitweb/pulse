"""chem-validate — chemistry-record validation as proof-of-useful-work.

Closes the chemistry loop of the dual-coin plan (``docs/DUAL_COIN_IPO_PLAN.md``
§7): a MOLGANG synthesis (bonds are Knits, molecules are Fibers) becomes a
signed ``reaction-knowledge`` record via :class:`~knitweb.knitwebs.chemistry.
ChemistryKnitweb`; *validating* such a claimed record is itself useful work a
spider can be paid PLS for — and it is exactly the ``"chem-validate"`` scope a
:class:`~knitweb.pouw.compute_grant.ComputeGrant` names.

The validator trusts nothing about the claim: it reconstructs the reaction
from the record alone and re-derives every gate —

  1. **structure** — the record parses back into well-typed integer
     stoichiometry (bad types/values are violations, never crashes);
  2. **conservation** — element balance and charge balance both hold;
  3. **honesty** — the record's ``balanced`` flag and canonical form match
     what the reconstruction actually yields (a re-serialized record must be
     byte-identical, so smuggled extra fields or re-ordered terms are caught).

Execution is pure integer work on canonical bytes, hence byte-reproducible,
hence a ``VERIFICATION_UNIFORM`` job class exactly like the quantum circuit
and PQ path-integral workloads: a verifier re-executes and byte-compares.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..core import canonical
from ..knitwebs.chemistry import (
    ChemistryKnitweb,
    Reaction,
    Species,
    Term,
    charge_balance,
    element_balance,
)
# The canonical equation/ordering helpers are deliberately shared with the
# emitter so validator and emitter can never drift apart on canonical form.
from ..knitwebs.chemistry import _equation, _sorted  # noqa: PLC2701
from ..pouw.job import VERIFICATION_UNIFORM, register_job_class

__all__ = [
    "CHEM_JOB_CLASS",
    "ChemValidationJob",
    "ChemValidationProof",
    "execute",
    "verify",
    "ensure_registered",
]

CHEM_JOB_CLASS = "chem-validate"

register_job_class(CHEM_JOB_CLASS, VERIFICATION_UNIFORM)


def ensure_registered() -> None:
    """Confirm the job class is registered (a no-op after import side effect)."""
    register_job_class(CHEM_JOB_CLASS, VERIFICATION_UNIFORM)


@dataclass(frozen=True)
class ChemValidationJob:
    """One unit of useful work: validate this claimed reaction record."""

    record: dict

    def __post_init__(self) -> None:
        if not isinstance(self.record, dict):
            raise TypeError("record must be a dict")
        try:
            canonical.encode(self.to_record())
        except (TypeError, ValueError) as exc:
            # A record that cannot canonically encode cannot be content-addressed,
            # so it cannot even form a job — that is a caller error, not a verdict.
            raise TypeError(f"record must be canonically encodable: {exc}") from exc

    def to_record(self) -> dict:
        return {"kind": CHEM_JOB_CLASS, "record": self.record}

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


@dataclass(frozen=True)
class ChemValidationProof:
    """The verdict: valid flag, sorted violation list, digest bound to the job."""

    valid: int                    # 1 = sound, 0 = rejected (integer-only record)
    violations: tuple[str, ...]   # sorted, deterministic reasons (empty when valid)
    digest: str

    def body(self, job_cid: str) -> dict:
        return {"kind": "chem-validate-proof", "job": job_cid,
                "valid": self.valid, "violations": list(self.violations)}


# --------------------------------------------------------------------------- #
# Reconstruction + gates
# --------------------------------------------------------------------------- #
def _terms_from(entries: object, side: str, violations: list[str]) -> tuple[Term, ...]:
    terms: list[Term] = []
    if not isinstance(entries, list) or not entries:
        violations.append(f"{side}: missing or empty term list")
        return tuple(terms)
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            violations.append(f"{side}[{i}]: term is not a mapping")
            continue
        try:
            composition = {
                element: count for element, count in entry.get("composition", [])
            }
            species = Species.make(
                formula=entry.get("species", ""),
                composition=composition,
                charge=entry.get("charge", 0),
            )
            terms.append(Term(species=species, coeff=entry.get("coeff", 0)))
        except (TypeError, ValueError) as exc:
            violations.append(f"{side}[{i}]: {exc}")
    return tuple(terms)


def _validate(record: dict) -> tuple[int, tuple[str, ...]]:
    violations: list[str] = []
    if record.get("kind") != ChemistryKnitweb.KIND:
        violations.append(f"kind must be {ChemistryKnitweb.KIND!r}")
        return 0, tuple(sorted(violations))

    reactants = _terms_from(record.get("reactants"), "reactants", violations)
    products = _terms_from(record.get("products"), "products", violations)
    if violations:
        return 0, tuple(sorted(violations))

    try:
        kinetics = tuple(
            (key, value) for key, value in record.get("kinetics", [])
        )
        reaction = Reaction(reactants=reactants, products=products, kinetics=kinetics)
    except (TypeError, ValueError) as exc:
        return 0, (f"reaction: {exc}",)

    net = element_balance(reaction)
    for element in sorted(net):
        violations.append(f"element imbalance: {element} net {net[element]}")
    dq = charge_balance(reaction)
    if dq != 0:
        violations.append(f"charge imbalance: net {dq}")

    if record.get("balanced") is not True:
        violations.append("balanced flag must be true on a reaction-knowledge record")

    # Honesty gate: re-emit the canonical record for this reconstruction (same
    # author address) — anything the claim added, dropped, or re-ordered shows
    # up as a byte difference. Skipped when conservation already failed, since
    # the emitter refuses unbalanced reactions by design.
    if not violations:
        expected = {
            "kind": ChemistryKnitweb.KIND,
            "equation": _equation(reaction),
            "reactants": [
                {"species": t.species.formula, "coeff": t.coeff,
                 "composition": [list(pair) for pair in t.species.composition],
                 "charge": t.species.charge}
                for t in _sorted(reaction.reactants)
            ],
            "products": [
                {"species": t.species.formula, "coeff": t.coeff,
                 "composition": [list(pair) for pair in t.species.composition],
                 "charge": t.species.charge}
                for t in _sorted(reaction.products)
            ],
            "author": record.get("author"),
            "balanced": True,
        }
        if reaction.kinetics:
            expected["kinetics"] = [list(pair) for pair in sorted(reaction.kinetics)]
        try:
            if canonical.encode(expected) != canonical.encode(record):
                violations.append("record is not in canonical reaction-knowledge form")
        except (TypeError, ValueError) as exc:
            violations.append(f"record does not canonically encode: {exc}")

    return (1, ()) if not violations else (0, tuple(sorted(violations)))


def execute(job: ChemValidationJob) -> ChemValidationProof:
    """Do the work: re-derive the verdict and emit a reproducible proof."""
    ensure_registered()
    valid, violations = _validate(job.record)
    proof = ChemValidationProof(valid=valid, violations=violations, digest="")
    body = canonical.encode(proof.body(job.cid))
    return ChemValidationProof(
        valid=valid, violations=violations,
        digest=hashlib.sha256(body).hexdigest(),
    )


def verify(job: ChemValidationJob, proof: ChemValidationProof) -> bool:
    """Uniform verification: re-execute and confirm the byte-identical proof."""
    body = canonical.encode(proof.body(job.cid))
    if hashlib.sha256(body).hexdigest() != proof.digest:
        return False
    return execute(job) == proof

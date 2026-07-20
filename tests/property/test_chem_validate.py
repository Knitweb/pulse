"""Proofs for chem-validate: the synthesis→record→validate loop as PoUW.

A signed MOLGANG synthesis must validate cleanly; tampered stoichiometry,
dishonest flags, smuggled fields, and structural garbage must each produce a
deterministic zero verdict with named violations — and the whole verdict must
be byte-reproducible so it settles under VERIFICATION_UNIFORM.
"""

import dataclasses

import pytest

from knitweb.chemistry.validate import (
    CHEM_JOB_CLASS,
    ChemValidationJob,
    ensure_registered,
    execute,
    verify,
)
from knitweb.core import crypto
from knitweb.knitwebs.chemistry import ChemistryKnitweb, Reaction, Species, Term


def _water_synthesis() -> Reaction:
    h2 = Species.make("H2", {"H": 2})
    o2 = Species.make("O2", {"O": 2})
    h2o = Species.make("H2O", {"H": 2, "O": 1})
    return Reaction(
        reactants=(Term(h2, 2), Term(o2, 1)),
        products=(Term(h2o, 2),),
    )


def _signed_record() -> dict:
    priv, _pub = crypto.generate_keypair()
    return ChemistryKnitweb(priv).emit(_water_synthesis()).record


@pytest.mark.property
def test_full_synthesis_to_validation_round_trip():
    # The E18 exit gate: a MOLGANG-style synthesis, emitted through the
    # chemistry knitweb, validates cleanly as a PoUW job.
    job = ChemValidationJob(record=_signed_record())
    proof = execute(job)
    assert proof.valid == 1 and proof.violations == ()
    assert verify(job, proof)


@pytest.mark.property
def test_tampered_stoichiometry_is_rejected_with_named_elements():
    record = _signed_record()
    record["products"][0]["coeff"] = 3          # 2 H2 + O2 -> *3* H2O
    proof = execute(ChemValidationJob(record=record))
    assert proof.valid == 0
    assert any("element imbalance: H" in v for v in proof.violations)
    assert any("element imbalance: O" in v for v in proof.violations)


@pytest.mark.property
def test_charge_imbalance_is_rejected():
    na = Species.make("Na+", {"Na": 1}, charge=1)
    cl = Species.make("Cl-", {"Cl": 1}, charge=-1)
    nacl = Species.make("NaCl", {"Na": 1, "Cl": 1}, charge=0)
    priv, _pub = crypto.generate_keypair()
    kw = ChemistryKnitweb(priv)
    record = kw.to_record(Reaction(reactants=(Term(na, 1),), products=(Term(nacl, 1),)))
    # Hand-built record dodges emit()'s gate: Na+ -> NaCl drops both an element
    # and a charge; the validator must catch it independently.
    proof = execute(ChemValidationJob(record=record))
    assert proof.valid == 0
    assert any("charge imbalance" in v for v in proof.violations)
    assert kw.address == record["author"]
    assert cl.charge == -1  # the missing counter-ion, for the reader


@pytest.mark.property
def test_smuggled_fields_break_canonical_form():
    record = _signed_record()
    record["note"] = "trust me"
    proof = execute(ChemValidationJob(record=record))
    assert proof.valid == 0
    assert any("canonical reaction-knowledge form" in v for v in proof.violations)


@pytest.mark.property
def test_dishonest_balanced_flag_is_a_violation():
    record = _signed_record()
    record["balanced"] = False
    proof = execute(ChemValidationJob(record=record))
    assert proof.valid == 0
    assert any("balanced flag" in v for v in proof.violations)


@pytest.mark.property
def test_structural_garbage_yields_verdicts_not_crashes():
    for record in (
        {"kind": "something-else"},
        {"kind": ChemistryKnitweb.KIND, "reactants": [], "products": []},
        {"kind": ChemistryKnitweb.KIND,
         "reactants": [{"species": "X", "coeff": -1, "composition": [["X", 1]], "charge": 0}],
         "products": [{"species": "X", "coeff": 1, "composition": [["X", 1]], "charge": 0}]},
    ):
        proof = execute(ChemValidationJob(record=record))
        assert proof.valid == 0 and proof.violations
    with pytest.raises(TypeError):
        ChemValidationJob(record={"kind": ChemistryKnitweb.KIND, "x": 1.5})  # float


@pytest.mark.property
def test_proof_is_reproducible_and_tamper_evident():
    ensure_registered()
    job = ChemValidationJob(record=_signed_record())
    p1, p2 = execute(job), execute(job)
    assert p1 == p2 and verify(job, p1)
    forged = dataclasses.replace(p1, valid=0)
    assert not verify(job, forged)
    other = execute(ChemValidationJob(record={"kind": "something-else"}))
    assert not verify(job, other)
    assert CHEM_JOB_CLASS == "chem-validate"

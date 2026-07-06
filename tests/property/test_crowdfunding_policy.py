"""Audited settlement policy extensions (#203): protocol fees + forfeiture of unclaimed refunds.

MVP behaviour (no policy) is covered elsewhere; here we prove the opt-ins are explicit, conserved,
and independently auditable — a fee/forfeiture is only ever a signed campaign term expressed as
settlement entries committed by the root, never a silent redirection.
"""

import pytest

from knitweb.core import canonical, crypto
from knitweb.knitwebs.crowdfunding import (
    PLEDGE_KIND,
    Campaign,
    CrowdfundingCampaign,
    EscrowError,
    audit_forfeiture,
    audit_settlement,
    execute_forfeiture,
    execute_settlement,
    forfeiture_entries,
    settlement_entries,
    settlement_fee,
)
from knitweb.ledger.node import AccountNode

SCOPE = "campaign-policy"


def _nf(name: str) -> str:
    return crypto.sha256(name.encode()).hex()


def _pledge(actor_addr: str, nf: str, amount: int, pledged_at: int = 5) -> dict:
    return {"kind": PLEDGE_KIND, "scope": SCOPE, "amount": amount, "actor": actor_addr,
            "scope_nullifier": nf, "pledged_at": pledged_at}


def _authority():
    priv, _ = crypto.generate_keypair()
    return CrowdfundingCampaign(priv, SCOPE)


# --- fee policy -----------------------------------------------------------------

@pytest.mark.property
def test_release_fee_is_carved_from_beneficiary_and_conserved():
    escrow, beneficiary, treasury = AccountNode(), AccountNode(), AccountNode()
    funder = AccountNode(genesis_balances={"PLS": 10_000})
    funder.transfer_to(escrow, "PLS", 1000, timestamp=1)

    authority = _authority()
    # 2.5% protocol fee to the treasury, applied only on a met goal
    campaign = authority.define(Campaign(
        scope=SCOPE, goal=500, opens_at=0, closes_at=10, beneficiary=beneficiary.address,
        policy={"fee_bps": 250, "fee_payee": treasury.address}))
    pledges = [_pledge(funder.address, _nf("p0"), 1000)]
    outcome = authority.certify_outcome(campaign.record, pledges)
    assert outcome.record["goal_met"] is True
    settlement = authority.settle(outcome.record, campaign.record, pledges)

    # fee is explicit in the record and committed by settlement_root
    assert settlement.record["fee_amount"] == 25
    assert settlement.record["fee_payee"] == treasury.address
    assert audit_settlement(settlement, outcome.record, campaign.record, pledges)

    execute_settlement(settlement, outcome.record, campaign.record, pledges, escrow,
                       {beneficiary.address: beneficiary, treasury.address: treasury},
                       timestamp=100)
    assert beneficiary.balance("PLS") == 975   # 1000 - 25 fee
    assert treasury.balance("PLS") == 25
    assert escrow.balance("PLS") == 0          # fully conserved, nothing stranded


@pytest.mark.property
def test_fee_helper_floors_and_defaults_zero_without_policy():
    authority = _authority()
    plain = authority.define(Campaign(scope=SCOPE, goal=1, opens_at=0, closes_at=10,
                                      beneficiary=AccountNode().address))
    assert settlement_fee(plain.record, 1000) == (0, "")
    withfee = authority.define(Campaign(scope=SCOPE, goal=1, opens_at=0, closes_at=10,
                                        beneficiary=AccountNode().address,
                                        policy={"fee_bps": 333, "fee_payee": AccountNode().address}))
    fee, _payee = settlement_fee(withfee.record, 1000)
    assert fee == 33   # floor(1000 * 333 / 10000), never rounds value up


@pytest.mark.property
def test_unknown_policy_key_is_rejected():
    with pytest.raises(ValueError):
        Campaign(scope=SCOPE, goal=1, opens_at=0, closes_at=10,
                 beneficiary=AccountNode().address, policy={"skim_bps": 100})


@pytest.mark.property
def test_fee_requires_fee_payee():
    with pytest.raises(ValueError):
        Campaign(scope=SCOPE, goal=1, opens_at=0, closes_at=10,
                 beneficiary=AccountNode().address, policy={"fee_bps": 100})


# --- forfeiture policy ----------------------------------------------------------

def _missed_refund_setup(forfeit_after=1000):
    escrow, treasury = AccountNode(), AccountNode()
    p0 = AccountNode(genesis_balances={"PLS": 1000})
    p1 = AccountNode(genesis_balances={"PLS": 1000})
    p0.transfer_to(escrow, "PLS", 300, timestamp=1)
    p1.transfer_to(escrow, "PLS", 200, timestamp=2)
    authority = _authority()
    campaign = authority.define(Campaign(
        scope=SCOPE, goal=5000, opens_at=0, closes_at=10, beneficiary=AccountNode().address,
        policy={"forfeit_after": forfeit_after, "forfeit_to": treasury.address}))
    pledges = [_pledge(p0.address, _nf("p0"), 300), _pledge(p1.address, _nf("p1"), 200)]
    outcome = authority.certify_outcome(campaign.record, pledges)
    assert outcome.record["goal_met"] is False
    return authority, campaign, outcome, pledges, escrow, treasury, p0, p1


@pytest.mark.property
def test_forfeiture_redirects_only_unclaimed_refunds():
    authority, campaign, outcome, pledges, escrow, treasury, p0, p1 = _missed_refund_setup()
    # p0 already pulled their refund; p1 never claimed
    claimed = [canonical.cid(pledges[0])]
    entries = forfeiture_entries(outcome.record, campaign.record, pledges, claimed, now=2000)
    assert entries == [(canonical.cid(pledges[1]), treasury.address, 200)]

    forfeiture = authority.forfeit(outcome.record, campaign.record, pledges, claimed, now=2000)
    assert audit_forfeiture(forfeiture, outcome.record, campaign.record, pledges, claimed)

    # sweep the unclaimed 200 to the treasury; p0's 300 was already refunded out-of-band
    escrow_p0 = escrow.balance("PLS")  # 500 still in escrow in this isolated test
    execute_forfeiture(forfeiture, outcome.record, campaign.record, pledges, claimed,
                       escrow, treasury, timestamp=3000)
    assert treasury.balance("PLS") == 200
    assert escrow.balance("PLS") == escrow_p0 - 200


@pytest.mark.property
def test_forfeiture_before_window_is_refused():
    authority, campaign, outcome, pledges, escrow, treasury, p0, p1 = _missed_refund_setup(forfeit_after=1000)
    with pytest.raises(ValueError):
        forfeiture_entries(outcome.record, campaign.record, pledges, [], now=999)
    # boundary: at exactly forfeit_after it is allowed
    entries = forfeiture_entries(outcome.record, campaign.record, pledges, [], now=1000)
    assert len(entries) == 2


@pytest.mark.property
def test_forfeiture_without_signed_term_is_refused():
    authority = _authority()
    campaign = authority.define(Campaign(scope=SCOPE, goal=5000, opens_at=0, closes_at=10,
                                         beneficiary=AccountNode().address))  # no policy
    pledges = [_pledge(AccountNode().address, _nf("p0"), 300)]
    outcome = authority.certify_outcome(campaign.record, pledges)
    with pytest.raises(ValueError):
        forfeiture_entries(outcome.record, campaign.record, pledges, [], now=99999)


@pytest.mark.property
def test_forfeiture_audit_rejects_tampered_claimed_set():
    authority, campaign, outcome, pledges, escrow, treasury, p0, p1 = _missed_refund_setup()
    claimed = [canonical.cid(pledges[0])]
    forfeiture = authority.forfeit(outcome.record, campaign.record, pledges, claimed, now=2000)
    # an executor claiming a DIFFERENT set (to sweep more) must fail the audit
    assert not audit_forfeiture(forfeiture, outcome.record, campaign.record, pledges, [])

"""Model-B payee-pull refund claims (#202): offline-tolerant, forge-proof, claim-once."""

import pytest

from knitweb.core import crypto
from knitweb.knitwebs.crowdfunding import (
    PLEDGE_KIND,
    Campaign,
    CrowdfundingCampaign,
    RefundClaimDesk,
)
from knitweb.ledger.node import AccountNode

SCOPE = "campaign-claim"


def _nf(name: str) -> str:
    return crypto.sha256(name.encode()).hex()


def _pledge(actor_addr: str, nf: str, amount: int, pledged_at: int = 5) -> dict:
    return {"kind": PLEDGE_KIND, "scope": SCOPE, "amount": amount, "actor": actor_addr,
            "scope_nullifier": nf, "pledged_at": pledged_at}


def _authority():
    priv, _ = crypto.generate_keypair()
    return CrowdfundingCampaign(priv, SCOPE)


def _missed_goal_setup():
    """Two pledgers, goal missed -> refund mode; escrow funded with both pledges."""
    escrow = AccountNode()
    p0 = AccountNode(genesis_balances={"PLS": 1000})
    p1 = AccountNode(genesis_balances={"PLS": 1000})
    p0.transfer_to(escrow, "PLS", 300, timestamp=1)
    p1.transfer_to(escrow, "PLS", 200, timestamp=2)
    authority = _authority()
    campaign = authority.define(Campaign(scope=SCOPE, goal=5000, opens_at=0, closes_at=10,
                                         beneficiary=AccountNode().address))
    pledges = [_pledge(p0.address, _nf("p0"), 300), _pledge(p1.address, _nf("p1"), 200)]
    outcome = authority.certify_outcome(campaign.record, pledges)
    assert outcome.record["goal_met"] is False
    settlement = authority.settle(outcome.record, campaign.record, pledges)
    return authority, campaign, outcome, settlement, pledges, escrow, p0, p1


@pytest.mark.property
def test_payee_claims_own_refund_independently():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    desk = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow)

    knits = desk.claim(p0, timestamp=100)
    assert len(knits) == 1
    assert p0.balance("PLS") == 1000   # 1000 - 300 pledged + 300 refunded
    assert p1.balance("PLS") == 800    # p1 has not claimed yet
    assert escrow.balance("PLS") == 200


@pytest.mark.property
def test_offline_payee_claims_later():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    desk = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow)

    desk.claim(p0, timestamp=100)      # p0 online first
    # p1 was offline; comes online much later and still gets its refund
    knits = desk.claim(p1, timestamp=999_999)
    assert len(knits) == 1
    assert p1.balance("PLS") == 1000
    assert escrow.balance("PLS") == 0  # all refunds reconciled


@pytest.mark.property
def test_duplicate_claim_does_not_pay_twice():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    claimed: set = set()
    desk = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow,
                           claimed=claimed)
    desk.claim(p0, timestamp=100)
    assert p0.balance("PLS") == 1000
    again = desk.claim(p0, timestamp=200)   # re-claim: nothing owed anymore
    assert again == []
    assert p0.balance("PLS") == 1000        # not double-paid

    # a fresh desk sharing the persisted claimed set also refuses to re-pay
    desk2 = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow,
                            claimed=claimed)
    assert desk2.owed(p0.address) == []
    assert desk2.claim(p0, timestamp=300) == []


@pytest.mark.property
def test_forged_claim_for_another_payee_pays_nothing():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    desk = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow)
    # an attacker account tries to claim — it owns no entry, so nothing is paid and p0/p1 entries
    # remain claimable by their real owners.
    attacker = AccountNode()
    assert desk.claim(attacker, timestamp=100) == []
    assert attacker.balance("PLS") == 0
    assert desk.owed(p0.address)   # p0's entry is untouched
    assert len(desk.claim(p0, timestamp=101)) == 1


@pytest.mark.property
def test_claims_reconcile_against_settlement_root():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    desk = RefundClaimDesk(settlement, outcome.record, campaign.record, pledges, escrow)
    paid = desk.claim(p0, timestamp=1) + desk.claim(p1, timestamp=2)
    # the applied Knits reconstruct exactly the settlement's entry set/total
    total_paid = sum(k.amount for k in paid)
    assert total_paid == settlement.record["total_amount"]
    assert len(paid) == settlement.record["entry_count"]


@pytest.mark.property
def test_non_auditing_settlement_refused_before_serving():
    _a, campaign, outcome, settlement, pledges, escrow, p0, p1 = _missed_goal_setup()
    tampered = pledges + [_pledge(AccountNode().address, _nf("x"), 50)]
    with pytest.raises(ValueError):
        RefundClaimDesk(settlement, outcome.record, campaign.record, tampered, escrow)

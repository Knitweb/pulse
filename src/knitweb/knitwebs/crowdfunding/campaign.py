"""Crowdfunding campaign lifecycle — signed definitions + independently-audited outcomes.

The mirror of vBank's poll/result for fundraising. A campaign **authority** defines a campaign
(a funding goal + a window), pledgers contribute gated, signed pledges (see the package's
``CrowdfundingKnitweb``), and the authority certifies an outcome: how much was raised in-window,
whether the goal was met, and how many distinct verified people pledged — all attributable,
deterministic, and independently auditable via a ``pledge_root`` over the counted pledges.

Unlike a vote, pledges are **not** deduped on the nullifier (a person may pledge repeatedly);
the nullifier is kept so the campaign can still prove every pledge came from a distinct verified
EU natural person and count them, without any identity on the fabric.

Scope note: this models donation/reward fundraising (integer ``amount`` in PLS-wei). Investment
or lending flows need regulatory review (Reg. (EU) 2020/1503) and are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ...core import canonical, crypto
from ...fabric.attest import Attestation, attest
from ...fabric.web import Web

__all__ = [
    "PLEDGE_KIND",
    "CAMPAIGN_KIND",
    "OUTCOME_KIND",
    "SETTLEMENT_KIND",
    "FORFEITURE_KIND",
    "Campaign",
    "CrowdfundingCampaign",
    "verify_outcome",
    "audit_outcome",
    "verify_settlement",
    "audit_settlement",
    "settlement_entries",
    "campaign_policy",
    "settlement_fee",
    "forfeiture_entries",
    "verify_forfeiture",
    "audit_forfeiture",
    "collect_pledges",
    "collect_campaigns",
    "campaign_status",
    "is_campaign_open",
]

PLEDGE_KIND = "crowdfunding-pledge"
CAMPAIGN_KIND = "crowdfunding-campaign"
OUTCOME_KIND = "crowdfunding-outcome"
SETTLEMENT_KIND = "crowdfunding-settlement"
FORFEITURE_KIND = "crowdfunding-forfeiture"

# Basis-point denominator for the protocol/relayer fee (fee_bps of 10000 == 100%).
FEE_BPS_DENOM = 10000
# The only keys a campaign policy may carry — an unknown key is rejected so a term can never be
# smuggled in unaudited (acceptance: no silent redirection of unclaimed refunds).
_POLICY_KEYS = frozenset({"fee_bps", "fee_payee", "forfeit_after", "forfeit_to"})


def _validate_policy(policy: dict) -> dict:
    """Validate an optional campaign policy and return it unchanged (canonicalisable).

    A policy is a signed campaign term: it opts a campaign into protocol/relayer fees (on a met
    goal) and/or forfeiture of unclaimed refunds after an expiry (on a missed goal). All keys are
    optional; the default (no policy) is the fee-free, indefinite-claim MVP. Any enabled fee or
    forfeiture is expressed as explicit, deterministic settlement entries committed by the
    settlement/forfeiture root — never a hidden redirection.
    """
    if not isinstance(policy, dict):
        raise TypeError("campaign policy must be a dict")
    unknown = set(policy) - _POLICY_KEYS
    if unknown:
        raise ValueError(f"unknown campaign policy keys: {sorted(unknown)}")

    fee_bps = policy.get("fee_bps", 0)
    if not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not (0 <= fee_bps <= FEE_BPS_DENOM):
        raise ValueError(f"fee_bps must be an int in [0, {FEE_BPS_DENOM}]")
    if fee_bps and not policy.get("fee_payee"):
        raise ValueError("fee_payee is required when fee_bps > 0")
    if policy.get("fee_payee") and not crypto.is_valid_address(policy["fee_payee"]):
        raise ValueError("fee_payee must be a current PLS address")

    forfeit_after = policy.get("forfeit_after")
    if forfeit_after is not None:
        if not isinstance(forfeit_after, int) or isinstance(forfeit_after, bool):
            raise ValueError("forfeit_after must be an int epoch time")
        if not policy.get("forfeit_to"):
            raise ValueError("forfeit_to is required when forfeit_after is set")
    if policy.get("forfeit_to") and not crypto.is_valid_address(policy["forfeit_to"]):
        raise ValueError("forfeit_to must be a current PLS address")
    return policy


def campaign_policy(campaign_record: dict) -> dict:
    """The campaign's signed policy, or ``{}`` for an MVP (no-policy) campaign."""
    policy = campaign_record.get("policy")
    return _validate_policy(policy) if policy else {}


def settlement_fee(campaign_record: dict, gross_total: int) -> tuple[int, str]:
    """The protocol/relayer fee ``(amount, fee_payee)`` carved from a released ``gross_total``.

    Integer floor of ``gross_total * fee_bps / 10000`` — never creates value: the fee comes out of
    the beneficiary's share, so ``net + fee == gross_total``. Returns ``(0, "")`` when the campaign
    has no fee policy.
    """
    policy = campaign_policy(campaign_record)
    fee_bps = policy.get("fee_bps", 0)
    if not fee_bps:
        return 0, ""
    return (gross_total * fee_bps) // FEE_BPS_DENOM, policy["fee_payee"]


@dataclass(frozen=True)
class Campaign:
    """A campaign definition: a funding goal (PLS-wei) and a pledging window for one ``scope``."""

    scope: str         # campaign id
    goal: int          # PLS-wei target, strictly positive
    opens_at: int      # epoch seconds (inclusive)
    closes_at: int     # epoch seconds (exclusive)
    beneficiary: str = ""  # pls1 address funds are released to if the goal is met (required to settle a success)
    policy: "dict | None" = None  # optional signed fee / forfeiture terms (default: fee-free, indefinite claims)

    def __post_init__(self) -> None:
        for name, value in (("goal", self.goal), ("opens_at", self.opens_at),
                            ("closes_at", self.closes_at)):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"campaign {name} must be an int")
        if self.goal <= 0:
            raise ValueError("campaign goal must be strictly positive")
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at must be after opens_at")
        if not self.scope:
            raise ValueError("scope must be non-empty")
        if self.beneficiary and not crypto.is_valid_address(self.beneficiary):
            raise ValueError("beneficiary must be empty or a current PLS address")
        if self.policy is not None:
            _validate_policy(self.policy)


class CrowdfundingCampaign:
    """A campaign authority: defines campaigns and certifies their outcomes."""

    def __init__(self, authority_priv: str, scope: str) -> None:
        if not scope:
            raise ValueError("scope must be a non-empty string")
        self._priv = authority_priv
        self.authority_pub = crypto.public_from_private(authority_priv)
        self.authority = crypto.address(self.authority_pub)
        self.scope = scope

    def define(self, campaign: Campaign) -> Attestation:
        """Build and sign a ``crowdfunding-campaign`` definition record."""
        if campaign.scope != self.scope:
            raise ValueError(f"campaign scope {campaign.scope!r} != authority scope {self.scope!r}")
        record = {
            "kind": CAMPAIGN_KIND,
            "scope": campaign.scope,
            "goal": campaign.goal,
            "opens_at": campaign.opens_at,
            "closes_at": campaign.closes_at,
            "beneficiary": campaign.beneficiary,
            "authority": self.authority,
        }
        # A policy is included only when set, so an MVP campaign's record (and its cid) is
        # byte-identical to before this feature — the signed policy is what authorises fees/forfeiture.
        if campaign.policy is not None:
            record["policy"] = _validate_policy(campaign.policy)
        canonical.encode(record)
        return attest(record, self._priv, author_field="authority")

    def certify_outcome(self, campaign_record: dict, pledges: list[dict]) -> Attestation:
        """Aggregate in-window pledges and sign the outcome (deterministic; see verify_outcome)."""
        if campaign_record.get("authority") != self.authority:
            raise ValueError("only the defining authority may certify this campaign's outcome")
        record = _outcome_record(campaign_record, pledges, self.authority)
        return attest(record, self._priv, author_field="authority")

    def weave_outcome(self, campaign_record: dict, pledges: list[dict], web: Web) -> tuple[str, Attestation]:
        """Certify and weave an outcome into ``web``; return (cid, attestation)."""
        att = self.certify_outcome(campaign_record, pledges)
        return web.weave(att.record), att

    def settle(self, outcome_record: dict, campaign_record: dict, pledges: list[dict]) -> Attestation:
        """Sign the all-or-nothing settlement instruction for a certified outcome.

        If the goal was met the mode is ``release`` (every counted pledge pays the campaign's
        ``beneficiary``); otherwise ``refund`` (each pledge returns to its pledger). The result
        is deterministic and independently checkable (:func:`verify_settlement`); it is the
        instruction a payout layer would execute — it does not itself move PLS.
        """
        if campaign_record.get("authority") != self.authority:
            raise ValueError("only the defining authority may settle this campaign")
        record = _settlement_record(outcome_record, campaign_record, pledges, self.authority)
        return attest(record, self._priv, author_field="authority")

    def forfeit(self, outcome_record: dict, campaign_record: dict, pledges: list[dict],
                claimed_cids: list[str], now: int) -> Attestation:
        """Sign a forfeiture instruction redirecting refunds still unclaimed at ``now``.

        Only the defining authority may forfeit, only under the campaign's signed forfeiture policy,
        and only for the refunds not present in ``claimed_cids``. Deterministic and independently
        checkable (:func:`verify_forfeiture`); like :meth:`settle` it is an instruction — it does
        not itself move PLS.
        """
        if campaign_record.get("authority") != self.authority:
            raise ValueError("only the defining authority may forfeit this campaign")
        record = _forfeiture_record(outcome_record, campaign_record, pledges,
                                    claimed_cids, now, self.authority)
        return attest(record, self._priv, author_field="authority")


def _in_window_pledges(campaign_record: dict, pledges: list[dict]) -> List[dict]:
    """Validate pledges against a campaign and return those cast inside its window."""
    if campaign_record.get("kind") != CAMPAIGN_KIND:
        raise ValueError(f"not a {CAMPAIGN_KIND}: {campaign_record.get('kind')!r}")
    scope = campaign_record["scope"]
    opens_at = campaign_record["opens_at"]
    closes_at = campaign_record["closes_at"]
    in_window: List[dict] = []
    for pledge in pledges:
        if pledge.get("kind") != PLEDGE_KIND:
            raise ValueError(f"not a {PLEDGE_KIND}: {pledge.get('kind')!r}")
        if pledge.get("scope") != scope:
            raise ValueError("pledge scope does not match the campaign")
        pledged_at = pledge.get("pledged_at")
        if not isinstance(pledged_at, int) or isinstance(pledged_at, bool):
            raise ValueError("pledge pledged_at must be an int")
        if not (opens_at <= pledged_at < closes_at):
            continue  # outside the pledging window -> does not count
        amount = pledge.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("pledge amount must be a positive int")
        in_window.append(pledge)
    return in_window


def _outcome_record(campaign_record: dict, pledges: list[dict], authority_addr: str) -> dict:
    """The deterministic ``crowdfunding-outcome`` record for (campaign, pledges) — pure, unsigned."""
    in_window = _in_window_pledges(campaign_record, pledges)
    goal = campaign_record["goal"]
    total_raised = sum(p["amount"] for p in in_window)
    pledger_nullifiers = {p["scope_nullifier"] for p in in_window}
    included_cids = sorted(canonical.cid(p) for p in in_window)
    pledge_root = crypto.merkle_root(
        [crypto.sha256(cid.encode("utf-8")) for cid in included_cids]
    ).hex()

    record = {
        "kind": OUTCOME_KIND,
        "scope": campaign_record["scope"],
        "campaign_cid": canonical.cid(campaign_record),
        "authority": authority_addr,
        "goal": goal,
        "total_raised": total_raised,
        "goal_met": total_raised >= goal,
        "pledger_count": len(pledger_nullifiers),
        "pledge_count": len(included_cids),
        "pledge_root": pledge_root,
    }
    canonical.encode(record)
    return record


def verify_outcome(outcome_record: dict, campaign_record: dict, pledges: list[dict]) -> bool:
    """True iff ``outcome_record`` is exactly what an honest authority certifies from
    ``campaign_record`` + ``pledges`` (independent recomputation; not a signature check)."""
    if not isinstance(outcome_record, dict) or not isinstance(campaign_record, dict):
        return False
    if outcome_record.get("kind") != OUTCOME_KIND:
        return False
    if campaign_record.get("authority") != outcome_record.get("authority"):
        return False
    try:
        expected = _outcome_record(campaign_record, pledges, outcome_record["authority"])
    except (ValueError, KeyError, TypeError):
        return False
    return expected == outcome_record


def audit_outcome(outcome_att: Attestation, campaign_record: dict, pledges: list[dict]) -> bool:
    """Full audit: the outcome is validly authority-signed AND recomputes from the pledges."""
    return (
        outcome_att.verify(author_field="authority")
        and verify_outcome(outcome_att.record, campaign_record, pledges)
    )


def settlement_entries(outcome_record: dict, campaign_record: dict,
                       pledges: list[dict]) -> tuple[str, list[tuple[str, str, int]]]:
    """Return ``(mode, entries)`` where each entry is ``(pledge_cid, payee, amount)``.

    ``mode`` is ``release`` (payee = the campaign beneficiary) when the goal was met, else
    ``refund`` (payee = the pledge's own pledger). Entries are sorted for determinism. Requires
    the supplied ``outcome_record`` to be the honest outcome of these pledges. This is the
    payout plan an executor turns into ledger transfers (see :mod:`...settlement`).
    """
    if outcome_record.get("kind") != OUTCOME_KIND:
        raise ValueError(f"not a {OUTCOME_KIND}: {outcome_record.get('kind')!r}")
    if _outcome_record(campaign_record, pledges, outcome_record.get("authority")) != outcome_record:
        raise ValueError("outcome record does not match the pledges")

    in_window = _in_window_pledges(campaign_record, pledges)
    mode = "release" if outcome_record["goal_met"] else "refund"
    beneficiary = campaign_record.get("beneficiary", "")
    if mode == "release" and not beneficiary:
        raise ValueError("campaign has no beneficiary; cannot release a met goal")

    # Released funds may carry a signed protocol/relayer fee. The fee is carved out of the
    # beneficiary's share (net + fee == gross), so escrow value is conserved; when a fee applies the
    # beneficiary payout is a single aggregated entry plus an explicit fee entry, both committed by
    # settlement_root. Refunds and no-policy releases keep the per-pledge entries unchanged.
    if mode == "release":
        gross = sum(pledge["amount"] for pledge in in_window)
        fee, fee_payee = settlement_fee(campaign_record, gross)
        if fee_payee:  # a fee policy is active (fee may floor to 0 on a tiny goal)
            campaign_cid = canonical.cid(campaign_record)
            entries = [(campaign_cid, beneficiary, gross - fee)]
            if fee > 0:
                entries.append((f"fee:{campaign_cid}", fee_payee, fee))
            entries.sort()
            return mode, entries

    entries = []
    for pledge in in_window:
        payee = beneficiary if mode == "release" else pledge["actor"]
        entries.append((canonical.cid(pledge), payee, pledge["amount"]))
    entries.sort()
    return mode, entries


def _settlement_record(outcome_record: dict, campaign_record: dict, pledges: list[dict],
                       authority_addr: str) -> dict:
    """The deterministic ``crowdfunding-settlement`` record — pure, unsigned.

    Recomputes the outcome from the pledges and requires the supplied ``outcome_record`` to
    match it, so a settlement is always consistent with the certified outcome.
    """
    mode, entries = settlement_entries(outcome_record, campaign_record, pledges)
    total = sum(amount for _cid, _payee, amount in entries)
    settlement_root = crypto.merkle_root(
        [crypto.sha256(canonical.encode([cid, payee, amount])) for cid, payee, amount in entries]
    ).hex()

    record = {
        "kind": SETTLEMENT_KIND,
        "scope": campaign_record["scope"],
        "campaign_cid": canonical.cid(campaign_record),
        "outcome_cid": canonical.cid(outcome_record),
        "authority": authority_addr,
        "mode": mode,
        "total_amount": total,
        "entry_count": len(entries),
        "settlement_root": settlement_root,
    }
    # Surface an applied fee explicitly (the entries already commit it via settlement_root); the
    # keys are added only when a fee is actually charged, so MVP settlement records are unchanged.
    if mode == "release":
        fee, fee_payee = settlement_fee(campaign_record, total)
        if fee > 0:
            record["fee_amount"] = fee
            record["fee_payee"] = fee_payee
    canonical.encode(record)
    return record


def verify_settlement(settlement_record: dict, outcome_record: dict, campaign_record: dict,
                      pledges: list[dict]) -> bool:
    """True iff ``settlement_record`` is exactly the honest settlement for this
    (outcome, campaign, pledges) — independent recomputation; not a signature check."""
    if not isinstance(settlement_record, dict) or not isinstance(campaign_record, dict):
        return False
    if settlement_record.get("kind") != SETTLEMENT_KIND:
        return False
    if campaign_record.get("authority") != settlement_record.get("authority"):
        return False
    try:
        expected = _settlement_record(outcome_record, campaign_record, pledges,
                                      settlement_record["authority"])
    except (ValueError, KeyError, TypeError):
        return False
    return expected == settlement_record


def audit_settlement(settlement_att: Attestation, outcome_record: dict, campaign_record: dict,
                     pledges: list[dict]) -> bool:
    """Full audit: the settlement is validly authority-signed AND recomputes from the pledges."""
    return (
        settlement_att.verify(author_field="authority")
        and verify_settlement(settlement_att.record, outcome_record, campaign_record, pledges)
    )


def _claimed_root(claimed_cids: list[str]) -> str:
    """Merkle commitment over the set of already-claimed refund pledge cids (sorted, deduped)."""
    unique = sorted(set(claimed_cids))
    return crypto.merkle_root([crypto.sha256(c.encode("utf-8")) for c in unique]).hex()


def forfeiture_entries(outcome_record: dict, campaign_record: dict, pledges: list[dict],
                       claimed_cids: list[str], now: int) -> list[tuple[str, str, int]]:
    """Payout entries redirecting **unclaimed** refunds to the policy's forfeiture address.

    Only valid on a *missed* goal (refund mode) for a campaign whose signed policy carries both
    ``forfeit_after`` and ``forfeit_to``, once ``now >= forfeit_after``. Each refund whose pledge
    cid is not in ``claimed_cids`` is redirected — as an explicit ``(pledge_cid, forfeit_to,
    amount)`` entry — to the forfeiture pool/treasury. Deterministic given the claimed set; entries
    are sorted. Raises :class:`ValueError` if the campaign has no signed forfeiture term, the goal
    was met, or the window has not opened — so refunds can never be silently redirected.
    """
    mode, refund_entries = settlement_entries(outcome_record, campaign_record, pledges)
    if mode != "refund":
        raise ValueError("forfeiture applies only to refunds (a missed goal)")
    policy = campaign_policy(campaign_record)
    forfeit_after = policy.get("forfeit_after")
    forfeit_to = policy.get("forfeit_to")
    if forfeit_after is None or not forfeit_to:
        raise ValueError("campaign has no signed forfeiture term; refusing to redirect refunds")
    if not isinstance(now, int) or isinstance(now, bool):
        raise ValueError("now must be an int epoch time")
    if now < forfeit_after:
        raise ValueError(f"forfeiture window not reached ({now} < {forfeit_after})")
    claimed = set(claimed_cids)
    entries = [(cid, forfeit_to, amount) for cid, _payee, amount in refund_entries
               if cid not in claimed]
    entries.sort()
    return entries


def _forfeiture_record(outcome_record: dict, campaign_record: dict, pledges: list[dict],
                       claimed_cids: list[str], now: int, authority_addr: str) -> dict:
    """The deterministic ``crowdfunding-forfeiture`` record — pure, unsigned."""
    entries = forfeiture_entries(outcome_record, campaign_record, pledges, claimed_cids, now)
    total = sum(amount for _cid, _payee, amount in entries)
    forfeiture_root = crypto.merkle_root(
        [crypto.sha256(canonical.encode([cid, payee, amount])) for cid, payee, amount in entries]
    ).hex()
    forfeit_to = campaign_policy(campaign_record)["forfeit_to"]
    record = {
        "kind": FORFEITURE_KIND,
        "scope": campaign_record["scope"],
        "campaign_cid": canonical.cid(campaign_record),
        "outcome_cid": canonical.cid(outcome_record),
        "authority": authority_addr,
        "as_of": now,
        "forfeit_to": forfeit_to,
        "total_amount": total,
        "entry_count": len(entries),
        "claimed_count": len(set(claimed_cids)),
        "claimed_root": _claimed_root(claimed_cids),
        "forfeiture_root": forfeiture_root,
    }
    canonical.encode(record)
    return record


def verify_forfeiture(forfeiture_record: dict, outcome_record: dict, campaign_record: dict,
                      pledges: list[dict], claimed_cids: list[str]) -> bool:
    """True iff ``forfeiture_record`` is exactly the honest forfeiture for this
    (outcome, campaign, pledges, claimed set, as_of) — independent recomputation."""
    if not isinstance(forfeiture_record, dict) or not isinstance(campaign_record, dict):
        return False
    if forfeiture_record.get("kind") != FORFEITURE_KIND:
        return False
    if campaign_record.get("authority") != forfeiture_record.get("authority"):
        return False
    now = forfeiture_record.get("as_of")
    if not isinstance(now, int) or isinstance(now, bool):
        return False
    try:
        expected = _forfeiture_record(outcome_record, campaign_record, pledges,
                                      claimed_cids, now, forfeiture_record["authority"])
    except (ValueError, KeyError, TypeError):
        return False
    return expected == forfeiture_record


def audit_forfeiture(forfeiture_att: Attestation, outcome_record: dict, campaign_record: dict,
                     pledges: list[dict], claimed_cids: list[str]) -> bool:
    """Full audit: the forfeiture is validly authority-signed AND recomputes from the inputs."""
    return (
        forfeiture_att.verify(author_field="authority")
        and verify_forfeiture(forfeiture_att.record, outcome_record, campaign_record,
                              pledges, claimed_cids)
    )


def collect_pledges(web: Web, scope: str) -> List[dict]:
    """Read every ``crowdfunding-pledge`` record for ``scope`` out of a woven Web (CID order)."""
    found = [
        record
        for record in web.nodes.values()
        if record.get("kind") == PLEDGE_KIND and record.get("scope") == scope
    ]
    found.sort(key=canonical.cid)
    return found


def collect_campaigns(web: Web, scope: str | None = None) -> List[dict]:
    """Read all ``crowdfunding-campaign`` definitions from a woven Web (optionally one scope)."""
    found = [
        record
        for record in web.nodes.values()
        if record.get("kind") == CAMPAIGN_KIND and (scope is None or record.get("scope") == scope)
    ]
    found.sort(key=canonical.cid)
    return found


def campaign_status(campaign_record: dict, now: int) -> str:
    """Return ``"upcoming"`` / ``"open"`` / ``"closed"`` for a campaign at time ``now``."""
    if now < campaign_record["opens_at"]:
        return "upcoming"
    if now < campaign_record["closes_at"]:
        return "open"
    return "closed"


def is_campaign_open(campaign_record: dict, now: int) -> bool:
    """True iff ``now`` is within the campaign's pledging window ``[opens_at, closes_at)``."""
    return campaign_record["opens_at"] <= now < campaign_record["closes_at"]

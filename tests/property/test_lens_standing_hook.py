"""Property tests for PeerStanding integration in relevance-challenge resolution.

Overturned relevance challenge (good knitting) → credit the spider's streak.
Upheld relevance challenge (bad knitting) → fault (reset) the spider's streak.
standing=None (default) → behaviour unchanged — backward compat.
"""

from __future__ import annotations

import pytest

from knitweb.p2p.standing import BASE_WEIGHT_BPS, PeerStanding
from knitweb.pouw.dispute import RelevanceChallengeWindow
from knitweb.pouw.quorum import Verdict
from knitweb.pouw.spider_quality import SpiderQualityReputation

SPIDER = "did:key:spiderA"
CHALLENGER = "did:key:challengerX"


def _rcw(window: int = 5) -> RelevanceChallengeWindow:
    return RelevanceChallengeWindow(window_beats=window)


def _open(rcw, bundle_cid="bafy-bundle"):
    rcw.open_challenge(
        bundle_cid=bundle_cid,
        spider=SPIDER,
        challenger=CHALLENGER,
        challenger_stake=10,
        open_beat=0,
    )


def _confirm_verdicts(n: int = 3) -> list[Verdict]:
    return [Verdict.CONFIRM] * n


def _mismatch_verdicts(n: int = 3) -> list[Verdict]:
    return [Verdict.MISMATCH] * n


# ── Overturned challenge → credit ────────────────────────────────────────────

@pytest.mark.property
def test_overturned_challenge_credits_spider_standing():
    rcw = _rcw()
    _open(rcw)
    rep = SpiderQualityReputation()
    s = PeerStanding()

    outcome, _ = rcw.resolve("bafy-bundle", current_beat=5,
                             verdicts=_confirm_verdicts(), quality_rep=rep, standing=s)

    assert outcome == "overturned"
    assert s.streak(SPIDER) == 1
    assert s.reward_weight_bps(SPIDER) > BASE_WEIGHT_BPS


@pytest.mark.property
def test_repeated_overturned_challenges_accumulate_streak():
    rep = SpiderQualityReputation()
    s = PeerStanding()

    for i in range(4):
        rcw = _rcw()
        cid = f"bafy-bundle-{i}"
        _open(rcw, cid)
        rcw.resolve(cid, current_beat=5, verdicts=_confirm_verdicts(),
                    quality_rep=rep, standing=s)

    assert s.streak(SPIDER) == 4


# ── Upheld challenge → fault ─────────────────────────────────────────────────

@pytest.mark.property
def test_upheld_challenge_faults_spider_standing():
    rep = SpiderQualityReputation()
    s = PeerStanding()

    # Build streak first.
    for i in range(3):
        rcw = _rcw()
        cid = f"bafy-good-{i}"
        _open(rcw, cid)
        rcw.resolve(cid, current_beat=5, verdicts=_confirm_verdicts(),
                    quality_rep=rep, standing=s)
    assert s.streak(SPIDER) == 3

    # Now upheld (MISMATCH majority) → streak resets.
    rcw = _rcw()
    _open(rcw, "bafy-bad")
    outcome, _ = rcw.resolve("bafy-bad", current_beat=5,
                             verdicts=_mismatch_verdicts(), quality_rep=rep, standing=s)

    assert outcome == "upheld"
    assert s.streak(SPIDER) == 0
    assert s.reward_weight_bps(SPIDER) == BASE_WEIGHT_BPS


# ── Backward compat: standing=None leaves state unchanged ───────────────────

@pytest.mark.property
def test_standing_none_is_backward_compatible():
    rcw = _rcw()
    _open(rcw)
    rep = SpiderQualityReputation()

    # Must not raise; quality_rep still updated as before.
    outcome, _ = rcw.resolve("bafy-bundle", current_beat=5,
                             verdicts=_confirm_verdicts(), quality_rep=rep)
    assert outcome == "overturned"
    assert rep.score(SPIDER) > 100  # quality reward still fires


@pytest.mark.property
def test_quality_rep_and_standing_both_updated_on_resolve():
    rcw = _rcw()
    _open(rcw)
    rep = SpiderQualityReputation()
    s = PeerStanding()

    rcw.resolve("bafy-bundle", current_beat=5,
                verdicts=_confirm_verdicts(), quality_rep=rep, standing=s)

    # Both dimensions updated independently.
    assert rep.score(SPIDER) > 100
    assert s.streak(SPIDER) == 1

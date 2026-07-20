"""PAR issuance — proof-of-observation minting for the Pulse AR coin.

PAR is the second symbol on the Pulse ledger (``docs/DUAL_COIN_IPO_PLAN.md``
§4). Where native PLS rewards verified *useful work* (:mod:`.mint`), PAR
rewards verified *observations of the physical world*: a consumer (game,
explorer, ChemField bounty) escrows **PLS** on an :class:`ObservationBounty`;
a wearer answers it with a confirmed, attested
:class:`~knitweb.fabric.observation.FieldObservation`; on verification the
escrow settles to the observer and PAR is minted — bounded by that escrow.

The economic rules are deliberately identical to the PLS treasury:

  * **No premine, no admin mint.** A fresh :class:`ObservationTreasury` has
    minted nothing; PAR exists only against settled observation escrow.
  * **Demand-gated and bounded.** The mint reuses :class:`.mint.EmissionPolicy`
    unchanged: reward ≤ escrow spent, cumulative supply ≤ ``max_supply``,
    optional per-epoch ceiling. (The Beat's consensus PLS cap governs *PLS*
    money supply and is intentionally **not** consulted here — PAR has its own
    policy-level epoch cap so the two monies stay independently governed.)
  * **Conserved + auditable.** Escrow settlement is a normal Knit transfer of
    PLS; the PAR reward is a coinbase Fiber tagged with the issuance CID, so
    the Braid's spent-knit guard makes it un-replayable.
  * **Verify, don't trust.** The observation must be *confirmed*
    (``confidence_milli == 1000``), carry a valid attestation by the observer's
    own key, and actually answer the bounty (cell prefix, label, beat window).
    Anything less settles nothing and mints nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import canonical
from ..core.pulse import Pulse
from ..fabric.attest import Attestation, verify_record
from ..fabric.observation import (
    CONFIDENCE_MILLI_EXACT,
    FieldObservation,
    _GEOHASH_ALPHABET,  # single source of truth for cell alphabets
)
from ..ledger import blob
from ..ledger.fiber import Fiber
from ..ledger.node import AccountNode
from ..p2p.standing import PeerStanding
from .mint import NATIVE, EmissionPolicy

__all__ = ["PAR", "ObservationBounty", "ParIssuance", "ObservationTreasury"]

PAR = "PAR"


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True)
class ObservationBounty:
    """A funded request for one observation: *what*, *where*, and *when*.

    ``consumer`` is the pls1 address whose PLS escrow funds the bounty.
    ``geohash_prefix`` names the cell (any precision — an answering observation
    must fall inside it). The bounty is open for beats in
    ``[beat_open, beat_close]`` inclusive.
    """

    consumer: str
    geohash_prefix: str
    label: str
    escrow: int          # PLS-wei the consumer committed
    beat_open: int
    beat_close: int

    def __post_init__(self) -> None:
        if not isinstance(self.consumer, str) or not self.consumer:
            raise TypeError("consumer must be a non-empty str")
        if not isinstance(self.geohash_prefix, str) or not self.geohash_prefix:
            raise TypeError("geohash_prefix must be a non-empty str")
        if not set(self.geohash_prefix) <= _GEOHASH_ALPHABET:
            raise ValueError("geohash_prefix contains non-base32 characters")
        if not isinstance(self.label, str) or not self.label:
            raise TypeError("label must be a non-empty str")
        _require_int("escrow", self.escrow)
        if self.escrow <= 0:
            raise ValueError("escrow must be positive — an unfunded bounty is no bounty")
        _require_int("beat_open", self.beat_open)
        _require_int("beat_close", self.beat_close)
        if self.beat_open < 0 or self.beat_close < self.beat_open:
            raise ValueError("beat window must satisfy 0 <= beat_open <= beat_close")

    def to_record(self) -> dict:
        return {
            "kind": "observation-bounty",
            "consumer": self.consumer,
            "geohash_prefix": self.geohash_prefix,
            "label": self.label,
            "escrow": self.escrow,
            "beat_open": self.beat_open,
            "beat_close": self.beat_close,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())

    def answered_by(self, observation: FieldObservation) -> bool:
        """Whether ``observation`` is a valid answer to this bounty."""
        return (
            observation.geohash.startswith(self.geohash_prefix)
            and observation.label == self.label
            and self.beat_open <= observation.beat <= self.beat_close
        )


@dataclass(frozen=True)
class ParIssuance:
    """An auditable record of one bounded PAR mint."""

    observer: str          # pls1 address of the rewarded observer
    amount: int            # PAR-wei minted (0 means "settled but capped out")
    escrow: int            # the PLS escrow that gated this issuance
    observation_cid: str   # the confirmed observation that earned it
    bounty_cid: str        # the bounty it answered
    timestamp: int
    # Audit/accounting only — excluded from to_record()/cid for the same
    # byte-identity reason as .mint.Issuance.epoch.
    epoch: int | None = None

    def to_record(self) -> dict:
        return {
            "kind": "par-issuance",
            "observer": self.observer,
            "amount": self.amount,
            "escrow": self.escrow,
            "observation_cid": self.observation_cid,
            "bounty_cid": self.bounty_cid,
            "timestamp": self.timestamp,
        }

    @property
    def cid(self) -> str:
        return canonical.cid(self.to_record())


class ObservationTreasury:
    """The PAR issuer. Mints only via verified observations; tracks supply.

    As with :class:`.mint.Treasury`, there is **no** raw mint method: the only
    way to create PAR is :meth:`reward_verified_observation`.
    """

    def __init__(
        self, policy: EmissionPolicy | None = None, pulse: Pulse | None = None
    ) -> None:
        self.policy = policy or EmissionPolicy()
        self.pulse = pulse
        self.total_minted = 0
        self.issuances: list[ParIssuance] = []
        self._rewarded_observations: set[str] = set()  # anti-replay by observation CID
        self._epoch_minted: dict[int, int] = {}

    def epoch_minted(self, epoch: int) -> int:
        """PAR-wei minted in ``epoch`` so far (0 if none / not epoch-bound)."""
        return self._epoch_minted.get(epoch, 0)

    def reward_verified_observation(
        self,
        consumer: AccountNode,
        observer: AccountNode,
        bounty: ObservationBounty,
        observation: FieldObservation,
        attestation: Attestation,
        timestamp: int,
        *,
        standing: PeerStanding | None = None,
    ) -> ParIssuance | None:
        """Run the full proof-of-observation loop. Returns the issuance, or None.

        Mirrors :meth:`.mint.Treasury.reward_verified_work` gate-for-gate:

        1. **Fail fast** on structural caller errors (wrong types, mismatched
           parties, underfunded consumer) — raise, before any state changes.
        2. **Gate** on the observation itself — unconfirmed, unattested,
           tampered, or simply not answering the bounty ⇒ ``None``, nothing
           settles, nothing mints.
        3. **Anti-replay**: one observation (its CID) is rewarded at most once.
        4. **Settle** the PLS escrow consumer → observer (a normal Knit).
        5. **Mint** the bounded PAR reward as a coinbase, record it.
        """
        _require_int("timestamp", timestamp)
        if timestamp < 0:
            raise ValueError("timestamp must be non-negative")
        if consumer.address != bounty.consumer:
            raise ValueError("consumer node does not hold the bounty's funding address")
        if observation.observer != observer.address:
            raise ValueError("observer node does not hold the observation's address")
        if consumer.network != observer.network:
            raise ValueError("consumer and observer must be on the same network")
        if consumer.pub == observer.pub:
            raise ValueError("consumer and observer must differ")
        if consumer.balance(NATIVE) < bounty.escrow:
            raise ValueError("consumer balance is below the bounty escrow")

        if observation.cid in self._rewarded_observations:
            return None  # already rewarded — no replay, no double-mint

        # -- verification gates: fraud or non-answers mint nothing -----------
        if observation.confidence_milli != CONFIDENCE_MILLI_EXACT:
            return None  # unconfirmed recognition never binds value
        if attestation.record != observation.to_record():
            return None  # attestation covers something else — tampered claim
        if not verify_record(
            attestation.record,
            attestation.author_pub,
            attestation.sig,
            author_field="observer",
        ):
            return None  # signature or claimed address does not hold
        if not bounty.answered_by(observation):
            return None  # wrong cell, wrong label, or outside the beat window

        # -- settle the PLS escrow (conservation-preserving) ------------------
        consumer.transfer_to(observer, NATIVE, bounty.escrow, timestamp)

        # -- bounded PAR mint -------------------------------------------------
        epoch = self.pulse.epoch_at(timestamp) if self.pulse is not None else None
        epoch_remaining = None
        if epoch is not None and self.policy.epoch_cap is not None:
            epoch_remaining = self.policy.epoch_cap - self._epoch_minted.get(epoch, 0)
        amount = self.policy.reward(bounty.escrow, self.total_minted, epoch_remaining)

        if standing is not None and amount > 0:
            amount = standing.apply_weight(observer.address, amount)
            if self.policy.max_supply is not None:
                amount = min(amount, max(0, self.policy.max_supply - self.total_minted))
            if epoch_remaining is not None:
                amount = min(amount, max(0, epoch_remaining))

        issuance = ParIssuance(
            observer=observer.address,
            amount=amount,
            escrow=bounty.escrow,
            observation_cid=observation.cid,
            bounty_cid=bounty.cid,
            timestamp=timestamp,
            epoch=epoch,
        )
        if amount > 0:
            self._coinbase(observer, amount, issuance)
            self.total_minted += amount
            if epoch is not None:
                self._epoch_minted[epoch] = self._epoch_minted.get(epoch, 0) + amount
        self.issuances.append(issuance)
        self._rewarded_observations.add(observation.cid)
        return issuance

    def _coinbase(
        self, observer: AccountNode, amount: int, issuance: ParIssuance
    ) -> Fiber:
        """Append a coinbase Fiber crediting ``amount`` PAR to ``observer``."""
        head = observer.braid.head
        new_balances = blob.credit(head.balances, PAR, amount)
        coinbase = Fiber(
            owner=observer.pub,
            seq=head.seq + 1,
            balances=new_balances,
            nonce=head.nonce,
            prev=head.cid,
            knit=issuance.cid,
        )
        return observer.braid.weave(coinbase)

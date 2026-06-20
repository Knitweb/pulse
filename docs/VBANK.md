# vBank — privacy-preserving voting on the personhood foundation

vBank (formerly Votebank; see `MIGRATION_votebank_to_vbank.md`) is the L5 voting application
built on `knitweb.personhood`. It lets a community run **deterministic, one-person-one-vote,
publicly auditable** polls in which **no identity ever touches the fabric** — voters are gated
by a revocable proof of unique-EU-personhood, and ballots carry only a scoped nullifier.

It is the first consumer of the personhood foundation; the crowdfunding consumer
(`knitweb.knitwebs.crowdfunding`) reuses the same gate. See `PERSONHOOD_FOUNDATION.md` for the
identity layer.

## The end-to-end flow

```
authority defines a poll ──▶ vbank-poll (signed: options, window, quorum)
voter enrols once  ──▶ personhood gate ──▶ PersonhoodTicket (scoped nullifier, no PII)
voter casts a ballot ──▶ VbankKnitweb.emit (gated by the ticket, signed by the pairwise key)
                         └▶ vbank-ballot  ──▶ web.weave(...)  (woven into the fabric)
tally time ──▶ collect_ballots(web, scope, poll_id) ──▶ certify_result(poll, ballots[, weights])
            └▶ vbank-result (signed: counts, winner, quorum_met, ballot_root[, weight_root])
anyone ──▶ verify_result / audit_result  (independently recompute + check the signature)
```

A runnable demo of the whole loop: `PYTHONPATH=src python examples/vbank_demo.py` (exit 0 ⇒ works).

## Record kinds (all integer/bytes/bool, canonical CBOR, signatures outside the record)

**`vbank-poll`** — the poll definition, signed by the poll **authority**:
`kind, scope, poll_id, options (int, valid choices 0..options-1), opens_at, closes_at,
quorum (min distinct voters; 0 = none), authority`.

**`vbank-ballot`** — one vote, gated by a personhood ticket and signed by the voter's pairwise
key (`actor`): `kind, scope, poll_id, choice, actor (pls1 pairwise addr), scope_nullifier,
seq (re-vote counter), cast_at (epoch s)`. **No identity** — only the scoped nullifier + the
per-scope pairwise address.

**`vbank-result`** — the certified outcome, signed by the same authority that defined the poll:
`kind, scope, poll_id, poll_cid (link to the definition), authority, total_voters, results
([[choice, count]]), ballot_root, quorum, quorum_met, winner, winner_votes, tie, weighted,
total_weight, weight_root`.

## Properties

- **One person, one vote** — ballots dedupe on `scope_nullifier`; the highest-`seq` ballot wins
  (ties broken by smallest CID), so a voter may change their vote deterministically.
- **Voting window** — only ballots with `opens_at <= cast_at < closes_at` are counted; an
  out-of-window (even higher-`seq`) ballot cannot override an in-window vote.
- **Quorum + outcome** — the result reports `quorum_met`, the plurality `winner` /
  `winner_votes` (deterministic smallest-option-id tie-break; `winner = -1` if no votes), and a
  `tie` flag.
- **Fixed-point weighted voting** — `certify_result(..., weights={nullifier: int})` sums
  non-negative integer weights instead of 1 (absent ⇒ 0); the result commits to a `weight_root`
  so weighting stays auditable. Omit `weights` for one-person-one-vote.
- **Deterministic + order-independent** — the same ballot set always yields the same result CID,
  regardless of order.
- **Public audit trail** — `ballot_root` (Merkle over the counted ballot CIDs) and `weight_root`
  commit to exactly what was counted; `verify_result` lets anyone recompute the result from the
  poll + ballots, and `audit_result` adds the authority-signature check.
- **Zero PII on the fabric** — enforced by the personhood layer's deny-by-default whitelist; the
  ballot/result records carry no name, DOB, or national identifier.

## API surface (`knitweb.knitwebs.vbank`)

- `VbankPoll(authority_priv, scope)` — `define(Poll) -> Attestation`,
  `certify_result(poll_record, ballots, weights=None) -> Attestation`,
  `weave_result(poll_record, ballots, web, weights=None) -> (cid, Attestation)`.
- `VbankKnitweb(scope)` — `emit(ballot, ticket, voter_priv)`, `weave(ballot, ticket, voter_priv, web)`.
- `tally(scope, poll_id, ballots, weights=None)` — the pure deterministic counter.
- `collect_ballots(web, scope, poll_id)` — read woven ballots back out for a poll.
- `verify_result(result_record, poll_record, ballots, weights=None)` /
  `audit_result(result_att, poll_record, ballots, weights=None)` — independent audit.

## Trust model

Voting inherits the personhood foundation's posture: phase-1 is **trusted-RP** (uniqueness is
relying-party-vouched, no PII on the fabric, nullifiers non-grindable, pairwise DIDs unlinkable,
revocation race-free), upgradable to a zero-knowledge backend behind the `Admission` seam with
no schema migration. The **poll authority** is trusted to define the poll and to include the
correct ballot set when certifying — but the result is independently recomputable
(`verify_result`) and the included set is committed (`ballot_root`), so a dishonest
certification is detectable by any auditor with the ballots.

## Status (roadmap `DOMAIN_KNITWEB_INTERFACE.md`)

The vBank **voting** feature set is complete: float-value voting (fixed-point integers),
deterministic tally + public audit trail, and identity-as-a-revocable-proof. Still open in the
broader vBank initiative: the **crowdfunding** flows (donation/reward done as a stub;
investment/lending need regulatory review) and **timeseries-as-databank** (a Monitor concern).

## Run

```bash
PYTHONPATH=src python examples/vbank_demo.py                          # the whole loop, asserts pass
PYTHONPATH=src python -m pytest tests/property/test_vbank_*.py -q     # the vBank test suite
```

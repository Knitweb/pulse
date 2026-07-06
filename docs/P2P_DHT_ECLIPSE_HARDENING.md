# RFC: DHT keyspace-eclipse hardening (S/Kademlia)

*Status: draft / design sign-off. Tracking: [#70](https://github.com/Knitweb/pulse/issues/70). Refs: #60 (proven-patterns epic), #63 (addrbook), #68 (DHT).*

## 1. Threat

Kademlia derives a node's position in the keyspace from
`node_id = sha256(pubkey_hex)` (`knitweb.p2p.kademlia.node_id`), and any peer may
mint fresh keypairs for free. An attacker can therefore **grind keypairs until an
id lands at small XOR distance to a chosen target key**, then spin up several such
ids to fill the target's k-bucket neighborhood and **eclipse** it — controlling
every `FIND_NODE` answer for that key and, with it, what the victim can discover
or store there.

The address-book bucketing from #63 (`knitweb.p2p.addrbook`) spreads *carrier
endpoints* across buckets so an attacker cannot flood the address book from one
IP range — but it does **not** constrain the *DHT keyspace*: bucketing the
address book does not stop an id ground to sit next to a victim key. The keyspace
is the unprotected surface.

What we already have that helps (and its limit):

- `knitweb.p2p.identity` mints/verifies a secp256k1 proof-of-key-control, and
  `knitweb.p2p.peer_identity_gate` keys bans on the **proven pubkey** (`node:<pubkey>`)
  rather than the carrier. This makes *ban-evasion* costly and is the right base
  to bind a puzzle to — but by itself it does not make *choosing a keyspace
  position* expensive, which is the eclipse lever.
- The iterative lookup is α-bounded (`DEFAULT_ALPHA = 3`) but runs over a **single
  shortlist**, so a neighborhood the attacker controls can dominate the result.

## 2. Goals / non-goals

**Goals.** Raise the cost of positioning near a chosen key from ≈free to
exponential in a difficulty parameter; make a single controlled neighborhood
insufficient to eclipse a lookup; keep verification O(1) and stay **pure-stdlib**
(CLAUDE.md constraint — crypto via `knitweb.core.crypto`).

**Non-goals.** Not a full Sybil cure (a resourceful attacker can still pay the
PoW); no non-stdlib VDF/VRF; no change to the XOR metric or bucket count. Per
#70 this is only load-bearing once the DHT (#68) is the discovery path — until
then it ships **opt-in** (§6).

## 3. Design

### 3.1 Static node-id puzzle (raises the cost of *existing* at a chosen spot)

Bind id generation to work, S/Kademlia-style. A node id is valid only if

```
c1_ok(pubkey) := leading_zero_bits( sha256(sha256(pubkey_hex)) ) >= C1
```

The peer must grind its **keypair** (not a throwaway nonce) until its pubkey
satisfies `C1`. Because the id is `sha256(pubkey_hex)`, an attacker who wants an
id near a *specific* target must satisfy `C1` **and** hit the target prefix — the
two costs multiply. Verification is two hashes; generation is `2^C1` expected
hashes plus `2^b` for `b` bits of targeting.

- Bind it to the identity we already prove: `peer_identity_gate` verifies `C1`
  at connection setup alongside the existing key-control proof, and refuses
  DHT-routing trust to ids that fail it (they may still gossip as leaf peers).

### 3.2 Dynamic puzzle (raises the cost of *sustaining* a position)

A static puzzle is paid once. Add a periodic, epoch-bound challenge so a
long-lived eclipse must be re-paid:

```
c2_ok(pubkey, epoch) := leading_zero_bits( sha256(node_id || epoch_seed) ) >= C2
```

`epoch_seed` is a low-entropy, everyone-agrees value (e.g. a recent checkpoint /
pulse-epoch root already in the engine). Peers re-present a fresh `C2` proof each
epoch to keep full routing trust; failing it degrades a peer to reduced fan-in
near sensitive keys rather than an outright drop.

### 3.3 Disjoint-path lookups (a single neighborhood can't decide the result)

Replace the single-shortlist lookup with **`d` node-disjoint iterative lookups**
(Castro et al.): run `d` lookups in parallel whose intermediate node sets are
kept disjoint; accept a key/value only when a quorum of the `d` paths agree.
Implementation stays within the existing α-bounded state machine — it becomes `d`
state machines sharing a "already used by another path" exclusion set. Suggested
`d = 3`, quorum `2`.

## 4. Parameters (tunable, ship conservative)

| symbol | meaning | initial |
|---|---|---|
| `C1` | static id-puzzle leading-zero bits | 20 (~1M hashes to mint an id) |
| `C2` | per-epoch dynamic-puzzle bits | 12 |
| `d`  | disjoint lookup paths | 3 |
| `q`  | agreeing paths required | 2 |

`C1=20` is seconds of CPU for an honest join, but a targeted eclipse wanting `b`
bits of prefix proximity now costs `~2^(C1+b)` — turning a free attack into a
priced one. Tune from measured join times before enforcing.

## 5. Integration points

- `knitweb.p2p.kademlia`: add `id_puzzle_ok(pubkey)` / `epoch_puzzle_ok(pubkey, seed)`
  helpers next to `node_id`; add a disjoint-path variant of the iterative lookup.
- `knitweb.p2p.peer_identity_gate`: verify `C1` (and current-epoch `C2`) after the
  existing key-control proof; expose the result to routing-table admission.
- `knitweb.p2p.addrbook` / routing table: gate k-bucket admission (or trust level)
  on puzzle validity, so ground-but-unpuzzled ids don't fill a neighborhood.

## 6. Rollout / migration

1. **Advisory** — compute and log puzzle validity; change nothing. Gather honest
   join-cost and current-id-validity data.
2. **Opt-in** — a node flag enforces `C1` for *its own* routing-table admission;
   legacy ids accepted at reduced trust. Safe while the DHT is not yet the
   discovery path.
3. **Enforced** — once #68 is load-bearing, require `C1` for routing trust and
   `C2` per epoch near sensitive keys; disjoint-path lookups on by default.

Backward-compatible throughout: unpuzzled peers still connect and gossip; they
just don't get to *shape the keyspace*.

## 7. Test plan

- **Puzzle**: `id_puzzle_ok` accepts a mined pubkey at `C1`, rejects below; verify
  is O(1); a grinding-cost estimate asserts expected work scales with `C1`.
- **Epoch**: `epoch_puzzle_ok` binds to `epoch_seed` (different seed → re-proof).
- **Disjoint lookup**: property test that the `d` paths share no intermediate
  node; a simulated controlled neighborhood cannot reach quorum `q`.
- **Eclipse sim**: with `C1` enforced, the attacker hashes needed to eclipse a
  key rise ≥`2^C1`× vs. the free-grind baseline.

## 8. Decision needed

Approve (a) adopting S/Kademlia static+dynamic puzzles bound to the existing
`peer_identity_gate` identity, (b) disjoint-path lookups with `d=3,q=2`, and
(c) the conservative parameters in §4 as *advisory-first*. Implementation is
deferred until the DHT (#68) is load-bearing, per #70.

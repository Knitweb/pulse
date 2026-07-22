# Twenty features to win the user

Twenty strong features and additions, in the spirit of the shipped node work
(relay v2 → rendezvous → feed mirror → monitor → ops feed), each grounded in a
seam that already exists in this codebase — so every item is a build, not a
wish. Written 2026-07-21 against the project's own answer to *what is pulse*:

> An evolution of Bitcoin that is neither a blockchain nor an efficient
> hashgraph, but a **web with the ambition to be a field** for its
> applications. The application comes first; the token serves it. Whether a
> knowledge-graph field, a geospatial field or a visual game field — we serve
> the application with a **trust-free relay to compute and technique**.
> Utility-driven value: through the **integer** (technical) and **integere**
> (organizational-integrity) structure, demand is met fast and inexhaustible
> resources are shared node to node. EHMAC as the unique sealing layer.

The ordering follows the user's journey: the first minute, then visible
aliveness, then the fields themselves, then compute, economy, and privacy.

---

## The first minute (nothing to install, something to feel)

**1. One-tap browser node.**
A pulse node running entirely in the tab: visit the page, an identity is
minted, a relay mailbox registered, and you are a peer — in ten seconds,
no install. The molgang serverless dapp already proves "the engine in every
tab"; the relay endpoints already speak CORS.
*Wins the user because:* the distance from curiosity to being a node is one
click. — *Builds on:* `molgang serverless/web`, `RelayTransport` CORS,
`api/relay` mailboxes.

**2. QR / tap-to-peer handshake.**
Two phones exchange `relay://` + `hp://` addresses via a QR code (or BLE
bitchat when offline) and open an EHMAC-sealed private channel over the dumb
relay. *Wins:* "we just connected, direct, no account" is the demo that sells
P2P. — *Builds on:* `bluetooth_transport.py`, relay mailboxes, `HttpRendezvous`.

**3. Faucet-to-first-knit quest.**
A guided first five minutes: claim PLS from the faucet → weave your first
knit → watch it verified on another node, live on the monitor. *Wins:* the
user's first token immediately *does* something and they see the network
react. — *Builds on:* PLS/PAR faucets (#344), `monitor.html`, `FabricNode.weave`.

**4. Portable identity card.**
Export/print your `did:key` with a recovery phrase; optionally anchor it in
vBank personhood (revocable, zero-PII). *Wins:* self-custody of identity made
tangible; nothing to lose to a platform. — *Builds on:* `p2p/identity.py`,
vBank anchor/pairwise DIDs.

**5. Invite links with a queue position.**
`/api/invite` (stubbed in node.knitweb.art's `serve.py`) becomes real:
shareable links, a visible queue, and the inviter sees their invitee come
alive on the monitor. *Wins:* built-in, measurable word of mouth. —
*Builds on:* `node.knitweb.art/serve.py`, node registry.

## Visible aliveness (trust through transparency)

**6. Network weather page.**
Extend the relay monitor into network-wide "weather": relays, feeds, node
counts, and sparkline history straight from the signed ops feed. *Wins:*
a network you can *watch breathe* is a network you believe in. — *Builds
on:* `monitor.html`, ops feed (`ops/records-*.jsonl`).

**7. Verifiable uptime badges.**
Nodes earn signed uptime attestations derived from ops-feed history; an
embeddable badge links to the proof. *Wins:* operators show off, and showing
off recruits operators. — *Builds on:* ops feed heads, heartbeat chains.

**8. In-browser feed explorer with live verification.**
Browse any feed (head, shards, records) and watch `verify_head` /
`verify_entries` run in the page against the mirror. *Wins:* "don't trust,
verify" as a click instead of a slogan. — *Builds on:* feed mirror
(`/api/feed/…`), `knitweb.fabric.feed` verification.

**9. Equivocation wall of shame.**
The fork-counter design makes double-signing *provable*; publish any caught
conflict pair as a public, verifiable exhibit. *Wins:* visible teeth — users
see that cheating is not just forbidden but self-incriminating. — *Builds
on:* `check_conflict` / `check_prefix_conflict`.

## The fields (the core promise)

**10. Field SDK with three starter templates.**
"Create a field in an afternoon": knowledge-field, geo-field and game-field
starter kits — each one record schema plus weave/subscribe calls, served by
the same relay. *Wins:* builders are users who bring users. — *Builds on:*
fabric record kinds, `chemistry/schema.py`, `fabric/observation.py`,
`fabric/subscription.py`.

**11. Geospatial field beta: shared AR anchors.**
A public map of confidence-gated FieldObservations; phones drop and discover
anchors, raw captures stay in the wearer's pod. *Wins:* the first "walk
around and see the field" moment. — *Builds on:* `pulse_ar` edge stack
(#344), `SpatialAnchor`/`SpatialIndex`, geohash cells.

**12. Ask-the-graph for everyone.**
A public query box over the knowledge field: Lens interprets the question,
answers carry provenance CIDs you can expand. *Wins:* the knowledge graph
stops being a demo and starts being an answer machine with receipts. —
*Builds on:* `lens/interpret.py`, atomspace, knitweb.art 3D graph.

**13. Cheat-proof game leaderboards as feeds.**
Molgang scores woven as signed feed entries: leaderboards portable across
any UI and verifiable by anyone. *Wins:* players trust the board; builders
reuse it for free. — *Builds on:* molgang dapp, signed feeds.

**14. Field crowdfunding with a claim desk.**
Back a field's development in PLS; milestones settle through the existing
crowdfunding module with public settlement proofs. *Wins:* users become
stakeholders with receipts, not donors with hope. — *Builds on:*
`knitwebs/crowdfunding` (campaign/policy/claim-desk tests already exist).

## Trust-free relay to compute

**15. Compute bounties.**
Post a job (chemistry sim, quantum estimate) with PLS in escrow; workers
compute, a verifier quorum settles, the relay carries the frames. *Wins:*
the token's utility is literal: it buys verified computation. — *Builds on:*
`pouw/marketplace`, `escrow`, `quorum_settlement`, `verifier_reward`.

**16. Idle-grid time-sharing.**
Desktops advertise integer compute quanta in the registry; demand is matched
node-to-node over rendezvous/relay — "inexhaustible resources shared node to
node", made concrete. *Wins:* every user's idle machine becomes supply, and
supply-side users are retained users. — *Builds on:* punch/registry,
`pouw/job`, `HolePunchTransport`.

**17. Signed quantum-cost estimates as a service.**
The sha256.fail methodology as a PoUW job: request an estimate, receive a
signed, reproducible result registered on the web. *Wins:* a headline-grade
capability nobody else offers as a verifiable service. — *Builds on:*
`quantum/estimate`, `quantum/pouw_register`, sha256.fail corpus.

## Integer economy

**18. Streaming micro-settlement (pay-per-served-byte).**
Integer-only PLS debit channels where only *served* bytes settle — the
serve-budget seam finished and surfaced: seed shards, earn per verified
byte. *Wins:* hosting the network pays, so the network hosts itself. —
*Builds on:* serve-budget branch (`febuz/serve-budget-debit-served-only`),
`swarm/erasure`, `token/mint`.

## Privacy and integere structure

**19. Private pods with selective disclosure.**
A personal data vault behind pairwise DIDs: share a field observation, a
credential, a score — without linkability, zero PII on the web. *Wins:* the
privacy-conscious user finally gets P2P *and* discretion. — *Builds on:*
`pod_ref` pattern in observations, vBank scope nullifiers/pairwise DIDs,
`privacy/zerotrust`.

**20. Person-tier fairness (eIDAS-ready, no PII).**
An optional verified-person tier through the trusted-RP seam unlocks fair
allocation — faucets, votes, the 150-per-country MiCA cap — while the web
itself never sees identity data. *Wins:* fairness a bot cannot farm, in a
form a regulator can love. — *Builds on:* vBank eIDAS/EUDI verifier seam,
faucet caps (#344), MiCA dossier.

---

*Sequencing note:* items 1, 3, 6 and 8 are pure presentation over shipped
infrastructure and are the cheapest wins; 5, 7, 13 and 18 are small
completions of existing seams; the rest are field-level builds that each
deserve their own plan document before work starts.

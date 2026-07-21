# PAR Maturity Plan — Pulse AR across the Knitweb estate

How the AR line of work ("PAR": Pulse AR / GeoWeave) grows from working modules
into a mature, connected product across the Knitweb repositories and MOLGANG.
Owner framing per `docs/OWNER_DIRECTION.md` applies throughout: Knitweb is a
peer-to-peer web/fabric; PLS is activity accounting for useful work.

## The estate today

| Repo | Role | State |
|---|---|---|
| `Knitweb/pulse` | protocol engine: ledger, p2p, fabric, PoUW, edge/AR primitives, Solid seam | active, ~1830 property proofs |
| `Knitweb/weave-core` | GeoWeave core: OGC GeoPose model, canonical-JSON findings, Ed25519 `did:key`, SQLite ledger | active |
| `Knitweb/weave-node` | FastAPI observe/gossip/explore server + YOLO (onnxruntime) + map viewer | active |
| `Knitweb/weave-client-unity` | Quest 3/3S client: passthrough capture → GeoPose findings | active |
| `Knitweb/weave-client-web` | browser client: in-browser YOLO via onnxruntime-web/WebGPU | active |
| `Knitweb/molgang` | chemistry learning game; bonds are Knits, molecules are Fibers, votes are quorum verdicts | active |
| `Knitweb/vank` | vBank voting domain package | active |
| `Knitweb/knitfield` | PoUW registry + settlement policies (`knitweb-knitfield` dependency) | active |
| `Knitweb/gither` | serverless code forge / review gate | active |
| `Knitweb/monitor`, `news`, `chemfield`, `docs`, landing repos | ops + storytelling surface | active |
| `knitweb`, `lens`, `vein`, `bt`, `k.nitweb.art` | absorbed into pulse | archived |

## The four seams between the repos

1. **Identity.** GeoWeave observers are Ed25519 `did:key`; pulse accounts are
   secp256k1 `pls1` addresses; Solid pods are WebIDs. The fabric records that
   join them: `did-link` (`knitweb.geoweave.bridge`) and `webid-link`
   (`knitweb.solid.webid`) — both attested, latest beat wins, validate-at-read.
   One wearer, three names, every pair provably the same holder.
2. **Data.** GeoWeave speaks canonical JSON with floats (fine for a capture
   pipeline); pulse speaks float-free canonical CBOR (mandatory for hashing).
   The single declared crossing is `finding_to_observation`: verify the foreign
   envelope first, then re-express as a `field-observation` (confidence →
   milli-integer, lat/lon → geohash, `image_sha256` → `capture_digest`).
   Raw frames never cross; they stay device/vault-side (`knitweb.solid.pod`).
3. **Recognition targets.** YOLO labels are not knowledge. `edge/labelmap.py`
   turns woven, titled knowledge nodes into detector target tables — which is
   the MOLGANG interlock: molecules and apparatus the game weaves become the
   things a glass recognizes in a lab, and a confirmed sighting anchors back
   onto the game's own nodes.
4. **Work & settlement.** Recognition compute (server YOLO, future JEPA-style
   embedding jobs) is useful work: PoUW jobs with sampled re-execution, metered
   in PLS via `knitfield` policies. Vank supplies the non-custodial
   ask/grant/settle pattern for pod-access grants (see `/web/data.html`).

## Maturity phases

### M0 — Contract tests across repos (now)
- [x] Field observations + confirmation gate in pulse (#342)
- [x] Glass-to-glass exchange + transport e2e (#357)
- [x] Solid pod seam + webid-link + `/web/data` explainer (#364)
- [x] GeoWeave→pulse bridge + did-link + MOLGANG label maps (this PR)
- [ ] Mirror contract test in `weave-core` (envelope fixtures generated there,
      verified byte-identically by `knitweb.geoweave.bridge`) so neither repo
      can drift silently.

### M1 — One wearer end to end
- [ ] `weave-node` gains a `--pulse-bridge` sidecar: verified findings import
      into a pulse node's Web and gossip as attested observations.
- [ ] `weave-client-unity` stores frames to the wearer's pod (PodBridge
      backend with Solid-OIDC) instead of local-only; `pod_ref` flows through
      the bridge.
- [ ] Confirmation UX: pending observations surface in the headset; confirm /
      reject drives `GlassObserver`.

### M2 — Many wearers, one field
- [ ] Cell feeds: per-geohash subscription over the existing fabric feed layer;
      BitChat for buren, WebRTC/relay for the wider web.
- [ ] Reputation: forged bundles debit standing via the existing
      peer-reputation path; personhood gating for sybil-resistant curation.
- [ ] MOLGANG field trips: the game consumes confirmed lab sightings as quest
      evidence (a bond formed at a real bench, witnessed by peers' votes).

### M3 — Compute market
- [ ] Recognition/embedding inference as a PoUW job class (escrow, sampled
      re-execution, dispute) — `knitfield` policy addition.
- [ ] Vank order intents for pod-access grants and relay/curation work;
      integer PLS settlement only.

### M4 — Hardening & release
- [ ] Packaging: `pip install knitweb` (pulse) and `geoweave` published with
      pinned interop versions; CI matrix runs both repos' contract fixtures.
- [ ] Threat review: bundle floods (size caps exist), location privacy
      (geohash truncation defaults), bystander privacy (device-side blurring
      before any pod write), key rotation for all three identity kinds.
- [ ] Docs: this plan folded into `Knitweb/docs`, one folder per repo, with
      the `/web/data.html` page as the public explainer.

## Definition of mature

A wearer with a Quest 3S (or a browser) can: capture → recognize → confirm →
vault the original in their own pod → weave the digest → share it with buren
over BLE and the wider web over WebRTC → have a MOLGANG node light up as the
target → get the work metered in PLS — with every crossing verified, every
record float-free, and no operator holding frames, keys, or funds.

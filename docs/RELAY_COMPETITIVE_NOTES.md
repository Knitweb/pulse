# Relay design vs. the field — competitive notes

How the Knitweb store-and-forward relay (`deploy/5mart/api/relay/`,
`scripts/relay_server.py`, client `src/knitweb/p2p/relay.py`) compares to the
established NAT-traversal/relay designs, and which of their ideas the v2
hardening adopted. Written alongside the v2 upgrade (2026-07-20); update it
when the relay's behavior changes.

## The comparison set

| System | Model | What it does well |
|---|---|---|
| **libp2p Circuit Relay v2** | reserved circuit through a relay peer | explicit *reservations* with resource limits (duration + byte caps) and refusal semantics; relay is untrusted, payloads end-to-end encrypted; designed to be cheap enough to run everywhere |
| **TURN (RFC 8656)** | allocated UDP/TCP relay address | *allocations expire* (lifetime + refresh); per-allocation quotas; standardized error codes so clients fall back cleanly |
| **Tailscale DERP** | per-key mailbox over held HTTPS connection | push delivery over a *held connection* (no polling); home-region assignment; relay only sees pubkey→pubkey envelopes, payload is WireGuard-encrypted |
| **Nostr relays** | signed events posted to any set of relays | radical simplicity (JSON over WebSocket); strict input validation; clients multi-home across relays so one relay is never a SPOF |
| **Syncthing strelaysrv** | session relay with global pool | public pool + `strelaypoolsrv` discovery; per-session rate limits; operators self-host and join the pool |
| **BitTorrent DHT / hole punching** | rendezvous, then direct | relay is only a *rendezvous*, upgraded to a direct connection whenever possible |

## Where our design already stood

- **Dumb pipe, opaque frames** — like DERP and relay v2, the PHP relay never
  decodes payloads; signed records keep their CIDs across the hop
  (byte-identity, see `p2p/relay.py`). Relay compromise ⇒ metadata only.
- **Unguessable correlation ids** — 63-bit random `rid` as a capability
  (`_new_rid`), so mailbox writers can't spoof replies. Nostr solves the same
  class of problem with signatures; ours is cheaper for a dumb pipe.
- **Identity beyond the carrier** — optional piggybacked node-identity proof
  (#58) upgrades reputation keying from the self-asserted mailbox to a proven
  `node:<pubkey>`, mirroring how DERP keys everything on the WireGuard pubkey.
- **Federation seam** — cross-host gossip (`heartbeat.php`/`status.php` +
  `RELAY_PEER_STATUS`) is a small step toward Nostr/Syncthing-style
  multi-relay operation.
- **Hole-punch upgrade path** — `p2p/holepunch.py`, `webrtc_transport.py` and
  `dht_discovery.py` already exist client-side; like BitTorrent, the relay
  should be the fallback, not the default path.

## Gaps the v2 hardening closed (adopted ideas)

| Gap in v1 | Adopted from | v2 behavior |
|---|---|---|
| undelivered frames lived forever | TURN allocation lifetimes; relay-v2 reservation expiry | frames expire after `RELAY_FRAME_TTL` (1 h), swept on every queue touch; abandoned queue files GC'd probabilistically |
| no resource limits — any sender could fill the shared host's disk | relay-v2 limited reservations; TURN quotas | per-mailbox (`RELAY_MB_MAX_BYTES`, 32 MiB) and global (`RELAY_TOTAL_MAX_BYTES`, 512 MiB) budgets; explicit `429 mailbox full` / `429 relay full` so clients can fall back |
| `fetch` ignored the client's `wait` → 1 req/s busy-polling | DERP's held connection | bounded long-poll honoring `wait` up to `RELAY_MAX_WAIT` (8 s) — deliberately low: each waiter pins a PHP-FPM worker on shared hosting |
| any string accepted as a "frame" | Nostr's strict validation | strict base64 validation against the wire limit (8 MiB, matching `knitweb.p2p.wire.MAX_FRAME_BYTES`); 413 for oversized bodies |
| browser preflight broken (no OPTIONS handling) | — (basic hygiene) | proper CORS preflight on send/fetch |
| unauthenticated `from` polluted the node registry | — | `from` validated against the mailbox-name grammar before it touches the registry |
| limits invisible to operators | Syncthing pool status pages | `status.php` reports queue bytes + all active limits |

## Deliberately NOT adopted (and why)

- **Held connections / WebSocket push (DERP, Nostr):** impossible on shared
  PHP hosting without exhausting the FPM worker pool. The FastAPI variant
  (`scripts/relay_server.py`) is the right home for that on a real VPS.
- **Reservations as a protocol step (relay v2):** would change the client
  wire contract for little gain at current scale; byte budgets give the same
  protection without a handshake.
- **Signed frames at the relay (Nostr):** the relay stays a dumb pipe;
  authenticity lives in the carried records and the #58 identity proof.
  Verifying signatures at the relay would add CPU and trust surface for
  nothing.
- **A public relay pool (Syncthing):** premature with two hosts; the gossip
  seam (`RELAY_PEER_STATUS`) is the hook when more relays exist.

## Next steps worth taking (not in this round)

1. ~~**Direct-upgrade coordination**~~ — **DONE (second round)**: the relay
   host now serves a hole-punch rendezvous (`api/relay/punch`) and
   `HttpRendezvous` binds `HolePunchTransport` to it, so peers graduate to
   direct TCP and the mailbox becomes the fallback floor (DCUtR-style).
2. **Multi-relay client failover**: `RelayTransport` takes one `base_url`;
   Nostr-style multi-homing (try knitweb.art when 5mart.ml refuses/429s)
   is a small client change with real availability gain.
3. **Per-IP token bucket** on send: shared hosting makes real rate limiting
   awkward (no shared memory), but a coarse per-IP counter file would blunt
   the cheapest abuse.
4. **Relay self-metrics in the feed**: publish `status.php` snapshots into
   the FinField feed so relay health is itself P2P-distributed.

# 5mart.ml deploy bundle

Assembles the 5mart.ml site from the repositories' `/web` folders and the
QuantumV game, so **5mart.ml stays in sync with the repos** and forms one
connected whole with the shared hop-menu (no dead ends).

## What it serves

| Path | Source |
|---|---|
| `/`         | this bundle's `index.html` (landing) |
| `/wnw/`     | `Knitweb/pulse` → `web/` (World Narrow Web) |
| `/lens/`    | `Knitweb/lens` → `web/` (circuit library) |
| `/molgang/` | `Knitweb/molgang` → `web/` (chemistry game) |
| `/quantum/` | `Knitweb/k.nitweb.art` → `quantum/` (QuantumV) |
| `/chemfield/` | `Knitweb/chemfield` → `web/` (interactive 3D steel-slag logo) |
| `/dapp/` | `Knitweb/molgang` → `serverless/web/` (pure-P2P MOLGANG — the engine in every tab, no backend) |
| `/api/relay/` | this bundle's `api/relay/` (Knitweb p2p mailbox relay + hole-punch rendezvous) |
| `/api/feed/` | this bundle's `api/feed/` (FinField feed mirror — second HTTPS bootstrap origin) |
| `/nav.js`   | the shared cross-host menu |

## Deploy (on the 5mart.ml host)

```sh
git clone https://github.com/Knitweb/pulse && cd pulse/deploy/5mart
WEBROOT=/var/www/5mart RELOAD='sudo systemctl reload nginx' ./deploy.sh
```

The script is **idempotent, secret-free and atomic** (builds into a temp dir, then
swaps). Point nginx at `/var/www/5mart` using `nginx.conf`.

## Keep it in sync automatically

Run the deploy from cron so 5mart.ml tracks every merge:

```cron
*/15 * * * * WEBROOT=/var/www/5mart RELOAD='systemctl reload nginx' /opt/knitweb/pulse/deploy/5mart/deploy.sh >> /var/log/5mart-deploy.log 2>&1
```

## Relay API (`/api/relay/{send,fetch,health}`) — issue #337

`RelayTransport` (`src/knitweb/p2p/relay.py`) posts to
`https://5mart.ml/api/relay/send` and `/api/relay/fetch` (path-style, no
query string). `api/relay/` here mirrors the implementation live on the
5mart.ml host (endpoint-per-file + `_lib.php`, with a node registry and
cross-host gossip so a browser monitor can show the network). The bundled
`.htaccess` routes the extensionless paths to `send.php`/`fetch.php`/
`heartbeat.php` and 403s the internals (`_config.php`, `_lib.php`, `_data/`).

v2 hardening (design notes: `docs/RELAY_COMPETITIVE_NOTES.md`): undelivered
frames expire after `RELAY_FRAME_TTL` (1 h), per-mailbox and global byte
budgets refuse with an explicit 429, `fetch` honors the client's `wait` as a
bounded long-poll (capped at `RELAY_MAX_WAIT`, default 8 s — every waiter
pins a PHP worker on shared hosting), and frames are strictly
base64-validated up to the wire limit (8 MiB). All limits are overridable
via `define()` in `_config.php`.

The host is also a **hole-punch rendezvous** (`/api/relay/punch`,
`punch.php`): NAT'd listeners publish their punched endpoint
(server-observed IP + declared port, BitTorrent-tracker model; owner-pinned
per IP, 300 s TTL) and dialers resolve it to go **direct over TCP**, with
the mailbox as fallback. Client binding: `knitweb.p2p.holepunch.HttpRendezvous`.

`send` is additionally rate-limited per source IP (`RELAY_SEND_PER_MIN`,
default 120/min, fail-open; `fetch` stays unlimited so shared-IP households
are never starved).

**Live monitor** (`/api/relay/monitor.html`): the browser view of the
network the relay lib was designed for — self-contained page polling
`status.php` every 10 s (nodes, mailboxes, queue bytes, peer gossip,
active limits). Keep the host-node's heartbeat fresh by curling
`/api/relay/health` from any cron (e.g. every 5 min); each beat rolls the
host head and warms the peer-status gossip cache.

**Feed mirror** (`/api/feed/<path>`, `api/feed/index.php`): mirrors the
signed FinField feed (`head.json`, `MANIFEST.json`, record shards) from
GitHub raw with an on-disk cache (60 s for the moving heads, 600 s for
shards) and stale-while-error, so nodes have a bootstrap origin that
survives a GitHub outage. Trust-free: heads are signed and records
content-addressed — a mirror cannot forge the feed.

Two ways to serve it, depending on the host:

- **Apache + PHP (TransIP shared hosting):** the bundle works as-is. Queue
  files live in `api/relay/_data/` next to the scripts; the publish step
  excludes that directory from `rsync --delete` so state survives redeploys.
  ⚠️ The live 5mart.ml webroot is managed by selective SFTP uploads — never
  point this script's `rsync --delete` at it without checking what else
  lives there.
- **nginx (no PHP):** run the FastAPI equivalent instead and proxy to it —
  `uvicorn scripts.relay_server:app --host 127.0.0.1 --port 8765` plus the
  `location /api/relay/` block in `nginx.conf` (shipped commented; enable it).

Smoke test after deploying:

```sh
curl -s https://5mart.ml/api/relay/health
curl -s -X POST https://5mart.ml/api/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","rid":1,"frame":"aGVsbG8="}'
curl -s -X POST https://5mart.ml/api/relay/fetch \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","wait":1}'   # → {"messages":[{"rid":1,"frame":"aGVsbG8="}]}
```

## Notes

- No secrets are read or written; all sources are public repos over HTTPS.
- The shared menu links every property to the same canonical URLs, so hopping
  works identically here, on knitweb.art, and in the repo `/web` folders.
- `robots.txt` + a generated `sitemap.xml` (optional) aid discovery.

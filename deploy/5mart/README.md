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
| `/api/relay/` | this bundle's `api/relay/relay.php` (Knitweb p2p mailbox relay) |
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
query string). `deploy.sh` publishes `api/relay/` into the webroot so those
endpoints resolve; `relay.php` accepts both `?action=send` and the path-style
`/api/relay/send` form, and answers `GET /api/relay/health` for liveness.

Two ways to serve it, depending on the host:

- **Apache + PHP (TransIP shared hosting):** nothing else needed — the
  bundled `api/relay/.htaccess` rewrites `/api/relay/{send,fetch,health}` to
  `relay.php` and blocks direct access to the `_mailboxes/` queue files.
- **nginx (no PHP):** run the FastAPI equivalent instead and proxy to it —
  `uvicorn scripts.relay_server:app --host 127.0.0.1 --port 8765` plus the
  `location /api/relay/` block in `nginx.conf` (shipped commented; enable it).

Mailbox queues live in `api/relay/_mailboxes/` next to the script; the
publish step excludes that directory from `rsync --delete` so queued frames
survive redeploys.

Smoke test after deploying:

```sh
curl -s https://5mart.ml/api/relay/health
curl -s -X POST https://5mart.ml/api/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","rid":1,"frame":"aGVsbG8="}'
curl -s -X POST https://5mart.ml/api/relay/fetch \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","wait":1}'   # → {"messages":[{"frame":"aGVsbG8="}]}
```

## Notes

- No secrets are read or written; all sources are public repos over HTTPS.
- The shared menu links every property to the same canonical URLs, so hopping
  works identically here, on knitweb.art, and in the repo `/web` folders.
- `robots.txt` + a generated `sitemap.xml` (optional) aid discovery.

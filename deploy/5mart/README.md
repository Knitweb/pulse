# 5mart.ml relay deployment

Fixes [#337](https://github.com/Knitweb/pulse/issues/337): `RelayTransport`
(`src/knitweb/p2p/relay.py`) talks to `POST https://5mart.ml/api/relay/{send,fetch}`,
but nothing was published under that path — NAT'd nodes got a 404/Apache
error page and silently fell back to HTTPS feed bootstrap, so live
feed-head announce over the relay was blocked.

5mart.ml is TransIP **shared** hosting (Apache + PHP 8.1, no persistent
process, no reverse proxy control) — see the hosting notes in
`docs/p2p.md` and the sibling static-site deploy at
`sha-fail-akash-hosting/fallback-5mart/deploy_to_5mart.py`. That rules out
running `uvicorn` continuously; the relay is implemented as plain PHP
instead, matching what `relay.py`'s docstring already calls "the live PHP
relay on 5mart.ml".

## Layout

```
relay/
  _common.php   shared JSON I/O, mailbox validation, TTL sweep
  send.php      POST api/relay/send  — queue one frame
  fetch.php     POST api/relay/fetch — long-poll drain a mailbox
  health.php    GET  api/relay/health — liveness probe
  .htaccess     routes extensionless /api/relay/{send,fetch,health} to .php
```

Queued frames are stored one-file-per-message under
`WEBROOT/../relay_queues/<mailbox>/`, **outside** the web docroot, so a
queued frame can never be fetched by guessing a static URL. Each mailbox is
swept for messages older than `RELAY_MESSAGE_TTL_SECONDS` (1h) on every
touch — an abandoned mailbox self-cleans instead of growing forever on a
disk-quota'd shared host.

## Wire contract (must match `src/knitweb/p2p/relay.py`)

- `POST api/relay/send` — `{"mailbox": str, "rid": int, "frame": base64}` →
  `{"ok": true}` / `{"ok": false, "error": str}`
- `POST api/relay/fetch` — `{"mailbox": str, "wait": int}` →
  `{"messages": [{"frame": base64}, ...]}`
- `GET api/relay/health` — `{"ok": true, "service": "knitweb-relay", "time": ...}`

The relay never decodes the frame payload (dumb pipe, see the `relay.py`
module docstring); PHP only validates base64-ness and an 8 MiB size cap
(`knitweb.p2p.wire.MAX_FRAME_BYTES`).

## Deploying

Requires SFTP credentials for the TransIP host (not stored in this repo):

```bash
export FIVEMART_HOST=5martm.ssh.transip.me
export FIVEMART_USER=5martml
export FIVEMART_PASS='...'          # rotate after use; never commit
pip install --user paramiko          # if not already present
python3 deploy/5mart/deploy_relay_to_5mart.py
```

Then verify:

```bash
curl -s https://5mart.ml/api/relay/health
curl -s -X POST https://5mart.ml/api/relay/send \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","rid":1,"frame":"aGVsbG8="}'
curl -s -X POST https://5mart.ml/api/relay/fetch \
  -H 'Content-Type: application/json' \
  -d '{"mailbox":"smoketest","wait":1}'
```

`fetch` should echo back `{"messages":[{"frame":"aGVsbG8="}]}`.

**This deploy step has not been run yet** — it requires the TransIP
credentials, which are not present in the environment that authored this
fix. Whoever holds `FIVEMART_PASS` needs to run the script above once to
make the fix live; the code fix (this PR) and the live deployment are
tracked separately for that reason.

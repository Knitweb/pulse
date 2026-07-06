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

## Notes

- No secrets are read or written; all sources are public repos over HTTPS.
- The shared menu links every property to the same canonical URLs, so hopping
  works identically here, on knitweb.art, and in the repo `/web` folders.
- `robots.txt` + a generated `sitemap.xml` (optional) aid discovery.

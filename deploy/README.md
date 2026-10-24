# Deploying

`docker-compose.yml` in the repo root is a **dev** convenience (`--reload`, mounted
source, Vite dev server). It is not what you want on a server. This directory is.

The shape: nginx serves the built bundle and reverse-proxies the API and WebSocket from
the same origin; uvicorn runs on `127.0.0.1:8000` under systemd; the optional
SmartSpectra sidecar runs on `127.0.0.1:3001`.

## First run

```bash
# the units and nginx vhost hardcode this path
sudo mv ~/git/emotional-damage /srv/emotional-damage
cd /srv/emotional-damage

cd backend  && python3 -m venv .venv && .venv/bin/pip install -e . && cd ..
cd frontend && npm ci && npm run build && cd ..

sudo ./deploy/install.sh your.domain
sudo certbot --nginx -d your.domain
```

Then add your keys to `/etc/emotional-damage/backend.env` and
`systemctl restart ed-backend`.

`GET /api/health` is the one-curl answer to "did my keys land": it reports the active
processor, `voice.enabled` / `voice.speaks`, queue depth and frames dropped.

## Redeploying

```bash
cd /srv/emotional-damage && git pull
cd frontend && npm ci && npm run build        # static files, no restart needed
sudo systemctl restart ed-backend             # only if backend/ changed
sudo ./deploy/install.sh your.domain          # only if deploy/ changed
```

## Four constraints this layout exists to satisfy

**HTTPS is mandatory.** `getUserMedia` requires a secure context. Over plain HTTP on
anything but `localhost` the camera fails silently — no frames, no scoring, usually no
visible error. Run certbot. See "No domain yet" below if you only have an IP.

**One backend worker.** Rooms, players and scores live in process memory behind a
per-room `asyncio.Lock`. `--workers 2` is two separate game worlds. Scaling out means
implementing `app/game/store.py` on Redis first.

**One origin.** The client defaults to a relative `/api` and derives its WebSocket URL
from `location.host`, so routing everything through one vhost means no `VITE_*` vars at
build time and no CORS.

**Don't serve out of `/root`.** It's mode 0700 and nginx runs as `www-data`, so every
static file 403s. Hence `/srv`.

## Backend-only mode (no nginx)

If the box hosts just the API and the UI runs from a dev server elsewhere, skip nginx
and certbot entirely:

```bash
sudo systemctl disable --now nginx
sudo mkdir -p /etc/systemd/system/ed-backend.service.d
sudo cp deploy/direct-bind.conf /etc/systemd/system/ed-backend.service.d/
sudo systemctl daemon-reload && sudo systemctl restart ed-backend
```

Open TCP 8000 instead of 80/443, set
`CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]` in
`/etc/emotional-damage/backend.env`, and run the frontend against it:

```bash
cd frontend && BACKEND_URL=http://<ip>:8000 npm run dev
```

No TLS is needed here, and that is not a shortcut: `vite.config.ts` proxies `/api` and
`/ws` server-side, so the browser only ever talks to `http://localhost:5173` — which is
a secure context, so the camera works. The HTTPS requirement comes back the moment you
serve the page itself from this host.

## No domain yet

Let's Encrypt will not issue for a bare IP, so point a free wildcard-DNS hostname at it
instead. `nip.io` and `sslip.io` resolve `<any-ip>.<domain>` straight to that IP with no
signup, and certbot treats the result like any other name:

```bash
sudo ./deploy/install.sh 203.0.113.9.nip.io
sudo certbot --nginx -d 203.0.113.9.nip.io
```

Port 80 has to be reachable from the internet for the HTTP-01 challenge to land.

If Let's Encrypt refuses those hostnames (they are shared and occasionally
rate-limited), the fallbacks, in order of how well they hold up in front of real
players:

1. **A free subdomain** from DuckDNS or similar, then certbot as above. Stable, and it
   survives an IP change.
2. **A Cloudflare quick tunnel** — `cloudflared tunnel --url http://localhost:80` prints
   a `https://*.trycloudflare.com` URL with a valid certificate. Works without touching
   DNS, and because the client derives its API and WebSocket URLs from
   `location.host`, no rebuild is needed. The URL changes every restart.
3. **A self-signed certificate.** The origin still counts as secure once each player
   clicks through the interstitial, which is a bad thing to ask a room full of people
   to do, but it does work.

`--unsafely-treat-insecure-origin-as-secure=http://<ip>` also works, but only for
browsers you launch yourself, so it is no use for players on their own phones.

## SmartSpectra sidecar (optional)

Vite inlines `VITE_*` at build time, so this has to happen **before** `npm run build`:

```bash
echo 'VITE_SPECTRA_WS_URL=wss://your.domain/spectra' >> frontend/.env
cd frontend && npm run build
```

Then put the key in `/etc/emotional-damage/spectra.env` and
`sudo systemctl enable --now ed-spectra`. `WEB_ORIGIN` must equal the page origin
exactly — no trailing slash — or `verifyClient` 403s every connection.

## Before you point real users at it

`player_id` is not authentication. It's an opaque id handed out at join and passed back
as a form field, so on a public domain anyone with a room code and an id can act as
another player. Fine for a demo; add real auth before anything else.

Rooms are destroyed when they empty — immediately when the last player calls `/leave`,
or `EMPTY_ROOM_GRACE_SECONDS` (60) after the last socket drops. Expect rooms to
disappear while you're testing alone with the tab closed.

## Logs

```bash
journalctl -u ed-backend -f
tail -f /var/log/nginx/emotional-damage.error.log
```

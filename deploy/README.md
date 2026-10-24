# Deploying

One box serves everything from one HTTPS origin: nginx hands out the built frontend
and proxies `/api`, `/ws` and `/spectra` to the services behind it. Players just open
the URL. `docker-compose.yml` in the repo root is a local dev loop, not this.

| Unit                 | Listens on       | Reached as              |
| -------------------- | ---------------- | ----------------------- |
| `nginx`              | `:80`, `:443`    | `https://<domain>/`     |
| `ed-backend.service` | `127.0.0.1:8000` | `/api/`, `/ws/`         |
| `ed-spectra.service` | `:3001`          | `/spectra/` (optional)  |

The live box is `https://95.179.200.43.nip.io`.

## First run

```bash
# the units and vhost hardcode this path; /root is 0700 and nginx would 403 every file
sudo mv ~/git/emotional-damage /srv/emotional-damage
sudo apt install -y nginx certbot python3-certbot-nginx

cd /srv/emotional-damage/backend
python3 -m venv .venv && .venv/bin/pip install -e .

cd ../frontend && npm ci
# Vite inlines VITE_* at build time. Only needed for the SmartSpectra sidecar; the
# API and game socket derive their URLs from location.host.
VITE_SPECTRA_WS_URL=wss://<domain>/spectra/ npm run build

sudo useradd --system --no-create-home --shell /usr/sbin/nologin edgame
sudo install -d -m 0750 -o root -g edgame /etc/emotional-damage
sudo tee /etc/emotional-damage/backend.env >/dev/null <<'ENV'
# dummy  = label from the frame's SHA-256, ignores the actual face (no key needed)
# gemini = real vision classification (needs GEMINI_API_KEY)
PROCESSOR=gemini
GEMINI_API_KEY=
ELEVENLABS_API_KEY=       # absent -> narration is text, no audio
MEDIA_DIR=/var/lib/emotional-damage/media
ENV
sudo tee /etc/emotional-damage/spectra.env >/dev/null <<'ENV'
SMARTSPECTRA_API_KEY=
# Exact match against the browser's Origin header. No trailing slash.
WEB_ORIGIN=https://<domain>
PORT=3001
ENV
sudo chmod 0640 /etc/emotional-damage/*.env

sudo install -m 0644 /srv/emotional-damage/deploy/ed-*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ed-backend ed-spectra

sed 's|__DOMAIN__|<domain>|g' /srv/emotional-damage/deploy/nginx.conf \
  | sudo tee /etc/nginx/sites-available/emotional-damage >/dev/null
sudo ln -sfn /etc/nginx/sites-available/emotional-damage /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl enable --now nginx
sudo certbot --nginx -d <domain> --redirect
```

Write env files as `KEY=value`: no spaces around `=`, no quotes.

Ports 80 and 443 have to be open in both `ufw` on the box and the Vultr firewall
(Products -> instance -> Firewall). Port 80 is needed even after TLS is up, for
certbot's renewal challenge. Don't open 8000 or 3001; nginx is the only way in.

## No domain

Let's Encrypt will not issue for a bare IP. `nip.io` and `sslip.io` resolve
`<ip>.nip.io` straight to that IP with no signup, and certbot treats the result like any
other name, so use `<ip>.nip.io` as `<domain>` above. If Let's Encrypt refuses it (the
names are shared and occasionally rate-limited), a free DuckDNS subdomain works the
same way and survives an IP change.

## Check it

```bash
curl -sS https://<domain>/api/health | python3 -m json.tool
```

`/api/health` is the one-call answer to "did my keys land". It reports the live
processor, `voice.enabled` / `voice.speaks`, queue depth and frames dropped. It only
shows that keys are *set*, so a revoked key still reads as enabled. The journal shows
the provider's error on the first real call.

## Redeploying

```bash
cd /srv/emotional-damage && git pull
cd backend && .venv/bin/pip install -e . && cd ..                 # if deps changed
cd frontend && npm ci && VITE_SPECTRA_WS_URL=wss://<domain>/spectra/ npm run build && cd ..
sudo systemctl restart ed-backend ed-spectra
```

nginx serves `frontend/dist` straight off disk, so a rebuild needs no reload. A backend
restart drops every room in progress.

## Constraints worth knowing

**The camera needs HTTPS.** `getUserMedia` requires a secure context. Over plain HTTP
on anything but `localhost` the camera fails silently: the page renders, but no frames,
no scoring and no obvious error.

**One worker.** Rooms, players and scores live in process memory behind a per-room
`asyncio.Lock`. `--workers 2` is two independent game worlds. Scaling out means
implementing `app/game/store.py` on Redis first.

**`player_id` is not authentication.** It's an opaque id handed out at join and passed
back as a form field, so anyone with the URL can create rooms and act as another
player. Fine for a demo box; don't leave it up unattended.

Also: rooms are destroyed when they empty, immediately when the last player calls
`/leave`, or `EMPTY_ROOM_GRACE_SECONDS` (60) after the last socket drops. Expect rooms
to vanish while testing alone with the tab closed.

## Local frontend against the box

To hack on the UI against the live backend, skip the build:

```bash
cd frontend && BACKEND_URL=https://<domain> npm run dev
```

`vite.config.ts` proxies `/api` and `/ws` there, and the browser stays on
`http://localhost:5173`, which counts as a secure context for the camera.

## Logs

```bash
journalctl -u ed-backend -f
journalctl -u ed-spectra -f
tail -f /var/log/nginx/emotional-damage.error.log
```

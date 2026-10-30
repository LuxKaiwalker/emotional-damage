# Deploying

One box serves everything from one HTTPS origin: nginx hands out the built frontend
and proxies `/api`, `/ws` and `/spectra` to the services behind it. Players just open
the URL. `docker-compose.yml` in the repo root is a local dev loop, not this.

| Unit                 | Listens on       | Reached as              |
| -------------------- | ---------------- | ----------------------- |
| `nginx`              | `:80`, `:443`    | `https://<domain>/`     |
| `ed-backend.service` | `127.0.0.1:8000` | `/api/`, `/ws/`         |
| `ed-spectra.service` | `:3001`          | `/spectra/` (optional)  |

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
# dummy   = label from the frame's SHA-256, ignores the actual face (no key needed)
# gemini  = real vision classification (needs GEMINI_API_KEY)
# presage = Presage's expression read, pushed by ed-spectra (needs the token below)
PROCESSOR=presage
# Same value in spectra.env; generate with `openssl rand -hex 32`.
PRESAGE_INGEST_TOKEN=
GEMINI_API_KEY=           # absent -> narration speaks the prompt as written
ELEVENLABS_API_KEY=       # absent -> narration is text, no audio
MEDIA_DIR=/var/lib/emotional-damage/media
ENV
sudo tee /etc/emotional-damage/spectra.env >/dev/null <<'ENV'
SMARTSPECTRA_API_KEY=
# Exact match against the browser's Origin header. No trailing slash.
WEB_ORIGIN=https://<domain>
PORT=3001
# Presage blocks this box's IP; see "Presage and the proxy" below.
HTTPS_PROXY=socks5h://127.0.0.1:1080
# Where expression readings go, and the token backend.env expects.
BACKEND_URL=http://127.0.0.1:8000
PRESAGE_INGEST_TOKEN=
# Each player costs one Presage session (~1/3 core, ~0.5 GB) for expressions, plus one
# more for vitals unless this is off. A 1 vCPU / 4 GB box fits two or three players.
SPECTRA_VITALS=off
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

## Moving to a different domain

Nothing in the application code knows the hostname: the client derives `/api` and
`wss://<host>/ws` from `location.host`. So a move is four pieces of config, two of which
fail *silently* if you forget them.

Point an A record at the box, wait for it to resolve, then:

```bash
cd /srv/emotional-damage
sed 's|__DOMAIN__|<new>|g' deploy/nginx.conf \
  | sudo tee /etc/nginx/sites-available/emotional-damage >/dev/null
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <new> --redirect

sudo sed -i 's|^WEB_ORIGIN=.*|WEB_ORIGIN=https://<new>|' /etc/emotional-damage/spectra.env
sudo systemctl restart ed-spectra

cd frontend && VITE_SPECTRA_WS_URL=wss://<new>/spectra/ npm run build
```

The two silent ones: `server.js` compares the browser's `Origin` header to `WEB_ORIGIN`
with `===`, so a stale value 403s every sidecar connection; and Vite inlines
`VITE_SPECTRA_WS_URL` at build time, so an un-rebuilt bundle still dials the old host.
Either way the page loads and plays perfectly while **nothing ever scores**, because
`PROCESSOR=presage` gets its labels from that sidecar. `/api/health` is the tell:
`presage.players_reading` stays at 0 with a camera open.

Note the vhost claims one `server_name`, and `WEB_ORIGIN` is a single exact string, so
the old hostname stops working when you switch. Serving two names at once needs the
sidecar taught to accept a list.

**Behind Cloudflare, use "DNS only" (grey cloud).** Proxied, the HTTP-01 challenge never
reaches the box, an origin cert for the old name gives 526, an unreachable origin gives
521, and the edge puts an idle timeout in front of the game socket.

## No domain

Let's Encrypt will not issue for a bare IP. `nip.io` and `sslip.io` resolve
`<ip>.nip.io` straight to that IP with no signup, and certbot treats the result like any
other name, so use `<ip>.nip.io` as `<domain>` above. If Let's Encrypt refuses it (the
names are shared and occasionally rate-limited), a free DuckDNS subdomain works the
same way and survives an IP change.

## Presage and the proxy

Presage's API (`cont-api.physiology.presagetech.com`) refuses this box at its load
balancer: every request, keyed or not, gets a bare `403 Forbidden` HTML page from
`awselb/2.0`, while the same request from a home connection reaches the API. The key
is never even checked. Without a way out, the SDK stops the session before it starts
and the browser shows "Vitals unavailable: Presage did not authorize this session."

The SDK uses an embedded libcurl that honours `HTTPS_PROXY`, so its traffic can leave
through a machine Presage doesn't block. From that machine, open a reverse SOCKS
tunnel to this box:

```bash
ssh -N -R 1080 root@<this box>     # OpenSSH 7.6+, including Windows' built-in client
```

That listens on this box's loopback only, which is what `spectra.env` points at. No
inbound port is opened on either side. To check the route, run this on the box (403 =
blocked, 405 = reached the API):

```bash
curl -sI --proxy socks5h://127.0.0.1:1080 https://cont-api.physiology.presagetech.com/ | head -1
```

**Every score depends on this tunnel.** Opened by hand from a laptop, it dies whenever
the laptop sleeps or changes networks, and every game in that window scores nothing:
the sidecar logs `COULDNT_CONNECT ... port 1080` (tunnel gone) or `OPERATION_TIMEDOUT`
(tunnel too slow; Presage calls time out after 3 s). The sidecar retries a refused
session with backoff, so players recover once the tunnel is back, but nothing scores
until then. The real fix is Presage allowlisting this box's IP; once they do, delete
`HTTPS_PROXY` from `spectra.env` and restart `ed-spectra`.

### Always-on tunnel

Run `ed-tunnel.service` under `autossh` on a machine that stays on. It needs a key,
since a unit cannot type a password. On that machine:

```bash
sudo pacman -S autossh            # or: sudo apt install -y autossh
sudo install -d -m 0700 /etc/ed-tunnel
sudo ssh-keygen -t ed25519 -N '' -C ed-tunnel -f /etc/ed-tunnel/id_ed25519
sudo cat /etc/ed-tunnel/id_ed25519.pub
sed 's|__VPS__|<this box>|' deploy/ed-tunnel.service | sudo tee /etc/systemd/system/ed-tunnel.service >/dev/null
```

On this box, authorize that key for the tunnel and nothing else, and make sshd drop a
dead tunnel quickly. Without the keepalive, a tunnel whose far end vanished keeps
holding 1080 for hours and every reconnect is refused the forward:

```bash
# restrict alone still runs any command sent with the key; the forced command stops
# that, and `ssh -N` never asks for one, so the tunnel is unaffected.
echo 'restrict,port-forwarding,permitlisten="127.0.0.1:1080",command="/usr/sbin/nologin" <the .pub line>' \
  | sudo tee -a /root/.ssh/authorized_keys
sudo install -m 0644 deploy/sshd-tunnel-keepalive.conf /etc/ssh/sshd_config.d/50-tunnel-keepalive.conf
sudo sshd -t && sudo systemctl reload ssh
```

Then `sudo systemctl enable --now ed-tunnel` on the always-on machine, and run the
`curl` check above. Keepalives catch a dead link, not a slow one: if the curl takes
seconds, that machine's uplink is the problem.

## How PROCESSOR=presage works

The browser streams its camera to `ed-spectra` (wss://<domain>/spectra/), naming its room
and player. The sidecar forks one process per Presage session (`session.js`): SDK state
is process-global, so sessions cannot share a process. Each expression reading is POSTed
to the backend at `/internal/presage/expressions` over loopback; nginx does not proxy
that path. A frame upload is then judged by that player's newest reading, at most
`PRESAGE_MAX_AGE_MS` (1500) old. `/api/health` shows `presage.players_reading`: 0
mid-game means the sidecar is not getting through, and every frame scores "none".

`session.js` works around three SDK behaviours that otherwise kill sessions within
seconds on this box. It calls `sendFrame` off the JS thread, because a synchronous call
deadlocks against the SDK's callbacks. It copies each frame into stable memory. And it
feeds expressions on a steady 30 fps clock, because Presage abandons sessions running
much below camera rate. A wedged session is still caught by a heartbeat watchdog and
replaced.

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

# Deploying the backend

This box runs the API and nothing else. Players run the frontend from a dev server on
their own machine, pointed here. `docker-compose.yml` in the repo root is a local dev
loop, not this.

One systemd unit, one open port.

## First run

```bash
# the unit hardcodes this path
sudo mv ~/git/emotional-damage /srv/emotional-damage
cd /srv/emotional-damage/backend
python3 -m venv .venv && .venv/bin/pip install -e .

sudo useradd --system --no-create-home --shell /usr/sbin/nologin edgame
sudo install -d -m 0750 -o root -g edgame /etc/emotional-damage
sudo tee /etc/emotional-damage/backend.env >/dev/null <<'ENV'
# dummy  = label from the frame's SHA-256, ignores the actual face (no key needed)
# gemini = real vision classification (needs GEMINI_API_KEY)
PROCESSOR=dummy
# GEMINI_API_KEY=
# ELEVENLABS_API_KEY=       # absent -> narration is text, no audio
MEDIA_DIR=/var/lib/emotional-damage/media
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
ENV
sudo chmod 0640 /etc/emotional-damage/backend.env

sudo install -m 0644 /srv/emotional-damage/deploy/ed-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ed-backend
```

Then open TCP 8000 to the internet. On a Vultr box that lives in the control panel
(Products -> instance -> Firewall), not in `nft`/`ufw` on the machine, so a clean local
ruleset is not evidence the port is open.

`backend/.env.example` documents every other knob; env vars in `backend.env` win over it.

## Check it

```bash
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool   # on the box
curl -sS --max-time 5 http://<ip>:8000/api/health                  # from elsewhere
```

Use `127.0.0.1`, not `localhost`: uvicorn binds IPv4 and `localhost` resolves to `::1`
first on Debian. `/api/health` is the one-call answer to "did my keys land" — it reports
the live processor, `voice.enabled` / `voice.speaks`, queue depth and frames dropped.

## Run the frontend against it

```bash
cd frontend && BACKEND_URL=http://<ip>:8000 npm run dev
```

`vite.config.ts` proxies `/api` and `/ws` there, server-side.

## Redeploying

```bash
cd /srv/emotional-damage && git pull
cd backend && .venv/bin/pip install -e . && cd ..   # only if dependencies changed
sudo systemctl restart ed-backend
```

## Three constraints worth knowing

**The camera needs HTTPS.** `getUserMedia` requires a secure context, so this layout
works *because* the browser only ever talks to `http://localhost:5173` — localhost
qualifies, and the vite proxy does the remote hop server-side. Serve the page itself
from this box over plain HTTP and the camera fails silently: page renders, no frames, no
scoring, no obvious error. Doing that properly means a reverse proxy and a certificate;
the nginx vhost and installer for it are in git history at `27435d9`
(`git show 27435d9 -- deploy/nginx.conf`).

**One worker.** Rooms, players and scores live in process memory behind a per-room
`asyncio.Lock`. `--workers 2` is two independent game worlds. Scaling out means
implementing `app/game/store.py` on Redis first.

**`player_id` is not authentication.** It's an opaque id handed out at join and passed
back as a form field, so anyone who can reach the open port can create rooms and act as
another player. Fine for a demo box; don't leave it up unattended.

Also: rooms are destroyed when they empty — immediately when the last player calls
`/leave`, or `EMPTY_ROOM_GRACE_SECONDS` (60) after the last socket drops. Expect rooms
to vanish while testing alone with the tab closed.

## Logs

```bash
journalctl -u ed-backend -f
```

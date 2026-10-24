#!/usr/bin/env bash
# Install emotional-damage as systemd services behind nginx. Idempotent: safe to re-run
# after a `git pull` to pick up changed unit files.
#
#   sudo ./deploy/install.sh your.domain
#
# Expects the checkout at /srv/emotional-damage, backend/.venv built, and
# frontend/dist built. Secrets are NOT written here -- see /etc/emotional-damage.

set -euo pipefail

DOMAIN="${1:-}"
ROOT=/srv/emotional-damage
ETC=/etc/emotional-damage
USER_NAME=edgame

if [[ -z "$DOMAIN" ]]; then
    echo "usage: sudo $0 <domain>" >&2
    exit 64
fi
if [[ $EUID -ne 0 ]]; then
    echo "must run as root" >&2
    exit 1
fi

# --- preflight: fail here rather than halfway through -------------------------
for path in "$ROOT/backend/.venv/bin/python" "$ROOT/frontend/dist/index.html"; do
    if [[ ! -e "$path" ]]; then
        echo "missing $path -- build it before installing (see deploy/README.md)" >&2
        exit 1
    fi
done

# nginx's Debian-style layout is where the vhost goes; its absence means nginx
# itself is missing, which is a clearer thing to say than a failed redirect.
if [[ ! -d /etc/nginx/sites-available ]]; then
    echo "no /etc/nginx/sites-available -- install nginx first:" >&2
    echo "    apt install -y nginx certbot python3-certbot-nginx" >&2
    exit 1
fi
if ! command -v certbot &>/dev/null; then
    echo "warning: certbot not installed. Without TLS, getUserMedia has no secure" >&2
    echo "context and the camera fails silently. apt install -y certbot python3-certbot-nginx" >&2
fi

# --- service account ----------------------------------------------------------
if ! id "$USER_NAME" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$USER_NAME"
    echo "created user $USER_NAME"
fi

# --- secrets: templates only, never overwritten -------------------------------
install -d -m 0750 "$ETC"

if [[ ! -f "$ETC/backend.env" ]]; then
    cat > "$ETC/backend.env" <<ENVEOF
# Secrets and prod overrides for ed-backend.service. Defaults live in app/config.py;
# backend/.env.example documents every knob. Env vars win over backend/.env.

# dummy  = label from the frame's SHA-256, ignores the actual face (no key needed)
# gemini = real vision classification (needs GEMINI_API_KEY)
PROCESSOR=dummy

# Absent keys disable the feature that needs them rather than failing requests:
#   no GEMINI_API_KEY     -> prompt text is spoken as written
#   no ELEVENLABS_API_KEY -> narration is published as text, no audio
# GEMINI_API_KEY=
# ELEVENLABS_API_KEY=

# systemd's StateDirectory owns this path.
MEDIA_DIR=/var/lib/emotional-damage/media

# Parsed as JSON. Moot while nginx keeps everything same-origin, but correct.
CORS_ORIGINS=["https://$DOMAIN"]
ENVEOF
    chmod 0640 "$ETC/backend.env"
    echo "wrote $ETC/backend.env -- add your API keys"
fi

if [[ ! -f "$ETC/spectra.env" ]]; then
    cat > "$ETC/spectra.env" <<ENVEOF
# Secrets for ed-spectra.service (optional; leave the service disabled if unused).
# server.js throws on boot without the key.
SMARTSPECTRA_API_KEY=

# Exact string match against the browser's Origin header. No trailing slash, or
# every connection is refused with 403 -- including from localhost.
WEB_ORIGIN=https://$DOMAIN
PORT=3001
ENVEOF
    chmod 0640 "$ETC/spectra.env"
    echo "wrote $ETC/spectra.env -- add your API key if you want vitals"
fi

chown -R root:"$USER_NAME" "$ETC"

# --- units --------------------------------------------------------------------
install -m 0644 "$ROOT/deploy/ed-backend.service" /etc/systemd/system/
install -m 0644 "$ROOT/deploy/ed-spectra.service" /etc/systemd/system/
systemctl daemon-reload

# --- nginx --------------------------------------------------------------------
sed "s|__DOMAIN__|$DOMAIN|g" "$ROOT/deploy/nginx.conf" \
    > /etc/nginx/sites-available/emotional-damage
ln -sfn /etc/nginx/sites-available/emotional-damage \
        /etc/nginx/sites-enabled/emotional-damage
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# --- go -----------------------------------------------------------------------
# The sidecar is deliberately not enabled: it needs a key, and the frontend must be
# rebuilt with VITE_SPECTRA_WS_URL before the browser will reach it.
systemctl enable --now ed-backend.service
systemctl --no-pager --lines=0 status ed-backend.service || true

cat <<DONE

installed. next:
  1. add keys to $ETC/backend.env, then: systemctl restart ed-backend
  2. certbot --nginx -d $DOMAIN      # camera will NOT work without this
  3. curl -s https://$DOMAIN/api/health | python3 -m json.tool
DONE

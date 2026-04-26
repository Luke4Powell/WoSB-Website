# WoSB LXC Deployment Runbook (Current Live Setup)

This is the operational runbook for the live WoSB site hosted in a Proxmox LXC and published through Cloudflare Tunnel.

Use this file for maintenance, updates, and recovery.

## !!! DAILY USE: DEPLOY LATEST WEBSITE UPDATE !!!

After you push code changes to GitHub, run this on the LXC server:

```bash
bash /opt/wosb/WoSB-Website/scripts/deploy-live.sh
```

Success looks like:

- `wosb.service` = `active (running)`
- `nginx` config test = `syntax is ok`
- `cloudflared.service` = `active (running)`
- final line: `[wosb] Done.`

If deploy fails, run:

```bash
systemctl status wosb --no-pager
journalctl -u wosb -n 80 --no-pager
```

## 1) Current architecture

- Hosting: Proxmox LXC (Ubuntu)
- App: FastAPI/Uvicorn (`wosb` systemd service)
- Reverse proxy: Nginx (`nginx` systemd service)
- Public ingress: Cloudflare Tunnel (`cloudflared` systemd service)
- Domain: `spanishfactionwosb.org`

Traffic path:

`Browser -> Cloudflare -> cloudflared tunnel -> Nginx (127.0.0.1:80) -> Uvicorn (127.0.0.1:8000)`

## 2) Important paths

- App repo: `/opt/wosb/WoSB-Website`
- App env file: `/opt/wosb/WoSB-Website/.env`
- Systemd service file: `/etc/systemd/system/wosb.service`
- Nginx site: `/etc/nginx/sites-available/wosb`
- Cloudflared config: `/etc/cloudflared/config.yml`
- Cloudflared credentials: `/root/.cloudflared/<tunnel-uuid>.json`

## 3) Service status and logs

Check service status:

```bash
systemctl status wosb --no-pager
systemctl status nginx --no-pager
systemctl status cloudflared --no-pager
```

Tail logs:

```bash
journalctl -u wosb -f
journalctl -u nginx -f
journalctl -u cloudflared -f
```

## 4) Normal deploy/update workflow

1. Make code changes on development machine.
2. Commit and push to GitHub.
3. Run one-command live deploy on server:

```bash
cd /opt/wosb/WoSB-Website
bash ./scripts/deploy-live.sh
```

This script:

- fast-forwards to latest `origin/main`
- installs dependency updates
- validates local-only config drift (`.env` keys vs `.env.example`)
- validates `SITE_BACKGROUND_IMAGE` file path (if set)
- restarts `wosb`, reloads `nginx`, and prints service statuses

Manual equivalent:

```bash
cd /opt/wosb/WoSB-Website
sudo -u www-data git fetch origin
sudo -u www-data git pull --ff-only
/opt/wosb/WoSB-Website/.venv/bin/pip install -r /opt/wosb/WoSB-Website/requirements.txt
systemctl restart wosb
systemctl status wosb --no-pager
```

## 4.1) Why updates can "miss files" between machines

Some files are intentionally gitignored and therefore never sync through Git:

- `.env`
- `.venv/`
- `*.db`
- uploaded reimbursement files (`data/reimbursement_uploads/`)

Rule of thumb:

- If a file is in `.gitignore`, copy/configure it per machine manually.
- Keep required keys documented in `.env.example`.
- The deploy script now blocks deploy when `.env` is missing required keys.

## 5) Environment changes

If `.env` changes, restart app:

```bash
systemctl restart wosb
```

Common required values:

- `DISCORD_REDIRECT_URI=https://spanishfactionwosb.org/auth/callback`
- `DISCORD_ROLE_MEMBER_ID=...`
- `REIMBURSEMENT_ENABLED_GUILD_TAGS=TIF,BWC`
- `SITE_BACKGROUND_IMAGE=/static/images/website_background_2.png`

## 6) Cloudflare tunnel notes

Check tunnel health:

```bash
cloudflared tunnel info wosb-tunnel
systemctl status cloudflared --no-pager
```

Create/update DNS route:

```bash
cloudflared tunnel route dns wosb-tunnel spanishfactionwosb.org
```

## 7) Quick recovery commands

If app becomes unstable or bind conflicts appear:

```bash
systemctl stop wosb
pkill -f "uvicorn app.main:app" || true
systemctl start wosb
systemctl status wosb --no-pager
```

If Nginx serves default Ubuntu page:

```bash
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/wosb /etc/nginx/sites-enabled/wosb
nginx -t
systemctl reload nginx
```

## 8) Post-change verification checklist

- Home page loads at `https://spanishfactionwosb.org`
- Discord sign-in works
- Roster page loads (`/rosters`)
- Port battle tool works (`/tools/port-battle`)
- Reimbursement page works (`/tools/repair-reimbursement`)
- Guild pages and Port Orders edits work for authorized roles

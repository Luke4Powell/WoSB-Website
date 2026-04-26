# WoSB Proxmox LXC Setup (Ubuntu 24.04)

This guide is the complete deployment path for running the WoSB website on a Proxmox LXC node using Ubuntu 24.04.

Use this file as the source of truth for production setup and updates.

---

## 0) Scope and assumptions

- Proxmox host is already running and reachable.
- You already created an Ubuntu 24.04 LXC container.
- You have sudo access inside the LXC.
- You are deploying this repo from GitHub.
- App runs on `127.0.0.1:8000`, fronted by Nginx.

---

## 0.5) If you do NOT have a domain yet (safe defaults)

Use these defaults now:

- Install path: `/opt/wosb/WoSB-Website`
- Service user/group: `www-data:www-data`
- Temporary URL: `http://<LXC_IP>`
- Temporary OAuth callback: `http://<LXC_IP>/auth/callback`

What this means:

- You can fully test the app by IP before buying/configuring a domain.
- You should skip TLS/Certbot until DNS is ready.
- Later, when you have a domain, you will update:
  - `.env` → `DISCORD_REDIRECT_URI`
  - Discord Developer Portal callback URL
  - Nginx `server_name`
  - TLS certificate (`certbot`)

---

## 1) Prepare Ubuntu packages

Inside the Ubuntu 24.04 LXC:

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv python3-pip nginx
```

Verify Python:

```bash
python3.12 --version
```

---

## 2) Clone repo and enter directory

Choose a stable location (recommended `/opt/wosb`):

```bash
sudo mkdir -p /opt/wosb
sudo chown -R "$USER":"$USER" /opt/wosb
cd /opt/wosb
git clone <YOUR_GIT_URL> WoSB-Website
cd WoSB-Website
```

---

## 3) One-time app setup

Run setup script:

```bash
chmod +x ./scripts/*.sh
bash ./scripts/setup-dev.sh
```

Notes:

- First run will install dependencies and then start dev mode.
- Stop it after confirming it starts (`Ctrl+C`).
- For long-term hosting, use production mode and systemd (steps below).

---

## 4) Configure environment (.env)

Create your production env:

```bash
cp .env.example .env
```

Edit `.env` with real values:

- `SECRET_KEY` (long random string)
- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_REDIRECT_URI` (must match your public domain callback)
- `DISCORD_BOT_TOKEN`
- `DISCORD_GUILD_ID`
- role IDs (`DISCORD_ROLE_*`)
- optionally `DATABASE_URL` (recommended: Postgres for long-term production)

Important for OAuth:

- If your public URL is `https://wosb.yourdomain.com`, set:
  - `DISCORD_REDIRECT_URI=https://wosb.yourdomain.com/auth/callback`
- Add the same callback URL in Discord Developer Portal.
- If you do not have a domain yet, use:
  - `DISCORD_REDIRECT_URI=http://<LXC_IP>/auth/callback`
  - and add that exact IP callback in Discord Developer Portal.

---

## 5) Test production startup manually

Run:

```bash
bash ./scripts/run-prod.sh
```

Verify from LXC:

```bash
curl -I http://127.0.0.1:8000
```

Then stop (`Ctrl+C`) and continue to systemd.

---

## 6) Install systemd service (auto-start)

Copy service template:

```bash
sudo cp ./scripts/wosb.service.example /etc/systemd/system/wosb.service
```

Edit it:

```bash
sudo nano /etc/systemd/system/wosb.service
```

Update these values to match your server:

- `User=...`
- `Group=...`
- `WorkingDirectory=/opt/wosb/WoSB-Website`
- `EnvironmentFile=/opt/wosb/WoSB-Website/.env`
- `ExecStart=/opt/wosb/WoSB-Website/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wosb
sudo systemctl start wosb
sudo systemctl status wosb --no-pager
```

Tail logs:

```bash
journalctl -u wosb -f
```

---

## 7) Configure Nginx reverse proxy

Create site config:

```bash
sudo nano /etc/nginx/sites-available/wosb
```

Paste:

```nginx
server {
    listen 80;
    server_name wosb.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/wosb /etc/nginx/sites-enabled/wosb
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8) Add HTTPS (Let's Encrypt)

Only do this after your real domain DNS points to the server IP.

Install certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Issue cert:

```bash
sudo certbot --nginx -d wosb.yourdomain.com
```

---

## 9) Deploy updates from git (normal workflow)

Whenever `main` is updated:

```bash
cd /opt/wosb/WoSB-Website
bash ./scripts/deploy-update.sh
sudo systemctl restart wosb
sudo systemctl status wosb --no-pager
```

---

## 10) Multi-device developer workflow (Windows + Fedora + Server)

- Develop on Windows/Fedora with:
  - Windows: `.\scripts\setup-dev.ps1`
  - Fedora/Linux: `bash ./scripts/setup-dev.sh`
- Push code to GitHub.
- Pull/deploy on Ubuntu LXC with `deploy-update.sh`.
- Keep each machine's `.env` local and private.
- Do not share `.venv` between machines.

---

## 11) Troubleshooting checklist

- App service not running:
  - `sudo systemctl status wosb --no-pager`
  - `journalctl -u wosb -f`
- Nginx errors:
  - `sudo nginx -t`
  - `sudo systemctl status nginx --no-pager`
- OAuth login fails:
  - verify `DISCORD_REDIRECT_URI` exactly matches Discord app callback
- Bot/member visibility issues:
  - check bot token, guild ID, intents, and role IDs in `.env`
- Fresh clone not working:
  - ensure `.env` exists and is filled
  - re-run setup scripts

---

## 12) Maintenance rule (important)

Whenever deployment-relevant code/config changes are made, this file must be updated in the same PR/commit.

Examples of deployment-relevant changes:

- new environment variables
- changed startup command, host, or port
- new scripts under `scripts/`
- service, proxy, TLS, database, auth callback, or runtime behavior changes

---

## 13) After you get a real domain (mandatory update checklist)

When your domain is ready, perform all of these:

1. Update `.env`:
   - `DISCORD_REDIRECT_URI=https://<YOUR_DOMAIN>/auth/callback`
2. Update Discord Developer Portal OAuth redirect:
   - `https://<YOUR_DOMAIN>/auth/callback`
3. Update Nginx config:
   - `server_name <YOUR_DOMAIN>;`
4. Run certbot for HTTPS:
   - `sudo certbot --nginx -d <YOUR_DOMAIN>`
5. Restart services:
   - `sudo systemctl restart nginx`
   - `sudo systemctl restart wosb`
6. Verify login flow from browser.

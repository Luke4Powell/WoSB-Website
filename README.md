# WoSB Guild site (scaffold)

Python **FastAPI** app with **Discord OAuth**, signed **sessions**, and a small **SQLite** database (swap to Postgres later via `DATABASE_URL`). Pages are **server-rendered** with Jinja2 so you can grow into APIs and richer tools incrementally.

## Local setup

1. Use Python 3.12 for this project (`.python-version` and `pyproject.toml` both enforce this policy):

PowerShell (Windows):

```powershell
py -3.12 --version
```

Bash (Linux/macOS):

```bash
python3.12 --version
```

2. Create a virtual environment and install dependencies:

PowerShell (Windows):

```powershell
cd "C:\path\to\WoSB-Website"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Bash (Linux/macOS):

```bash
cd /path/to/WoSB-Website
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in Discord values (see below).

4. Run the app:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

## Environment recovery (6 months later)

If the project breaks after OS or Python updates, rebuild from a clean venv:

PowerShell (Windows):

```powershell
cd "C:\path\to\WoSB-Website"
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Bash (Linux/macOS):

```bash
cd /path/to/WoSB-Website
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Discord application

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application.
2. **OAuth2 → Redirects**: add `http://127.0.0.1:8000/auth/callback` (and your production URL later).
3. Copy **Client ID** and **Client Secret** into `.env`.
4. Under **Bot**, create a bot and copy the token into `DISCORD_BOT_TOKEN`. Invite the bot to your server with permissions that allow it to read members (membership in the server is enough for the REST member lookup in most setups).
5. Enable **Developer Mode** in Discord, right-click your server and **Copy Server ID** → `DISCORD_GUILD_ID`. Right-click roles → **Copy Role ID** for Admiral, Leader, and Alliance Leader.

## Permission mapping (current code)

- **Admiral** or **Leader**: treated as able to manage guild rosters (once those pages exist); both can read all profiles (same flags used for “officer” visibility later).
- **Alliance Leader**: can edit the alliance roster team (once that UI exists).
- Everyone who completes OAuth and is found in the guild is a baseline **member**.

Roles are **refreshed on each successful sign-in** from Discord.

## What is implemented now

- Discord login/logout, guild membership check via bot, role flags stored on `User`.
- Placeholder pages: home, dashboard, profile stub, tools stub.

## Next implementation slices

- Form to edit `ships_json` (or normalized ship/build tables).
- Roster models and UI per guild (A/B/C) plus alliance team.
- Mount your port battle scheduler logic behind a route or shared Python package.

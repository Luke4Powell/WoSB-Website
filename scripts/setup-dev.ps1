$ErrorActionPreference = "Stop"

Write-Host "[wosb] Setup starting..."

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher 'py' not found. Install Python 3.12 and try again."
}

$versionOut = & py -3.12 --version 2>&1
if ($LASTEXITCODE -ne 0) {
  throw "Python 3.12 is required. Install it, then rerun this script."
}
Write-Host "[wosb] $versionOut"

if (-not (Test-Path ".venv")) {
  Write-Host "[wosb] Creating virtual environment..."
  & py -3.12 -m venv .venv
}

Write-Host "[wosb] Activating virtual environment..."
. ".\.venv\Scripts\Activate.ps1"

Write-Host "[wosb] Upgrading pip and installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

if (-not (Test-Path ".env")) {
  Write-Warning "[wosb] .env is missing. Copy .env.example to .env and fill Discord values before login features will work."
}

Write-Host "[wosb] Starting app at http://127.0.0.1:8000"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

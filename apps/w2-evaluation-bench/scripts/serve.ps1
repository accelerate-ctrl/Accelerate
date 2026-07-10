# serve.ps1 — run the W2 Evaluation Bench server on Windows (PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\serve.ps1          # port 8000
#   powershell -ExecutionPolicy Bypass -File scripts\serve.ps1 -Port 9000
#
# First run creates .venv and installs requirements. Data lands in
# %USERPROFILE%\.w2\bench-data unless W2APP_DATA is already set.
# Optional env before launching:
#   W2APP_TOKENS       = "you:longrandomtoken"   (member auth; omit = open local dev)
#   W2_GOOGLE_CLIENT_ID= "<id>.apps.googleusercontent.com"  (Google gate; needs
#                        http://localhost:<port> registered as a JS origin)
#   W2_EVIDENCE_SOURCE = "crawl" (default) | "judge"  (release-evidence gathering)
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.11+ is required (winget install Python.Python.3.12)"
}
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if (-not $env:W2APP_DATA) { $env:W2APP_DATA = "$env:USERPROFILE\.w2\bench-data" }
New-Item -ItemType Directory -Force -Path $env:W2APP_DATA | Out-Null

Write-Host "W2 Evaluation Bench -> http://localhost:$Port  (data: $env:W2APP_DATA)"
& .\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port $Port

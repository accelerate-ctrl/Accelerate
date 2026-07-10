# W2 Evaluation Bench — personal runner installer for WINDOWS (native).
# Served personalized by GET /install.ps1 (TR-30/FR-12; Windows counterpart of
# install.sh). Idempotent: safe to re-run; keeps an existing env file.
#
#   irm -Headers @{'X-W2-Token'='<YOUR-TOKEN>'} https://<bench>/install.ps1 | iex
#
# What it does: installs Claude Code if missing -> opens Anthropic's login for
# your Team seat (claude setup-token; the credential never leaves this
# machine) -> downloads the runner -> writes %USERPROFILE%\.w2\env ->
# registers a logon Scheduled Task (with a Startup-folder fallback) -> runs
# the self-check. Add your Gemini key to the env file afterwards (doc 07).
$ErrorActionPreference = 'Stop'

$W2Server = '__W2_SERVER__'
$W2Token  = '__W2_TOKEN__'
if ([string]::IsNullOrWhiteSpace($W2Token) -or $W2Token.StartsWith('__W2_')) {
  Write-Error "No bench token. Re-fetch with: irm -Headers @{'X-W2-Token'='<YOUR-TOKEN>'} $W2Server/install.ps1 | iex"
}

$W2Home = Join-Path $HOME '.w2'
New-Item -ItemType Directory -Force -Path $W2Home | Out-Null

# --- python ---------------------------------------------------------------
$Py = $null
if (Get-Command py -ErrorAction SilentlyContinue)          { $Py = 'py' }
elseif (Get-Command python -ErrorAction SilentlyContinue)  { $Py = 'python' }
if (-not $Py) {
  Write-Error "Python 3 is required. Install it from https://www.python.org/downloads/ (check 'Add to PATH'), reopen PowerShell, and re-run this installer."
}
Write-Host "[install] python ................. $Py"

# --- Claude Code (Judge A runs under YOUR Team seat) ------------------------
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Host "[install] Claude Code not found - installing (official Windows installer)..."
  irm https://claude.ai/install.ps1 | iex
  # refresh PATH for this session
  $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:Path
}
if (Get-Command claude -ErrorAction SilentlyContinue) {
  Write-Host "[install] Claude Code ............ present"
  Write-Host "[install] opening Anthropic's login for your Team seat (claude setup-token)..."
  try { claude setup-token } catch { Write-Warning "setup-token did not complete - run 'claude setup-token' manually, then re-run the self-check." }
} else {
  Write-Warning "Claude Code still not on PATH - install it, run 'claude setup-token', then re-run this installer."
}

# --- runner payload ---------------------------------------------------------
$Zip = Join-Path $W2Home 'runner.zip'
Invoke-WebRequest -Uri "$W2Server/runner.zip" -Headers @{ 'X-W2-Token' = $W2Token } -OutFile $Zip
Expand-Archive -Path $Zip -DestinationPath $W2Home -Force
Remove-Item $Zip
Write-Host "[install] runner ................. $W2Home\runner"

# --- env file (created once; edit it to add your Gemini key) ----------------
$EnvFile = Join-Path $W2Home 'env'
if (-not (Test-Path $EnvFile)) {
@"
W2_SERVER=$W2Server
W2_TOKEN=$W2Token
# Judging engine: gemini = single-AI (Gemini Pro + Flash, no Claude);
# panel = legacy Claude + Gemini; mock = pipeline test without models.
W2_ENGINE=gemini
# Gemini key (REQUIRED for real evaluations; paid-tier key, doc 07):
#GEMINI_API_KEY=
#W2_GEMINI_TIER=paid
"@ | Set-Content -Path $EnvFile -Encoding UTF8
  Write-Host "[install] env .................... $EnvFile (add your GEMINI_API_KEY here)"
} else {
  Write-Host "[install] env .................... exists - keeping it (edit to rotate tokens/keys)."
}

# --- starter: loads the env file, then keeps the runner alive ---------------
$Starter = Join-Path $W2Home 'start-runner.ps1'
@'
$W2Home = Join-Path $HOME '.w2'
Get-Content (Join-Path $W2Home 'env') | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
  }
}
$Py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
while ($true) {
  & $Py (Join-Path $W2Home 'runner\w2_runner.py') --server $env:W2_SERVER --token $env:W2_TOKEN
  Start-Sleep -Seconds 10   # mirror systemd Restart=always
}
'@ | Set-Content -Path $Starter -Encoding UTF8

# --- run at logon: Scheduled Task, Startup-folder fallback ------------------
$TaskArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Starter`""
$Installed = $false
try {
  $action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $TaskArgs
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:UserName
  Register-ScheduledTask -TaskName 'W2Runner' -Action $action -Trigger $trigger -Force | Out-Null
  Start-ScheduledTask -TaskName 'W2Runner'
  $Installed = $true
  Write-Host "[install] service ................ Scheduled Task 'W2Runner' (runs at logon; running now)"
} catch {
  $StartupCmd = Join-Path ([Environment]::GetFolderPath('Startup')) 'W2Runner.cmd'
  "start /min `"`" powershell.exe $TaskArgs" | Set-Content -Path $StartupCmd -Encoding ASCII
  Start-Process powershell.exe -ArgumentList $TaskArgs -WindowStyle Hidden
  $Installed = $true
  Write-Host "[install] service ................ Startup shortcut $StartupCmd (task scheduler unavailable; running now)"
}

# --- self-check --------------------------------------------------------------
Write-Host ""
& $Py (Join-Path $W2Home 'runner\w2_runner.py') --selfcheck --server $W2Server --token $W2Token
if ($Installed) { Write-Host "[selfcheck] runner service ........ INSTALLED" }
Write-Host ""
Write-Host "Next: edit $EnvFile - set GEMINI_API_KEY and W2_GEMINI_TIER=paid,"
Write-Host "then restart:  Stop-ScheduledTask -TaskName W2Runner; Start-ScheduledTask -TaskName W2Runner"
Write-Host "Console: $W2Server/bench - the header should show 'your runner: connected'."

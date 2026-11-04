# ClipAgent for Windows: one line, every agent (Claude Code, Codex, OpenCode, Antigravity).
#   irm https://raw.githubusercontent.com/truecallerabreham/Clipagent/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$Dir = if ($env:CLIPAGENT_DIR) { $env:CLIPAGENT_DIR } else { "$HOME\.clipagent\Clipagent" }
$HomeDir = if ($env:CLIPAGENT_HOME) { $env:CLIPAGENT_HOME } else { "$HOME\ClipAgent" }
function Say($m) { Write-Host "> $m" -ForegroundColor Cyan }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is required (winget install Git.Git)" }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say "installing uv"
  powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
  $env:Path = "$HOME\.local\bin;$env:Path"
}
if (Test-Path "$Dir\.git") { Say "updating ClipAgent"; git -C $Dir pull --ff-only --quiet }
else {
  Say "downloading ClipAgent (code only, no demo videos)"
  New-Item -ItemType Directory -Force (Split-Path $Dir) | Out-Null
  git clone --quiet --depth 1 --filter=blob:none --sparse https://github.com/truecallerabreham/Clipagent.git $Dir
  git -C $Dir sparse-checkout set skills engine looks recorder hooks .claude-plugin
}
Say "adding /screen-record to your coding agents"
$env:PYTHONPATH = "$Dir\engine"
uv run --no-project --quiet python -m clipagent.setup link
Remove-Item Env:PYTHONPATH
New-Item -ItemType Directory -Force $HomeDir | Out-Null
Start-Process -WindowStyle Hidden -FilePath "$Dir\skills\screen-record\ca.cmd" -ArgumentList "setup" `
  -RedirectStandardOutput "$HomeDir\setup.log" -RedirectStandardError "$HomeDir\setup.err.log"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Say "one thing to do yourself: winget install ffmpeg" }
Say "done. Open your agent and type: /screen-record   (setup finishes in the background)"

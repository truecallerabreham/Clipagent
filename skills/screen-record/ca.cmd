@echo off
rem The ClipAgent CLI for the agent on Windows:  <this skill's folder>\ca.cmd <command> [args]
setlocal
set "ENGINE=%~dp0..\..\engine"
if not exist "%ENGINE%\pyproject.toml" set "ENGINE=%USERPROFILE%\.clipagent\Clipagent\engine"
where uv >nul 2>nul || (
  echo first run: installing uv ^(Python runner^)... 1>&2
  powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex" >nul
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
uv run --quiet --project "%ENGINE%" clipagent %*

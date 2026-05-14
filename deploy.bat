@echo off
cd /d "%~dp0"
echo === Listing Generator ===
echo.

:: Try to get OpenRouter key from .env first (if exists)
if exist .env (
  for /f "tokens=2 delims==" %%a in ('findstr /b "OPENROUTER_API_KEY" .env') do set OPENROUTER_API_KEY=%%a
)

:: Fallback: try WSL
if "%OPENROUTER_API_KEY%"=="" (
  for /f "tokens=*" %%a in ('wsl -d Ubuntu -e bash -c "grep OPENROUTER_API_KEY ~/.bashrc 2>/dev/null | head -1 | cut -d'\"' -f2"') do set OPENROUTER_API_KEY=%%a
)

if "%OPENROUTER_API_KEY%"=="" (
  echo ERROR: No OpenRouter API key found in .env or WSL
  pause
  exit /b 1
)

:: Start server
set OPENROUTER_API_KEY=%OPENROUTER_API_KEY%
start /B python server.py
echo Server starting... http://localhost:8768
timeout /t 3 /nobreak >nul

:: Start tunnel
echo Starting tunnel...
cloudflared tunnel --url http://localhost:8768

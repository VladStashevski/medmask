@echo off
chcp 65001 >nul
cd /d "%~dp0"

where node >nul 2>nul || (
  echo Нужен Node.js 22 или новее: https://nodejs.org/
  pause
  exit /b 1
)

if not exist node_modules call corepack pnpm install --frozen-lockfile
if errorlevel 1 goto :error

if not exist dist\server\index.js call corepack pnpm build
if errorlevel 1 goto :error

start "" http://127.0.0.1:8765
call corepack pnpm start --hostname 127.0.0.1 --port 8765
exit /b 0

:error
echo Не удалось запустить приложение.
pause
exit /b 1

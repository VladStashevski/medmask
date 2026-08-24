#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "Нужен Node.js 22 или новее: https://nodejs.org/"
  read -r -p "Нажмите Enter, чтобы закрыть окно..."
  exit 1
fi

if [[ ! -d node_modules ]]; then
  corepack pnpm install --frozen-lockfile
fi

if [[ ! -f dist/server/index.js ]]; then
  corepack pnpm build
fi

(sleep 2; open "http://127.0.0.1:8765") &
exec corepack pnpm start --hostname 127.0.0.1 --port 8765

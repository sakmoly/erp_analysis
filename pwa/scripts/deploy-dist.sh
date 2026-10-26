#!/usr/bin/env bash
# Copy built PWA to a target directory (nginx alias root for /mobile).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-/var/www/printechs/mobile}"
npm run build --prefix "$ROOT"
mkdir -p "$TARGET"
rsync -a --delete "$ROOT/dist/" "$TARGET/"
echo "Deployed to $TARGET"

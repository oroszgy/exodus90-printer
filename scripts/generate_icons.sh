#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v magick >/dev/null 2>&1; then
    echo "error: ImageMagick (with librsvg) is required" >&2
    exit 1
fi

magick -background none addon/assets/icon.svg -depth 8 -strip addon/icon.png
magick -background none addon/assets/logo.svg -depth 8 -strip addon/logo.png

echo "Regenerated addon/icon.png and addon/logo.png"

#!/bin/sh
# Public release: explicit allowlist, with nested ZIP checks for private AMD DLLs.
set -eu
cd "$(dirname "$0")"
version=${ANR_VERSION:-V.B15}
mkdir -p bin
for kind in full addon; do
    f="bin/anr-fg-$version-$kind.zip"
    [ -e "$f" ] || curl -fL -o "$f" "https://github.com/apex-compute/ANR/releases/download/FG-$version/anr-fg-$version-$kind.zip"
done
npm run build
python3 tools/package-release.py

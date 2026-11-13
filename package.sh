#!/bin/sh
# Builds out/Decky ANR.zip for Decky Loader's "Install plugin from ZIP".
set -eu
cd "$(dirname "$0")"
version=${ANR_VERSION:-V.B15}
tag="FG-$version"
mkdir -p bin
for kind in full addon; do
    f="bin/anr-fg-$version-$kind.zip"
    [ -e "$f" ] || curl -fL -o "$f" "https://github.com/apex-compute/ANR/releases/download/$tag/anr-fg-$version-$kind.zip"
done
[ -e dist/index.js ] || npm run build
rm -rf out && mkdir -p "out/Decky ANR/dist" "out/Decky ANR/bin"
cp dist/index.js "out/Decky ANR/dist/"
cp main.py plugin.json package.json LICENSE README.md "out/Decky ANR/"
cp bin/anr-fg-"$version"-*.zip "out/Decky ANR/bin/"
(cd out && zip -qr "Decky ANR.zip" "Decky ANR")
echo "out/Decky ANR.zip"

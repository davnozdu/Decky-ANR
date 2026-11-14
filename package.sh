#!/bin/sh
# Builds out/Decky FrameGen Hub.zip for Decky Loader's "Install plugin from ZIP".
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
rm -rf out && mkdir -p "out/Decky FrameGen Hub/dist" "out/Decky FrameGen Hub/bin"
cp dist/index.js "out/Decky FrameGen Hub/dist/"
cp main.py plugin.json package.json LICENSE README.md "out/Decky FrameGen Hub/"
cp -R licenses py_modules "out/Decky FrameGen Hub/"
find "out/Decky FrameGen Hub" -name __pycache__ -type d -prune -exec rm -rf {} +
cp bin/anr-fg-"$version"-*.zip "out/Decky FrameGen Hub/bin/"
(cd out && zip -qr "Decky FrameGen Hub.zip" "Decky FrameGen Hub")
echo "out/Decky FrameGen Hub.zip"

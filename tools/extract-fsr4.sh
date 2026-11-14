#!/bin/sh
# SteamOS / Linux / macOS. Pass the downloaded driver path, or enter it when asked.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/extract-fsr4.py" "$@"

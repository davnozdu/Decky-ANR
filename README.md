# Decky ANR

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that installs and manages
**ANR FG** ([Apex Neural Rendering](https://github.com/apex-compute/ANR) frame generation) in Proton games on
Steam Deck, SteamOS and other Linux handhelds (Bazzite, CachyOS Handheld, …).

ANR FG replaces DLSS Frame Generation (`nvngx_dlssg.dll`) and is loaded through OptiScaler. The plugin uses the
official ANR FG packages and their own `install.sh` / `uninstall.sh`, so backups and restores work exactly as
upstream intends.

Based on the structure of [Decky-Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen).

## Features

- Bundled ANR FG package (`anr-fg-<version>-full.zip`, includes Apex's OptiScaler build), plus a
  **Get the newest release** button that downloads the latest GitHub release and checks it against `SHA256SUMS.txt`.
- Per-game install/remove from Game Mode: picks the game's `.exe` folder automatically (you can choose another one),
  sets the launch option `WINEDLLOVERRIDES="dxgi=n,b" %command%` (or `winmm` for Vulkan games) and removes it again,
  keeping your other launch options.
- Add-on mode: if the game already has an OptiScaler that supports custom FG providers (`FGNvngxReplacement`),
  ANR FG is added to it instead.
- **Copy launch options** button (and **Apply launch options to the game** if they were lost), with the game's
  current launch options shown.
- Shows which Proton the game runs on (per-game Steam Play setting or the Steam default, and the prefix version);
  warns about native Linux builds, which cannot use ANR FG.
- Per-game `nr_fg.ini` settings: generated frames (2X–6X), compute path, scene cut detection; view the newest log.
- Shows when a game has an older ANR FG than the selected package and updates it in one click.

## Usage

1. Download `Decky.ANR.zip` from [Releases](../../releases) and install it from Decky's developer settings
   (*Install plugin from ZIP*), or: from Decky's developer settings (*Install plugin from ZIP*).
2. Open the plugin, choose a game, press **Install ANR FG**.
3. Launch the game, enable **DLSS Frame Generation** in its settings: ANR FG generates the frames.

Games patched by Decky Framegen must be unpatched there first: its OptiScaler 0.9.4 cannot load custom FG providers.

## Build

```sh
npm install
npm run build
./package.sh        # writes out/Decky ANR.zip (downloads the ANR FG release into bin/ if missing)
```

## Licenses

Plugin code: BSD-3-Clause. ANR FG is © Apex Compute and distributed as published in its GitHub releases.
OptiScaler (inside the ANR FG package) is GPL-3.0; its source is attached to each ANR release.

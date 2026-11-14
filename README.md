# Decky ANR

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that installs and manages
**ANR FG** ([Apex Neural Rendering](https://github.com/apex-compute/ANR) frame generation) in Proton games on
Steam Deck, SteamOS and other Linux handhelds (Bazzite, CachyOS Handheld, …).

ANR FG replaces DLSS Frame Generation (`nvngx_dlssg.dll`) and is loaded through OptiScaler. The plugin uses the
official ANR FG packages and their own `install.sh` / `uninstall.sh`, so backups and restores work exactly as
upstream intends.

Based on the structure of [Decky-Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen).

## Beta: alternative XeFG frame generator

Version **0.2.0-beta.1** adds a per-game **Frame generator** selector: ANR FG or
**XeFG XMX Port (Build 10)**. Install ANR normally first; then close the game and choose XeFG.
The first selection downloads about 75 MB: the pinned upstream provider and Intel XeSS SDK 3.0.2,
both checked against SHA-256. Only the XeFG runtime, provider programs and licenses are installed.
ANR stays installed for switching back. The upscaler and multiplier remain independent.

XeFG is for **DirectX 12** games with DLSS FG inputs, using **SDR or HDR10** (not scRGB).
Start with 2X. Check **Show generator log** after starting the game (`Creating XeFG context`).

Tested: Forza Horizon 6 on ROG Xbox Ally X (Radeon 890M, Mesa 26.2.6, proton-cachyos 11), FSR 4 Balanced, 2X:
XeFG ~73 FPS shown (69–84 while driving) vs ANR FG ~71 (65–86), measured from gamescope; XeFG ran the
ported XMX model through its DXIL path (`Network path: XMX (native), model 16`, CUDA route inactive), no GPU faults,
and showed fewer artifacts. Other games and GPUs: unverified.
The loader detected as Vulkan (`winmm.dll`) cannot select XeFG. Other games need manual DX12 verification.

The generator choice survives reinstall / Update all. Copy/reset profile changes tuning and keeps
the selected generator. ANR-only controls are hidden while XeFG is selected. Removal also cleans up
managed XeFG files in add-on installs, preserving changed files and logs.

Sources: [XeFG Build 10](https://github.com/realdody/dlssg-to-xefg-xmx/releases/tag/build-10),
[Intel XeSS SDK](https://github.com/intel/xess/releases/tag/v3.0.2). Third-party notices: `licenses/`.

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
- **Benchmark**: runs ANR's official test kit on the device (every compute path at 1080p/1440p/4K, timed and
  checked against reference frames, next to AMD FSR 3.1 frame generation), shows the table and applies the best
  path to all games and new installs in one click. On a Radeon 890M, ANR's `auto` picks `coopmat` while
  `portable-linalg` is ~24% faster and more accurate.
- **Performance by compute path** per game, from ANR's own logs (GPU ms per real frame, real → shown FPS, errors).
- **Upscaler per game** (OptiScaler under ANR FG): as in the ANR package, FSR 3.1, **FSR 4 (ML)** or XeSS. FSR 4 uses
  AMD's own `amdxcffx64.dll` that Proton puts into a prefix (`PROTON_FFX4_UPGRADE`, proton-cachyos or GE-Proton):
  the plugin takes the newest AMD-signed copy on the device, places it in OptiScaler's folder and picks the INT8
  model (RDNA 2/3/3.5) or FP8 (RDNA4). No copy yet? One button adds `PROTON_FFX4_UPGRADE=1` to the launch options.
  The choice survives ANR updates and the copied DLL is removed with ANR. Optional FSR watermark to check it runs.
- **Game profiles**: every game keeps its own settings, re-applied after ANR updates and removed with ANR:
  - **Render quality** (OptiScaler `UpscaleRatio`): Ultra Quality … Ultra Performance, with the render resolution shown;
  - **Frame generation multiplier**: force 2X–6X (`[DLSSG] OverrideInterpolationCount`) in games that only ask for 2X
    on non-RTX 50 GPUs; **Dynamic MFG** with a target FPS (experimental: in Forza Horizon 6 on a Radeon 890M
    its rapid multiplier switching ended in a GPU page fault and reset; prefer a fixed multiplier);
  - **FPS limit** (steps of 10), **RCAS sharpening**, **OptiScaler FPS counter**;
  - **Copy the profile** from another game, **Reset the profile**.
- Per-game `nr_fg.ini` settings: generated frames (2X–6X), compute path, scene cut detection; view the newest log.
- **Update notifications**: checks GitHub at start and every 6 hours; a Steam toast and a banner tell you when a new
  ANR FG release or a new Decky ANR version is out. ANR FG downloads in one click (SHA256-checked), the plugin
  updates through Decky's own installer, and **Update all** brings every patched game to the new ANR FG.
- Shows when a game has an older ANR FG than the selected package and updates it in one click.

## Usage

1. Download `Decky.ANR.zip` from [Releases](../../releases) and install it from Decky's developer settings
   (*Install plugin from ZIP*), or: from Decky's developer settings (*Install plugin from ZIP*).
2. Open the plugin, choose a game, press **Install ANR FG**.
3. Launch the game, enable **DLSS Frame Generation** in its settings: ANR FG generates the frames.

Games patched by Decky Framegen must be unpatched there first: its OptiScaler 0.9.4 cannot load custom FG providers.

## Tested

| Device | OS / Proton | Game | Result |
|---|---|---|---|
| ROG Xbox Ally X (Ryzen AI Z2 Extreme, Radeon 890M) | CachyOS Handheld, proton-cachyos 11.0 | Forza Horizon 6 (D3D12, Streamline DLSS-G) | Works: 2X at 1920x1080, ~40–43 real FPS → ~80–86 shown (10 min of driving), ANR ~6.0–6.4 ms GPU per real frame, 0 generation errors |

Test kit on the same device (ANR FG V.B15, 2X, ms per real frame, lower is better; dB vs reference, higher is better):

| | portable-linalg | coopmat (auto) | packed | FSR 3.1 FG |
|---|---|---|---|---|
| 1080p | **4.01** · 90.9 dB | 5.27 · 82.2 dB | 5.53 · 82.7 dB | 6.07 |
| 1440p | **6.90** · 91.3 dB | 8.89 · 82.9 dB | 9.33 · 83.5 dB | 10.74 |
| 2160p | **15.58** · 91.5 dB | 20.18 · 84.0 dB | 21.20 · 84.8 dB | 25.98 |

Notes:
- Frame generation starts when gameplay starts (menus may not use it); the game may re-create it on scene changes.
- In-game, portable-linalg vs coopmat was ~6.0 vs ~6.4 ms per real frame: the game's own rendering bounds the
  frame rate, so the kit's 24% shows as a small in-game gain.
- Frame generation feels best with 40+ real FPS.
- Forza Horizon 6 with FSR 4.1.1 INT8 (Quality, 720p→1080p) under ANR: ~37 real → ~74 shown FPS; FSR 3.1: ~42 → ~84.
  FSR 4 looks cleaner and costs more GPU time on a Radeon 890M.
- Forced 3X in Forza Horizon 6 (FSR 4, Quality): ~29 real → ~88 shown FPS, 0 errors (2X: ~37 → ~74). The game's own
  frame pacing is uneven at ~30 real FPS (p99 45–58 ms), which frame generation makes visible: raise real FPS first
  (FSR 3.1, Performance render quality), keep 2X, and use the FPS limit for steady pacing.
- OptiScaler logging is off in ANR's `OptiScaler.ini` (`LogLevel=5`); set `LogLevel=2` for `OptiScaler.log`.

## Build

```sh
npm install
npm run build
./package.sh        # writes out/Decky ANR.zip (downloads the ANR FG release into bin/ if missing)
```

## Licenses

Plugin code: BSD-3-Clause. ANR FG is © Apex Compute and distributed as published in its GitHub releases.
OptiScaler (inside the ANR FG full package) is GPL-3.0; the source of the bundled build (Apex OptiScaler, upstream
`d6b02459`) is [anr-fg-V.B15-full-optiscaler-source.zip](https://github.com/apex-compute/ANR/releases/download/FG-V.B15/anr-fg-V.B15-full-optiscaler-source.zip).

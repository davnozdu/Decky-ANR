# Decky FrameGen Hub

*Formerly **Decky ANR**.* Choose the frame generator for each game — **ANR FG** (Apex Neural Rendering) or
**XeFG** (Intel XeSS frame generation via the XMX port) — with OptiScaler upscalers and per-game profiles.
Updating from Decky ANR keeps your game profiles; the plugin then offers to remove the old one.

**Инструкция на русском: [README.ru.md](README.ru.md).**

## Quick start

1. Download `Decky.FrameGen.Hub.zip` from [Releases](../../releases) → Decky → Settings → Developer → Install Plugin
   from ZIP. Coming from Decky ANR: your game profiles are carried over; remove the old plugin when asked.
2. **Lossless Scaling (best FPS, any game):** own Lossless Scaling in Steam, set it to the **lsfg-vk** beta branch
   (Properties → Betas), press **Install lsfg-vk** in the plugin, then per game pick **Lossless Scaling**
   (2X, flow scale 75%) and turn the game's own frame generation off.
3. **ANR FG / XeFG (games with DLSS FG):** per game **Install ANR FG**, pick the **Frame generator**, then in the game
   choose NVIDIA DLSS and turn **DLSS Frame Generation** on.
4. For the most FPS: Upscaler **FSR 4** (cleaner) or **FSR 3.1** (faster), Render quality **Balanced/Performance**,
   run **Benchmark** once and use its best compute path for ANR, keep 2X, and set an FPS limit for steady pacing.
   **FSR 4 needs no environment variables:** the plugin takes AMD's library from Valve's **Proton Experimental**
   (or offers to install it) and copies it next to OptiScaler. The game must run on Proton 11+.
5. **Steam Deck (RDNA 2):** Lossless Scaling is the best fit (2X, flow scale 50–75%, performance mode); use
   **FSR 3.1** — FSR 4 runs but costs several ms a frame on RDNA 2. Not yet tested on a real Deck.

| Generator | Pick it for | Forza Horizon 6, ROG Xbox Ally X, 2X |
|---|---|---|
| Lossless Scaling (lsfg-vk) | most FPS, best responsiveness, any game | ~93 FPS shown |
| XeFG | cleanest image (DX12, DLSS FG games) | ~73 |
| ANR FG | Apex's neural FG, updated often | ~71 |

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that installs and manages
**ANR FG** ([Apex Neural Rendering](https://github.com/apex-compute/ANR) frame generation) in Proton games on
Steam Deck, SteamOS and other Linux handhelds (Bazzite, CachyOS Handheld, …).

ANR FG replaces DLSS Frame Generation (`nvngx_dlssg.dll`) and is loaded through OptiScaler. The plugin uses the
official ANR FG packages and their own `install.sh` / `uninstall.sh`, so backups and restores work exactly as
upstream intends.

Based on the structure of [Decky-Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen).

## Steam language and Lossless Scaling imports (0.2.4)

The UI follows **Steam's language** automatically: Russian Steam → Russian UI; English Steam → English UI.
Other languages fall back to English. Steam's setting takes priority over the Linux/browser locale.
Buttons, descriptions, option labels, plugin messages and notifications are translated; original game/driver
logs and protocol values stay unchanged. Changing the language in Steam takes effect when Steam reloads;
the plugin also listens for language/settings changes. No separate language preference is needed.

In the Lossless Scaling section choose **Import Lossless Scaling library (DLL / ZIP)** (Russian:
**Импорт библиотеки Lossless Scaling (DLL / ZIP)**). Select your original **lsfg-vk.dll** from the lsfg-vk beta
branch of your own Lossless Scaling copy, or a ZIP containing exactly one such DLL. The import checks an
x64 PE DLL and embedded Vulkan shaders, stores an unchanged copy under persistent plugin data, and updates
lsfg-vk's library path without changing existing game profiles. Restart games using Lossless Scaling.
`Lossless.dll` from the default branch is not accepted. Importing a newer compatible library works the same way.

Without an import, the plugin still finds the original library in Steam automatically. The lsfg-vk Vulkan
layer itself is installed separately with the existing Install lsfg-vk button. No Lossless Scaling DLL is
included in this plugin release or uploaded anywhere by the plugin. The file remains your own local copy.

## FSR 4 Lite: bring your own AMD libraries (0.2.2)

The plugin release contains **no AMD driver DLLs**. Download an official AMD Windows graphics driver yourself,
then use **FSR 4 libraries → Extract FSR 4 libraries from driver (.exe)**. The plugin extracts only
`amdxcffx64.dll` and `amdvkffx64.dll`, checks x64 PE headers, AMD/FidelityFX metadata, matching versions and Lite
model markers, then stores them in Decky's persistent plugin data. These metadata checks do not verify a
cryptographic publisher signature. The driver installer is never executed and no system driver is installed.
On SteamOS/Linux, a missing 7-Zip is downloaded as a portable tool from its official release, checked against a
pinned SHA-256, and kept in plugin data; no sudo or writable system partition is needed.

Alternatively, **Import libraries from ZIP** accepts both DLLs together (nested folders are fine). Mixed versions, duplicate DLLs,
unsafe ZIP paths and files without Lite markers are rejected. Importing a newer pair uses the same buttons;
there is no fixed DLL hash/version whitelist. Your library survives plugin updates.

After importing, choose a game → **Upscaler → FSR 4 Lite (INT8)**. Games already using Lite update automatically
when closed; running games are skipped until closed and Lite is selected again. Existing frame generator,
quality and sharpening choices are preserved. Only unchanged plugin-managed DLLs are replaced/removed.
A new game's upscaler is not switched automatically.

The watermark is **off by default**. Enable **Show the FSR watermark** temporarily to verify
**`FSR4L-i8 Upscale 4.1.2`** (or the version you imported); an FSR 4 label alone is not proof of Lite.
Tested on ROG Xbox Ally X / CachyOS / proton-cachyos 11 / Forza Horizon 6: driver library 2.4.0.4370,
Lite watermark confirmed in actual gameplay, Balanced 1129×635 → 1920×1080, ~3 ms upscaler time in one sample.
Steam Deck and other games: unverified; this is not an FPS guarantee.

For standalone extraction, download **FSR4-Extractor.zip** from this release. See
[FSR4-EXTRACTION.md](FSR4-EXTRACTION.md) for a one-command SteamOS workflow and Windows/macOS notes.
Download source: [AMD Adrenalin 26.10.1](https://www.amd.com/en/resources/support-articles/release-notes/rn-rad-win-26-10-1.html)
(or a newer driver that contains Lite). The extracted files retain AMD's terms; users supply them locally.

## Beta: alternative XeFG frame generator

Version **0.2.0-beta.1** adds a per-game **Frame generator** selector: ANR FG or
**XeFG XMX Port (Build 10)**. Install ANR normally first; then close the game and choose XeFG.
The first selection downloads about 75 MB: the pinned upstream provider and Intel XeSS SDK 3.0.2,
both checked against SHA-256. Only the XeFG runtime, provider programs and licenses are installed.
ANR stays installed for switching back. The upscaler and multiplier remain independent.

XeFG is for **DirectX 12** games with DLSS FG inputs, using **SDR or HDR10** (not scRGB).
Start with 2X. Check **Show generator log** after starting the game (`Creating XeFG context`).

Tested: Forza Horizon 6 on ROG Xbox Ally X (Radeon 890M, Mesa 26.2.6, proton-cachyos 11), FSR 4 Balanced, 2X:
**Lossless Scaling (lsfg-vk 2, flow 75%) ~93 FPS shown (84–108)**, XeFG ~73 (69–84), ANR FG ~71 (65–86), measured from
gamescope; lsfg-vk costs ~3.4 ms per real frame at 1080p 2X (1.9 ms with flow 50% + performance mode) and leaves the
game more GPU time, at the cost of more artifacts (no motion vectors). XeFG ran the
ported XMX model through its DXIL path (`Network path: XMX (native), model 16`, CUDA route inactive), no GPU faults,
and showed fewer artifacts. Other games and GPUs: unverified.
The loader detected as Vulkan (`winmm.dll`) cannot select XeFG. Other games need manual DX12 verification.

The generator choice survives reinstall / Update all. Copy/reset profile changes tuning and keeps
the selected generator. ANR-only controls are hidden while XeFG is selected. Removal also cleans up
managed XeFG files in add-on installs, preserving changed files and logs.

Sources: [XeFG Build 10](https://github.com/realdody/dlssg-to-xefg-xmx/releases/tag/build-10),
[Intel XeSS SDK](https://github.com/intel/xess/releases/tag/v3.0.2). Third-party notices: `licenses/`.

## Lossless Scaling (lsfg-vk)

A third generator for **any** game, also without DLSS Frame Generation: [lsfg-vk](https://lsfg-vk.dev) 2.x,
the Linux layer for Lossless Scaling's frame generation.

- You need your own **Lossless Scaling** (Steam app 993090) on the **lsfg-vk** beta branch (Properties → Betas): that
  branch has `lsfg-vk.dll`; the default branch's `Lossless.dll` lacks what lsfg-vk 2 needs. By default the plugin uses
  the Steam copy in place. You may also import your own DLL/ZIP into persistent plugin data; nothing is uploaded.
- **Install lsfg-vk** downloads the official build from builds.lsfg-vk.dev into `~/.local` (as its install guide
  does; lsfg-vk is CC BY-NC-ND 4.0 and is not bundled). Updates are offered when a new release is out.
- Per game: **Frame generator → Lossless Scaling** (or the toggle for games without ANR), multiplier 2X–4X,
  flow scale, performance mode. The plugin keeps its own `[[profile]]` entries in `~/.config/lsfg-vk/conf.toml`
  between markers, leaves yours alone and checks the file with `lsfg-vk-cli validate`.
- Turn the game's own frame generation off. With ANR installed, choosing Lossless Scaling turns OptiScaler's frame
  generation off for that game.

## Updates

The plugin checks at start and every 6 hours and shows a Steam notification once per new version of: the plugin
(betas see newer betas), ANR FG, lsfg-vk, a newer FSR 4 DLL from Proton, and new XeFG builds (those arrive with a plugin
update, as each build is pinned and SHA-256 checked).

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
  ANR FG release or a new Decky FrameGen Hub version is out. ANR FG downloads in one click (SHA256-checked), the plugin
  updates through Decky's own installer, and **Update all** brings every patched game to the new ANR FG.
- Shows when a game has an older ANR FG than the selected package and updates it in one click.

## Usage

1. Download `Decky.FrameGen.Hub.zip` from [Releases](../../releases) and install it from Decky's developer settings
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
./package.sh        # writes out/Decky.FrameGen.Hub.zip and out/FSR4-Extractor.zip; no AMD driver DLLs
```

## Licenses

Plugin code: BSD-3-Clause. ANR FG is © Apex Compute and distributed as published in its GitHub releases.
OptiScaler (inside the ANR FG full package) is GPL-3.0; the source of the bundled build (Apex OptiScaler, upstream
`d6b02459`) is [anr-fg-V.B15-full-optiscaler-source.zip](https://github.com/apex-compute/ANR/releases/download/FG-V.B15/anr-fg-V.B15-full-optiscaler-source.zip).

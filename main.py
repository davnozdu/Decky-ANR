"""Decky ANR: installs and manages ANR FG (Apex Neural Rendering frame generation) for Proton games.

ANR FG ships as a DLSS-G replacement (nvngx_dlssg.dll) loaded through OptiScaler. This backend keeps the
official ANR FG packages (bundled in bin/ or downloaded from GitHub releases), runs their own install.sh and
uninstall.sh for each game and edits nr_fg.ini. The frontend sets the Steam launch options.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import decky

GITHUB_REPO = "apex-compute/ANR"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
PLUGIN_REPO = "davnozdu/Decky-ANR"
PLUGIN_API_LATEST = f"https://api.github.com/repos/{PLUGIN_REPO}/releases/latest"
PLUGIN_ASSET = "Decky.ANR.zip"
UPDATE_CHECK_INTERVAL = 6 * 3600
UPDATE_CHECK_FIRST_DELAY = 30
USER_AGENT = "decky-anr"
CA_BUNDLES = [
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ca-certificates/extracted/tls-ca-bundle.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
]

ANR_DIR_NAME = "Apex Neural Rendering FG"
LEGACY_ANR_DIR_NAME = "nrfg"
INSTALL_RECORD = "nr_fg_install.json"
FRAMEGEN_MARKER = "FRAMEGEN_PATCH"

PACKAGE_RE = re.compile(r"^anr-fg-(?P<version>.+)-(?P<kind>full|addon)\.zip$")

# Files a user-installed OptiScaler may be loaded as; checked for FGNvngxReplacement support (add-on mode).
OPTISCALER_PROXY_NAMES = [
    "dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "wininet.dll", "winhttp.dll",
    "d3d12.dll", "OptiScaler.asi", "OptiScaler.dll",
]

BAD_EXE_SUBSTRINGS = [
    "crashreport", "crashhandler", "eac", "easyanticheat", "beclient", "eosbootstrap", "benchmark",
    "uninstall", "unins0", "setup", "launcher", "updater", "bootstrap", "_redist", "redist", "prereq",
    "vc_redist", "dxsetup", "dotnet", "unitycrashhandler", "quicksfv", "touchup", "cefprocess",
    "crashpad", "installer", "redistributable", "server.exe", "helper", "reporter",
]

NR_FG_SETTINGS = {
    "max_generated": {"type": "int", "min": 1, "max": 5},
    "path": {
        "type": "enum",
        "values": ["auto", "coopmat", "packed", "dp4a", "portable", "portable-linalg", "portable-xmx"],
    },
    "scene_cut": {"type": "enum", "values": ["0", "1"]},
}


def _version_key(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version or ""))


class Plugin:
    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _main(self):
        decky.logger.info("[ANR] plugin loaded")
        try:
            await asyncio.to_thread(self._ensure_bundled_package)
        except Exception as exc:
            decky.logger.error(f"[ANR] could not set up the bundled package: {exc}")
        self._update_task = asyncio.get_event_loop().create_task(self._update_loop())

    async def _unload(self):
        task = getattr(self, "_update_task", None)
        if task:
            task.cancel()
        decky.logger.info("[ANR] plugin unloaded")

    # ── Update checks ─────────────────────────────────────────────────────────

    def _plugin_version(self) -> str:
        return str(getattr(decky, "DECKY_PLUGIN_VERSION", "") or "0")

    def _check_updates_sync(self) -> dict:
        info: dict = {"checked_at": datetime.now(timezone.utc).isoformat(), "errors": []}
        installed = self._installed_versions()
        newest_installed = installed[-1] if installed else ""
        try:
            release = json.loads(self._http_get(GITHUB_API_LATEST, "application/vnd.github+json"))
            latest = None
            for asset in release.get("assets", []):
                m = PACKAGE_RE.match(asset.get("name", ""))
                if m and m["kind"] == "full":
                    latest = m["version"]
            info["anr_latest"] = latest
            info["anr_update"] = bool(latest) and _version_key(latest) > _version_key(newest_installed)
            info["anr_notes_url"] = release.get("html_url")
        except Exception as exc:
            info["errors"].append(f"ANR FG: {exc}")
        try:
            release = json.loads(self._http_get(PLUGIN_API_LATEST, "application/vnd.github+json"))
            tag = str(release.get("tag_name") or "").lstrip("vV")
            asset = next((a for a in release.get("assets", []) if a.get("name") == PLUGIN_ASSET), None)
            info["plugin_current"] = self._plugin_version()
            info["plugin_latest"] = tag or None
            info["plugin_update"] = bool(tag and asset) and _version_key(tag) > _version_key(self._plugin_version())
            if asset:
                info["plugin_url"] = asset.get("browser_download_url")
                digest = str(asset.get("digest") or "")
                info["plugin_hash"] = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
            info["plugin_notes_url"] = release.get("html_url")
        except Exception as exc:
            info["errors"].append(f"plugin: {exc}")
        state = self._load_state()
        state["updates"] = info
        self._save_state(state)
        return info

    async def _update_loop(self):
        await asyncio.sleep(UPDATE_CHECK_FIRST_DELAY)
        while True:
            try:
                info = await asyncio.to_thread(self._check_updates_sync)
                state = self._load_state()
                notified = state.setdefault("notified", {})
                changed = False
                if info.get("anr_update") and notified.get("anr") != info.get("anr_latest"):
                    await decky.emit("anr_update_available", "anr", info.get("anr_latest"))
                    notified["anr"] = info.get("anr_latest")
                    changed = True
                if info.get("plugin_update") and notified.get("plugin") != info.get("plugin_latest"):
                    await decky.emit("anr_update_available", "plugin", info.get("plugin_latest"))
                    notified["plugin"] = info.get("plugin_latest")
                    changed = True
                if changed:
                    self._save_state(state)
                if info.get("errors"):
                    decky.logger.info(f"[ANR] update check: {info['errors']}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                decky.logger.error(f"[ANR] update loop: {exc}")
            await asyncio.sleep(UPDATE_CHECK_INTERVAL)

    async def check_updates(self, force: bool = False) -> dict:
        try:
            cached = self._load_state().get("updates") or {}
            fresh = False
            if cached.get("checked_at"):
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["checked_at"])
                fresh = age.total_seconds() < 3600
            info = cached if (fresh and not force) else await asyncio.to_thread(self._check_updates_sync)
            # Re-evaluate against what is installed now (a download may have happened since).
            installed = self._installed_versions()
            if info.get("anr_latest"):
                info["anr_update"] = _version_key(info["anr_latest"]) > _version_key(installed[-1] if installed else "")
            info["plugin_current"] = self._plugin_version()
            if info.get("plugin_latest"):
                info["plugin_update"] = bool(info.get("plugin_url")) and (
                    _version_key(info["plugin_latest"]) > _version_key(self._plugin_version()))
            return {"status": "success", **info}
        except Exception as exc:
            decky.logger.error(f"[ANR] check_updates: {exc}")
            return {"status": "error", "message": str(exc)}

    def _outdated_games(self) -> list[dict]:
        active = self._active_version()
        result = []
        for appid, entry in self._load_state().get("games", {}).items():
            if entry.get("version") and active and entry["version"] != active:
                result.append({"appid": appid, "name": entry.get("name", appid), "version": entry["version"]})
        return result

    async def list_outdated_games(self) -> dict:
        try:
            return {"status": "success", "games": self._outdated_games(), "active_version": self._active_version()}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "games": []}

    def _update_all(self) -> dict:
        updated, skipped = [], []
        for game in self._outdated_games():
            info = self._game(game["appid"])
            if not info or self._is_running(info):
                skipped.append(f"{game['name']} (running)" if info else game["name"])
                continue
            entry = self._load_state()["games"].get(game["appid"], {})
            # The proxy and launch options stay the same; install.sh replaces ANR FG and OptiScaler in place.
            r = self._patch(game["appid"], "", entry.get("target_dir", ""))
            (updated if r.get("status") == "success" else skipped).append(game["name"])
        msg = f"Updated: {', '.join(updated) or 'none'}" + (f". Skipped: {', '.join(skipped)}" if skipped else "")
        return {"status": "success", "updated": updated, "skipped": skipped, "message": msg}

    async def update_all_games(self) -> dict:
        try:
            return await asyncio.to_thread(self._update_all)
        except Exception as exc:
            decky.logger.error(f"[ANR] update_all_games: {exc}")
            return {"status": "error", "message": str(exc)}

    async def _uninstall(self):
        decky.logger.info("[ANR] plugin uninstalled; games keep ANR FG until they are unpatched")

    # ── Paths and state ───────────────────────────────────────────────────────

    def _runtime_dir(self) -> Path:
        return Path(decky.DECKY_PLUGIN_RUNTIME_DIR)

    def _packages_dir(self) -> Path:
        return self._runtime_dir() / "packages"

    def _state_path(self) -> Path:
        return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "state.json"

    def _load_state(self) -> dict:
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("games", {})
                return data
        except FileNotFoundError:
            pass
        except Exception as exc:
            decky.logger.error(f"[ANR] state.json unreadable: {exc}")
        return {"active_version": None, "games": {}}

    def _save_state(self, state: dict) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)

    def _home(self) -> Path:
        return Path(str(decky.HOME))

    # ── Packages ──────────────────────────────────────────────────────────────

    def _package_dir(self, version: str, kind: str) -> Path:
        return self._packages_dir() / version / kind

    def _installed_versions(self) -> list[str]:
        root = self._packages_dir()
        if not root.exists():
            return []
        versions = [p.name for p in root.iterdir() if (p / "full" / "install.sh").exists()]
        return sorted(versions, key=_version_key)

    def _active_version(self) -> str | None:
        state = self._load_state()
        active = state.get("active_version")
        installed = self._installed_versions()
        if active in installed:
            return active
        return installed[-1] if installed else None

    def _safe_extract(self, archive: Path, dest: Path) -> None:
        tmp = dest.with_name(dest.name + ".partial")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        root = tmp.resolve()
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                target = (tmp / member.filename).resolve()
                if root != target and root not in target.parents:
                    raise ValueError(f"unsafe path in {archive.name}: {member.filename}")
            zf.extractall(tmp)
        for script in tmp.glob("*.sh"):
            script.chmod(0o755)
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(tmp, dest)

    def _add_package(self, version: str, kind: str, archive: Path) -> None:
        dest = self._package_dir(version, kind)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._safe_extract(archive, dest)
        if not (dest / "install.sh").exists():
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError(f"{archive.name} has no install.sh")
        decky.logger.info(f"[ANR] package {version} {kind} ready in {dest}")

    def _bundled_archives(self) -> dict[str, dict[str, Path]]:
        found: dict[str, dict[str, Path]] = {}
        bin_dir = Path(decky.DECKY_PLUGIN_DIR) / "bin"
        if bin_dir.exists():
            for archive in bin_dir.glob("anr-fg-*.zip"):
                m = PACKAGE_RE.match(archive.name)
                if m:
                    found.setdefault(m["version"], {})[m["kind"]] = archive
        return found

    def _ensure_bundled_package(self) -> str | None:
        bundled = self._bundled_archives()
        installed = set(self._installed_versions())
        for version, kinds in bundled.items():
            if version in installed:
                continue
            for kind, archive in kinds.items():
                self._add_package(version, kind, archive)
        state = self._load_state()
        versions = self._installed_versions()
        if versions and state.get("active_version") not in versions:
            state["active_version"] = versions[-1]
            self._save_state(state)
        elif bundled and versions:
            newest_bundled = max(bundled, key=_version_key)
            if _version_key(newest_bundled) > _version_key(state.get("active_version") or ""):
                state["active_version"] = newest_bundled
                self._save_state(state)
        return self._active_version()

    def _package_info(self, version: str | None) -> dict:
        if not version:
            return {}
        try:
            with open(self._package_dir(version, "full") / "nr_fg_package.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _ssl_context(self) -> ssl.SSLContext:
        # Decky's bundled Python has no CA store of its own: use the system's bundle.
        for cafile in CA_BUNDLES:
            if os.path.exists(cafile):
                return ssl.create_default_context(cafile=cafile)
        return ssl.create_default_context()

    def _http_get(self, url: str, accept: str = "application/octet-stream") -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=60, context=self._ssl_context()) as resp:
                return resp.read()
        except Exception as exc:
            curl = shutil.which("curl") or ("/usr/bin/curl" if os.path.exists("/usr/bin/curl") else None)
            if not curl:
                raise
            decky.logger.info(f"[ANR] urllib failed ({exc}); retrying with curl")
            env = dict(os.environ)
            env.pop("LD_LIBRARY_PATH", None)
            proc = subprocess.run(
                [curl, "-fsSL", "--max-time", "300", "-A", USER_AGENT, "-H", f"Accept: {accept}", url],
                capture_output=True, timeout=320, env=env,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"curl: {proc.stderr.decode('utf-8', 'replace').strip()}") from exc
            return proc.stdout

    def _download_latest(self) -> dict:
        release = json.loads(self._http_get(GITHUB_API_LATEST, "application/vnd.github+json"))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        wanted: dict[str, tuple[str, str]] = {}
        for name, url in assets.items():
            m = PACKAGE_RE.match(name)
            if m:
                wanted[m["kind"]] = (name, url)
                version = m["version"]
        if "full" not in wanted:
            raise ValueError(f"release {release.get('tag_name')} has no anr-fg-*-full.zip")
        if version in self._installed_versions():
            return {"version": version, "downloaded": False}
        sums: dict[str, str] = {}
        if "SHA256SUMS.txt" in assets:
            for line in self._http_get(assets["SHA256SUMS.txt"]).decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    sums[parts[1].lstrip("*")] = parts[0].lower()
        download_dir = self._runtime_dir() / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        for kind, (name, url) in wanted.items():
            data = self._http_get(url)
            digest = hashlib.sha256(data).hexdigest()
            if name in sums and sums[name] != digest:
                raise ValueError(f"{name}: SHA256 does not match SHA256SUMS.txt")
            archive = download_dir / name
            archive.write_bytes(data)
            try:
                self._add_package(version, kind, archive)
            finally:
                archive.unlink(missing_ok=True)
        return {"version": version, "downloaded": True}

    async def get_anr_info(self) -> dict:
        try:
            version = self._active_version()
            info = self._package_info(version)
            return {
                "status": "success",
                "installed": version is not None,
                "version": version,
                "versions": self._installed_versions(),
                "built_at": info.get("built_at"),
                "optiscaler": info.get("optiscaler"),
            }
        except Exception as exc:
            decky.logger.error(f"[ANR] get_anr_info: {exc}")
            return {"status": "error", "message": str(exc)}

    async def install_bundled(self) -> dict:
        try:
            version = await asyncio.to_thread(self._ensure_bundled_package)
            if not version:
                return {"status": "error", "message": "No ANR FG package in the plugin's bin folder."}
            return {"status": "success", "version": version, "message": f"ANR FG {version} is ready."}
        except Exception as exc:
            decky.logger.error(f"[ANR] install_bundled: {exc}")
            return {"status": "error", "message": str(exc)}

    async def update_from_github(self) -> dict:
        try:
            result = await asyncio.to_thread(self._download_latest)
            version = result["version"]
            state = self._load_state()
            previous = state.get("active_version")
            state["active_version"] = version
            self._save_state(state)
            if result["downloaded"]:
                msg = f"Downloaded ANR FG {version}. Patch games again to update them."
            elif previous == version:
                msg = f"ANR FG {version} is the newest release."
            else:
                msg = f"Switched to ANR FG {version}."
            return {"status": "success", "version": version, "message": msg}
        except Exception as exc:
            decky.logger.error(f"[ANR] update_from_github: {exc}")
            return {"status": "error", "message": f"Update failed: {exc}"}

    async def set_active_version(self, version: str) -> dict:
        if version not in self._installed_versions():
            return {"status": "error", "message": f"ANR FG {version} is not downloaded."}
        state = self._load_state()
        state["active_version"] = version
        self._save_state(state)
        return {"status": "success", "version": version, "message": f"New patches use ANR FG {version}."}

    # ── Steam library ─────────────────────────────────────────────────────────

    def _steam_library_paths(self) -> list[Path]:
        home = self._home()
        roots = [
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".steam" / "root",
            home / ".var" / "app" / "com.valvesoftware.Steam" / "home" / ".local" / "share" / "Steam",
        ]
        libraries: list[Path] = []
        seen: set[str] = set()

        def add(p: Path) -> None:
            try:
                key = str(p.resolve())
            except Exception:
                key = str(p)
            if key not in seen and p.exists():
                seen.add(key)
                libraries.append(p)

        for root in roots:
            add(root)
            vdf = root / "steamapps" / "libraryfolders.vdf"
            if not vdf.exists():
                continue
            try:
                for line in vdf.read_text(encoding="utf-8", errors="replace").splitlines():
                    if '"path"' in line:
                        add(Path(line.split('"path"', 1)[1].strip().strip('"').replace("\\\\", "/")))
            except Exception as exc:
                decky.logger.error(f"[ANR] libraryfolders.vdf {vdf}: {exc}")
        return libraries

    def _find_games(self, appid: str | None = None) -> list[dict]:
        games: dict[str, dict] = {}
        for library in self._steam_library_paths():
            steamapps = library / "steamapps"
            for manifest in steamapps.glob("appmanifest_*.acf"):
                info = {"appid": "", "name": "", "installdir": ""}
                try:
                    for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
                        for key in info:
                            token = f'"{key}"'
                            if line.strip().startswith(token) and not info[key]:
                                info[key] = line.split(token, 1)[1].strip().strip('"')
                except Exception:
                    continue
                if not info["appid"] or not info["name"] or not info["installdir"]:
                    continue
                if appid is not None and info["appid"] != str(appid):
                    continue
                name = info["name"]
                if name.startswith("Proton") or "Steam Linux Runtime" in name or "Steamworks" in name:
                    continue
                games[info["appid"]] = {
                    "appid": info["appid"],
                    "name": name,
                    "install_path": str(steamapps / "common" / info["installdir"]),
                }
        return sorted(games.values(), key=lambda g: g["name"].lower())

    def _game(self, appid: str) -> dict | None:
        found = self._find_games(str(appid))
        return found[0] if found else None

    # ── Executable folder detection ───────────────────────────────────────────

    def _exes(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        result = []
        try:
            for exe in root.rglob("*.exe"):
                if exe.is_file() and "/_commonredist/" not in str(exe).lower():
                    result.append(exe)
        except Exception as exc:
            decky.logger.error(f"[ANR] exe scan {root}: {exc}")
        return result

    def _exe_score(self, exe: Path, root: Path, game_name: str) -> int:
        path = str(exe).lower().replace("\\", "/")
        name = exe.name.lower()
        score = 0
        if name.endswith("-win64-shipping.exe"):
            score += 300
        if "shipping.exe" in name:
            score += 220
        if "/binaries/win64/" in path:
            score += 200
        if "/win64/" in path or "/x64/" in path:
            score += 80
        if exe.parent == root:
            score += 20
        clean = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        if clean(game_name) and clean(game_name) in clean(exe.stem):
            score += 120
        if clean(root.name) and clean(root.name) in clean(exe.stem):
            score += 90
        rel = path[len(str(root).lower()):]
        for bad in BAD_EXE_SUBSTRINGS:
            if bad in rel:
                score -= 200
        try:
            score += min(exe.stat().st_size // (16 * 1024 * 1024), 20)
        except OSError:
            pass
        return score - len(exe.parts)

    def _running_exe(self, candidates: list[Path]) -> Path | None:
        if not candidates:
            return None
        try:
            lines = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True).stdout.splitlines()
        except Exception:
            return None
        norm = lambda s: s.lower().replace("\\", "/").replace("z:/", "/")
        best: tuple[int, Path] | None = None
        for line in map(norm, lines):
            for exe in candidates:
                n = norm(str(exe))
                if n in line and (best is None or len(n) > best[0]):
                    best = (len(n), exe)
        return best[1] if best else None

    def _candidate_dirs(self, game: dict) -> list[dict]:
        root = Path(game["install_path"])
        exes = self._exes(root)
        ranked = sorted(exes, key=lambda e: self._exe_score(e, root, game["name"]), reverse=True)
        dirs: list[dict] = []
        seen: set[str] = set()
        for exe in ranked:
            d = str(exe.parent)
            if d in seen:
                continue
            seen.add(d)
            rel = os.path.relpath(exe, root)
            dirs.append({"dir": d, "exe": rel})
            if len(dirs) >= 8:
                break
        return dirs

    def _is_running(self, game: dict) -> bool:
        return self._running_exe(self._exes(Path(game["install_path"]))) is not None

    # ── Detection of what a folder holds ──────────────────────────────────────

    def _anr_dirs(self, root: Path) -> list[Path]:
        """Our installs under a game's folder: the record next to OptiScaler (full) or in custom/ (add-on)."""
        found = []
        if not root.exists():
            return found
        for depth_glob in ("*", "*/*", "*/*/*", "*/*/*/*", "*/*/*/*/*", "*/*/*/*/*/*"):
            for record in root.glob(f"{depth_glob}/{INSTALL_RECORD}"):
                found.append(record.parent)
        return found

    def _describe_dir(self, target: Path) -> dict:
        full_record = target / "OptiScaler" / INSTALL_RECORD
        addon_dest = None
        for base in (target / "OptiScaler" / "custom", target / "custom"):
            for name in (ANR_DIR_NAME, LEGACY_ANR_DIR_NAME):
                if (base / name / INSTALL_RECORD).exists():
                    addon_dest = base / name
        mode = None
        proxy = None
        if full_record.exists():
            mode = "full"
            try:
                proxy = json.loads(full_record.read_text(encoding="utf-8")).get("proxy") or "dxgi.dll"
            except Exception:
                proxy = "dxgi.dll"
        elif addon_dest is not None:
            mode = "addon"
        anr_dir = None
        if mode == "full":
            anr_dir = target / "OptiScaler" / "custom" / ANR_DIR_NAME
        elif addon_dest is not None:
            anr_dir = addon_dest
        return {
            "mode": mode,
            "proxy": proxy,
            "anr_dir": anr_dir,
            "framegen": (target / FRAMEGEN_MARKER).exists(),
            "foreign_optiscaler": (target / "OptiScaler.ini").exists() and mode is None,
        }

    def _optiscaler_supports_custom_fg(self, target: Path) -> bool:
        for name in OPTISCALER_PROXY_NAMES:
            f = target / name
            try:
                if f.is_file() and b"FGNvngxReplacement" in f.read_bytes():
                    return True
            except OSError:
                continue
        return False

    def _provider_sha(self, anr_dir: Path | None) -> str | None:
        if not anr_dir:
            return None
        dll = anr_dir / "dlssg" / "nvngx_dlssg.dll"
        if not dll.exists():
            return None
        h = hashlib.sha256()
        with open(dll, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _version_of_provider(self, sha: str | None) -> str | None:
        if not sha:
            return None
        for version in self._installed_versions():
            if self._package_info(version).get("provider_sha256") == sha:
                return version
        return None

    # ── Launch options ────────────────────────────────────────────────────────

    _OVERRIDE_RE = re.compile(r"WINEDLLOVERRIDES=(\"[^\"]*\"|'[^']*'|\S*)")

    def _launch_with_override(self, current: str, proxy: str) -> str:
        base = proxy[:-4] if proxy.lower().endswith(".dll") else proxy
        ours = f"{base}=n,b"
        current = (current or "").strip()
        m = self._OVERRIDE_RE.search(current)
        if m:
            parts = [p for p in m.group(1).strip("\"'").split(";") if p and p.split("=")[0] != base]
            value = ";".join([ours] + parts)
            result = current[: m.start()] + f'WINEDLLOVERRIDES="{value}"' + current[m.end():]
            return result if "%command%" in result else f"{result} %command%"
        if "%command%" in current:
            return f'WINEDLLOVERRIDES="{ours}" {current}'
        if current:
            return f'WINEDLLOVERRIDES="{ours}" %command% {current}'
        return f'WINEDLLOVERRIDES="{ours}" %command%'

    def _launch_without_override(self, current: str, proxy: str | None) -> str:
        current = (current or "").strip()
        if not proxy:
            return current
        base = proxy[:-4] if proxy.lower().endswith(".dll") else proxy
        m = self._OVERRIDE_RE.search(current)
        if not m:
            return current
        parts = [p for p in m.group(1).strip("\"'").split(";") if p and p != f"{base}=n,b"]
        replacement = f'WINEDLLOVERRIDES="{";".join(parts)}"' if parts else ""
        result = " ".join((current[: m.start()] + replacement + current[m.end():]).split())
        return "" if result == "%command%" else result

    # ── nr_fg.ini ─────────────────────────────────────────────────────────────

    def _read_ini(self, path: Path) -> dict:
        values = {}
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s and not s.startswith((";", "#", "[")) and "=" in s:
                    k, v = s.split("=", 1)
                    values[k.strip()] = v.strip()
        except FileNotFoundError:
            pass
        return values

    def _write_ini_value(self, path: Path, key: str, value: str) -> None:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        done = False
        for i, line in enumerate(lines):
            s = line.strip()
            if not s.startswith((";", "#")) and "=" in s and s.split("=", 1)[0].strip() == key:
                lines[i] = f"{key} = {value}"
                done = True
        if not done:
            lines.append(f"{key} = {value}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Running the official scripts ──────────────────────────────────────────

    def _run_script(self, script: Path, target: Path) -> tuple[bool, str]:
        env = dict(os.environ)
        env["PATH"] = env.get("PATH", "") + ":/usr/local/bin:/usr/bin:/bin"
        env.pop("LD_LIBRARY_PATH", None)
        proc = subprocess.run(
            ["sh", str(script), str(target)],
            cwd=str(script.parent),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        output = (proc.stdout + proc.stderr).strip()
        decky.logger.info(f"[ANR] {script.parent.name}/{script.name} {target}: rc={proc.returncode} {output}")
        return proc.returncode == 0, output

    # ── Proton ────────────────────────────────────────────────────────────────

    def _compat_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for library in self._steam_library_paths():
            cfg = library / "config" / "config.vdf"
            if not cfg.exists():
                continue
            try:
                text = cfg.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            start = text.find('"CompatToolMapping"')
            if start < 0:
                continue
            # The block ends where its braces balance.
            i = text.find("{", start)
            depth, j = 0, i
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            for m in re.finditer(r'"(\d+)"\s*\{\s*"name"\s*"([^"]*)"', text[i:j]):
                mapping[m.group(1)] = m.group(2)
            if mapping:
                break
        return mapping

    def _proton_info(self, game: dict) -> dict:
        mapping = self._compat_mapping()
        appid = str(game["appid"])
        tool = mapping.get(appid) or ""
        source = "game"
        if not tool:
            tool = mapping.get("0") or ""
            source = "default"
        prefix = None
        version_file = Path(game["install_path"]).parent.parent / "compatdata" / appid / "version"
        try:
            prefix = version_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
        has_exe = bool(self._exes(Path(game["install_path"])))
        native = not has_exe
        return {"tool": tool or None, "source": source, "prefix": prefix, "native": native}

    # ── Frontend API: games ───────────────────────────────────────────────────

    async def list_games(self) -> dict:
        try:
            state = self._load_state()
            games = []
            for g in self._find_games():
                games.append({
                    "appid": g["appid"],
                    "name": g["name"],
                    "installed": Path(g["install_path"]).exists(),
                    "patched": g["appid"] in state.get("games", {}),
                })
            return {"status": "success", "games": games}
        except Exception as exc:
            decky.logger.error(f"[ANR] list_games: {exc}")
            return {"status": "error", "message": str(exc), "games": []}

    def _resolve_target(self, game: dict, state_entry: dict | None) -> Path | None:
        if state_entry and state_entry.get("target_dir") and Path(state_entry["target_dir"]).exists():
            return Path(state_entry["target_dir"])
        existing = self._anr_dirs(Path(game["install_path"]))
        for anr in existing:
            # full: <target>/OptiScaler/nr_fg_install.json; add-on: <...>/custom/<ANR>/nr_fg_install.json
            if anr.name == "OptiScaler":
                return anr.parent
            if anr.parent.name == "custom":
                base = anr.parent.parent
                return base.parent if base.name == "OptiScaler" else base
        return None

    def _game_status(self, appid: str) -> dict:
        game = self._game(appid)
        if not game:
            return {"status": "error", "message": "The game is not in the Steam library."}
        root = Path(game["install_path"])
        if not root.exists():
            return {"status": "success", "appid": appid, "name": game["name"], "installed": False,
                    "patched": False, "candidates": []}
        state = self._load_state()
        entry = state["games"].get(str(appid))
        target = self._resolve_target(game, entry)
        candidates = self._candidate_dirs(game)
        if target is None:
            return {
                "status": "success", "appid": appid, "name": game["name"], "installed": True,
                "patched": False, "candidates": candidates,
                "suggested_dir": candidates[0]["dir"] if candidates else str(root),
                "conflict": self._conflict_message(Path(candidates[0]["dir"])) if candidates else None,
                "running": self._is_running(game),
                "proton": self._proton_info(game),
            }
        desc = self._describe_dir(target)
        settings = {}
        log_file = None
        if desc["anr_dir"]:
            ini = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
            raw = self._read_ini(ini)
            settings = {k: raw.get(k) for k in NR_FG_SETTINGS}
            logs = sorted((desc["anr_dir"] / "dlssg").glob("nr_fg-*.log"), key=lambda p: p.stat().st_mtime)
            log_file = str(logs[-1]) if logs else None
        sha = self._provider_sha(desc["anr_dir"])
        game_version = self._version_of_provider(sha) or (entry or {}).get("version")
        return {
            "status": "success",
            "appid": appid,
            "name": game["name"],
            "installed": True,
            "patched": desc["mode"] is not None,
            "mode": desc["mode"],
            "proxy": desc["proxy"] or (entry or {}).get("proxy"),
            "target_dir": str(target),
            "target_rel": os.path.relpath(target, root),
            "game_version": game_version,
            "active_version": self._active_version(),
            "settings": settings,
            "log_file": log_file,
            "candidates": candidates,
            "suggested_dir": str(target),
            "running": self._is_running(game),
            "proton": self._proton_info(game),
        }

    def _conflict_message(self, target: Path) -> str | None:
        desc = self._describe_dir(target)
        if desc["framegen"]:
            return ("Decky Framegen has patched this folder. Its OptiScaler 0.9.4 cannot load ANR FG: "
                    "unpatch the game in Decky Framegen first.")
        if desc["foreign_optiscaler"]:
            if self._optiscaler_supports_custom_fg(target):
                return "OptiScaler is already here: ANR FG will be added to it as a custom provider (add-on)."
            return ("An OptiScaler without custom frame generation providers is here. Remove it first, or "
                    "update it to a build with FGNvngxReplacement.")
        return None

    async def get_game_status(self, appid: str) -> dict:
        try:
            return await asyncio.to_thread(self._game_status, str(appid))
        except Exception as exc:
            decky.logger.error(f"[ANR] get_game_status {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    def _patch(self, appid: str, current_launch_options: str, target_dir: str) -> dict:
        version = self._active_version()
        if not version:
            return {"status": "error", "message": "ANR FG is not set up yet."}
        game = self._game(appid)
        if not game:
            return {"status": "error", "message": "The game is not in the Steam library."}
        root = Path(game["install_path"]).resolve()
        if self._is_running(game):
            return {"status": "error", "message": "Close the game first."}
        state = self._load_state()
        entry = state["games"].get(appid)
        if target_dir:
            target = Path(target_dir).resolve()
        else:
            target = self._resolve_target(game, entry)
            if target is None:
                candidates = self._candidate_dirs(game)
                if not candidates:
                    return {"status": "error", "message": "No .exe found in the game's folder."}
                target = Path(candidates[0]["dir"])
        if target != root and root not in target.parents:
            return {"status": "error", "message": "The folder is outside the game's install folder."}
        if not any(target.glob("*.exe")):
            return {"status": "error", "message": f"No .exe in {target}."}

        # A different folder of the same game is patched: unpatch it first.
        if entry and entry.get("target_dir") and Path(entry["target_dir"]) != target:
            old = Path(entry["target_dir"])
            if old.exists() and self._describe_dir(old)["mode"]:
                self._unpatch_dir(old, entry.get("version") or version)

        desc = self._describe_dir(target)
        if desc["framegen"]:
            return {"status": "error", "message": self._conflict_message(target)}
        if desc["mode"] == "addon" or (desc["foreign_optiscaler"]):
            if desc["mode"] is None and not self._optiscaler_supports_custom_fg(target):
                return {"status": "error", "message": self._conflict_message(target)}
            kind = "addon"
        else:
            kind = "full"
        package = self._package_dir(version, kind)
        if not (package / "install.sh").exists():
            return {"status": "error", "message": f"ANR FG {version} has no {kind} package."}
        ok, output = self._run_script(package / "install.sh", target)
        if not ok:
            return {"status": "error", "message": output.splitlines()[-1] if output else "install.sh failed",
                    "output": output}
        desc = self._describe_dir(target)
        preferred = self._load_state().get("preferred_path")
        if preferred and desc["anr_dir"]:
            ini = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
            if ini.exists() and self._read_ini(ini).get("path", "auto") == "auto":
                self._write_ini_value(ini, "path", preferred)
        proxy = desc["proxy"] if kind == "full" else None
        launch_options = (
            self._launch_with_override(current_launch_options, proxy) if proxy else current_launch_options
        )
        previous = state["games"].get(appid, {})
        state["games"][appid] = {
            "upscaler": previous.get("upscaler"),
            "render_quality": previous.get("render_quality"),
            "opti": previous.get("opti", {}),
            "upscaler_watermark": previous.get("upscaler_watermark", False),
            "managed_files": previous.get("managed_files", []),
            "name": game["name"],
            "target_dir": str(target),
            "mode": kind,
            "proxy": proxy,
            "version": version,
            "original_launch_options": (entry or {}).get("original_launch_options", current_launch_options),
            "patched_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_state(state)
        try:
            self._reapply_upscaler(appid, target)
        except Exception as exc:
            decky.logger.error(f"[ANR] re-applying the upscaler for {appid}: {exc}")
        return {
            "status": "success",
            "launch_options": launch_options,
            "mode": kind,
            "proxy": proxy,
            "output": output,
            "message": f"ANR FG {version} installed in {game['name']}"
                       + (f" (OptiScaler as {proxy})." if proxy else " as an OptiScaler add-on."),
        }

    async def patch_game(self, appid: str, current_launch_options: str = "", target_dir: str = "") -> dict:
        try:
            return await asyncio.to_thread(self._patch, str(appid), current_launch_options or "", target_dir or "")
        except Exception as exc:
            decky.logger.error(f"[ANR] patch_game {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    def _unpatch_dir(self, target: Path, version: str) -> tuple[bool, str]:
        desc = self._describe_dir(target)
        if not desc["mode"]:
            return True, "nothing to remove"
        package = self._package_dir(version, desc["mode"])
        if not (package / "uninstall.sh").exists():
            active = self._active_version()
            package = self._package_dir(active, desc["mode"]) if active else package
        if not (package / "uninstall.sh").exists():
            return False, f"no {desc['mode']} uninstaller available"
        return self._run_script(package / "uninstall.sh", target)

    def _unpatch(self, appid: str, current_launch_options: str) -> dict:
        game = self._game(appid)
        if not game:
            return {"status": "error", "message": "The game is not in the Steam library."}
        if self._is_running(game):
            return {"status": "error", "message": "Close the game first."}
        state = self._load_state()
        entry = state["games"].get(appid)
        target = self._resolve_target(game, entry)
        proxy = (entry or {}).get("proxy")
        output = ""
        if target is not None:
            desc = self._describe_dir(target)
            proxy = desc["proxy"] or proxy
            ok, output = self._unpatch_dir(target, (entry or {}).get("version") or self._active_version() or "")
            if not ok:
                return {"status": "error", "message": output.splitlines()[-1] if output else "uninstall failed",
                        "output": output}
        self._remove_managed_files(appid)
        state = self._load_state()
        state["games"].pop(appid, None)
        self._save_state(state)
        return {
            "status": "success",
            "launch_options": self._launch_without_override(current_launch_options, proxy),
            "output": output,
            "message": f"ANR FG removed from {game['name']}.",
        }

    async def unpatch_game(self, appid: str, current_launch_options: str = "") -> dict:
        try:
            return await asyncio.to_thread(self._unpatch, str(appid), current_launch_options or "")
        except Exception as exc:
            decky.logger.error(f"[ANR] unpatch_game {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def set_game_setting(self, appid: str, key: str, value: str) -> dict:
        try:
            spec = NR_FG_SETTINGS.get(key)
            if not spec:
                return {"status": "error", "message": f"Unknown setting {key}"}
            value = str(value)
            if spec["type"] == "int":
                n = int(value)
                if not spec["min"] <= n <= spec["max"]:
                    return {"status": "error", "message": f"{key} must be {spec['min']}..{spec['max']}"}
                value = str(n)
            elif value not in spec["values"]:
                return {"status": "error", "message": f"{key} must be one of {', '.join(spec['values'])}"}
            game = self._game(str(appid))
            if not game:
                return {"status": "error", "message": "The game is not in the Steam library."}
            target = self._resolve_target(game, self._load_state()["games"].get(str(appid)))
            desc = self._describe_dir(target) if target else None
            if not desc or not desc["anr_dir"]:
                return {"status": "error", "message": "ANR FG is not installed in this game."}
            ini = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
            if not ini.exists():
                return {"status": "error", "message": f"{ini} is missing."}
            self._write_ini_value(ini, key, value)
            return {"status": "success", "message": f"{key} = {value}. Restart the game to apply."}
        except Exception as exc:
            decky.logger.error(f"[ANR] set_game_setting {appid} {key}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def read_game_log(self, appid: str, lines: int = 40) -> dict:
        try:
            status = await asyncio.to_thread(self._game_status, str(appid))
            log_file = status.get("log_file")
            if not log_file:
                return {"status": "success", "log": "", "message": "No nr_fg log yet: start the game with FG on."}
            text = Path(log_file).read_text(encoding="utf-8", errors="replace").splitlines()
            return {"status": "success", "log": "\n".join(text[-int(lines):]), "path": log_file}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Performance from nr_fg logs ───────────────────────────────────────────

    _RE_READY = re.compile(r"our frame generation ready for (\S+) colors \((\S+?), ")
    _RE_FEATURE = re.compile(r"frame generation feature: (\d+)x(\d+)")
    _RE_MEDIANS = re.compile(
        r"GPU ms \(medians[^)]*\): frame in ([\d.]+) pair ([\d.]+), per generated frame phase ([\d.]+) "
        r"out ([\d.]+), (\d+)X \((\d+) generated evaluations, (\d+) generation errors\)")

    @staticmethod
    def _log_seconds(line: str) -> float | None:
        m = re.match(r"\[(\d+):(\d+):(\d+(?:\.\d+)?)\]", line)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None

    def _parse_session(self, log: Path) -> dict | None:
        """One game launch: the path, ANR's GPU cost from its medians, and the real frame rate from how many
        frames it generated while frame generation ran (each feature from 'ready' to its last medians line)."""
        paths: list[str] = []
        res = None
        pairs: list[float] = []
        gens: list[float] = []
        mult = None
        errors = 0
        feature_start = None
        feature_last: tuple[float, int] | None = None
        gen_total = 0
        seconds_total = 0.0

        def close_feature() -> None:
            nonlocal gen_total, seconds_total, feature_last
            if feature_start is not None and feature_last is not None:
                dt = feature_last[0] - feature_start
                if dt > 10:  # skip short menu blips
                    gen_total += feature_last[1]
                    seconds_total += dt
            feature_last = None

        try:
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = self._RE_READY.search(line)
                    if m:
                        close_feature()
                        paths.append(m.group(2))
                        feature_start = self._log_seconds(line)
                        continue
                    m = self._RE_FEATURE.search(line)
                    if m:
                        res = f"{m.group(1)}x{m.group(2)}"
                        continue
                    m = self._RE_MEDIANS.search(line)
                    if m:
                        pair, phase, out = float(m.group(2)), float(m.group(3)), float(m.group(4))
                        if pair > 0 and phase > 0:
                            pairs.append(pair)
                            gens.append(phase + out)
                        mult = int(m.group(5))
                        errors = max(errors, int(m.group(7)))
                        t = self._log_seconds(line)
                        if t is not None and feature_start is not None:
                            feature_last = (t, int(m.group(6)))
                        if "final" in line:
                            close_feature()
                            feature_start = None
            close_feature()
        except OSError:
            return None
        if not paths:
            return None
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
        gen = med(gens)
        pair = med(pairs)
        real_fps = None
        if seconds_total > 0 and mult and mult > 1:
            real_fps = round(gen_total / (mult - 1) / seconds_total, 1)
        return {
            "log": log.name,
            "started": log.stem.replace("nr_fg-", ""),
            "path": paths[-1],
            "resolution": res,
            "multiplier": mult,
            "pair_ms": round(pair, 2) if pair is not None else None,
            "gen_ms": round(gen, 2) if gen is not None else None,
            "total_ms": round(pair + gen * (mult - 1), 2) if pair is not None and gen is not None and mult else None,
            "real_fps": real_fps,
            "shown_fps": round(real_fps * mult, 1) if real_fps and mult else None,
            "seconds": round(seconds_total),
            "evaluations": gen_total,
            "errors": errors,
            "samples": len(pairs),
        }

    def _performance(self, appid: str, limit: int) -> dict:
        game = self._game(appid)
        if not game:
            return {"status": "error", "message": "The game is not in the Steam library.", "sessions": []}
        target = self._resolve_target(game, self._load_state()["games"].get(appid))
        desc = self._describe_dir(target) if target else None
        if not desc or not desc["anr_dir"]:
            return {"status": "success", "sessions": [], "message": "ANR FG is not installed in this game."}
        logs = sorted((desc["anr_dir"] / "dlssg").glob("nr_fg-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        sessions = []
        for log in logs:
            parsed = self._parse_session(log)
            if parsed:
                sessions.append(parsed)
            if len(sessions) >= limit:
                break
        by_path: dict[str, list[dict]] = {}
        for sess in sessions:
            if sess["total_ms"] is not None:
                by_path.setdefault(sess["path"], []).append(sess)
        summary = []
        for path, items in by_path.items():
            totals = sorted(x["total_ms"] for x in items)
            fps = sorted(x["real_fps"] for x in items if x["real_fps"])
            summary.append({
                "path": path,
                "sessions": len(items),
                "total_ms": totals[len(totals) // 2],
                "real_fps": fps[len(fps) // 2] if fps else None,
            })
        summary.sort(key=lambda x: x["total_ms"])
        return {"status": "success", "sessions": sessions, "summary": summary}

    async def get_performance(self, appid: str, limit: int = 8) -> dict:
        try:
            return await asyncio.to_thread(self._performance, str(appid), int(limit))
        except Exception as exc:
            decky.logger.error(f"[ANR] get_performance {appid}: {exc}")
            return {"status": "error", "message": str(exc), "sessions": []}

    # ── Upscaler (OptiScaler) ─────────────────────────────────────────────────

    FSR4_DLL = "amdxcffx64.dll"
    RDNA4_DEVICE_IDS = {0x7550, 0x7551, 0x7590, 0x7591, 0x7599, 0x75A0, 0x75A3}
    UPSCALERS = {
        "package": "As in the ANR package",
        "fsr31": "FSR 3.1",
        "fsr4": "FSR 4 (ML)",
        "xess": "XeSS",
    }
    # OptiScaler [UpscaleRatio]: output size divided by render size, per axis.
    RENDER_QUALITY = {
        "game": ("As set in the game", None),
        "ultra_quality": ("Ultra Quality", 1.3),
        "quality": ("Quality", 1.5),
        "balanced": ("Balanced", 1.7),
        "performance": ("Performance", 2.0),
        "ultra_performance": ("Ultra Performance", 3.0),
    }

    def _optiscaler_ini(self, target: Path, desc: dict) -> Path | None:
        if desc.get("mode") == "full":
            return target / "OptiScaler.ini"
        if desc.get("mode") == "addon" and desc.get("anr_dir"):
            try:
                rec = json.loads((desc["anr_dir"] / INSTALL_RECORD).read_text(encoding="utf-8"))
                ini = Path(rec.get("optiscaler_ini", ""))
                return ini if ini.exists() else None
            except Exception:
                return None
        return None

    def _optiscaler_main_dir(self, ini: Path) -> Path:
        """OptiScaler's working folder (MainDllPath), where it looks for amdxcffx64.dll and custom providers:
        [Libraries] OptiDllPath, else ./OptiScaler next to the ini where it exists, else the ini's folder
        (the same rule as ANR's add-on installer)."""
        game = ini.parent
        value = None
        section = None
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*\[([^\]]+)\]", line)
            if m:
                section = m.group(1)
            elif section == "Libraries" and re.match(r"\s*OptiDllPath\s*=", line):
                value = line.split("=", 1)[1].strip()
        if value and value.lower() != "auto":
            v = value.replace("\\", "/")
            if re.match(r"^[A-Za-z]:", v):
                v = re.sub(r"^[A-Za-z]:", "", v)  # a Windows path inside the prefix: best effort
            path = Path(v) if v.startswith("/") else game / v
            if path.is_dir():
                return path
        return game / "OptiScaler" if (game / "OptiScaler").is_dir() else game

    def _set_ini_sections(self, ini: Path, values: dict[tuple[str, str], str]) -> None:
        lines = ini.read_text(encoding="utf-8", errors="replace").split("\n")
        pending = dict(values)
        section = None
        for i, line in enumerate(lines):
            m = re.match(r"\s*\[([^\]]+)\]", line)
            if m:
                section = m.group(1)
                continue
            if "=" in line and not line.lstrip().startswith((";", "#")):
                key = line.split("=", 1)[0].strip()
                if (section, key) in pending:
                    lines[i] = f"{key}={pending.pop((section, key))}"
        for (sec, key), val in pending.items():
            header = next((i for i, l in enumerate(lines) if l.strip() == f"[{sec}]"), None)
            if header is None:
                lines += [f"[{sec}]", f"{key}={val}"]
            else:
                lines.insert(header + 1, f"{key}={val}")
        ini.write_text("\n".join(lines), encoding="utf-8")

    def _gpu_is_rdna4(self) -> bool:
        for dev in Path("/sys/class/drm").glob("card*/device"):
            try:
                if (dev / "vendor").read_text().strip().lower() != "0x1002":
                    continue
                if int((dev / "device").read_text().strip(), 16) in self.RDNA4_DEVICE_IDS:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _pe_string(data: bytes, name: str) -> str | None:
        key = name.encode("utf-16-le") + b"\x00\x00"
        i = data.find(key)
        if i < 0:
            return None
        j = i + len(key)
        while j < len(data) and data[j:j + 2] == b"\x00\x00":
            j += 2
        end = data.find(b"\x00\x00", j)
        while end > 0 and (end - j) % 2:
            end = data.find(b"\x00\x00", end + 1)
        try:
            return data[j:end].decode("utf-16-le").strip() or None
        except Exception:
            return None

    def _fsr4_dll_info(self, path: Path) -> dict | None:
        try:
            if path.stat().st_size < 1_000_000:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        if data[:2] != b"MZ":
            return None
        company = self._pe_string(data, "CompanyName") or ""
        if "Advanced Micro Devices" not in company:
            return None
        version = self._pe_string(data, "FileVersion") or "0"
        return {"path": str(path), "version": version, "size": len(data)}

    def _find_fsr4_dll(self, appid: str | None) -> dict | None:
        """Newest AMD-signed amdxcffx64.dll that Proton put into a prefix (PROTON_FFX4_UPGRADE), this game's first."""
        found: list[dict] = []
        for library in self._steam_library_paths():
            compat = library / "steamapps" / "compatdata"
            if not compat.exists():
                continue
            order = sorted(compat.iterdir(), key=lambda p: p.name != str(appid))
            for prefix in order:
                info = self._fsr4_dll_info(prefix / "pfx" / "drive_c" / "windows" / "system32" / self.FSR4_DLL)
                if info:
                    info["own_prefix"] = prefix.name == str(appid)
                    found.append(info)
        if not found:
            return None
        found.sort(key=lambda x: (_version_key(x["version"]), x["own_prefix"]), reverse=True)
        return found[0]

    def _upscaler_values(self, choice: str, watermark: bool) -> dict[tuple[str, str], str]:
        wm = "true" if watermark else "auto"
        if choice == "fsr31":
            return {("Upscalers", "Dx12Upscaler"): "ffx", ("FSR", "UpscalerIndex"): "1",
                    ("FSR", "Fsr4GpuSupport"): "auto", ("FSR", "Fsr4Model"): "auto",
                    ("FSR", "Fsr4EnableWatermark"): "auto"}
        if choice == "fsr4":
            rdna4 = self._gpu_is_rdna4()
            return {("Upscalers", "Dx12Upscaler"): "ffx", ("FSR", "UpscalerIndex"): "0",
                    ("FSR", "Fsr4GpuSupport"): "auto" if rdna4 else "2",
                    ("FSR", "Fsr4Model"): "auto" if rdna4 else "1",
                    ("FSR", "Fsr4EnableWatermark"): wm}
        if choice == "xess":
            return {("Upscalers", "Dx12Upscaler"): "xess", ("FSR", "Fsr4EnableWatermark"): "auto"}
        return {}

    def _apply_upscaler(self, appid: str, target: Path, choice: str, watermark: bool) -> dict:
        desc = self._describe_dir(target)
        ini = self._optiscaler_ini(target, desc)
        if not ini or not ini.exists():
            return {"status": "error", "message": "OptiScaler.ini not found for this game."}
        state = self._load_state()
        entry = state["games"].setdefault(appid, {})
        managed = entry.get("managed_files", [])
        dll_dest = self._optiscaler_main_dir(ini) / self.FSR4_DLL
        note = ""
        if choice == "fsr4":
            src = self._find_fsr4_dll(appid)
            if not src:
                return {"status": "error", "need_ffx4_upgrade": True,
                        "message": "No FSR 4 driver DLL on this device yet. Add PROTON_FFX4_UPGRADE=1 to the "
                                   "game's launch options (proton-cachyos or GE-Proton), start the game once, "
                                   "then choose FSR 4 again."}
            existing = self._fsr4_dll_info(dll_dest) if dll_dest.exists() else None
            ours = any(m.get("path") == str(dll_dest) for m in managed)
            if dll_dest.exists() and not ours and not existing:
                return {"status": "error", "message": f"{dll_dest.name} in the game folder is not AMD's; not replaced."}
            if not existing or _version_key(existing["version"]) < _version_key(src["version"]):
                shutil.copy2(src["path"], dll_dest)
            if not ours:
                managed.append({"path": str(dll_dest), "sha256": self._file_sha256(dll_dest)})
            note = f" (AMD FidelityFX {src['version']})"
        else:
            # Remove the DLL only if we put it there and it is unchanged.
            keep = []
            for m in managed:
                p = Path(m.get("path", ""))
                if p.name == self.FSR4_DLL and p.exists() and self._file_sha256(p) == m.get("sha256"):
                    p.unlink()
                elif p.exists():
                    keep.append(m)
            managed = keep
        values = self._upscaler_values(choice, watermark)
        if values:
            self._set_ini_sections(ini, values)
        entry["upscaler"] = choice
        entry["upscaler_watermark"] = bool(watermark)
        entry["managed_files"] = managed
        self._save_state(state)
        label = self.UPSCALERS.get(choice, choice)
        msg = f"Upscaler: {label}{note}. Restart the game."
        if choice == "package":
            msg = "Upscaler settings are as the ANR package sets them on the next reinstall. Restart the game."
        return {"status": "success", "message": msg}

    async def set_upscaler(self, appid: str, choice: str, watermark: bool = False) -> dict:
        try:
            if choice not in self.UPSCALERS:
                return {"status": "error", "message": f"Unknown upscaler {choice}"}
            game = self._game(str(appid))
            if not game:
                return {"status": "error", "message": "The game is not in the Steam library."}
            if self._is_running(game):
                return {"status": "error", "message": "Close the game first."}
            target = self._resolve_target(game, self._load_state()["games"].get(str(appid)))
            if not target:
                return {"status": "error", "message": "ANR FG is not installed in this game."}
            return await asyncio.to_thread(self._apply_upscaler, str(appid), target, choice, bool(watermark))
        except Exception as exc:
            decky.logger.error(f"[ANR] set_upscaler {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def get_upscaler(self, appid: str) -> dict:
        try:
            entry = self._load_state()["games"].get(str(appid), {})
            src = await asyncio.to_thread(self._find_fsr4_dll, str(appid))
            out = await asyncio.to_thread(self._output_size, str(appid))
            return {"status": "success", "choice": entry.get("upscaler", "package"),
                    "render_quality": entry.get("render_quality", "game"),
                    "render_options": [{"value": k, "label": v[0], "ratio": v[1]}
                                       for k, v in self.RENDER_QUALITY.items()],
                    "output": list(out) if out else None,
                    "watermark": bool(entry.get("upscaler_watermark")),
                    "fsr4_source": src, "rdna4": self._gpu_is_rdna4(),
                    "options": [{"value": k, "label": v} for k, v in self.UPSCALERS.items()]}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _apply_render_quality(self, appid: str, target: Path, choice: str) -> dict:
        desc = self._describe_dir(target)
        ini = self._optiscaler_ini(target, desc)
        if not ini or not ini.exists():
            return {"status": "error", "message": "OptiScaler.ini not found for this game."}
        label, ratio = self.RENDER_QUALITY[choice]
        self._set_ini_sections(ini, {
            ("UpscaleRatio", "UpscaleRatioOverrideEnabled"): "true" if ratio else "auto",
            ("UpscaleRatio", "UpscaleRatioOverrideValue"): str(ratio) if ratio else "auto",
        })
        state = self._load_state()
        state["games"].setdefault(appid, {})["render_quality"] = choice
        self._save_state(state)
        if ratio:
            return {"status": "success", "message": f"Render quality: {label} (1/{ratio} of the output size, "
                                                    "whatever the game's DLSS mode). Restart the game."}
        return {"status": "success", "message": "Render quality follows the game's DLSS mode. Restart the game."}

    async def set_render_quality(self, appid: str, choice: str) -> dict:
        try:
            if choice not in self.RENDER_QUALITY:
                return {"status": "error", "message": f"Unknown render quality {choice}"}
            game = self._game(str(appid))
            if not game:
                return {"status": "error", "message": "The game is not in the Steam library."}
            if self._is_running(game):
                return {"status": "error", "message": "Close the game first."}
            target = self._resolve_target(game, self._load_state()["games"].get(str(appid)))
            if not target:
                return {"status": "error", "message": "ANR FG is not installed in this game."}
            return await asyncio.to_thread(self._apply_render_quality, str(appid), target, choice)
        except Exception as exc:
            decky.logger.error(f"[ANR] set_render_quality {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    def _output_size(self, appid: str) -> tuple[int, int] | None:
        """The output size ANR last saw for this game (its log), for showing render resolutions."""
        game = self._game(appid)
        target = self._resolve_target(game, self._load_state()["games"].get(appid)) if game else None
        desc = self._describe_dir(target) if target else None
        if not desc or not desc["anr_dir"]:
            return None
        logs = sorted((desc["anr_dir"] / "dlssg").glob("nr_fg-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for log in logs[:5]:
            try:
                for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                    m = self._RE_FEATURE.search(line)
                    if m:
                        return int(m.group(1)), int(m.group(2))
            except OSError:
                continue
        return None

    # Per-game OptiScaler tuning: key -> (section, ini key, kind, extra)
    OPTI_SETTINGS = {
        "fg_multiplier": ("DLSSG", "OverrideInterpolationCount", "enum", ["auto", "1", "2", "3", "4", "5"]),
        "dynamic_mfg": ("DLSSG", "OverrideForceDMFG", "bool", None),
        "dmfg_target": ("DLSSG", "FramerateTargetDMFG", "float", (0.0, 360.0)),
        "fps_limit": ("Framerate", "FramerateLimit", "float", (0.0, 360.0)),
        "sharpness_override": ("Sharpness", "OverrideSharpness", "bool", None),
        "sharpness": ("Sharpness", "Sharpness", "float", (0.0, 1.3)),
        "show_fps": ("Menu", "ShowFps", "bool", None),
    }

    def _read_ini_sections(self, ini: Path) -> dict[tuple[str, str], str]:
        values: dict[tuple[str, str], str] = {}
        section = None
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*\[([^\]]+)\]", line)
            if m:
                section = m.group(1)
                continue
            if "=" in line and not line.lstrip().startswith((";", "#")):
                k, v = line.split("=", 1)
                values[(section, k.strip())] = v.strip()
        return values

    def _normalize_opti(self, key: str, value) -> str:
        section, ini_key, kind, extra = self.OPTI_SETTINGS[key]
        if value is None or str(value).strip().lower() in ("", "auto"):
            return "auto"
        if kind == "bool":
            return "true" if str(value).lower() in ("1", "true", "yes", "on") else "false"
        if kind == "enum":
            v = str(value)
            if v not in extra:
                raise ValueError(f"{key} must be one of {', '.join(extra)}")
            return v
        f = float(value)
        lo, hi = extra
        if not lo <= f <= hi:
            raise ValueError(f"{key} must be {lo}..{hi}")
        if f == 0 and key in ("fps_limit", "dmfg_target"):
            return "auto"
        return f"{f:g}"

    def _target_and_ini(self, appid: str) -> tuple[Path, dict, Path]:
        game = self._game(appid)
        if not game:
            raise ValueError("The game is not in the Steam library.")
        target = self._resolve_target(game, self._load_state()["games"].get(appid))
        if not target:
            raise ValueError("ANR FG is not installed in this game.")
        desc = self._describe_dir(target)
        ini = self._optiscaler_ini(target, desc)
        if not ini or not ini.exists():
            raise ValueError("OptiScaler.ini not found for this game.")
        return target, desc, ini

    def _apply_opti(self, appid: str, settings: dict[str, str]) -> None:
        target, desc, ini = self._target_and_ini(appid)
        values = {}
        for key, val in settings.items():
            section, ini_key, _, _ = self.OPTI_SETTINGS[key]
            values[(section, ini_key)] = val
        if values:
            self._set_ini_sections(ini, values)
        # A forced multiplier above what ANR offers would be capped: raise max_generated to match.
        mult = settings.get("fg_multiplier")
        if mult and mult != "auto" and desc.get("anr_dir"):
            nr = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
            if nr.exists():
                cur = int(self._read_ini(nr).get("max_generated", "1") or 1)
                if cur < int(mult):
                    self._write_ini_value(nr, "max_generated", mult)

    async def get_opti_settings(self, appid: str) -> dict:
        try:
            _, _, ini = await asyncio.to_thread(self._target_and_ini, str(appid))
            raw = self._read_ini_sections(ini)
            current = {k: raw.get((sec, ik), "auto") for k, (sec, ik, _, _) in self.OPTI_SETTINGS.items()}
            return {"status": "success", "settings": current}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "settings": {}}

    async def set_opti_setting(self, appid: str, key: str, value: str) -> dict:
        try:
            appid = str(appid)
            if key not in self.OPTI_SETTINGS:
                return {"status": "error", "message": f"Unknown setting {key}"}
            game = self._game(appid)
            if game and self._is_running(game):
                return {"status": "error", "message": "Close the game first: OptiScaler reads its settings at start."}
            val = self._normalize_opti(key, value)
            await asyncio.to_thread(self._apply_opti, appid, {key: val})
            state = self._load_state()
            entry = state["games"].setdefault(appid, {})
            opti = entry.setdefault("opti", {})
            if val == "auto":
                opti.pop(key, None)
            else:
                opti[key] = val
            self._save_state(state)
            return {"status": "success", "message": f"{key} = {val}. Restart the game to apply."}
        except Exception as exc:
            decky.logger.error(f"[ANR] set_opti_setting {appid} {key}: {exc}")
            return {"status": "error", "message": str(exc)}

    PROFILE_NR_KEYS = ("max_generated", "path", "scene_cut")

    def _export_profile(self, appid: str) -> dict:
        entry = self._load_state()["games"].get(appid, {})
        profile = {
            "upscaler": entry.get("upscaler") or "package",
            "upscaler_watermark": bool(entry.get("upscaler_watermark")),
            "render_quality": entry.get("render_quality") or "game",
            "opti": dict(entry.get("opti", {})),
            "nr_fg": {},
        }
        try:
            target, desc, _ = self._target_and_ini(appid)
            if desc.get("anr_dir"):
                raw = self._read_ini(desc["anr_dir"] / "dlssg" / "nr_fg.ini")
                profile["nr_fg"] = {k: raw[k] for k in self.PROFILE_NR_KEYS if k in raw}
        except Exception:
            pass
        return profile

    def _import_profile(self, appid: str, profile: dict) -> None:
        target, desc, ini = self._target_and_ini(appid)
        # OptiScaler tuning: write every known key (auto where the profile has none)
        opti = {k: profile.get("opti", {}).get(k, "auto") for k in self.OPTI_SETTINGS}
        self._apply_opti(appid, opti)
        state = self._load_state()
        entry = state["games"].setdefault(appid, {})
        entry["opti"] = {k: v for k, v in opti.items() if v != "auto"}
        self._save_state(state)
        self._apply_render_quality(appid, target, profile.get("render_quality") or "game")
        up = profile.get("upscaler") or "package"
        r = self._apply_upscaler(appid, target, up, bool(profile.get("upscaler_watermark")))
        if r.get("status") != "success" and up != "package":
            raise ValueError(r.get("message"))
        if desc.get("anr_dir"):
            nr = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
            for k, v in (profile.get("nr_fg") or {}).items():
                if k in self.PROFILE_NR_KEYS and nr.exists():
                    self._write_ini_value(nr, k, str(v))

    async def copy_profile(self, appid: str, from_appid: str) -> dict:
        try:
            appid, from_appid = str(appid), str(from_appid)
            game = self._game(appid)
            if game and self._is_running(game):
                return {"status": "error", "message": "Close the game first."}
            profile = await asyncio.to_thread(self._export_profile, from_appid)
            await asyncio.to_thread(self._import_profile, appid, profile)
            src = self._load_state()["games"].get(from_appid, {}).get("name", from_appid)
            return {"status": "success", "message": f"Profile copied from {src}. Restart the game."}
        except Exception as exc:
            decky.logger.error(f"[ANR] copy_profile {from_appid} -> {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    async def reset_profile(self, appid: str) -> dict:
        try:
            appid = str(appid)
            game = self._game(appid)
            if game and self._is_running(game):
                return {"status": "error", "message": "Close the game first."}
            default = {"upscaler": "package", "render_quality": "game", "opti": {},
                       "nr_fg": {"path": self._load_state().get("preferred_path") or "auto"}}
            await asyncio.to_thread(self._import_profile, appid, default)
            return {"status": "success", "message": "Profile reset to the ANR package's settings (upscaler: "
                                                    "applies fully on the next reinstall). Restart the game."}
        except Exception as exc:
            decky.logger.error(f"[ANR] reset_profile {appid}: {exc}")
            return {"status": "error", "message": str(exc)}

    def _reapply_upscaler(self, appid: str, target: Path) -> None:
        entry = self._load_state()["games"].get(appid, {})
        if entry.get("opti"):
            try:
                self._apply_opti(appid, dict(entry["opti"]))
                decky.logger.info(f"[ANR] re-applied OptiScaler settings for {appid}: {entry['opti']}")
            except Exception as exc:
                decky.logger.error(f"[ANR] re-applying OptiScaler settings for {appid}: {exc}")
        rq = entry.get("render_quality")
        if rq and rq != "game" and rq in self.RENDER_QUALITY:
            r = self._apply_render_quality(appid, target, rq)
            decky.logger.info(f"[ANR] re-applied render quality {rq} for {appid}: {r.get('message')}")
        choice = entry.get("upscaler")
        if choice and choice != "package":
            r = self._apply_upscaler(appid, target, choice, bool(entry.get("upscaler_watermark")))
            decky.logger.info(f"[ANR] re-applied upscaler {choice} for {appid}: {r.get('message')}")

    def _remove_managed_files(self, appid: str) -> None:
        state = self._load_state()
        entry = state["games"].get(appid, {})
        for m in entry.get("managed_files", []):
            p = Path(m.get("path", ""))
            try:
                if p.exists() and self._file_sha256(p) == m.get("sha256"):
                    p.unlink()
            except OSError:
                pass

    # ── Benchmark (the ANR FG test kit) ───────────────────────────────────────

    KIT_TOTAL_RE = re.compile(r"\[(\d+)/(\d+)\]\s+(\S+)")
    INI_PATHS = {"coopmat", "packed", "dp4a", "portable", "portable-linalg", "portable-xmx"}

    def _bench_dir(self) -> Path:
        return self._runtime_dir() / "benchmark"

    def _bench_set(self, **kw) -> None:
        cur = getattr(self, "_bench", {}) or {}
        cur.update(kw)
        self._bench = cur

    def _download_file(self, url: str, dest: Path, expected_size: int | None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        curl = shutil.which("curl") or ("/usr/bin/curl" if os.path.exists("/usr/bin/curl") else None)
        if curl:
            env = dict(os.environ)
            env.pop("LD_LIBRARY_PATH", None)
            proc = subprocess.Popen([curl, "-fsSL", "-A", USER_AGENT, "-o", str(part), url],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
            while proc.poll() is None:
                done = part.stat().st_size if part.exists() else 0
                self._bench_set(progress=done, total=expected_size or 0)
                if getattr(self, "_bench_cancel", False):
                    proc.kill()
                    raise RuntimeError("cancelled")
                time.sleep(1)
            if proc.returncode != 0:
                raise RuntimeError(f"curl: {proc.stderr.read().decode('utf-8', 'replace').strip()}")
        else:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60, context=self._ssl_context()) as resp, open(part, "wb") as f:
                done = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    self._bench_set(progress=done, total=expected_size or 0)
        os.replace(part, dest)

    def _kit_ready(self, version: str) -> Path | None:
        root = self._bench_dir() / f"anr-fg-{version}-kit-linux"
        return root if (root / "run.sh").exists() else None

    def _benchmark_job(self) -> None:
        import tarfile
        try:
            version = self._active_version()
            if not version:
                raise RuntimeError("ANR FG is not set up yet.")
            for g in self._find_games():
                if g["appid"] in self._load_state().get("games", {}) and self._is_running(g):
                    raise RuntimeError(f"Close {g['name']} first: the benchmark needs the GPU to itself.")
            kit = self._kit_ready(version)
            if not kit:
                self._bench_set(stage="download", message=f"Downloading the ANR FG {version} test kit…")
                tag = f"FG-{version}"
                release = json.loads(self._http_get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag}", "application/vnd.github+json"))
                assets = {a["name"]: a for a in release.get("assets", [])}
                name = f"anr-fg-{version}-kit-linux.tar.gz"
                if name not in assets:
                    raise RuntimeError(f"{tag} has no {name}")
                sums = {}
                if "SHA256SUMS.txt" in assets:
                    for line in self._http_get(assets["SHA256SUMS.txt"]["browser_download_url"]).decode().splitlines():
                        parts = line.split()
                        if len(parts) == 2:
                            sums[parts[1].lstrip("*")] = parts[0].lower()
                archive = self._bench_dir() / name
                self._download_file(assets[name]["browser_download_url"], archive, assets[name].get("size"))
                self._bench_set(stage="verify", message="Checking the download…", progress=0, total=0)
                if name in sums and self._file_sha256(archive) != sums[name]:
                    archive.unlink(missing_ok=True)
                    raise RuntimeError("the kit's SHA256 does not match SHA256SUMS.txt")
                self._bench_set(stage="extract", message="Unpacking the kit…")
                for old in self._bench_dir().glob("anr-fg-*-kit-linux"):
                    shutil.rmtree(old, ignore_errors=True)
                with tarfile.open(archive) as tf:
                    root = self._bench_dir().resolve()
                    for m in tf.getmembers():
                        target = (self._bench_dir() / m.name).resolve()
                        if root not in target.parents and target != root:
                            raise RuntimeError(f"unsafe path in the kit: {m.name}")
                        if m.issym() or m.islnk():
                            link = (target.parent / m.linkname).resolve()
                            if root not in link.parents:
                                raise RuntimeError(f"unsafe link in the kit: {m.name}")
                    tf.extractall(self._bench_dir())
                archive.unlink(missing_ok=True)
                kit = self._kit_ready(version)
                if not kit:
                    raise RuntimeError("the kit has no run.sh")
            self._bench_set(stage="run", message="Running the test kit (5–15 min). Keep games closed.",
                            progress=0, total=0)
            env = dict(os.environ)
            env.pop("LD_LIBRARY_PATH", None)
            env["PATH"] = env.get("PATH", "") + ":/usr/local/bin:/usr/bin:/bin"
            log_path = kit / "decky-run.log"
            with open(log_path, "w") as log:
                proc = subprocess.Popen(["sh", "./run.sh"], cwd=str(kit), stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, env=env, start_new_session=True)
                self._bench_proc = proc
                while proc.poll() is None:
                    if getattr(self, "_bench_cancel", False):
                        os.killpg(proc.pid, 15)
                        raise RuntimeError("cancelled")
                    try:
                        lines = log_path.read_text(errors="replace").splitlines()
                    except OSError:
                        lines = []
                    for line in reversed(lines):
                        m = self.KIT_TOTAL_RE.search(line)
                        if m:
                            self._bench_set(progress=int(m.group(1)), total=int(m.group(2)),
                                            message=f"Run {m.group(1)}/{m.group(2)}: {m.group(3)}")
                            break
                    time.sleep(2)
            text = log_path.read_text(errors="replace")
            m = re.search(r"(results/anr-fg-kit-\S+\.json)", text)
            if proc.returncode != 0 or not m:
                raise RuntimeError("the kit failed: " + " ".join(text.strip().splitlines()[-2:]))
            result_file = kit / m.group(1).rstrip(":")
            summary = self._summarize_kit(result_file, version)
            state = self._load_state()
            state["benchmark"] = summary
            self._save_state(state)
            self._bench_set(stage="done", message=f"Best path: {summary.get('best_path')}", result=summary)
        except Exception as exc:
            decky.logger.error(f"[ANR] benchmark: {exc}")
            self._bench_set(stage="error", message=str(exc))
        finally:
            self._bench_proc = None
            self._bench_cancel = False

    def _file_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _summarize_kit(self, result_file: Path, version: str) -> dict:
        data = json.loads(result_file.read_text())
        table: dict[str, dict[str, dict]] = {}
        fsr: dict[str, float] = {}
        gpu = None
        for run in data.get("runs", []):
            name = run.get("run", "")
            rec = run.get("record") or {}
            m = re.match(r"timing-(\d+p)-(\d)x-(.+)$", name)
            if not m or run.get("exit") != 0:
                continue
            res, mult, variant = m.group(1), int(m.group(2)), m.group(3)
            if variant == "fsrfg":
                t = rec.get("timing") or {}
                if t.get("frame_ms_median"):
                    fsr[res] = round(t["frame_ms_median"], 2)
                continue
            gpu = gpu or rec.get("adapter")
            if variant == "auto":
                path = rec.get("path_selected") or rec.get("path")
            elif variant in self.INI_PATHS:
                path = variant
            else:
                continue  # kit-only variants (sm-loops, nvidia-ada, portable-dp4a)
            if path not in self.INI_PATHS or mult != 2:
                continue
            ms = (rec.get("frame_ms") or {}).get("median")
            entry = table.setdefault(res, {}).setdefault(path, {})
            if ms is not None and (entry.get("ms") is None or ms < entry["ms"]):
                entry["ms"] = round(ms, 2)
            if rec.get("host_vs_reference_db") is not None:
                entry["db"] = round(rec["host_vs_reference_db"], 1)
                entry["passes"] = bool(rec.get("passes_bar"))
            if variant == "auto":
                entry["auto"] = True
        # The best path wins on the most sizes (fastest that passes), 1080p breaking ties.
        wins: dict[str, int] = {}
        for res, paths in table.items():
            ok = {p: v for p, v in paths.items() if v.get("ms") is not None and v.get("passes", True)}
            if ok:
                best = min(ok, key=lambda p: ok[p]["ms"])
                wins[best] = wins.get(best, 0) + (2 if res == "1080p" else 1)
        best_path = max(wins, key=wins.get) if wins else None
        auto_path = next((p for paths in table.values() for p, v in paths.items() if v.get("auto")), None)
        return {
            "version": version,
            "date": datetime.now(timezone.utc).isoformat(),
            "gpu": gpu,
            "file": str(result_file),
            "runs": len(data.get("runs", [])),
            "failed": data.get("failed_runs"),
            "best_path": best_path,
            "auto_path": auto_path,
            "table": table,
            "fsr": fsr,
        }

    async def start_benchmark(self) -> dict:
        if getattr(self, "_bench", {}).get("stage") in ("download", "verify", "extract", "run"):
            return {"status": "error", "message": "The benchmark is already running."}
        self._bench = {"stage": "starting", "message": "Starting…", "progress": 0, "total": 0}
        self._bench_cancel = False
        import threading
        threading.Thread(target=self._benchmark_job, daemon=True).start()
        return {"status": "success", "message": "Benchmark started."}

    async def cancel_benchmark(self) -> dict:
        self._bench_cancel = True
        return {"status": "success", "message": "Stopping the benchmark…"}

    async def get_benchmark(self) -> dict:
        state = self._load_state()
        live = getattr(self, "_bench", None) or {}
        kit_size = 0
        if self._bench_dir().exists():
            for f in self._bench_dir().rglob("*"):
                try:
                    kit_size += f.stat().st_size if f.is_file() else 0
                except OSError:
                    pass
        return {
            "status": "success",
            "live": live,
            "result": state.get("benchmark"),
            "preferred_path": state.get("preferred_path"),
            "kit_mb": round(kit_size / 2**20),
        }

    def _apply_path_all(self, path: str) -> dict:
        if path != "auto" and path not in self.INI_PATHS:
            return {"status": "error", "message": f"Unknown path {path}"}
        state = self._load_state()
        state["preferred_path"] = None if path == "auto" else path
        self._save_state(state)
        done = []
        for appid, entry in state.get("games", {}).items():
            target = Path(entry.get("target_dir", ""))
            desc = self._describe_dir(target) if target.exists() else None
            if desc and desc["anr_dir"]:
                ini = desc["anr_dir"] / "dlssg" / "nr_fg.ini"
                if ini.exists():
                    self._write_ini_value(ini, "path", path)
                    done.append(entry.get("name", appid))
        return {"status": "success",
                "message": f"Compute path {path} for {', '.join(done) or 'no games yet'} and new installs. "
                           "Restart running games."}

    async def apply_path_all(self, path: str) -> dict:
        try:
            return await asyncio.to_thread(self._apply_path_all, str(path))
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def delete_benchmark_kit(self) -> dict:
        if getattr(self, "_bench", {}).get("stage") in ("download", "verify", "extract", "run"):
            return {"status": "error", "message": "The benchmark is running."}
        for old in self._bench_dir().glob("anr-fg-*-kit-linux*"):
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            else:
                old.unlink(missing_ok=True)
        return {"status": "success", "message": "Test kit removed (results kept)."}

    async def log_error(self, error: str) -> None:
        decky.logger.error(f"[ANR] frontend: {error}")

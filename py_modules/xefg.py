"""Pinned, optional XeFG provider for Decky FrameGen Hub. No game files change during download."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

XEFG_NAME = "XeMFG XMX"
XEFG_BUILD = "build-10"
XEFG_DLL = "dlssg_to_xefg_intel_is_better.dll"
XEFG_LOG = "dlssg_to_xefg_intel_is_better.log"
MANIFEST = "decky-xefg.json"
SOURCES = (
    ("https://github.com/realdody/dlssg-to-xefg-xmx/releases/download/build-10/dlssg-to-xefg-10.zip",
     "838dcc6c2f9b367b5b98a5731c07b90c7f610ddde7da1422a0595680cc4157b0"),
    ("https://github.com/intel/xess/releases/download/v3.0.2/XeSS_SDK_3.0.2.zip",
     "88b8a373f30e33f3558a77a93e634f11b8132fc3047ea1a8edeead32b8471990"),
)


class GeneratorMixin:
    def _generator_lock(self):
        if not hasattr(self, "_fg_lock"):
            self._fg_lock = asyncio.Lock()
        return self._fg_lock

    def _xefg_cache(self) -> Path:
        return self._runtime_dir() / "xefg" / XEFG_BUILD

    @staticmethod
    def _xefg_files(root: Path) -> dict[str, str]:
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and p.name != MANIFEST}

    def _xefg_valid(self, root: Path) -> bool:
        try:
            record = json.loads((root / MANIFEST).read_text())
            files = record["files"]
            required = {f"dlssg/{XEFG_DLL}", "dlssg/libxess_fg.dll",
                        "dlssg/xefg_mfg_programs/programs.tsv"}
            return (record.get("build") == XEFG_BUILD and required <= files.keys()
                    and all(self._xefg_owned_path(root, name).is_file()
                            and self._file_sha256(self._xefg_owned_path(root, name)) == sha
                            for name, sha in files.items()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return False

    @staticmethod
    def _xefg_owned_path(root: Path, name: str) -> Path:
        rel = PurePosixPath(name)
        if rel.is_absolute() or not rel.parts or any(p in ("..", ".") for p in rel.parts) or "\\" in name:
            raise ValueError("Unsafe XeFG manifest path")
        dest = root.joinpath(*rel.parts)
        if root.is_symlink() or any(p.is_symlink() for p in (dest, *dest.parents) if p == root or root in p.parents):
            raise ValueError("XeFG paths must not be symbolic links")
        return dest

    def _ensure_xefg(self) -> Path:
        cache = self._xefg_cache()
        if self._xefg_valid(cache):
            return cache
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="xefg-", dir=cache.parent) as temp:
            stage = Path(temp) / "provider"
            stage.mkdir()
            for index, (url, expected) in enumerate(SOURCES):
                data = self._http_get(url)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("XeFG download failed SHA-256 verification; game files were not changed.")
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        name = member.filename
                        if index == 0:
                            prefix = XEFG_NAME + "/"
                            if not name.startswith(prefix):
                                continue
                            rel = name[len(prefix):]
                        else:
                            selected = {"bin/libxess_fg.dll": "dlssg/libxess_fg.dll",
                                        "LICENSE.txt": "LICENSE-Intel-XeSS.txt"}
                            if name not in selected:
                                continue
                            rel = selected[name]
                        if member.file_size > 64 * 1024 * 1024 or member.external_attr >> 28 == 0xA:
                            raise ValueError("Invalid XeFG archive member")
                        dest = self._xefg_owned_path(stage, rel)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(archive.read(member))
            # Keep the original SDK license and all of the upstream shader package, including its MIT license.
            import decky
            license_dir = Path(decky.DECKY_PLUGIN_DIR) / "licenses"
            for name in ("XeFG-GPL-3.0.txt", "XeFG-NOTICE.md"):
                shutil.copy2(license_dir / name, stage / name)
            manifest = {"build": XEFG_BUILD, "files": self._xefg_files(stage)}
            (stage / MANIFEST).write_text(json.dumps(manifest, indent=2))
            if not self._xefg_valid(stage):
                raise ValueError("Incomplete XeFG provider package")
            if cache.exists():
                shutil.rmtree(cache)
            os.replace(stage, cache)
        return cache

    def _xefg_dest(self, ini: Path) -> Path:
        return self._optiscaler_main_dir(ini) / "custom" / XEFG_NAME

    def _install_xefg(self, ini: Path, source: Path) -> None:
        dest = self._xefg_dest(ini)
        if dest.is_symlink():
            raise ValueError("XeFG provider folder is a symbolic link; not replaced.")
        if dest.exists():
            if self._xefg_valid(dest):
                return
            raise ValueError("XeMFG XMX already exists and is not an unchanged Decky install. Move it aside first.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".decky-xefg-", dir=dest.parent) as temp:
            stage = Path(temp) / XEFG_NAME
            shutil.copytree(source, stage)
            os.replace(stage, dest)

    def _remove_xefg(self, ini: Path) -> None:
        dest = self._xefg_dest(ini)
        record_path = dest / MANIFEST
        if not record_path.is_file() or dest.is_symlink():
            return
        record = json.loads(record_path.read_text())
        for name, sha in record.get("files", {}).items():
            path = self._xefg_owned_path(dest, name)
            if path.is_file() and self._file_sha256(path) == sha:
                path.unlink()
        record_path.unlink()
        for directory in sorted((p for p in dest.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            dest.rmdir()
        except OSError:
            pass  # Preserve logs and user-modified files in add-on installs.

    def _generator_status(self, ini: Path, proxy: str | None) -> dict:
        raw = self._read_ini_sections(ini)
        provider = raw.get(("FrameGen", "FGNvngxReplacement"), "")
        choice = "xefg" if provider == XEFG_NAME else "anr" if provider in ("Apex Neural Rendering FG", "nrfg") else "custom"
        return {"choice": choice, "provider": provider, "build": XEFG_BUILD,
                "ready": self._xefg_valid(self._xefg_dest(ini)),
                "dx12_only": True, "available": proxy != "winmm.dll"}

    def _apply_generator(self, appid: str, choice: str, source: Path | None = None) -> None:
        if choice not in ("anr", "xefg"):
            raise ValueError("Unknown frame generator")
        target, desc, ini = self._target_and_ini(appid)
        if choice == "xefg":
            if desc.get("proxy") == "winmm.dll":
                raise ValueError("XeFG supports DirectX 12 games only; this install uses the Vulkan loader.")
            self._install_xefg(ini, source or self._ensure_xefg())
        state = self._load_state()
        # ANR may be installed without a record of ours (installed by hand): start one instead of failing.
        entry = state["games"].setdefault(appid, {"target_dir": str(target), "mode": desc.get("mode")})
        if "generator_original_output" not in entry:
            entry["generator_original_output"] = self._read_ini_sections(ini).get(("FrameGen", "FGOutput"), "auto")
        # XeFG is reached through FGInput=nvngxfg with FGOutput=auto; back on ANR, the user's own FGOutput returns.
        output = "auto" if choice == "xefg" else entry.get("generator_original_output", "auto")
        self._set_ini_sections(ini, {("FrameGen", "FGInput"): "nvngxfg", ("FrameGen", "FGOutput"): output,
                                     ("FrameGen", "FGNvngxReplacement"): XEFG_NAME if choice == "xefg" else "Apex Neural Rendering FG"})
        entry["generator"] = choice
        self._save_state(state)

    async def set_frame_generator(self, appid: str, choice: str) -> dict:
        try:
            async with self._generator_lock():
                appid = str(appid)
                game = self._game(appid)
                if not game:
                    raise ValueError("The game is not in the Steam library.")
                if self._is_running(game):
                    raise ValueError("Close the game before changing the frame generator.")
                # Validate installation before downloading. Check again after the download.
                _, desc, _ = self._target_and_ini(appid)
                if choice == "xefg" and desc.get("proxy") == "winmm.dll":
                    raise ValueError("XeFG supports DirectX 12 games only; this install uses the Vulkan loader.")
                if choice not in ("anr", "xefg"):
                    raise ValueError("Unknown frame generator")
                source = await asyncio.to_thread(self._ensure_xefg) if choice == "xefg" else None
                if self._is_running(game):
                    raise ValueError("The game started during download. Close it and try again.")
                await asyncio.to_thread(self._apply_generator, appid, choice, source)
                label = "XeFG XMX Port (Build 10, beta)" if choice == "xefg" else "ANR FG"
                return {"status": "success", "message": f"Frame generator: {label}. Start the game with DLSS FG enabled."}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

"""User-supplied FSR libraries. No AMD binaries are distributed by this module."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import zipfile

DLL_NAMES = ("amdxcffx64.dll", "amdvkffx64.dll")
MAX_DLL_SIZE = 256 * 1024 * 1024


def pe_string(data: bytes, name: str) -> str:
    key = name.encode("utf-16-le") + b"\x00\x00"
    i = data.find(key)
    if i < 0:
        return ""
    start = i + len(key)
    while data[start:start + 2] == b"\x00\x00":
        start += 2
    end = start
    while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
        end += 2
    return data[start:end].decode("utf-16-le", errors="replace").strip()


def validate_library(name: str, data: bytes) -> dict:
    if name not in DLL_NAMES or not 1_000_000 <= len(data) <= MAX_DLL_SIZE:
        raise ValueError(f"Invalid size or name: {name}")
    if data[:2] != b"MZ":
        raise ValueError(f"{name} is not a Windows DLL")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if pe + 26 > len(data) or data[pe:pe + 4] != b"PE\x00\x00":
        raise ValueError(f"Invalid PE header: {name}")
    if struct.unpack_from("<H", data, pe + 4)[0] != 0x8664 or not struct.unpack_from("<H", data, pe + 22)[0] & 0x2000:
        raise ValueError(f"{name} must be an x64 DLL")
    if "Advanced Micro Devices" not in pe_string(data, "CompanyName"):
        raise ValueError(f"AMD metadata missing: {name}")
    if "FidelityFX" not in pe_string(data, "FileDescription"):
        raise ValueError(f"FidelityFX metadata missing: {name}")
    version = pe_string(data, "FileVersion")
    if not re.fullmatch(r"[0-9]+(?:[., ]+[0-9]+){1,3}", version):
        raise ValueError(f"Invalid library version: {name}")
    if b"Fsr4LiteInt8UpscalerModel" not in data or b"ffxProvider_FSR4Lite_Int8" not in data:
        raise ValueError(f"INT8 Lite model missing: {name}")
    return {"version": version, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read_library_zip(archive: Path) -> tuple[dict[str, bytes], dict]:
    if archive.suffix.lower() != ".zip" or not archive.is_file() or archive.stat().st_size > 1024**3:
        raise ValueError("Choose a ZIP (up to 1 GB) containing both AMD FSR DLLs")
    selected = {}
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 10000:
            raise ValueError("Too many files in ZIP")
        for item in z.infolist():
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", str(path)) or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unsafe ZIP member")
            name = path.name.lower()
            if name not in DLL_NAMES or item.is_dir():
                continue
            if name in selected:
                raise ValueError(f"Multiple copies of {name}; use one matching pair")
            if not 1_000_000 <= item.file_size <= MAX_DLL_SIZE or item.flag_bits & 1:
                raise ValueError(f"Invalid or encrypted DLL: {name}")
            selected[name] = item
        if set(selected) != set(DLL_NAMES):
            raise ValueError("ZIP must contain amdxcffx64.dll and amdvkffx64.dll")
        data = {name: z.read(selected[name]) for name in DLL_NAMES}
    files = {name: validate_library(name, data[name]) for name in DLL_NAMES}
    versions = {f["version"] for f in files.values()}
    if len(versions) != 1:
        raise ValueError("The two DLL versions differ; extract them from the same driver folder")
    return data, {"version": versions.pop(), "files": files}


class Fsr4Mixin:
    FSR4_DLL_NAMES = DLL_NAMES

    def _local_fsr4_source(self) -> dict | None:
        rec = self._load_state().get("fsr4_library") or {}
        ident = rec.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{64}", ident):
            return None
        folder = self._runtime_dir() / "fsr4-libraries" / ident
        files = rec.get("files", {})
        if set(files) != set(DLL_NAMES):
            return None
        for name in DLL_NAMES:
            path = folder / name
            if not path.is_file() or self._file_sha256(path) != files[name].get("sha256"):
                return None
        info = self._fsr4_dll_info(folder / "amdxcffx64.dll")
        if not info or info["version"] != rec.get("version"):
            return None
        info.update(source="imported ZIP", own_prefix=False,
                    hashes={name: files[name]["sha256"] for name in DLL_NAMES})
        return info

    def _import_fsr4_zip(self, path: str) -> dict:
        payload, manifest = read_library_zip(Path(path).expanduser())
        ident = hashlib.sha256("".join(manifest["files"][n]["sha256"] for n in DLL_NAMES).encode()).hexdigest()
        root = self._runtime_dir() / "fsr4-libraries"
        root.mkdir(parents=True, exist_ok=True)
        dest = root / ident
        with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as temp:
            stage = Path(temp) / ident
            stage.mkdir()
            for name in DLL_NAMES:
                (stage / name).write_bytes(payload[name])
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if dest.exists():
                if not all((dest / n).is_file() and self._file_sha256(dest / n) == manifest["files"][n]["sha256"] for n in DLL_NAMES):
                    raise ValueError("Stored library was modified; import cancelled")
            else:
                os.replace(stage, dest)
        state = self._load_state()
        state["fsr4_library"] = {"id": ident, **manifest}
        self._save_state(state)
        return {"status": "success", "version": manifest["version"],
                "message": f"FSR Lite libraries {manifest['version']} imported. Close the game and select FSR 4 Lite to apply them."}

    def _apply_import_to_lite_games(self, result: dict) -> dict:
        updated, pending = [], []
        for appid, entry in self._load_state().get("games", {}).items():
            if entry.get("upscaler") != "fsr4lite":
                continue
            name = entry.get("name", appid)
            try:
                game = self._game(appid)
                if not game or self._is_running(game):
                    pending.append(name)
                    continue
                target = self._resolve_target(game, entry)
                if not target:
                    pending.append(name)
                    continue
                applied = self._apply_upscaler(appid, target, "fsr4lite", bool(entry.get("upscaler_watermark")))
                (updated if applied.get("status") == "success" else pending).append(name)
            except Exception:
                pending.append(name)
        result["updated_games"], result["pending_games"] = updated, pending
        result["message"] = f"FSR Lite libraries {result['version']} imported. "
        if updated:
            result["message"] += "Installed in: " + ", ".join(updated) + ". "
        if pending:
            result["message"] += "Close these games and select Lite again: " + ", ".join(pending) + ". "
        result["message"] += "For other games, choose FSR 4 Lite in Upscaler."
        return result

    async def import_fsr4_libraries(self, archive: str) -> dict:
        try:
            async with self._generator_lock():
                result = await asyncio.to_thread(self._import_fsr4_zip, str(archive))
                return await asyncio.to_thread(self._apply_import_to_lite_games, result)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _extract_fsr4_driver(self, driver: str) -> dict:
        from fsr4_extract import extract_driver
        archive = extract_driver(Path(driver), self._runtime_dir() / "fsr4-archives",
                                 self._runtime_dir() / "tools-cache")
        result = self._import_fsr4_zip(str(archive))
        result["archive"] = str(archive)
        return self._apply_import_to_lite_games(result)

    async def extract_fsr4_driver(self, driver: str) -> dict:
        try:
            async with self._generator_lock():
                return await asyncio.to_thread(self._extract_fsr4_driver, str(driver))
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def get_fsr4_library(self) -> dict:
        try:
            src = await asyncio.to_thread(self._local_fsr4_source)
            return {"status": "success", "available": bool(src), "version": src["version"] if src else None,
                    "home": str(self._home())}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "home": str(self._home())}

"""Extract FSR DLLs from a user-provided driver; never run the driver installer."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

from fsr4 import DLL_NAMES, validate_library

# Official portable 7-Zip releases, pinned to the publisher's SHA-256 digests.
PORTABLE = {
    ("Linux", "x86_64"): ("7z2606-linux-x64.tar.xz", "2b539cf067b2ad48e1baa5093dbaa8818b73542d1222a0ffde9dc5f2922ea62e"),
    ("Linux", "aarch64"): ("7z2606-linux-arm64.tar.xz", "edcc408aacce77da5223728f2eceb5e9f6dc713b8a9df934ad21e2a7f7560627"),
    ("Darwin", "arm64"): ("7z2606-mac.tar.xz", "b6f17920b4240940461dac8ef4009891881ac44d2a5ead625ede2ec8472185dd"),
    ("Darwin", "x86_64"): ("7z2606-mac-x64.tar.xz", "3af68b124052da7fc2a246c96b0bea6a68bfee389baa788f4cead1a133445586"),
}


def find_7zip(cache: Path, explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError("7-Zip executable not found")
        return str(path)
    for name in ("7zz", "7z", "7za"):
        found = shutil.which(name)
        if found:
            return found
    for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")):
        found = Path(base) / "7-Zip/7z.exe"
        if found.is_file():
            return str(found)
    source = PORTABLE.get((platform.system(), platform.machine().lower()))
    if not source:
        raise ValueError("Install 7-Zip from https://www.7-zip.org/ and try again (Python 3 is also required)")
    name, expected = source
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / name.replace(".tar.xz", "")
    archive = cache / name
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        print("Downloading portable 7-Zip from its official release (no sudo needed)…", flush=True)
        req = urllib.request.Request("https://github.com/ip7z/7zip/releases/download/26.06/" + name,
                                     headers={"User-Agent": "Decky-FrameGen-Hub-FSR-extractor"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read(16 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("7-Zip download checksum mismatch")
        archive.write_bytes(data)
    with tarfile.open(archive, "r:xz") as tar:
        member = next((m for m in tar.getmembers() if PurePosixPath(m.name).name == "7zz" and m.isfile()), None)
        if member is None or member.size > 32 * 1024 * 1024:
            raise ValueError("7zz missing from official portable archive")
        data = tar.extractfile(member).read()
    # Recreate from the verified tar on every run, avoiding a stale or modified cached executable.
    dest.write_bytes(data)
    dest.chmod(0o700)
    return str(dest)


def extract_driver(driver: Path, output_dir: Path, cache: Path, sevenzip: str | None = None) -> Path:
    driver = driver.expanduser().resolve()
    if not driver.is_file() or driver.suffix.lower() != ".exe":
        raise ValueError("Select the downloaded AMD Windows driver .exe")
    tool = find_7zip(cache, sevenzip)
    print("Reading driver archive…", flush=True)
    result = subprocess.run([tool, "l", "-slt", "-sccUTF-8", "-r", str(driver), "*ffx64.dll"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise ValueError("7-Zip cannot read this driver: " + result.stderr[-1000:])
    groups = {}
    for line in result.stdout.splitlines():
        if not line.startswith("Path = "):
            continue
        value = line[7:].replace("\\", "/")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", value):
            continue
        if path.name.lower() in DLL_NAMES:
            groups.setdefault(str(path.parent), {})[path.name.lower()] = value
    pairs = [(folder, files) for folder, files in groups.items() if set(files) == set(DLL_NAMES)]
    pairs.sort(key=lambda item: ("/display/" not in ("/" + item[0].lower() + "/"), len(item[0]), item[0]))
    if not pairs:
        raise ValueError("This driver has no matching amdxcffx64.dll + amdvkffx64.dll pair. Use a newer AMD driver with FSR 4 Lite.")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fsr-extract-", dir=output_dir) as temp:
        root = Path(temp)
        errors = []
        for folder, files in pairs:
            target = root / "dlls"
            target.mkdir(exist_ok=True)
            print("Extracting only the two FSR libraries…", flush=True)
            result = subprocess.run([tool, "e", "-y", "-o" + str(target), str(driver), *files.values()],
                                    capture_output=True, text=True, errors="replace", timeout=600)
            if result.returncode:
                raise ValueError("7-Zip extraction failed: " + result.stderr[-1000:])
            payload = {p.name.lower(): p.read_bytes() for p in target.iterdir() if p.is_file() and p.name.lower() in DLL_NAMES}
            try:
                metadata = {n: validate_library(n, payload[n]) for n in DLL_NAMES}
                versions = {f["version"] for f in metadata.values()}
                if len(versions) != 1:
                    raise ValueError("DLL versions differ")
            except (ValueError, KeyError) as exc:
                errors.append(str(exc))
                for f in target.iterdir():
                    f.unlink()
                continue
            version = versions.pop()
            manifest = {"version": version, "driver": driver.name, "driver_folder": folder, "files": metadata}
            dest = output_dir / ("AMD-FSR4-Libraries-" + re.sub(r"[^0-9A-Za-z._-]", "_", version) + ".zip")
            if dest.exists():
                # Never overwrite a different archive. Identical DLLs can reuse an existing ZIP.
                from fsr4 import read_library_zip
                _, old = read_library_zip(dest)
                if old["files"] == metadata:
                    print("Ready: " + str(dest), flush=True)
                    return dest
                dest = output_dir / (dest.stem + "-" + metadata[DLL_NAMES[0]]["sha256"][:12] + ".zip")
                if dest.exists():
                    raise ValueError("Output archive already exists; choose another output folder")
            staged = root / "libraries.zip"
            with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as z:
                for name in DLL_NAMES:
                    z.writestr(name, payload[name])
                z.writestr("manifest.json", json.dumps(manifest, indent=2))
                z.writestr("README.txt", "Extracted locally from your AMD Windows driver. Import this ZIP in Decky FrameGen Hub. AMD libraries retain AMD terms; this archive is not part of the plugin release.\\n")
            os.replace(staged, dest)
            print("Ready: " + str(dest), flush=True)
            return dest
    raise ValueError("No Lite-capable DLL pair found: " + "; ".join(errors))


def cli() -> int:
    parser = argparse.ArgumentParser(description="AMD driver .exe → ZIP with FSR 4 Lite DLLs. No driver installation.")
    parser.add_argument("driver", nargs="?", help="Path to the downloaded driver .exe")
    parser.add_argument("-o", "--output-dir", type=Path, help="Output folder (default: next to the driver)")
    parser.add_argument("--sevenzip", help="Optional path to 7z/7zz")
    args = parser.parse_args()
    raw = args.driver or input("AMD driver .exe path: ").strip().strip('"').strip("'")
    driver = Path(raw).expanduser().resolve()
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "decky-fsr4-extractor"
    try:
        extract_driver(driver, args.output_dir or driver.parent, cache, args.sevenzip)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print("Error: " + str(exc), flush=True)
        return 1

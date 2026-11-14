"""lsfg-vk (Lossless Scaling frame generation for Linux) as a per-game frame generator.

lsfg-vk is a Vulkan layer that works in any game, also without DLSS Frame Generation. It needs the user's own
copy of Lossless Scaling (Steam app 993090, branch "lsfg-vk"), whose lsfg-vk.dll it loads in place or imports locally. lsfg-vk itself is
CC BY-NC-ND 4.0: this plugin never ships or modifies it; it downloads the official build from builds.lsfg-vk.dev
into ~/.local (as its install guide does) and only edits its own profiles in ~/.config/lsfg-vk/conf.toml.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import struct
import zipfile
import stat
from pathlib import Path, PurePosixPath

BUILDS_URL = "https://builds.lsfg-vk.dev/"
RELEASE_RE = re.compile(r'href="(lsfg-vk-(\d+\.\d+\.\d+)\.tar\.xz)"')
# SHA-256 of release archives this plugin has checked; newer releases are trusted over TLS and recorded.
KNOWN_SHA256 = {"2.0.0": "08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74"}
LS_APPID = "993090"
DLL_NAMES = ("lsfg-vk.dll",)  # Lossless.dll of the default branch lacks the shaders lsfg-vk 2 needs
BEGIN = "# BEGIN Decky FrameGen Hub profiles (managed, edit in the plugin)"
END = "# END Decky FrameGen Hub profiles"
# The whole official archive, so `lsfg-vk-cli healthcheck` sees a complete install.
WANTED = ("bin/lsfg-vk-cli", "bin/lsfg-vk-ui", "lib/liblsfg-vk-layer.so", "lib/liblsfg-vk-layer.x86.so",
          "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json",
          "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.x86.json",
          "share/applications/gay.pancake.lsfg-vk-ui.desktop",
          "share/icons/hicolor/256x256/apps/gay.pancake.lsfg-vk-ui.png")
CONFIG_VERSION = 2


def _version_key(v: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", v or ""))


class LsfgMixin:
    # ── Paths ─────────────────────────────────────────────────────────────────

    def _lsfg_prefix(self) -> Path:
        return self._home() / ".local"

    def _lsfg_record(self) -> Path:
        return Path(self._runtime_dir()) / "lsfg-vk" / "install.json"

    def _lsfg_config(self) -> Path:
        base = os.environ.get("XDG_CONFIG_HOME") or str(self._home() / ".config")
        return Path(base) / "lsfg-vk" / "conf.toml"

    def _lsfg_installed(self) -> dict | None:
        try:
            rec = json.loads(self._lsfg_record().read_text())
            prefix = Path(rec["prefix"])
            if all((prefix / f).is_file() for f in rec["files"]):
                return rec
        except (OSError, ValueError, KeyError):
            pass
        return None

    def _lsfg_folder(self) -> Path | None:
        for library in self._steam_library_paths():
            folder = library / "steamapps" / "common" / "Lossless Scaling"
            if folder.is_dir():
                return folder
        return None

    def _lsfg_imported_dll(self) -> Path | None:
        rec = self._load_state().get("lsfg_library", {})
        digest = rec.get("sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            return None
        path = self._runtime_dir() / "lsfg-library" / digest / "lsfg-vk.dll"
        if path.is_file() and self._file_sha256(path) == digest:
            return path
        return None

    def _lsfg_dll(self) -> Path | None:
        imported = self._lsfg_imported_dll()
        if imported:
            return imported
        folder = self._lsfg_folder()
        for name in DLL_NAMES:
            if folder and (folder / name).is_file():
                return folder / name
        return None

    def _lsfg_dll_state(self) -> str:
        """ok, wrong_branch (only the default branch's Lossless.dll) or missing."""
        if self._lsfg_dll():
            return "ok"
        folder = self._lsfg_folder()
        return "wrong_branch" if folder and (folder / "Lossless.dll").is_file() else "missing"

    @staticmethod
    def _lsfg_read_library(path: Path) -> bytes:
        maximum = 32 * 1024 * 1024
        if not path.is_file():
            raise ValueError("Select lsfg-vk.dll or a ZIP containing it")
        if path.suffix.lower() == ".zip":
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Lossless Scaling ZIP is too large (maximum 64 MB)")
            with zipfile.ZipFile(path) as z:
                matches = []
                if len(z.infolist()) > 1000:
                    raise ValueError("Too many files in ZIP")
                for item in z.infolist():
                    name = PurePosixPath(item.filename.replace("\\", "/"))
                    if name.is_absolute() or ".." in name.parts or re.match(r"^[A-Za-z]:", str(name)) or stat.S_ISLNK(item.external_attr >> 16):
                        raise ValueError("Unsafe ZIP member")
                    if name.name.lower() == "lsfg-vk.dll" and not item.is_dir():
                        matches.append(item)
                if len(matches) != 1:
                    raise ValueError("ZIP must contain exactly one lsfg-vk.dll")
                member = matches[0]
                if not 100_000 <= member.file_size <= maximum or member.flag_bits & 1:
                    raise ValueError("Invalid or encrypted lsfg-vk.dll")
                data = z.read(member)
        elif path.name.lower() == "lsfg-vk.dll" and 100_000 <= path.stat().st_size <= maximum:
            data = path.read_bytes()
        else:
            raise ValueError("Select lsfg-vk.dll or a ZIP containing it; Lossless.dll is not compatible")
        if data[:2] != b"MZ":
            raise ValueError("Invalid lsfg-vk.dll: Windows DLL header is missing")
        offset = struct.unpack_from("<I", data, 0x3c)[0]
        if offset + 24 > len(data) or data[offset:offset + 4] != b"PE\x00\x00" or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664 or not struct.unpack_from("<H", data, offset + 22)[0] & 0x2000:
            raise ValueError("Invalid lsfg-vk.dll: expected an x64 DLL")
        if bytes.fromhex("03022307") not in data:
            raise ValueError("Vulkan shaders are missing from lsfg-vk.dll")
        return data

    def _import_lsfg_library(self, filename: str) -> dict:
        data = self._lsfg_read_library(Path(filename).expanduser())
        digest = hashlib.sha256(data).hexdigest()
        folder = self._runtime_dir() / "lsfg-library" / digest
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "lsfg-vk.dll"
        if dest.exists() and self._file_sha256(dest) != digest:
            raise ValueError("Stored Lossless Scaling library was modified; import cancelled")
        if not dest.exists():
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
                tmp = Path(f.name)
                f.write(data)
            os.replace(tmp, dest)
        state = self._load_state()
        previous = state.get("lsfg_library")
        cfg = self._lsfg_config()
        original = cfg.read_bytes() if cfg.exists() else None
        state["lsfg_library"] = {"sha256": digest, "size": len(data)}
        self._save_state(state)
        try:
            self._lsfg_write_config()
            if self._lsfg_installed() and cfg.exists():
                ok, detail = self._lsfg_validate()
                if not ok:
                    raise ValueError("lsfg-vk rejected the configuration: " + detail[-300:])
        except Exception:
            state = self._load_state()
            if previous is None:
                state.pop("lsfg_library", None)
            else:
                state["lsfg_library"] = previous
            self._save_state(state)
            if original is None:
                cfg.unlink(missing_ok=True)
            else:
                cfg.write_bytes(original)
            raise
        return {"status": "success", "message": "Lossless Scaling library imported. Restart games using Lossless Scaling to apply it."}

    async def import_lsfg_library(self, filename: str) -> dict:
        import asyncio
        try:
            async with self._generator_lock():
                return await asyncio.to_thread(self._import_lsfg_library, str(filename))
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── Install / update ──────────────────────────────────────────────────────

    def _lsfg_latest(self) -> tuple[str, str] | None:
        page = self._http_get(BUILDS_URL, "text/html").decode("utf-8", "replace")
        found = [(m.group(2), m.group(1)) for m in RELEASE_RE.finditer(page)]
        if not found:
            return None
        version, name = max(found, key=lambda x: _version_key(x[0]))
        return version, BUILDS_URL + name

    def _lsfg_install(self) -> dict:
        latest = self._lsfg_latest()
        if not latest:
            raise ValueError("No lsfg-vk release found on builds.lsfg-vk.dev")
        version, url = latest
        current = self._lsfg_installed()
        if current and current.get("version") == version and set(current.get("files", [])) >= set(WANTED):
            return current
        data = self._http_get(url)
        digest = hashlib.sha256(data).hexdigest()
        if version in KNOWN_SHA256 and KNOWN_SHA256[version] != digest:
            raise ValueError("lsfg-vk download failed SHA-256 verification; nothing was installed.")
        prefix = self._lsfg_prefix()
        installed = []
        with tempfile.TemporaryDirectory(prefix="lsfg-") as temp:
            stage = Path(temp)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tar:
                for member in tar.getmembers():
                    name = PurePosixPath(member.name.lstrip("./"))
                    rel = str(name)
                    if rel not in WANTED:
                        continue
                    if not member.isfile() or member.size > 64 * 1024 * 1024:
                        raise ValueError(f"Unexpected archive entry {member.name}")
                    dest = stage / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(tar.extractfile(member).read())
                    dest.chmod(0o755 if rel.startswith("bin/") or rel.endswith(".so") else 0o644)
            missing = [f for f in WANTED if not (stage / f).is_file()]
            if missing:
                raise ValueError(f"lsfg-vk archive is missing {', '.join(missing)}")
            # Our own copies only replace files we installed before or that do not exist yet.
            previous = set((current or {}).get("files", []))
            for rel in WANTED:
                dest = prefix / rel
                if dest.exists() and rel not in previous:
                    raise ValueError(f"{dest} exists and was not installed by this plugin; not replaced. "
                                     "Remove the other lsfg-vk install first.")
            for rel in WANTED:
                dest = prefix / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".fghub-new")
                shutil.copy2(stage / rel, tmp)
                os.replace(tmp, dest)
                installed.append(rel)
        record = {"version": version, "sha256": digest, "url": url, "prefix": str(prefix), "files": installed}
        self._lsfg_record().parent.mkdir(parents=True, exist_ok=True)
        self._lsfg_record().write_text(json.dumps(record, indent=2))
        return record

    def _lsfg_uninstall(self) -> None:
        rec = self._lsfg_installed()
        if not rec:
            return
        prefix = Path(rec["prefix"])
        for rel in rec["files"]:
            try:
                (prefix / rel).unlink()
            except OSError:
                pass
        self._lsfg_record().unlink(missing_ok=True)

    # ── Config (our profiles only) ────────────────────────────────────────────

    def _lsfg_profiles(self) -> dict:
        return self._load_state().get("lsfg_profiles", {})

    @staticmethod
    def _toml_str(value: str) -> str:
        return json.dumps(value)  # a TOML basic string is JSON-compatible for these values

    HEADER = "# lsfg-vk configuration. Decky FrameGen Hub manages the global dll path and the marked profiles.\n"

    def _lsfg_render(self, text: str) -> str:
        """Our profiles between markers, `version = 2`, a [global] table with the right dll. lsfg-vk 2 only
        accepts a file with all three plus at least one named [[profile]]."""
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            text = head.rstrip("\n") + "\n" + rest.split(END, 1)[1].lstrip("\n")
        dll = self._lsfg_dll()
        lines = text.split("\n")
        section = None
        out = []
        has_global = False
        for line in lines:
            m = re.match(r"\s*\[\[?([^\]]+)\]\]?", line)
            if m:
                section = m.group(1).strip()
                has_global = has_global or section == "global"
                out.append(line)
                if section == "global" and dll:
                    out.append(f"dll = {self._toml_str(str(dll))}")
                continue
            if section == "global" and re.match(r"\s*dll\s*=", line):
                continue  # replaced above (or dropped: a stale Lossless.dll of the default branch)
            out.append(line)
        text = "\n".join(out)
        if not has_global:
            text = "[global]\n" + (f"dll = {self._toml_str(str(dll))}\n" if dll else "") + "\n" + text.lstrip("\n")
        top = []
        for line in text.split("\n"):
            if re.match(r"\s*\[", line):
                break
            top.append(line)
        if not any(re.match(r"\s*version\s*=", l) for l in top):
            text = f"version = {CONFIG_VERSION}\n\n" + text
        if not text.startswith(self.HEADER.strip()):
            text = self.HEADER + text
        blocks = []
        for appid, p in sorted(self._lsfg_profiles().items()):
            exes = [e for e in p.get("active_in", []) if e]
            if not exes:
                continue
            blocks.append("\n".join([
                "[[profile]]",
                f"name = {self._toml_str('fghub-' + appid)}",
                "active_in = [" + ", ".join(self._toml_str(e) for e in exes) + "]",
                f"multiplier = {int(p.get('multiplier', 2))}",
                f"flow_scale = {float(p.get('flow_scale', 1.0)):g}",
                f"performance_mode = {'true' if p.get('performance_mode') else 'false'}",
            ]))
        if blocks:
            text = text.rstrip("\n") + "\n\n" + BEGIN + "\n" + "\n\n".join(blocks) + "\n" + END
        return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"

    def _lsfg_write_config(self) -> None:
        cfg = self._lsfg_config()
        original = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        text = self._lsfg_render(original)
        if not re.search(r"(?m)^\s*\[\[profile\]\]", text):
            # No profile at all: lsfg-vk rejects such a file, and without one the layer stays idle.
            meaningful = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
            ours_only = all(re.match(r"(version|dll|allow_fp16)\s*=|\[global\]$", l) for l in meaningful)
            if cfg.exists() and ours_only:
                cfg.unlink()
            return
        cfg.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg.with_name(cfg.name + ".fghub-new")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, cfg)

    def _lsfg_validate(self) -> tuple[bool, str]:
        rec = self._lsfg_installed()
        if not rec:
            return False, "lsfg-vk is not installed"
        cli = Path(rec["prefix"]) / "bin" / "lsfg-vk-cli"
        env = dict(os.environ)
        env.pop("LD_LIBRARY_PATH", None)
        proc = subprocess.run([str(cli), "validate", "-c", str(self._lsfg_config())], capture_output=True,
                              text=True, timeout=30, env=env)
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()

    def _lsfg_exes(self, appid: str) -> list[str]:
        game = self._game(appid)
        if not game:
            return []
        cands = self._candidate_dirs(game)
        return [Path(c["exe"]).name for c in cands[:1]]

    # ── Frontend API ──────────────────────────────────────────────────────────

    async def get_lsfg_status(self, appid: str = "") -> dict:
        import asyncio
        try:
            rec = self._lsfg_installed()
            dll = self._lsfg_dll()
            profile = self._lsfg_profiles().get(str(appid)) if appid else None
            return {"status": "success", "installed": bool(rec), "version": (rec or {}).get("version"),
                    "dll": str(dll) if dll else None, "dll_state": self._lsfg_dll_state(), "profile": profile,
                    "ls_appid": LS_APPID, "dll_source": "imported" if self._lsfg_imported_dll() else "steam",
                    "home": str(self._home())}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def install_lsfg(self) -> dict:
        import asyncio
        try:
            rec = await asyncio.to_thread(self._lsfg_install)
            await asyncio.to_thread(self._lsfg_write_config)
            state = self._lsfg_dll_state()
            note = "" if state == "ok" else (
                " Lossless Scaling is on its default branch: pick the 'lsfg-vk' beta branch (Properties → Betas)."
                if state == "wrong_branch" else
                " Install Lossless Scaling from Steam and pick its 'lsfg-vk' beta branch (Properties → Betas).")
            return {"status": "success", "version": rec["version"], "message": f"lsfg-vk {rec['version']} installed.{note}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    async def set_lsfg_profile(self, appid: str, enabled: bool, multiplier: int = 2, flow_scale: float = 1.0,
                               performance_mode: bool = False) -> dict:
        import asyncio
        try:
            appid = str(appid)
            if enabled and not self._lsfg_installed():
                return {"status": "error", "message": "Install lsfg-vk first."}
            multiplier = int(multiplier)
            flow_scale = float(flow_scale)
            if not 2 <= multiplier <= 6:
                return {"status": "error", "message": "Multiplier must be 2..6"}
            if not 0.25 <= flow_scale <= 1.0:
                return {"status": "error", "message": "Flow scale must be 0.25..1.0"}
            state = self._load_state()
            profiles = state.setdefault("lsfg_profiles", {})
            if enabled:
                exes = profiles.get(appid, {}).get("active_in") or await asyncio.to_thread(self._lsfg_exes, appid)
                if not exes:
                    return {"status": "error", "message": "No .exe found for this game."}
                profiles[appid] = {"active_in": exes, "multiplier": multiplier, "flow_scale": flow_scale,
                                   "performance_mode": bool(performance_mode)}
            else:
                profiles.pop(appid, None)
            self._save_state(state)
            await asyncio.to_thread(self._lsfg_write_config)
            ok, out = await asyncio.to_thread(self._lsfg_validate) if self._lsfg_installed() else (True, "")
            if not ok:
                return {"status": "error", "message": f"lsfg-vk rejected the configuration: {out[-300:]}"}
            if not enabled:
                return {"status": "success", "message": "Lossless Scaling frame generation is off for this game."}
            dll = "" if self._lsfg_dll() else (" Lossless Scaling's 'lsfg-vk' beta branch is not installed yet: "
                                               "lsfg-vk will not run without its lsfg-vk.dll.")
            return {"status": "success",
                    "message": f"Lossless Scaling FG {multiplier}X on for {', '.join(profiles[appid]['active_in'])}. "
                               f"Turn the game's own frame generation off.{dll}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

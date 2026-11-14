"""Offline integration checks for per-game generator routing and file ownership."""
import asyncio
import hashlib
import importlib.util
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py_modules"))
decky = types.ModuleType("decky")
decky.logger = logging.getLogger("test")
decky.DECKY_PLUGIN_DIR = str(ROOT)
sys.modules["decky"] = decky
spec = importlib.util.spec_from_file_location("backend", ROOT / "main.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
import xefg


def archive(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()


class Generators(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        decky.DECKY_PLUGIN_RUNTIME_DIR = str(self.root / "runtime")
        decky.DECKY_PLUGIN_SETTINGS_DIR = str(self.root / "settings")
        self.game = self.root / "game"
        (self.game / "OptiScaler").mkdir(parents=True)
        (self.game / "game.exe").touch()
        self.ini = self.game / "OptiScaler.ini"
        self.ini.write_text("[FrameGen]\nFGInput=nvngxfg\nFGOutput=auto\nFGNvngxReplacement=Apex Neural Rendering FG\n[Upscalers]\nDx12Upscaler=ffx\n[DLSSG]\nOverrideInterpolationCount=2\n")
        (self.game / "OptiScaler/nr_fg_install.json").write_text('{"proxy":"dxgi.dll"}')
        self.p = backend.Plugin()
        self.info = {"appid": "1", "name": "Test game", "install_path": str(self.game)}
        self.p._game = lambda appid: self.info if appid == "1" else None
        self.running = False
        self.p._is_running = lambda game: self.running
        self.p._save_state({"active_version": "test", "games": {"1": {"target_dir": str(self.game), "mode": "full", "version": "old", "name": "Test game"}}})
        self.payloads = {
            "provider": archive({f"XeMFG XMX/dlssg/{xefg.XEFG_DLL}": b"MZ-provider",
                                 "XeMFG XMX/dlssg/xefg_mfg_programs/programs.tsv": b"programs",
                                 "XeMFG XMX/dlssg/xefg_mfg_programs/LICENSE": b"MIT"}),
            "sdk": archive({"bin/libxess_fg.dll": b"MZ-runtime", "LICENSE.txt": b"Intel license"}),
        }
        sources = tuple((name, hashlib.sha256(data).hexdigest()) for name, data in self.payloads.items())
        patcher = patch.object(xefg, "SOURCES", sources)
        patcher.start(); self.addCleanup(patcher.stop)
        self.p._http_get = lambda url, *args: self.payloads[url]

    def select(self, choice):
        return asyncio.run(self.p.set_frame_generator("1", choice))

    def test_switch_keeps_upscaler_and_multiplier_and_caches_download(self):
        self.assertEqual(self.select("xefg")["status"], "success")
        before = self.p._read_ini_sections(self.ini)
        self.assertEqual(before[("FrameGen", "FGNvngxReplacement")], "XeMFG XMX")
        self.assertEqual(before[("Upscalers", "Dx12Upscaler")], "ffx")
        self.assertEqual(before[("DLSSG", "OverrideInterpolationCount")], "2")
        self.assertTrue(self.p._xefg_valid(self.p._xefg_dest(self.ini)))
        self.p._http_get = lambda *a: self.fail("cache should avoid another download")
        self.assertEqual(self.select("anr")["status"], "success")
        self.assertEqual(self.select("xefg")["status"], "success")
        self.assertEqual(self.p._load_state()["games"]["1"]["generator"], "xefg")

    def test_bad_download_keeps_game_and_state(self):
        before = self.ini.read_bytes()
        self.p._http_get = lambda *a: b"corrupt"
        self.assertEqual(self.select("xefg")["status"], "error")
        self.assertEqual(self.ini.read_bytes(), before)
        self.assertNotIn("generator", self.p._load_state()["games"]["1"])
        self.assertFalse(self.p._xefg_dest(self.ini).exists())

    def test_running_game_cannot_switch_or_download(self):
        self.running = True
        self.p._http_get = lambda *a: self.fail("must not download")
        self.assertEqual(self.select("xefg")["status"], "error")

    def test_game_started_during_download(self):
        ensure = self.p._ensure_xefg
        def started():
            source = ensure(); self.running = True; return source
        self.p._ensure_xefg = started
        self.assertEqual(self.select("xefg")["status"], "error")
        self.assertFalse(self.p._xefg_dest(self.ini).exists())

    def test_foreign_provider_is_never_overwritten(self):
        dest = self.p._xefg_dest(self.ini)
        dest.mkdir(parents=True)
        (dest / "mine.dll").write_bytes(b"mine")
        self.assertEqual(self.select("xefg")["status"], "error")
        self.assertEqual((dest / "mine.dll").read_bytes(), b"mine")
        self.assertNotIn("generator", self.p._load_state()["games"]["1"])

    def test_modified_install_is_not_silently_replaced(self):
        self.select("xefg")
        dll = self.p._xefg_dest(self.ini) / "dlssg" / xefg.XEFG_DLL
        dll.write_bytes(b"user modified")
        self.select("anr")
        self.assertEqual(self.select("xefg")["status"], "error")
        self.assertEqual(dll.read_bytes(), b"user modified")

    def test_cleanup_preserves_user_files_and_logs(self):
        self.select("xefg")
        dest = self.p._xefg_dest(self.ini)
        dll = dest / "dlssg" / xefg.XEFG_DLL
        dll.write_bytes(b"user modified")
        log = dest / "dlssg" / xefg.XEFG_LOG
        log.write_text("diagnostic")
        self.p._remove_xefg(self.ini)
        self.assertEqual(dll.read_bytes(), b"user modified")
        self.assertEqual(log.read_text(), "diagnostic")
        self.assertFalse((dest / "dlssg/libxess_fg.dll").exists())

    def test_vulkan_rejected_before_download(self):
        (self.game / "OptiScaler/nr_fg_install.json").write_text('{"proxy":"winmm.dll"}')
        self.p._http_get = lambda *a: self.fail("must not download")
        self.assertEqual(self.select("xefg")["status"], "error")

    def test_archive_traversal_rejected(self):
        bad = archive({"XeMFG XMX/../../escaped": b"bad"})
        self.payloads["provider"] = bad
        with patch.object(xefg, "SOURCES", (("provider", hashlib.sha256(bad).hexdigest()),)):
            self.assertEqual(self.select("xefg")["status"], "error")
        self.assertFalse((self.root / "escaped").exists())

    def test_reinstall_restores_generator(self):
        self.select("xefg")
        self.p._active_version = lambda: "test"
        self.p._package_dir = lambda *a: self.root
        (self.root / "install.sh").touch()
        original = self.ini.read_text()
        def install(*a):
            self.ini.write_text(original.replace("FGNvngxReplacement=XeMFG XMX", "FGNvngxReplacement=Apex Neural Rendering FG"))
            return True, "installed"
        self.p._run_script = install
        self.p._reapply_upscaler = lambda *a: None
        result = self.p._patch("1", "%command%", str(self.game))
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(self.p._read_ini_sections(self.ini)[("FrameGen", "FGNvngxReplacement")], "XeMFG XMX")
        self.assertEqual(self.p._load_state()["games"]["1"]["generator"], "xefg")

    def test_log_uses_selected_provider(self):
        self.select("xefg")
        log = self.p._xefg_dest(self.ini) / "dlssg" / xefg.XEFG_LOG
        log.write_text("XMX Port active")
        self.p._game_status = lambda appid: {"generator": {"choice": "xefg"}}
        result = asyncio.run(self.p.read_game_log("1"))
        self.assertEqual(result["log"], "XMX Port active")

    def test_unknown_game_record_and_output_restored(self):
        self.ini.write_text(self.ini.read_text().replace("FGOutput=auto", "FGOutput=fsrfg"))
        self.p._save_state({"active_version": "test", "games": {}})
        self.assertEqual(self.select("xefg")["status"], "success")
        self.assertEqual(self.p._read_ini_sections(self.ini)[("FrameGen", "FGOutput")], "auto")
        self.assertEqual(self.select("anr")["status"], "success")
        self.assertEqual(self.p._read_ini_sections(self.ini)[("FrameGen", "FGOutput")], "fsrfg")

    def test_prerelease_sorts_before_stable(self):
        key = backend._plugin_version_key
        self.assertLess(key("0.1.9"), key("0.2.0-beta.1"))
        self.assertLess(key("0.2.0-beta.1"), key("0.2.0"))


if __name__ == "__main__":
    unittest.main()

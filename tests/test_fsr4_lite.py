"""Private FSR Lite integration: pair validation, ownership and switching."""
import test_generators as fixtures
import unittest
backend = fixtures.backend
import hashlib
from pathlib import Path
from unittest.mock import patch

class Fsr4Lite(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.hashes = {}
        for name in self.p.FSR4_DLL_NAMES:
            b = ("MZ-test-" + name).encode()
            (self.sources / name).write_bytes(b)
            self.hashes[name] = hashlib.sha256(b).hexdigest()
        self.p._local_fsr4_source = lambda: {"path": str(self.sources / self.p.FSR4_DLL), "version": "2.4.0.4370", "hashes": self.hashes}

    def test_pair_model_and_cleanup(self):
        r = self.p._apply_upscaler("1", self.game, "fsr4lite", True)
        self.assertEqual(r["status"], "success", r)
        values = self.p._read_ini_sections(self.ini)
        self.assertEqual(values[("FSR", "Fsr4Model")], "3")
        self.assertEqual(values[("FSR", "Fsr4GpuSupport")], "4")
        self.assertEqual(values[("Log", "LogLevel")], "2")
        self.assertEqual(values[("FrameGen", "FGInput")], "nvngxfg")
        for name in self.hashes:
            self.assertEqual((self.game / "OptiScaler" / name).read_bytes(), (self.sources / name).read_bytes())
        self.assertEqual(self.p._apply_upscaler("1", self.game, "fsr31", False)["status"], "success")
        self.assertFalse(any((self.game / "OptiScaler" / n).exists() for n in self.hashes))

    def test_foreign_second_dll_prevents_any_write(self):
        dll = self.game / "OptiScaler/amdvkffx64.dll"
        dll.write_bytes(b"user file")
        before = self.ini.read_bytes()
        self.assertEqual(self.p._apply_upscaler("1", self.game, "fsr4lite", True)["status"], "error")
        self.assertEqual(dll.read_bytes(), b"user file")
        self.assertFalse((self.game / "OptiScaler/amdxcffx64.dll").exists())
        self.assertEqual(self.ini.read_bytes(), before)

    def test_reapply_and_modified_file_protection(self):
        self.p._apply_upscaler("1", self.game, "fsr4lite", False)
        self.assertEqual(self.p._apply_upscaler("1", self.game, "fsr4lite", True)["status"], "success")
        dll = self.game / "OptiScaler/amdvkffx64.dll"
        dll.write_bytes(b"changed")
        self.assertEqual(self.p._apply_upscaler("1", self.game, "fsr4lite", True)["status"], "error")
        self.p._remove_managed_files("1")
        self.assertEqual(dll.read_bytes(), b"changed")

    def test_missing_source_keeps_game(self):
        self.p._local_fsr4_source = lambda: None
        before = self.ini.read_bytes()
        self.assertEqual(self.p._apply_upscaler("1", self.game, "fsr4lite", True)["status"], "error")
        self.assertEqual(self.ini.read_bytes(), before)

    def test_partial_copy_failure_restores_both_previous_dlls(self):
        self.p._apply_upscaler("1", self.game, "fsr4lite", False)
        before = {n: (self.game / "OptiScaler" / n).read_bytes() for n in self.hashes}
        old_state = self.p._load_state()
        import os
        replace = os.replace
        def fail_second(source, dest):
            if str(source).endswith("amdvkffx64.dll"):
                raise OSError("simulated disk failure")
            return replace(source, dest)
        with patch.object(backend.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.p._apply_upscaler("1", self.game, "fsr4lite", False)
        self.assertEqual(self.p._load_state(), old_state)
        for n in self.hashes:
            self.assertEqual((self.game / "OptiScaler" / n).read_bytes(), before[n])

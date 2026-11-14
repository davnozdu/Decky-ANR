"""User archive validation and updates, using synthetic PE files only."""
import asyncio
import io
import json
from pathlib import Path
import struct
import unittest
import zipfile
from unittest.mock import patch
import test_generators as fixtures
from fsr4 import DLL_NAMES, read_library_zip, validate_library


def dll(version="2.4.0.4370", lite=True):
    data = bytearray(1_000_100)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)
    struct.pack_into("<H", data, 0x96, 0x2000)
    meta = "CompanyName\0Advanced Micro Devices, Inc.\0FileDescription\0AMD Driver Based FidelityFX Library\0FileVersion\0" + version + "\0"
    encoded = meta.encode("utf-16-le")
    data[0x200:0x200 + len(encoded)] = encoded
    if lite:
        marker = b"Fsr4LiteInt8UpscalerModel\0ffxProvider_FSR4Lite_Int8\0"
        data[0x1000:0x1000 + len(marker)] = marker
    return bytes(data)


class Imports(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.archive = self.root / "libraries.zip"

    def make_zip(self, files=None, version="2.4.0.4370"):
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as z:
            for n, data in (files or {"nested/" + n: dll(version) for n in DLL_NAMES}).items():
                z.writestr(n, data)
        return self.archive

    def test_import_survives_plugin_directory_update_and_accepts_new_version(self):
        self.p._import_fsr4_zip(str(self.make_zip()))
        old = self.p._local_fsr4_source()
        self.assertEqual(old["version"], "2.4.0.4370")
        with patch.object(fixtures.decky, "DECKY_PLUGIN_DIR", str(self.root / "new-plugin")):
            self.assertEqual(self.p._local_fsr4_source()["hashes"], old["hashes"])
        self.p._import_fsr4_zip(str(self.make_zip(version="2.5.0.5000")))
        self.assertEqual(self.p._local_fsr4_source()["version"], "2.5.0.5000")
        self.assertTrue(Path(old["path"]).exists())

    def test_failed_import_keeps_previous_library_and_game(self):
        self.p._import_fsr4_zip(str(self.make_zip()))
        state = self.p._load_state()
        original = self.ini.read_bytes()
        self.make_zip({DLL_NAMES[0]: dll(), DLL_NAMES[1]: dll(lite=False)})
        result = asyncio.run(self.p.import_fsr4_libraries(str(self.archive)))
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.p._load_state(), state)
        self.assertEqual(self.ini.read_bytes(), original)

    def test_reject_mixed_versions_missing_duplicate_and_traversal(self):
        cases = [
            {DLL_NAMES[0]: dll(), DLL_NAMES[1]: dll("2.5.0.5000")},
            {DLL_NAMES[0]: dll()},
            {DLL_NAMES[0]: dll(), "other/" + DLL_NAMES[0]: dll(), DLL_NAMES[1]: dll()},
            {"../escape": b"bad", **{n: dll() for n in DLL_NAMES}},
        ]
        for files in cases:
            with self.subTest(files=list(files)):
                with self.assertRaises(ValueError):
                    read_library_zip(self.make_zip(files))
        self.assertFalse((self.root.parent / "escape").exists())

    def test_reject_wrong_architecture_and_tampered_cache(self):
        data = bytearray(dll()); struct.pack_into("<H", data, 0x84, 0x14c)
        with self.assertRaises(ValueError):
            validate_library(DLL_NAMES[0], data)
        self.p._import_fsr4_zip(str(self.make_zip()))
        source = Path(self.p._local_fsr4_source()["path"])
        source.write_bytes(b"changed")
        self.assertIsNone(self.p._local_fsr4_source())

    def test_auto_apply_only_selected_lite_closed_games(self):
        state = self.p._load_state(); state['games']['1']['upscaler'] = 'fsr4lite'; self.p._save_state(state)
        self.running = True
        result = asyncio.run(self.p.import_fsr4_libraries(str(self.make_zip())))
        self.assertEqual(result['pending_games'], ['Test game'])
        self.assertFalse((self.game / 'OptiScaler' / DLL_NAMES[0]).exists())
        self.running = False
        result = asyncio.run(self.p.import_fsr4_libraries(str(self.archive)))
        self.assertEqual(result['updated_games'], ['Test game'])
        self.assertEqual(self.p._read_ini_sections(self.ini)[('FSR', 'Fsr4Model')], '3')
        self.assertEqual(self.p._read_ini_sections(self.ini)[('FSR', 'Fsr4EnableWatermark')], 'false')


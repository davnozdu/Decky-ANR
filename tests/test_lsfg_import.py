"""User-owned lsfg-vk.dll imports: format, persistence and config rollback."""
import asyncio
import hashlib
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zipfile
import test_generators as fixtures


def library():
    b=bytearray(150000); b[:2]=b'MZ'; struct.pack_into('<I',b,0x3c,0x80); b[0x80:0x84]=b'PE\0\0'
    struct.pack_into('<H',b,0x84,0x8664); struct.pack_into('<H',b,0x96,0x2000)
    b[0x1000:0x1004]=bytes.fromhex('03022307'); return bytes(b)


class LsfgImport(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.p._home=lambda: self.root
        self.p._steam_library_paths=lambda: [self.root/'steam']
        self.p._lsfg_installed=lambda: None
        self.dll=self.root/'lsfg-vk.dll'; self.dll.write_bytes(library())

    def test_single_file_import_persists_and_does_not_modify_source(self):
        original=self.dll.read_bytes()
        result=asyncio.run(self.p.import_lsfg_library(str(self.dll)))
        self.assertEqual(result['status'],'success',result)
        stored=self.p._lsfg_dll(); self.assertNotEqual(stored,self.dll)
        self.assertEqual(stored.read_bytes(),original)
        self.assertEqual(self.dll.read_bytes(),original)
        p2=fixtures.backend.Plugin(); p2._home=self.p._home; p2._steam_library_paths=self.p._steam_library_paths
        self.assertEqual(p2._lsfg_dll(),stored)
        self.assertEqual(self.p._lsfg_dll_state(),'ok')

    def test_import_archive_and_reject_traversal_and_duplicates(self):
        archive=self.root/'library.zip'
        with zipfile.ZipFile(archive,'w') as z: z.writestr('nested/lsfg-vk.dll',library())
        self.assertEqual(asyncio.run(self.p.import_lsfg_library(str(archive)))['status'],'success')
        previous=self.p._load_state()
        for entries in [ {'../bad':b'bad','lsfg-vk.dll':library()}, {'lsfg-vk.dll':library(),'copy/lsfg-vk.dll':library()} ]:
            with zipfile.ZipFile(archive,'w') as z:
                for name,data in entries.items(): z.writestr(name,data)
            self.assertEqual(asyncio.run(self.p.import_lsfg_library(str(archive)))['status'],'error')
            self.assertEqual(self.p._load_state(),previous)

    def test_steam_fallback_and_import_takes_precedence(self):
        steam=self.root/'steam/steamapps/common/Lossless Scaling'; steam.mkdir(parents=True)
        (steam/'lsfg-vk.dll').write_bytes(library())
        self.assertEqual(self.p._lsfg_dll(),steam/'lsfg-vk.dll')
        asyncio.run(self.p.import_lsfg_library(str(self.dll)))
        self.assertEqual(self.p._lsfg_dll(),self.p._lsfg_imported_dll())

    def test_wrong_library_and_missing_shader_do_not_change_state(self):
        wrong=self.root/'Lossless.dll'; wrong.write_bytes(library())
        self.assertEqual(asyncio.run(self.p.import_lsfg_library(str(wrong)))['status'],'error')
        self.dll.write_bytes(b'MZ'+b'\0'*150000)
        self.assertEqual(asyncio.run(self.p.import_lsfg_library(str(self.dll)))['status'],'error')
        self.assertNotIn('lsfg_library',self.p._load_state())

    def test_existing_profiles_and_generator_are_preserved(self):
        state=self.p._load_state(); state['lsfg_profiles']={'1':{'active_in':['game.exe'],'multiplier':2,'flow_scale':0.75}}
        state['games']['1']['generator']='lsfg'; self.p._save_state(state)
        cfg=self.p._lsfg_config(); cfg.parent.mkdir(parents=True)
        cfg.write_text('version = 2\n[global]\ndll = "old"\n[[profile]]\nname = "manual"\nactive_in = ["other.exe"]\nmultiplier = 2\n')
        result=asyncio.run(self.p.import_lsfg_library(str(self.dll)))
        self.assertEqual(result['status'],'success',result)
        text=cfg.read_text(); self.assertIn(str(self.p._lsfg_dll()),text)
        self.assertIn('name = "manual"',text)
        self.assertEqual(self.p._load_state()['lsfg_profiles'],state['lsfg_profiles'])
        self.assertEqual(self.p._load_state()['games']['1']['generator'],'lsfg')

    def test_failed_config_validation_restores_previous_choice_and_config(self):
        cfg=self.p._lsfg_config(); cfg.parent.mkdir(parents=True); original='version = 2\n[global]\ndll = "old"\n'; cfg.write_text(original)
        self.p._lsfg_installed=lambda: {'prefix':str(self.root)}
        self.p._lsfg_write_config=lambda: cfg.write_text('invalid')
        self.p._lsfg_validate=lambda: (False,'test failure')
        result=asyncio.run(self.p.import_lsfg_library(str(self.dll)))
        self.assertEqual(result['status'],'error')
        self.assertEqual(cfg.read_text(),original)
        self.assertNotIn('lsfg_library',self.p._load_state())

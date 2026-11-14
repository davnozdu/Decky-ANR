"""Restore removes only the selected game's plugin changes and LS profile."""
import asyncio
from pathlib import Path
import shutil
import unittest
import test_generators as fixtures

class RestoreGame(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.p._home=lambda:self.root
        self.p._lsfg_installed=lambda:None
        self.proxy=self.game/'dxgi.dll'; self.proxy.write_bytes(b'plugin proxy')
        self.original=self.game/'original.dat'; self.original.write_bytes(b'original game data')
        self.p._unpatch_dir=self.uninstall
        state=self.p._load_state()
        state['games']['1']['proxy']='dxgi.dll'
        state['lsfg_profiles']={'1':{'active_in':['game.exe'],'multiplier':2,'flow_scale':0.75,'performance_mode':False},
                                '2':{'active_in':['other.exe'],'multiplier':3,'flow_scale':1.0,'performance_mode':True}}
        self.p._save_state(state)
        self.p._lsfg_write_config()

    def uninstall(self,*args):
        self.proxy.unlink(missing_ok=True)
        self.ini.unlink(missing_ok=True)
        shutil.rmtree(self.game/'OptiScaler',ignore_errors=True)
        return True,'uninstalled'

    def restore(self,launch='WINEDLLOVERRIDES="dxgi=n,b;foo=b" %command% --flag'):
        return asyncio.run(self.p.unpatch_game('1',launch))

    def test_restore_patches_and_lsfg_preserves_other_game_and_original_files(self):
        state=self.p._load_state(); state['lsfg_library']={'sha256':'user-library'}; self.p._save_state(state)
        result=self.restore(); self.assertEqual(result['status'],'success',result)
        state=self.p._load_state(); self.assertNotIn('1',state['games']); self.assertNotIn('1',state['lsfg_profiles'])
        self.assertIn('2',state['lsfg_profiles']); self.assertEqual(state['lsfg_library'],{'sha256':'user-library'})
        self.assertNotIn('fghub-1"',self.p._lsfg_config().read_text()); self.assertIn('fghub-2"',self.p._lsfg_config().read_text())
        self.assertEqual(self.original.read_bytes(),b'original game data'); self.assertFalse(self.proxy.exists())
        self.assertEqual(result['launch_options'],'WINEDLLOVERRIDES="foo=b" %command% --flag')
        self.assertEqual(self.p._outdated_games(),[])

    def test_lsfg_only_game_can_be_restored(self):
        self.uninstall(); s=self.p._load_state(); s['games'].pop('1'); self.p._save_state(s)
        result=self.restore('%command% --flag'); self.assertEqual(result['status'],'success',result)
        self.assertEqual(result['launch_options'],'%command% --flag'); self.assertNotIn('1',self.p._lsfg_profiles())

    def test_running_game_is_not_modified(self):
        self.running=True; before=self.p._load_state(); config=self.p._lsfg_config().read_bytes()
        self.assertEqual(self.restore()['status'],'error'); self.assertTrue(self.proxy.exists())
        self.assertEqual(self.p._load_state(),before); self.assertEqual(self.p._lsfg_config().read_bytes(),config)

    def test_uninstall_failure_restores_lsfg_config_and_profile(self):
        self.p._unpatch_dir=lambda *args:(False,'cannot remove')
        before=self.p._load_state(); config=self.p._lsfg_config().read_bytes()
        self.assertEqual(self.restore()['status'],'error'); self.assertEqual(self.p._load_state(),before)
        self.assertEqual(self.p._lsfg_config().read_bytes(),config)

    def test_original_override_is_restored_and_quoted_spaces_are_preserved(self):
        s=self.p._load_state(); s['games']['1']['original_launch_options']='WINEDLLOVERRIDES="dxgi=b;foo=b" %command%'; self.p._save_state(s)
        result=self.restore('WINEDLLOVERRIDES="dxgi=n,b;foo=b" %command% --path="My  Game"')
        self.assertEqual(result['launch_options'],'WINEDLLOVERRIDES="dxgi=b;foo=b" %command% --path="My  Game"')

    def test_performance_switch_persists_on_and_off_without_changing_other_controls(self):
        import tomllib
        self.p._lsfg_installed=lambda:{"prefix":str(self.root)}
        self.p._lsfg_validate=lambda:(True, "valid")
        for enabled in (True, False):
            result=asyncio.run(self.p.set_generator_mode('1','lsfg',2,0.75,enabled))
            self.assertEqual(result['status'],'success',result)
            profile=self.p._load_state()['lsfg_profiles']['1']
            self.assertEqual(profile['performance_mode'],enabled)
            self.assertEqual(profile['multiplier'],2)
            self.assertEqual(profile['flow_scale'],0.75)
            config=tomllib.loads(self.p._lsfg_config().read_text())
            self.assertEqual(next(p for p in config['profile'] if p['name']=='fghub-1')['performance_mode'],enabled)

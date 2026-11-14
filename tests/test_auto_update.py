"""Automatic ANR downloads, verification, closed-game updates and deferred retries."""
import asyncio
import hashlib
import json
from pathlib import Path
import unittest
import test_generators as fixtures

class AutoUpdate(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.active='V.B15'
        self.p._active_version=lambda: self.active
        self.p._load_state = self.p._load_state
        self.p._outdated_games=lambda: [{'appid':'1','name':'Test game'}] if self.p._load_state()['games']['1']['version'] != self.active else []
        state=self.p._load_state(); state['games']['1']['version']='V.B15'; self.p._save_state(state)
        self.downloaded=0; self.patched=0
        def download(require_checksum=False):
            self.assertTrue(require_checksum)
            self.downloaded+=1; self.active='V.B16'
            return {'version':'V.B16','downloaded':True}
        self.p._download_latest=download
        def patch(appid,*args):
            self.patched+=1
            s=self.p._load_state(); s['games'][appid]['version']=self.active; self.p._save_state(s)
            return {'status':'success'}
        self.p._patch=patch

    def test_disabled_never_downloads_or_changes_games(self):
        s=self.p._load_state(); s['auto_update_anr']=False; self.p._save_state(s)
        r=self.p._auto_update_anr_sync({'anr_latest':'V.B16'})
        self.assertFalse(r['downloaded']); self.assertEqual(self.downloaded,0); self.assertEqual(self.patched,0)

    def test_enabled_downloads_and_updates_closed_game(self):
        r=self.p._auto_update_anr_sync({'anr_latest':'V.B16'})
        self.assertTrue(r['downloaded']); self.assertEqual(r['updated'],['Test game'])
        self.assertEqual(self.p._load_state()['active_version'],'V.B16')
        self.assertFalse(self.p._auto_anr_pending)

    def test_running_game_retried_after_closing_without_another_download(self):
        self.running=True
        r=self.p._auto_update_anr_sync({'anr_latest':'V.B16'})
        self.assertEqual(r['updated'],[]); self.assertEqual(self.patched,0); self.assertTrue(self.p._auto_anr_pending)
        self.running=False
        r=self.p._auto_update_anr_sync({})
        self.assertEqual(r['updated'],['Test game']); self.assertEqual(self.downloaded,1); self.assertFalse(self.p._auto_anr_pending)

    def test_verification_failure_never_activates_or_patches(self):
        s=self.p._load_state(); s['active_version']='V.B15'; self.p._save_state(s)
        def fail(**kwargs): raise ValueError('checksum mismatch')
        self.p._download_latest=fail
        with self.assertRaises(ValueError): self.p._auto_update_anr_sync({'anr_latest':'V.B16'})
        self.assertEqual(self.p._load_state()['active_version'],'V.B15'); self.assertEqual(self.patched,0)

class DownloadVerification(unittest.TestCase):
    def setUp(self):
        fixtures.Generators.setUp(self)
        self.full=fixtures.archive({'install.sh':'#!/bin/sh\n','nr_fg_package.json':'{}'})
        self.addon=fixtures.archive({'install.sh':'#!/bin/sh\n'})
        self.sums=f'{hashlib.sha256(self.full).hexdigest()}  anr-fg-V.B16-full.zip\n{hashlib.sha256(self.addon).hexdigest()}  anr-fg-V.B16-addon.zip\n'.encode()
        self.responses={fixtures.backend.GITHUB_API_LATEST:json.dumps({'assets':[
            {'name':'anr-fg-V.B16-full.zip','browser_download_url':'full'},
            {'name':'anr-fg-V.B16-addon.zip','browser_download_url':'addon'},
            {'name':'SHA256SUMS.txt','browser_download_url':'sums'}]}).encode(), 'full':self.full, 'addon':self.addon, 'sums':self.sums}
        self.p._http_get=lambda url,*a:self.responses[url]

    def test_all_archives_verified_before_installing_any(self):
        self.responses['addon']=b'bad download'
        with self.assertRaises(ValueError): self.p._download_latest(require_checksum=True)
        self.assertEqual(self.p._installed_versions(),[])
        self.responses['addon']=self.addon
        self.assertTrue(self.p._download_latest(require_checksum=True)['downloaded'])
        self.assertTrue((self.p._package_dir('V.B16','addon')/'install.sh').is_file())

    def test_auto_download_requires_checksum(self):
        self.responses['sums']=b''
        with self.assertRaises(ValueError): self.p._download_latest(require_checksum=True)
        self.assertEqual(self.p._installed_versions(),[])

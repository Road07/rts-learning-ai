import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import engine_update as update
from automatic_training import episode_environment


class EngineUpdate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_numeric_release_order_and_explicit_launcher_selection(self):
        for version in ['v0.4.12-nightly.261103100','v0.4.12-nightly.261105100']:
            p=self.root/'versions'/version;(p/'game').mkdir(parents=True)
            (p/'manifest.json').write_text('{}');(p/'game/VERSION').write_text('test')
        with patch.object(update,'OFFICIAL',self.root):
            self.assertEqual(update.installed().name,'v0.4.12-nightly.261105100')
            (self.root/'state.cfg').write_text('[launcher]\nselected="v0.4.12-nightly.261103100"')
            self.assertEqual(update.installed().name,'v0.4.12-nightly.261103100')
        self.assertGreater(update.release_order('v0.4.12'),update.release_order('v0.4.12-nightly.261105100'))

    def test_integrity_and_path_escape_rejected(self):
        p=self.root/'v0.4.12';(p/'game').mkdir(parents=True)
        (p/'game/VERSION').write_text('commit '+'a'*40)
        file=p/'game/engine';file.write_bytes(b'engine')
        manifest={'version':p.name,'repo':'Open-BFME/openbfme-godot','commit':'a'*40,'assets':{'game':{'windows-x64':{'files':{'engine':{'size':6,'sha256':update.digest(file)}}}}}}
        update.write(p/'manifest.json',manifest);update.verify_release(p)
        file.write_bytes(b'broken')
        with self.assertRaises(ValueError):update.verify_release(p)
        manifest['assets']['game']['windows-x64']['files']={'../outside':{'size':0,'sha256':'bad'}}
        update.write(p/'manifest.json',manifest)
        with self.assertRaises(ValueError):update.verify_release(p)

    def test_additive_ai_hook_keeps_new_upstream_code(self):
        base=b'func _process(delta: float) -> void:\n\told_work()\n'
        modified=b'func _process(delta: float) -> void:\n\tgeneral_ai_driver.tick()\n\told_work()\n'
        upstream=b'func _process(delta: float) -> void:\n\tnew_bug_fix()\n\told_work()\n'
        merged=update.merge_game_hooks(upstream,base,modified)
        self.assertIn(b'new_bug_fix()',merged);self.assertIn(b'general_ai_driver.tick()',merged)
        with self.assertRaises(RuntimeError):update.merge_game_hooks(upstream,base,b'unknown replacement\n')

    def test_training_pair_pins_engine_without_mutating_config(self):
        args=SimpleNamespace(engine_package='immutable-engine-A',rotate_factions=False,seconds=6)
        config={};a=episode_environment(args,config,1,'evaluate');b=episode_environment(args,{},2,'evaluate')
        self.assertEqual(a['arena_engine_directory'],b['arena_engine_directory'])
        self.assertEqual(config,{})

    def test_active_package_hashes_are_verified(self):
        binary=self.root/'OpenBFME.exe';binary.write_bytes(b'engine')
        state=self.root/'engine-state.json';update.write(state,{'directory':str(self.root),'files':{'OpenBFME.exe':update.digest(binary)}})
        with patch.object(update,'STATE',state):
            self.assertIsNotNone(update.active())
            binary.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):update.active()


if __name__=='__main__':unittest.main()

"""Reproduce the application's late import after engine_update prepends its folder."""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import checkpoint_registry

class RegistryChecks(unittest.TestCase):
    def test_cached_legacy_benchmark_cannot_shadow_registry(self):
        wrong=types.ModuleType('benchmark');wrong.__file__='legacy/benchmark.py'
        checkpoint_registry.module.cache_clear()
        with patch.dict(sys.modules,{'benchmark':wrong}):
            loaded=checkpoint_registry.module()
            self.assertEqual(Path(loaded.__file__).resolve(),Path(__file__).resolve().with_name('benchmark.py'))
            self.assertTrue(callable(loaded.add))
            self.assertIs(sys.modules['benchmark'],wrong)

    def test_parent_search_path_does_not_change_registry(self):
        checkpoint_registry.module.cache_clear()
        with patch.object(sys,'path',[str(Path(__file__).resolve().parent.parent)]+sys.path):
            loaded=checkpoint_registry.module()
            with patch.object(loaded,'add',return_value={'registered':True}) as register:
                self.assertEqual(checkpoint_registry.add('suite','config','label'),{'registered':True})
                register.assert_called_once_with('suite','config','label')

if __name__=='__main__':unittest.main()

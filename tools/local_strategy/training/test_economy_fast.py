"""Package integrity checks only: no game process and no model training."""
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from runtime_cache import FILES,prepare_cached


class CacheChecks(unittest.TestCase):
    def test_cached_bytes_identical_and_only_one_pack(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4]/'AI-Test-Sahasi') as folder:
            root=Path(folder);engine=root/'engine';engine.mkdir()
            for name in FILES:(engine/name).write_bytes(name.encode())
            def prepare(engine,runtime,model):
                for name in FILES:(runtime/name).write_bytes((engine/name).read_bytes())
                return {'identity':'fixture-not-game'}
            with patch('run_match.prepare',side_effect=prepare) as pack:
                for index in range(2):
                    runtime=root/str(index);runtime.mkdir()
                    identity=prepare_cached(engine,runtime,True,root/'cache')
                    self.assertEqual(identity,{'identity':'fixture-not-game'})
                    for name in FILES:self.assertEqual((runtime/name).read_bytes(),(engine/name).read_bytes())
                self.assertEqual(pack.call_count,1)
            cache=next((root/'cache').glob('*/manifest.json')).parent
            (cache/'OpenBFME.pck').write_bytes(b'corrupt')
            runtime=root/'third';runtime.mkdir()
            with self.assertRaisesRegex(ValueError,'bytes changed'):prepare_cached(engine,runtime,True,root/'cache')


if __name__=='__main__':unittest.main()

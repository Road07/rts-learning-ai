import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from match_pack import pack,unpack
from run_match import arguments,main
from run_matches import summary,compare_results

class MatchTests(unittest.TestCase):
    def test_pck_roundtrip_and_corruption(self):
        data={'scenes/game.tscn':b'abc','scripts/main.gd':b'node'};blob=pack(data)
        self.assertEqual(unpack(blob),data)
        corrupted=bytearray(blob);corrupted[104]^=1
        with self.assertRaises(ValueError):unpack(corrupted)
    def test_args_durations_and_controllers(self):
        a=arguments(['--headless','--duration','180','--time-scale','10','--out','out.json'])
        self.assertEqual(a.duration*5,900);self.assertEqual(a.controller_list,['native','native'])
        for opts in (['--duration','nan'],['--duration','.3'],['--time-scale','0'],['--controllers','model,native'],['--positions','0,0']):
            with self.assertRaises(SystemExit),redirect_stderr(io.StringIO()):arguments(['--out','x.json']+opts)
    def test_no_arguments_preserve_normal_game_entry(self):
        with patch('run_match.engine_path',return_value=Path('installed')),patch('run_match.subprocess.call',return_value=0) as call:
            self.assertEqual(main([]),0)
            self.assertEqual(call.call_args.args[0],[str(Path('installed')/'OpenBFME.exe')])
            self.assertEqual(call.call_args.kwargs['cwd'],Path('installed'))

    def test_batch_denominator_is_completed_matches(self):
        row={'ok':True,'winner':None,'end_reason':'duration','duration_seconds':180.,'worker_wall_seconds':20.,'simulation_wall_seconds':18.}
        result=summary([row,dict(row,winner=1,end_reason='victory'),{'ok':False}],42)
        self.assertEqual(result['completed'],1);self.assertEqual(result['failed'],1);self.assertEqual(result['win_rate_completed']['1'],1);self.assertEqual(result['average_duration_seconds'],180.)
        self.assertIsNone(summary([row],20)['win_rate_completed']['1'])
    def test_hash_comparison_reports_first_divergence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[3]/'AI-Test-Sahasi') as folder:
            p,q=Path(folder)/'a.json',Path(folder)/'b.json';r={'ok':True,'seed':1,'map':'m','factions':['a','b'],'initial_frame':1,'logic_frames':1,'model_identity':{},'winner':None,'players':[],'duration_seconds':.2,'end_reason':'duration','state_hash_chain_sha256':'abc'}
            for f in (p,q):f.write_text(json.dumps(r));Path(str(f)+'.hashes.jsonl').write_text('{"frame":2,"hash":"7"}\n')
            self.assertTrue(compare_results(p,q)['deterministic_equal'])
            Path(str(q)+'.hashes.jsonl').write_text('{"frame":2,"hash":"8"}\n')
            self.assertEqual(compare_results(p,q)['first_divergence']['right']['hash'],'8')

if __name__=='__main__':unittest.main()

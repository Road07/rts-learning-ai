from types import SimpleNamespace
import unittest
from automatic_training import episode_environment

class HeadlessTrainingTests(unittest.TestCase):
    def test_sample_and_evaluation_use_same_simulation_budget(self):
        args=SimpleNamespace(headless_training=True,time_scale=10.,rotate_factions=False,seconds=6)
        original={'arena_sim_frames':999}
        for mode in ('sample','evaluate'):
            config=episode_environment(args,original,42,mode)
            self.assertEqual(config['arena_sim_frames'],30)
            self.assertTrue(config['arena_headless_training'])
            self.assertEqual(config['arena_time_scale'],10.)
        self.assertEqual(original,{'arena_sim_frames':999})
    def test_legacy_mode_keeps_original_budget_and_wall_time(self):
        args=SimpleNamespace(rotate_factions=False,seconds=6)
        self.assertEqual(episode_environment(args,{},42,'evaluate')['arena_sim_frames'],120)
        self.assertNotIn('arena_sim_frames',episode_environment(args,{'arena_sim_frames':100},42,'sample'))
    def test_headless_engine_and_roster_are_pinned(self):
        args=SimpleNamespace(headless_training=True,time_scale=10.,rotate_factions=True,seconds=6,seed=7,engine_package='pinned')
        a=episode_environment(args,{},90,'sample',roster_seed=91)
        b=episode_environment(args,{},92,'evaluate',roster_seed=91)
        self.assertEqual(a['arena_factions'],b['arena_factions'])
        self.assertEqual(a['arena_engine_directory'],'pinned')

if __name__=='__main__':unittest.main()

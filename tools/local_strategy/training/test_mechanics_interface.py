from pathlib import Path
import tempfile
import unittest
import numpy as np
from automatic_training import features
from decision_net import DecisionNet,load_tactical_model,FACTIONS
from spend_policy import spend_features,load_spend_model,legal_spend_options,WAIT


class MechanicsChecks(unittest.TestCase):
    def test_negative_cp_is_not_silently_used_for_training(self):
        with self.assertRaisesRegex(ValueError,'cp_used_fraction=-0.192'):
            features({'mechanics':{'schema':'rts-mechanics-v1','cp_used_fraction':-.192}}, {'id':'none'})

    def test_coordinate_choices_and_native_yield_are_distinguishable(self):
        first={"id":"build:1:Farm:100:200","kind":"build","economy":True,"cost":300,"farm_share":.35,"base_income_per_second":1.5,"builder_distance":220,"nearest_farm_distance":80}
        second=dict(first,id="build:1:Farm:500:700",farm_share=.95,base_income_per_second=4.,builder_distance=900,nearest_farm_distance=800)
        choices=legal_spend_options([first,second],300)
        self.assertEqual(len(choices),3)
        self.assertFalse(np.array_equal(spend_features({},first),spend_features({},second)))

    def test_cavalry_pike_target_and_force_health_are_numeric_inputs(self):
        first={"id":"attack_enemy","mechanics":{"selected_cavalry_fraction":1.,"selected_health":.2,"target_pikes":1.,"enemy_local_value":3000}}
        second={"id":"attack_enemy","mechanics":{"selected_cavalry_fraction":0.,"selected_health":1.,"target_pikes":0.,"enemy_local_value":1000}}
        self.assertFalse(np.array_equal(features({},first),features({},second)))
        with self.assertRaises(ValueError): features({}, {"id":"attack_enemy","mechanics":{"target_health":float('nan')}})

    def test_wall_span_is_a_distinct_costed_action(self):
        wall={"id":"wall:1:cap:0:2","kind":"wall","cost":200,"connected_wall":True,"wall_tiles":4,"wall_length":320}
        self.assertEqual(len(legal_spend_options([wall],200)),2)
        self.assertEqual(len(legal_spend_options([wall],199)),1)
        self.assertFalse(np.array_equal(spend_features({},wall),spend_features({},WAIT)))

    def test_zero_extension_preserves_all_seven_existing_policies(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            for head,encoder,loader,candidate in [('tactical',features,load_tactical_model,{"id":"attack_enemy"}),('spend',spend_features,load_spend_model,WAIT)]:
                obs={"faction":"FactionWild","mechanics":{"schema":"rts-mechanics-v1","army_value":5000,"enemy_pikes":3}}
                old_x=encoder(obs,candidate,include_mechanics=False)[None,:]
                new_x=encoder(obs,candidate)[None,:]
                model=DecisionNet(old_x.shape[1]).ensure_factions()
                model.factions["FactionAngmar"].weights["b0"][0]+=.5
                path=Path(temp)/(head+'.npz'); model.save(path)
                restored=loader(path)
                for faction in FACTIONS:
                    np.testing.assert_allclose(model.factions[faction].forward(old_x)[0],restored.factions[faction].forward(new_x)[0],atol=1e-7)
                    self.assertTrue(np.all(restored.factions[faction].weights["w0"][old_x.shape[1]:]==0))


if __name__=='__main__': unittest.main()

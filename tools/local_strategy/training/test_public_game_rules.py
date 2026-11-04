import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from automatic_training import features
from decision_net import DecisionNet,load_tactical_model,FACTIONS
from spend_policy import spend_features,load_spend_model,WAIT
from public_game_rules import PublicGameRules,encode_card
from compile_game_rules import Compiler

ROOT=Path(__file__).resolve().parents[4]


class PublicRulesChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rules=PublicGameRules(ROOT/'AI-Egitim/game-rules-v2/game-rules.json')

    def test_retail_soldier_horde_and_hero_facts(self):
        soldier=self.rules.card('GondorFighter')['stats']
        horde=self.rules.card('GondorFighterHorde')
        self.assertEqual(soldier['max_health'],200)
        self.assertEqual(soldier['hit_damage'],40)
        self.assertEqual(horde['stats']['cost'],250)
        self.assertEqual(horde['stats']['max_health'],3000)
        self.assertEqual(horde['stats']['member_count'],15)
        self.assertEqual(horde['controller_max_health'],1)
        self.assertNotEqual(horde['stats']['max_health'],horde['controller_max_health'])
        self.assertEqual(self.rules.card('GondorAragorn')['stats']['cost'],2000)
        self.assertEqual(self.rules.card('DwarvenMineShaft')['stats']['cost'],300)
        self.assertIn('STRUCTURE',self.rules.card('DwarvenMineShaft')['flags'])
        self.assertEqual(soldier['armor_pierce'],.7)
        self.assertEqual(self.rules.card('DwarvenGuardian')['stats']['hit_damage'],80)
        self.assertEqual(self.rules.card('DwarvenGuardianHorde')['stats']['hit_damage'],800)
        self.assertEqual(self.rules.card('DwarvenPhalanx')['stats']['hit_damage'],60)

    def test_conditions_and_full_rules_are_retained(self):
        hero=self.rules.card('GondorAragorn')
        self.assertTrue(hero['power_refs'])
        self.assertTrue(any(w['conditions']=='WEAPONSET_HERO_MODE' for w in hero['weapon_refs']))
        self.assertIn('GondorSword',self.rules.data['tables']['Weapon'])
        self.assertEqual(len(self.rules.data['factions']),7)
        self.assertTrue(self.rules.definitions('GondorAragorn')['declarations'])

    def test_observed_refs_feed_both_heads_without_inventing_enemies(self):
        obs={'faction':'FactionMen','human_state_features':{'own_templates':{'GondorFighterHorde':2},'visible_enemy_templates':{}}}
        attack={'id':'attack_visible','rule_refs':{'selected':{'GondorFighterHorde':1},'target':''}}
        buy={'id':'hero:1:GondorAragorn:0:0','kind':'hero','template':'GondorAragorn','cost':2000}
        old_attack=features(obs,attack);old_buy=spend_features(obs,buy)
        self.rules.attach(obs,[attack],[buy])
        self.assertFalse(np.array_equal(old_attack,features(obs,attack)))
        self.assertFalse(np.array_equal(old_buy,spend_features(obs,buy)))
        self.assertEqual(obs['public_rules']['enemy'],{})
        self.assertEqual(attack['public_rules']['target'],{})
        self.assertEqual(buy['public_rules']['template']['stats']['max_health'],2400)

    def test_missing_stats_have_masks_and_nan_is_rejected(self):
        self.assertNotEqual(encode_card({}),encode_card({'stats':{'cost':0}}))
        with self.assertRaises(ValueError): encode_card({'stats':{'cost':float('nan')}})
        self.assertEqual(self.rules.numeric_card('NotAnExistingTemplate'),{})

    def test_pre_rules_weights_and_all_faction_predictions_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            for head,encoder,loader,choice in [('tactical',features,load_tactical_model,{'id':'attack_visible'}),('spend',spend_features,load_spend_model,WAIT)]:
                obs={'public_rules':{'own':self.rules.numeric_card('GondorFighterHorde')}}
                before=encoder(obs,choice,include_rules=False)[None,:]
                after=encoder(obs,choice)[None,:]
                model=DecisionNet(before.shape[1]).ensure_factions()
                path=Path(directory)/(head+'.npz');model.save(path);restored=loader(path)
                for faction in FACTIONS:
                    np.testing.assert_allclose(model.for_faction(faction).forward(before)[0],restored.for_faction(faction).forward(after)[0],atol=1e-7)
                    self.assertTrue(np.all(restored.for_faction(faction).weights['w0'][before.shape[1]:]==0))

    def test_additive_inherited_flags_and_module_removal(self):
        source={'file':'test.ini','line':1}
        def field(key,raw,value=None):
            f={'key':key,'raw':raw,'source':source}
            if value is not None:f['numeric']={'value':value}
            return f
        body={'header':'Body ActiveBody Tag_Body','source':source,'fields':[field('MaxHealth','100',100)],'blocks':[]}
        parent={'kind':'Object','parent':None,'declarations':[{'header':'Object Parent','source':source,'fields':[field('KindOf','STRUCTURE HERO')],'blocks':[body]}]}
        child={'kind':'ChildObject','parent':'Parent','declarations':[{'header':'ChildObject Child Parent','source':source,'fields':[field('KindOf','+INFANTRY -STRUCTURE'),field('RemoveModule','Tag_Body')],'blocks':[]}]}
        c=Compiler({'objects':{'Parent':parent,'Child':child},'tables':{}}).card('Child')
        self.assertIn('HERO',c['flags']);self.assertIn('INFANTRY',c['flags']);self.assertNotIn('STRUCTURE',c['flags'])
        self.assertIsNone(c['stats']['max_health'])


if __name__=='__main__': unittest.main()

"""Protocol boundaries and request-local cache isolation; not expert data."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from decision_protocol import decode
from feature_cache import begin,end,cached

def item(player=3,frame=25):
    return {'observation':{'player_index':player,'decision_frame':frame,'match_id':'test'},'candidates':[{'id':'defend_wait'}]}

class TransportTests(unittest.TestCase):
    def test_lossless_legacy_compact(self):
        request=item()
        old={'model':'m','messages':[{'role':'user','content':json.dumps(request)}]}
        self.assertEqual(decode(old,'m'),decode({'model':'m','request':request},'m'))

    def test_batch_preserves_order_and_validates_before_use(self):
        requests=[item(8),item(3)]
        self.assertEqual(decode({'model':'m','requests':requests},'m'),(requests,True))
        for invalid in ([item(3),item(3)],[item(3),item(4,30)],[],[item(i) for i in range(9)]):
            with self.assertRaises(ValueError):decode({'model':'m','requests':invalid},'m')
        wrong=copy.deepcopy(requests);wrong[1]['observation']['match_id']='other'
        with self.assertRaises(ValueError):decode({'model':'m','requests':wrong},'m')

    def test_cache_scope_and_mutation_isolation(self):
        observation={};calls=[]
        def compute():calls.append(1);return [1.,2.]
        token=begin(True)
        try:
            result=cached('state',observation,compute);result.append(9.)
            self.assertEqual(cached('state',observation,compute),[1.,2.])
            self.assertEqual(len(calls),1)
            cached('state',{},compute)
            self.assertEqual(len(calls),2)
        finally:end(token)
        token=begin(True)
        try:cached('state',observation,compute)
        finally:end(token)
        self.assertEqual(len(calls),3)

if __name__=='__main__':unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from rom.cache import CachedEstimator
from rom.measurement import measure_arm
from rom.yolo_pose import combine_predictions


class ConsensusTests(unittest.TestCase):
    def points(self):
        points=np.zeros((17,2),dtype=float)
        points[[5,7,9]]=[(20,50),(50,50),(50,20)]
        points[[6,8,10]]=[(20,80),(50,80),(80,80)]
        return points

    def test_both_anatomical_sides_and_confidence(self):
        points=self.points();scores=np.ones(17)*.9
        landmarks,disagreements=combine_predictions(points,scores,points.copy(),scores,100,100)
        self.assertAlmostEqual(measure_arm(landmarks,'left',100,100)[0],90)
        self.assertAlmostEqual(measure_arm(landmarks,'right',100,100)[0],0)
        self.assertEqual(disagreements,{'left':0.,'right':0.})

    def test_disagreement_is_withheld_instead_of_averaged_into_a_number(self):
        points=self.points();mirror=points.copy();mirror[9]=(80,50)
        landmarks,_=combine_predictions(points,np.ones(17),mirror,np.ones(17),100,100)
        value,_,reason,_=measure_arm(landmarks,'left',100,100)
        self.assertIsNone(value)
        self.assertEqual(reason,'model_disagreement')

    def test_either_prediction_can_fail_confidence(self):
        points=self.points();scores=np.ones(17);mirror_scores=scores.copy();mirror_scores[9]=.2
        landmarks,_=combine_predictions(points,scores,points.copy(),mirror_scores,100,100)
        self.assertEqual(measure_arm(landmarks,'left',100,100)[2],'low_confidence')


class CacheTests(unittest.TestCase):
    def test_replays_completed_inference_without_loading_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'run.jsonl'
            class Model:
                last_status='detected';last_disagreement={'left':1.,'right':2.}
                def detect(self,image,timestamp):return [SimpleNamespace(x=.2,y=.3,visibility=.9,presence=.9,agreement_ok=True)]
                def close(self):pass
            cache=CachedEstimator(Model,path,{'max_disagreement':25})
            cache.detect(None,0);cache.close()
            def forbidden():raise AssertionError('A cached frame must not load the model')
            replay=CachedEstimator(forbidden,path,{'max_disagreement':25})
            self.assertEqual(replay.detect(None,0)[0].x,.2)
            replay.close()

    def test_input_model_or_settings_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'run.jsonl'
            cache=CachedEstimator(lambda:None,path,{'input':'A'});cache.close()
            with self.assertRaises(ValueError):CachedEstimator(lambda:None,path,{'input':'B'})

    def test_partial_tail_recovers_but_middle_corruption_does_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'run.jsonl'
            path.write_text(json.dumps({'metadata':{}})+'\n{"incomplete')
            cache=CachedEstimator(lambda:None,path,{})
            self.assertEqual(cache.records,[]);cache.close()
            path.write_text(json.dumps({'metadata':{}})+'\ninvalid\n{}\n')
            with self.assertRaises(json.JSONDecodeError):CachedEstimator(lambda:None,path,{})

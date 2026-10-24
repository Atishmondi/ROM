"""Optional real codec + model smoke test; enabled once setup has installed assets."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from rom.yolo_pose import DEFAULT_MODEL, YOLOPoseEstimator
from rom.pipeline import analyze

READY = (importlib.util.find_spec('cv2') is not None and
         importlib.util.find_spec('ultralytics') is not None and DEFAULT_MODEL.is_file())


@unittest.skipUnless(READY, 'Run scripts/setup.sh to install the real backend and model')
class RealBackendTests(unittest.TestCase):
    def test_black_video_round_trip(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'blank.mp4'
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 240))
            self.assertTrue(writer.isOpened())
            try:
                for _ in range(5):
                    writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
            finally:
                writer.release()
            summary, paths = analyze(source, root / 'annotated.mp4', lambda: YOLOPoseEstimator(DEFAULT_MODEL), progress=None)
            self.assertEqual(summary['frames'], 5)
            self.assertEqual(summary['arms']['left']['valid_frames'], 0)
            self.assertIsNone(summary['arms']['right']['observed_rom_deg'])
            self.assertTrue(all(path.stat().st_size > 0 for path in paths.values()))

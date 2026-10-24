"""Pipeline contract tests use a fake decoder/model; they do not validate ML accuracy."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from rom.pipeline import analyze, validate_paths
from rom.yolo_pose import ensure_model
from rom.report import chart
from tests.test_measurement import landmarks


class Frame:
    shape = (480, 640, 3)


class Capture:
    def __init__(self, count, fps=30):
        self.remaining = self.count = count
        self.fps = fps
        self.released = False

    def isOpened(self):
        return not self.released

    def get(self, key):
        return {'fps': self.fps, 'width': 640, 'height': 480, 'count': self.count}[key]

    def read(self):
        if self.remaining == 0:
            return False, None
        self.remaining -= 1
        return True, Frame()

    def release(self):
        self.released = True


class FakeCV:
    CAP_PROP_FPS, CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT, CAP_PROP_FRAME_COUNT = 'fps', 'width', 'height', 'count'
    COLOR_BGR2RGB, FONT_HERSHEY_SIMPLEX, LINE_AA = 1, 1, 1

    def __init__(self, count=4, fps=30):
        self.source = Capture(count, fps)
        self.written = 0
        self.captures = []
        self.writer_released = False

    def VideoCapture(self, path):
        capture = self.source if not self.captures else Capture(self.written)
        self.captures.append(capture)
        return capture

    def VideoWriter_fourcc(self, *args):
        return 0

    def VideoWriter(self, path, *args):
        Path(path).write_bytes(b'fake video for pipeline contract test')
        return SimpleNamespace(isOpened=lambda: True, write=self.write, release=self.release_writer)

    def write(self, frame):
        self.written += 1

    def release_writer(self):
        self.writer_released = True

    def cvtColor(self, frame, code):
        return frame

    def rectangle(self, *args): pass
    def putText(self, *args): pass
    def line(self, *args): pass
    def circle(self, *args): pass


class Estimator:
    def __init__(self, absent=False, fail=False):
        self.timestamps, self.closed = [], False
        self.absent, self.fail = absent, fail

    def detect(self, image, timestamp):
        if self.fail:
            raise RuntimeError('Model failure')
        self.timestamps.append(timestamp)
        return None if self.absent else landmarks()

    def close(self):
        self.closed = True


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        self.source.write_bytes(b'input placeholder')
        self.output = self.root / 'run.mp4'

    def test_end_to_end_contract(self):
        cv, estimator = FakeCV(), Estimator()
        summary, paths = analyze(self.source, self.output, lambda: estimator, cv=cv, progress=None)
        self.assertTrue(all(p.is_file() for p in paths.values()))
        self.assertEqual(summary['arms']['left']['min_flexion_deg'], 90)
        self.assertEqual(summary['arms']['right']['max_flexion_deg'], 0)
        self.assertEqual(estimator.timestamps, [0, 33, 67, 100])
        with paths['csv'].open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['left_status'], 'valid')
        self.assertEqual(json.loads(paths['summary'].read_text())['frames'], 4)
        self.assertIn('Elbow movement', paths['report'].read_text())
        self.assertIn('<video id="evidence-video" controls', paths['report'].read_text())
        self.assertIn('src="run.mp4"', paths['report'].read_text())
        self.assertIn('data-seek="0.000000"', paths['report'].read_text())
        self.assertTrue(estimator.closed and cv.source.released and cv.writer_released)

    def test_no_person_exports_missing_values(self):
        summary, paths = analyze(self.source, self.output, lambda: Estimator(absent=True), cv=FakeCV(), progress=None)
        self.assertIsNone(summary['arms']['left']['observed_rom_deg'])
        with paths['csv'].open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['left_flexion_deg'], '')
        self.assertEqual(row['left_status'], 'no_pose')

    def test_inference_failure_cleans_up(self):
        cv, estimator = FakeCV(), Estimator(fail=True)
        with self.assertRaisesRegex(RuntimeError, 'Model failure'):
            analyze(self.source, self.output, lambda: estimator, cv=cv)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.rom-*')), [])
        self.assertTrue(estimator.closed and cv.writer_released and cv.source.released)

    def test_empty_and_invalid_fps_rejected(self):
        for cv in (FakeCV(count=0), FakeCV(fps=0), FakeCV(fps=float('nan'))):
            with self.assertRaises(ValueError):
                analyze(self.source, self.output, Estimator, cv=cv)
            self.assertTrue(cv.source.released)
            self.assertFalse(self.output.exists())

    def test_output_collision_and_source_preserved(self):
        self.output.with_suffix('.csv').write_text('keep me')
        with self.assertRaises(FileExistsError):
            validate_paths(self.source, self.output)
        self.assertEqual(self.output.with_suffix('.csv').read_text(), 'keep me')
        with self.assertRaises(ValueError):
            validate_paths(self.source, self.source)

    def test_invalid_input_and_suffix(self):
        with self.assertRaises(FileNotFoundError):
            validate_paths(self.root / 'missing.mp4', self.output)
        with self.assertRaises(ValueError):
            validate_paths(self.source, self.root / 'output.avi')

    def test_frame_cap(self):
        summary, _ = analyze(self.source, self.output, Estimator, cv=FakeCV(), max_frames=2, progress=None)
        self.assertEqual(summary['frames'], 2)
        self.assertTrue(any('capped' in text for text in summary['warnings']))

    def test_encoder_frame_loss_is_rejected(self):
        cv = FakeCV()
        cv.write = lambda frame: None
        with self.assertRaisesRegex(RuntimeError, 'verification failed'):
            analyze(self.source, self.output, Estimator, cv=cv)
        self.assertFalse(self.output.exists())

    def test_report_escapes_filename(self):
        source = self.root / '<script>.mp4'
        source.write_bytes(b'input')
        _, paths = analyze(source, self.output, Estimator, cv=FakeCV(), progress=None)
        self.assertNotIn('<script>.mp4', paths['report'].read_text())
        self.assertIn('&lt;script&gt;', paths['report'].read_text())

    def test_chart_does_not_bridge_invalid_frames(self):
        rows = [{'time_s': i, 'left_flexion_deg': v, 'right_flexion_deg': None} for i, v in enumerate([10, 20, None, 30, 40])]
        self.assertEqual(chart(rows).count('<polyline'), 2)

    def test_model_not_downloaded_without_flag(self):
        with patch('urllib.request.urlopen') as request:
            with self.assertRaises(FileNotFoundError):
                ensure_model(self.root / 'model.task')
            request.assert_not_called()

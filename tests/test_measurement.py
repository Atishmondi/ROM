import math
import unittest
from types import SimpleNamespace
from rom.measurement import AngleFilter, measure_arm, summarize
from utils.angle_utils import calculate_elbow_angles, joint_angle


def landmarks():
    points = [SimpleNamespace(x=.5, y=.5, visibility=.95, presence=.95) for _ in range(33)]
    for i, x, y in [(11, .2, .5), (13, .5, .5), (15, .5, .2),
                    (12, .2, .5), (14, .5, .5), (16, .8, .5)]:
        points[i].x, points[i].y = x, y
    return points


class GeometryTests(unittest.TestCase):
    def test_straight_and_right_angle(self):
        self.assertAlmostEqual(joint_angle((0, 0), (1, 0), (2, 0)), 180)
        self.assertAlmostEqual(joint_angle((0, 0), (1, 0), (1, 1)), 90)

    def test_translation_scale_and_3d(self):
        self.assertAlmostEqual(joint_angle((1, 2, 3), (2, 2, 3), (3, 3, 3)), 135)
        self.assertAlmostEqual(joint_angle((10, 20), (20, 20), (30, 30)), 135)

    def test_degenerate_and_nonfinite(self):
        self.assertIsNone(joint_angle((0, 0), (0, 0), (1, 0)))
        self.assertIsNone(joint_angle((math.nan, 0), (0, 0), (1, 0)))

    def test_dimension_mismatch(self):
        with self.assertRaises(ValueError):
            joint_angle((0, 0), (1, 0, 0), (2, 0))

    def test_named_points_and_missing_arm(self):
        values = calculate_elbow_angles({'left_shoulder': (0, 0), 'left_elbow': (1, 0), 'left_wrist': (2, 0)})
        self.assertEqual(values, {'left': 0, 'right': None})


class MeasurementTests(unittest.TestCase):
    def test_anatomical_sides(self):
        points = landmarks()
        self.assertAlmostEqual(measure_arm(points, 'left', 640, 480)[0], 90)
        self.assertAlmostEqual(measure_arm(points, 'right', 640, 480)[0], 0)

    def test_non_square_frames_use_pixel_coordinates(self):
        points = landmarks()
        points[15].x, points[15].y = .65, .2
        # Pixel forearm is (192, -216), not normalized (.15, -.3).
        expected = 180 - joint_angle((256, 360), (640, 360), (832, 144))
        self.assertAlmostEqual(measure_arm(points, 'left', 1280, 720)[0], expected)

    def test_visibility_presence_and_bounds(self):
        for field in ('visibility', 'presence'):
            points = landmarks()
            setattr(points[13], field, .2)
            self.assertEqual(measure_arm(points, 'left', 640, 480)[2], 'low_confidence')
        points = landmarks()
        points[15].x = 1.1
        self.assertEqual(measure_arm(points, 'left', 640, 480)[2], 'out_of_frame')

    def test_absent_pose_and_short_segment(self):
        self.assertEqual(measure_arm(None, 'left', 640, 480)[2], 'no_pose')
        points = landmarks()
        points[15].x, points[15].y = .501, .5
        self.assertEqual(measure_arm(points, 'left', 640, 480)[2], 'short_segment')

    def test_nonfinite_landmark_is_rejected(self):
        for field in ('presence', 'visibility', 'x', 'y'):
            points = landmarks()
            setattr(points[13], field, math.nan)
            self.assertIsNone(measure_arm(points, 'left', 640, 480)[0])

    def test_nearly_folded_projection_is_withheld(self):
        points = landmarks()
        points[15].x, points[15].y = .22, .51
        value, confidence, status, geometry = measure_arm(points, 'left', 640, 480)
        self.assertIsNone(value)
        self.assertEqual(status, 'ambiguous_projection')
        self.assertIsNotNone(geometry)

    def test_filter_suppresses_spike_and_resets_at_gap(self):
        smooth = AngleFilter(3)
        self.assertEqual([smooth.update(v) for v in (10, 10, 170, 10, None, 90)], [10, 10, 10, 10, None, 90])

    def test_invalid_windows(self):
        for window in (0, -1, 2):
            with self.assertRaises(ValueError):
                AngleFilter(window)

    def test_summary_missing_values_not_zero(self):
        rows = [{'left_flexion_deg': v} for v in (None, 30, 60, 90, None)]
        stats = summarize(rows, 'left')
        self.assertEqual(stats['observed_rom_deg'], 60)
        self.assertEqual(stats['coverage_percent'], 60)
        self.assertAlmostEqual(stats['central_90_range_deg'], 54)

    def test_no_or_single_measurement_has_no_range(self):
        for values in ([], [None], [40, None]):
            stats = summarize([{'left_flexion_deg': v} for v in values], 'left')
            self.assertIsNone(stats['observed_rom_deg'])
            self.assertEqual(stats['status'], 'insufficient_data')

    def test_low_coverage(self):
        stats = summarize([{'left_flexion_deg': v} for v in (10, 20, None, None, None)], 'left')
        self.assertEqual(stats['status'], 'low_coverage')

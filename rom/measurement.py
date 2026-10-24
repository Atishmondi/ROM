"""Confidence filtering, temporal smoothing and observed movement summaries."""
import math
from collections import deque
from statistics import median
from utils.angle_utils import joint_angle

ARMS = {'left': (11, 13, 15), 'right': (12, 14, 16)}


def measure_arm(landmarks, side, width, height, threshold=0.6):
    if not landmarks:
        return None, 0.0, 'no_pose', None
    joints = [landmarks[i] for i in ARMS[side]]
    scores = [score for p in joints for score in (p.visibility, p.presence)]
    if not all(math.isfinite(score) for score in scores):
        return None, 0.0, 'low_confidence', None
    confidence = min(scores)
    if confidence < threshold:
        return None, confidence, 'low_confidence', None
    if any(not math.isfinite(p.x) or not math.isfinite(p.y) or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for p in joints):
        return None, confidence, 'out_of_frame', None
    points = [(p.x * width, p.y * height) for p in joints]
    if not all(getattr(p, 'agreement_ok', True) for p in joints):
        return None, confidence, 'model_disagreement', None
    # Near-coincident projected joints have unstable angles (foreshortening).
    if any(math.dist(points[i], points[i+1]) < 5 for i in (0, 1)):
        return None, confidence, 'short_segment', None
    total_length = math.dist(points[0], points[1]) + math.dist(points[1], points[2])
    # When the projected shoulder and wrist nearly overlap, depth and incorrect
    # landmark assignment are hard to distinguish from a genuinely folded arm.
    # Withhold this ambiguous 2D measurement rather than claiming full flexion.
    if math.dist(points[0], points[2]) / total_length < .15:
        return None, confidence, 'ambiguous_projection', points
    angle = joint_angle(*points)
    return (None if angle is None else 180 - angle), confidence, 'valid' if angle is not None else 'degenerate', points


class AngleFilter:
    """Trailing median; reset at every invalid frame rather than bridging gaps."""
    def __init__(self, window=5):
        if window < 1 or window % 2 == 0:
            raise ValueError('Smoothing window must be a positive odd integer')
        self.values = deque(maxlen=window)

    def update(self, value):
        if value is None:
            self.values.clear()
            return None
        self.values.append(value)
        return median(self.values)


def percentile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def summarize(rows, side):
    values = [r[f'{side}_flexion_deg'] for r in rows if r[f'{side}_flexion_deg'] is not None]
    count, total = len(values), len(rows)
    result = {'valid_frames': count, 'total_frames': total,
              'coverage_percent': round(100 * count / total, 2) if total else 0,
              'min_flexion_deg': None, 'max_flexion_deg': None,
              'observed_rom_deg': None, 'p05_flexion_deg': None,
              'p95_flexion_deg': None, 'central_90_range_deg': None,
              'status': 'insufficient_data'}
    if count < 2:
        return result
    low, high = min(values), max(values)
    p05, p95 = percentile(values, .05), percentile(values, .95)
    result.update(min_flexion_deg=low, max_flexion_deg=high, observed_rom_deg=high-low,
                  p05_flexion_deg=p05, p95_flexion_deg=p95, central_90_range_deg=p95-p05,
                  status='low_coverage' if count / total < .5 else 'measured')
    return result

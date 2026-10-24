"""Geometry independent of the pose model. Coordinates must use equal axis units."""
import math


def joint_angle(shoulder, elbow, wrist):
    """Return the unsigned interior angle (straight arm = 180°), or None."""
    if not (len(shoulder) == len(elbow) == len(wrist)):
        raise ValueError("Joint coordinates must have equal dimensions")
    if len(elbow) not in (2, 3):
        raise ValueError("Expected 2D or 3D coordinates")
    if not all(math.isfinite(x) for p in (shoulder, elbow, wrist) for x in p):
        return None
    a = [s - e for s, e in zip(shoulder, elbow)]
    b = [w - e for w, e in zip(wrist, elbow)]
    length = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if length < 1e-12:
        return None
    cosine = sum(x*y for x, y in zip(a, b)) / length
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def calculate_elbow_angles(keypoints):
    """Named pixel/world points -> left/right flexion (straight arm = 0°)."""
    result = {}
    for side in ('left', 'right'):
        points = [keypoints.get(f'{side}_{joint}') for joint in ('shoulder', 'elbow', 'wrist')]
        angle = None if any(p is None for p in points) else joint_angle(*points)
        result[side] = None if angle is None else 180.0 - angle
    return result

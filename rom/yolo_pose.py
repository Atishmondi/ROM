"""Full-context YOLO11 Pose with mirrored-input agreement checks.

Coordinates are averaged only when the two predictions agree on arm angle.
No temporal interpolation or fabricated landmarks are introduced.
"""
import os
from pathlib import Path
from types import SimpleNamespace
import urllib.request
from utils.angle_utils import joint_angle

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / 'models' / 'yolo11m-pose.pt'
MODEL_URL = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-pose.pt'
COCO_ARMS = {'left': (5, 7, 9), 'right': (6, 8, 10)}
MEDIAPIPE_ARMS = {'left': (11, 13, 15), 'right': (12, 14, 16)}
COCO_FLIP = (0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15)


def ensure_model(path=DEFAULT_MODEL, download=False):
    path = Path(path)
    if path.is_file():
        return path
    if not download:
        raise FileNotFoundError(f'Model missing: {path}. Use --download-model once.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.part')
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=120) as response, temporary.open('wb') as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        if temporary.stat().st_size < 1024 * 1024:
            raise ValueError('Downloaded pose model is unexpectedly small')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def combine_predictions(points, scores, mirror_points, mirror_scores, width, height,
                        max_disagreement=25.0):
    """Map COCO joints into the common landmark interface with explicit validity."""
    landmarks = [SimpleNamespace(x=0., y=0., visibility=0., presence=0., agreement_ok=False) for _ in range(33)]
    disagreements = {}
    for side, indices in COCO_ARMS.items():
        a, b = points[list(indices)], mirror_points[list(indices)]
        angle_a, angle_b = joint_angle(*a), joint_angle(*b)
        disagreement = abs(angle_a - angle_b) if angle_a is not None and angle_b is not None else None
        disagreements[side] = disagreement
        agreed = disagreement is not None and disagreement <= max_disagreement
        for source, target in zip(indices, MEDIAPIPE_ARMS[side]):
            p = (points[source] + mirror_points[source]) / 2
            score = float(min(scores[source], mirror_scores[source]))
            landmarks[target] = SimpleNamespace(x=float(p[0])/width, y=float(p[1])/height,
                visibility=score, presence=score, agreement_ok=agreed)
    return landmarks, disagreements


class YOLOPoseEstimator:
    def __init__(self, model_path=DEFAULT_MODEL, image_size=960, max_disagreement=25.0):
        os.environ.setdefault('YOLO_CONFIG_DIR', '/tmp')
        os.environ.setdefault('MPLCONFIGDIR', '/tmp/rom-mpl')
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.model = YOLO(str(model_path), task='pose')
        self.image_size = image_size
        self.max_disagreement = max_disagreement
        self.last_disagreement = {'left': None, 'right': None}
        self.last_status = 'no_pose'

    def _predict(self, image):
        result = self.model.predict(image, imgsz=self.image_size, device='cpu', conf=.35, verbose=False)[0]
        if result.keypoints is None or len(result.boxes) == 0:
            return None
        # Never quietly switch identities or mix measurements from several people.
        if len(result.boxes) != 1:
            self.last_status = 'multiple_people'
            return None
        return result.keypoints.xy.cpu().numpy()[0], result.keypoints.conf.cpu().numpy()[0]

    def detect(self, rgb, timestamp_ms):
        import cv2
        self.last_disagreement = {'left': None, 'right': None}
        self.last_status = 'no_pose'
        h, w = rgb.shape[:2]
        factor = min(1., 1280 / max(h, w))
        image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if factor < 1:
            image = cv2.resize(image, (round(w*factor), round(h*factor)))
        height, width = image.shape[:2]
        original = self._predict(image)
        flipped = self._predict(image[:, ::-1].copy())
        if original is None or flipped is None:
            return None
        points, scores = original
        flip_points, flip_scores = flipped
        flip_points = flip_points[list(COCO_FLIP)].copy()
        flip_points[:, 0] = width - 1 - flip_points[:, 0]
        flip_scores = flip_scores[list(COCO_FLIP)]
        result, self.last_disagreement = combine_predictions(points, scores, flip_points,
            flip_scores, width, height, self.max_disagreement)
        self.last_status = 'detected'
        return result

    def close(self):
        self.model = None

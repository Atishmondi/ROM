"""MediaPipe Tasks backend with a versioned, locally cached model."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / 'models' / 'pose_landmarker_full.task'


def ensure_model(path=DEFAULT_MODEL, download=False):
    path = Path(path)
    if not path.is_file():
        if not download:
            raise FileNotFoundError(f'Model missing: {path}. Run with --download-model once, or provide --model PATH.')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.part')
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open('wb') as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            if not zipfile.is_zipfile(temporary):
                raise ValueError('Downloaded model is not a valid MediaPipe task bundle')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def model_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class PoseEstimator:
    def __init__(self, model_path):
        import mediapipe as mp
        self.mp = mp
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path), delegate=mp.tasks.BaseOptions.Delegate.CPU),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5)
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def detect(self, rgb, timestamp_ms):
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect_for_video(image, timestamp_ms)
        return result.pose_landmarks[0] if result.pose_landmarks else None

    def close(self):
        self.detector.close()

"""Shared analysis entry point for the command line and upload app."""
import json
import math
from pathlib import Path
from .cache import CachedEstimator
from .pipeline import analyze, validate_paths
from .pose import model_hash
from .yolo_pose import DEFAULT_MODEL, MODEL_URL, YOLOPoseEstimator, ensure_model


def run_analysis(input_path, output, *, model_path=DEFAULT_MODEL, download=False,
                 confidence=.6, image_size=960, max_disagreement=25., window=5,
                 max_frames=None, progress=print):
    validate_paths(input_path, output)
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('Confidence must be between 0 and 1')
    if window < 1 or window % 2 == 0:
        raise ValueError('Smoothing window must be a positive odd integer')
    if image_size < 32 or image_size % 32:
        raise ValueError('Image size must be a positive multiple of 32')
    if not math.isfinite(max_disagreement) or not 0 <= max_disagreement <= 180:
        raise ValueError('Maximum disagreement must be between 0 and 180')
    if max_frames is not None and max_frames < 1:
        raise ValueError('Maximum frames must be positive')
    import cv2
    import ultralytics
    model = ensure_model(model_path, download)
    fingerprint = model_hash(model)
    source_fingerprint = model_hash(input_path)
    metadata = {'input_sha256': source_fingerprint, 'model_sha256': fingerprint,
                'backend': 'yolo11_pose_flip_consensus_v1', 'image_size': image_size,
                'max_disagreement': max_disagreement, 'ultralytics': ultralytics.__version__}
    factory = lambda: CachedEstimator(lambda: YOLOPoseEstimator(model, image_size, max_disagreement),
        Path(output).with_suffix('.landmarks.jsonl'), metadata)
    summary, paths = analyze(input_path, output, factory, threshold=confidence, window=window,
        max_frames=max_frames, progress=progress, cv=cv2,
        model_info={'file': model.name, 'sha256': fingerprint,
                    'download_source': MODEL_URL if model.resolve() == DEFAULT_MODEL.resolve() else None,
                    'backend': 'yolo11_pose_flip_consensus', 'image_size': image_size,
                    'ultralytics_version': ultralytics.__version__})
    summary['input_sha256'] = source_fingerprint
    paths['summary'].write_text(json.dumps(summary, indent=2, allow_nan=False))
    return summary, paths

"""Analyze a video and publish a consistent set of outputs after success."""
import csv
import json
import math
import tempfile
from pathlib import Path
from .measurement import AngleFilter, measure_arm, summarize
from .report import write_report


def output_paths(output):
    output = Path(output)
    return {'video': output, 'csv': output.with_suffix('.csv'),
            'summary': output.with_suffix('.json'), 'report': output.with_suffix('.html')}


def validate_paths(input_path, output):
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f'Input video does not exist: {source}')
    if Path(output).suffix.lower() != '.mp4':
        raise ValueError('Output must have an .mp4 extension')
    paths = output_paths(output)
    for path in paths.values():
        if path.resolve() == source.resolve():
            raise ValueError('Output must not replace the input video')
        if path.exists():
            raise FileExistsError(f'Output already exists: {path}. Choose a new output filename.')
    return paths


def annotate(cv, frame, measurements, timestamp):
    height, width = frame.shape[:2]
    scale = max(.35, width / 1700)
    thickness = max(1, round(width / 1100))
    line_height = max(18, int(32 * scale / .75))
    stacked = width < 600
    row_count = 3 if stacked else 2
    top = max(0, height - line_height * row_count - 16)
    cv.rectangle(frame, (0, top), (width, height), (22, 29, 35), -1)
    cv.putText(frame, f'ELBOW ANGLES | 2D | {timestamp:.2f}s', (12, top + line_height), cv.FONT_HERSHEY_SIMPLEX, scale, (245, 245, 245), thickness, cv.LINE_AA)
    for index, side in enumerate(('left', 'right')):
        value, status, points = measurements[side]
        color = (190, 200, 50) if side == 'left' else (70, 155, 255)
        text = f'{side.upper()} | inside {180-value:.1f} | flex {value:.1f} deg' if value is not None else f'{side.upper()}: unavailable'
        position = (12, top + line_height * (index+2)) if stacked else (12 + index * (width // 2), top + line_height * 2)
        cv.putText(frame, text, position, cv.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv.LINE_AA)
        if points and value is not None:
            pts = [(int(x), int(y)) for x, y in points]
            for a, b in zip(pts, pts[1:]):
                cv.line(frame, a, b, color, max(3, thickness * 2), cv.LINE_AA)
            for p in pts:
                cv.circle(frame, p, max(5, thickness * 3), color, -1, cv.LINE_AA)
            for label, p in zip(('S', 'E', 'W'), pts):
                cv.putText(frame, label, (p[0]+10, p[1]-10), cv.FONT_HERSHEY_SIMPLEX, scale*.6, color, thickness, cv.LINE_AA)
    return frame


def analyze(input_path, output, estimator_factory, *, threshold=.6, window=5,
            model_info=None, max_frames=None, progress=print, cv=None):
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Confidence threshold must be between 0 and 1')
    filters = {side: AngleFilter(window) for side in ('left', 'right')}
    if max_frames is not None and max_frames < 1:
        raise ValueError('max_frames must be positive')
    paths = validate_paths(input_path, output)
    if cv is None:
        import cv2 as cv
    cap = cv.VideoCapture(str(input_path))
    writer = estimator = None
    try:
        if not cap.isOpened():
            raise ValueError('Cannot open input video; check the file format and codec')
        fps = cap.get(cv.CAP_PROP_FPS)
        width, height = int(cap.get(cv.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        expected_frames = cap.get(cv.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(fps) or not 0 < fps <= 1000 or min(width, height) < 1:
            raise ValueError('Video has invalid frame rate or dimensions')
        paths['video'].parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.rom-', dir=paths['video'].parent) as temp:
            staged = {key: Path(temp) / path.name for key, path in paths.items()}
            codec = 'avc1'
            writer = cv.VideoWriter(str(staged['video']), cv.VideoWriter_fourcc(*codec), fps, (width, height))
            if not writer.isOpened():
                writer.release()
                codec = 'mp4v'
                writer = cv.VideoWriter(str(staged['video']), cv.VideoWriter_fourcc(*codec), fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError('Cannot create MP4 video with the available OpenCV codec')
            estimator = estimator_factory()
            rows, previous_ms = [], -1
            while max_frames is None or len(rows) < max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[:2] != (height, width):
                    raise ValueError('Video frame dimensions changed during decoding')
                index = len(rows)
                seconds = index / fps
                timestamp_ms = max(previous_ms+1, round(seconds*1000))
                previous_ms = timestamp_ms
                landmarks = estimator.detect(cv.cvtColor(frame, cv.COLOR_BGR2RGB), timestamp_ms)
                row = {'frame': index, 'time_s': seconds}
                measurements = {}
                for side in ('left', 'right'):
                    raw, confidence, status, points = measure_arm(landmarks, side, width, height, threshold)
                    if landmarks is None and getattr(estimator, 'last_status', None) == 'multiple_people':
                        status = 'multiple_people'
                    filtered = filters[side].update(raw)
                    row.update({f'{side}_raw_flexion_deg': raw, f'{side}_flexion_deg': filtered,
                                f'{side}_inside_angle_deg': None if raw is None else 180-raw,
                                f'{side}_confidence': confidence, f'{side}_status': status})
                    row[f'{side}_flip_disagreement_deg'] = getattr(estimator, 'last_disagreement', {}).get(side)
                    # Draw the angle of the visible current-frame geometry.
                    # Smoothing is exported separately, never mislabeled as this frame.
                    measurements[side] = raw, status, points
                    for joint_index, joint in enumerate(('shoulder', 'elbow', 'wrist')):
                        row[f'{side}_{joint}_x_px'] = points[joint_index][0] if points else None
                        row[f'{side}_{joint}_y_px'] = points[joint_index][1] if points else None
                writer.write(annotate(cv, frame, measurements, seconds))
                rows.append(row)
                if progress and len(rows) % 25 == 0:
                    progress(f'Processed {len(rows)} frames ({seconds:.1f}s)')
            if not rows:
                raise ValueError('No frames could be decoded from the input video')
            writer.release()
            writer = None
            if not staged['video'].is_file() or staged['video'].stat().st_size == 0:
                raise RuntimeError('Video encoder produced an empty output')
            # Reopen and decode every output frame to detect silent encoder failures.
            verification = cv.VideoCapture(str(staged['video']))
            encoded_count = 0
            try:
                while verification.isOpened():
                    valid, _ = verification.read()
                    if not valid:
                        break
                    encoded_count += 1
            finally:
                verification.release()
            if encoded_count != len(rows):
                raise RuntimeError(f'Video verification failed: {encoded_count} of {len(rows)} frames readable')
            arms = {side: summarize(rows, side) for side in ('left', 'right')}
            warnings = ['Measurements are projected 2D estimates, not calibrated or clinically validated.',
                        'Timestamps use frame index / source FPS; variable-frame-rate timing is approximated.',
                        'One person is tracked. Subject changes are not detected; use a single-person clip.']
            if codec != 'avc1':
                warnings.append('H.264 encoding was unavailable. The exported MPEG-4 video may need a desktop player rather than browser playback.')
            for side, stats in arms.items():
                if stats['status'] != 'measured':
                    warnings.append(f'{side.title()} arm: {stats["status"].replace("_", " ")} ({stats["coverage_percent"]:.1f}% usable frames).')
            truncated = max_frames is not None and len(rows) >= max_frames
            if truncated:
                warnings.append(f'Processing was capped at {max_frames} frames; results may cover only part of the video.')
            elif math.isfinite(expected_frames) and expected_frames > len(rows)+1:
                warnings.append(f'Decoding ended after {len(rows)} frames; file metadata advertised {int(expected_frames)}. Input may be truncated.')
            summary = {'schema_version': 1, 'input_name': Path(input_path).name,
                       'frames': len(rows), 'fps': fps, 'width': width, 'height': height,
                       'duration_s': len(rows)/fps, 'angle_method': '2d_pixel_flexion',
                       'confidence_threshold': threshold, 'smoothing_window': window,
                       'video_angles': 'raw_current_frame', 'max_flip_disagreement_deg': getattr(estimator, 'max_disagreement', None),
                       'model': model_info, 'arms': arms, 'warnings': warnings}
            with staged['csv'].open('w', newline='', encoding='utf-8') as stream:
                csv_writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                csv_writer.writeheader()
                csv_writer.writerows(rows)
            staged['summary'].write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
            write_report(staged['report'], summary, rows)
            for key, destination in paths.items():
                if destination.exists():
                    raise FileExistsError(f'Output appeared during processing: {destination}')
            for key, destination in paths.items():
                staged[key].replace(destination)
            return summary, paths
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if estimator is not None:
            estimator.close()

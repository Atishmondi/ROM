"""Bundle a recorded run with source/output comparison, without new inference.

Usage: python -m rom.review --source inputs/hello.mp4 --run outputs/hello_rom
"""
import argparse
import csv
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from .report import write_report


def build_review(source, run):
    import cv2
    import numpy as np
    source, run = Path(source), Path(run)
    original_video = run.with_suffix('.mp4')
    summary = json.loads(run.with_suffix('.json').read_text())
    with run.with_suffix('.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key, value in row.items():
            if key == 'frame':
                row[key] = int(value)
            elif not key.endswith('_status'):
                row[key] = float(value) if value else None
    if len(rows) != summary['frames']:
        raise ValueError('CSV and JSON frame counts differ')
    if any(row['frame'] != index for index, row in enumerate(rows)):
        raise ValueError('CSV frame numbers are not sequential')
    comparison = run.with_name(run.name + '_comparison').with_suffix('.mp4')
    copied_source = run.with_name(run.name + '_source').with_suffix(source.suffix)
    left, right = cv2.VideoCapture(str(source)), cv2.VideoCapture(str(original_video))
    writer = None
    try:
        if not left.isOpened() or not right.isOpened():
            raise ValueError('Cannot read source or annotated recording')
        for capture in (left, right):
            if abs(capture.get(cv2.CAP_PROP_FPS) - summary['fps']) > .01:
                raise ValueError('Recording FPS differs from saved measurements')
        with tempfile.TemporaryDirectory(prefix='.review-', dir=run.parent) as temporary:
            temporary_video = Path(temporary) / comparison.name
            panel_w = 960
            panel_h = round(panel_w * summary['height'] / summary['width'])
            panel_h += panel_h % 2
            out_height = panel_h + 144
            writer = cv2.VideoWriter(str(temporary_video), cv2.VideoWriter_fourcc(*'avc1'), summary['fps'], (panel_w * 2, out_height))
            if not writer.isOpened():
                raise RuntimeError('H.264 encoding unavailable for comparison export')
            for index, row in enumerate(rows):
                valid_a, a = left.read()
                valid_b, b = right.read()
                if not valid_a or not valid_b:
                    raise ValueError(f'Recording ended before CSV frame {index}')
                canvas = np.full((out_height, panel_w * 2, 3), (22, 29, 35), dtype=np.uint8)
                canvas[58:58+panel_h, :panel_w] = cv2.resize(a, (panel_w, panel_h))
                canvas[58:58+panel_h, panel_w:] = cv2.resize(b, (panel_w, panel_h))
                cv2.putText(canvas, 'ORIGINAL FOOTAGE', (20, 38), cv2.FONT_HERSHEY_SIMPLEX, .85, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(canvas, 'RECORDED MODEL OUTPUT - INSPECT TRACKING', (panel_w+20, 38), cv2.FONT_HERSHEY_SIMPLEX, .75, (105, 200, 255), 2, cv2.LINE_AA)
                def angle(value):
                    return 'unavailable' if value is None else f'{value:.1f} deg'
                cv2.putText(canvas, f'FRAME {index} | {row["time_s"]:.2f}s | Same source frame in both panels', (20, out_height-53), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 1, cv2.LINE_AA)
                raw, smooth = row['left_raw_flexion_deg'], row['left_flexion_deg']
                text = f'LEFT: raw {angle(raw)} | smoothed {angle(smooth)} | Tracking overlay is an estimate, not accuracy validation'
                cv2.putText(canvas, text, (20, out_height-20), cv2.FONT_HERSHEY_SIMPLEX, .63, (105, 200, 255), 1, cv2.LINE_AA)
                writer.write(canvas)
            writer.release()
            writer = None
            verification = cv2.VideoCapture(str(temporary_video))
            count = 0
            try:
                while verification.read()[0]:
                    count += 1
            finally:
                verification.release()
            if count != len(rows):
                raise RuntimeError('Comparison encoding frame count mismatch')
            temporary_video.replace(comparison)
    finally:
        left.release()
        right.release()
        if writer is not None:
            writer.release()
    shutil.copy2(source, copied_source)
    summary['evidence_video'] = comparison.name
    summary['source_video'] = copied_source.name
    notes = [
        'This comparison replays the existing recorded run; it does not claim a new or more accurate pose estimate.',
        'The inspector and comparison footer show raw and smoothed values separately. The recorded summary values below are estimates, not verified physical ROM.'
    ]
    if summary.get('model', {}).get('backend') == 'yolo11_pose_flip_consensus':
        notes[0] = 'This comparison uses the freshly inferred YOLO11 Pose recording, with the source and output synchronized frame for frame.'
    if summary.get('video_angles') != 'raw_current_frame':
        notes.append('This older overlay displays smoothed numbers beside current-frame joints. These can disagree; the updated analyzer labels current-frame geometry with its raw angle.')
    for side in ('left', 'right'):
        valid = [row for row in rows if row[f'{side}_raw_flexion_deg'] is not None]
        if valid:
            peak = max(valid, key=lambda row: row[f'{side}_raw_flexion_deg'])
            value = peak[f'{side}_raw_flexion_deg']
            if value > 165:
                notes.append(f'{side.title()} arm at {peak["time_s"]:.2f}s: raw projected flexion reaches {value:.1f} degrees. Near-folded 2D geometry can be ambiguous; inspect the joints before trusting this extreme or the resulting range.')
        if summary['arms'][side]['coverage_percent'] < 50:
            notes.append(f'{side.title()} arm has low tracking coverage ({summary["arms"][side]["coverage_percent"]:.1f}%). Its recorded range needs review.')
    summary['review_notes'] = notes
    summary['evidence_export'] = {'kind': 'recorded_run_comparison', 'frames_verified': len(rows), 'new_inference': False}
    run.with_suffix('.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    write_report(run.with_suffix('.html'), summary, rows)
    bundle = run.with_name(run.name + '_evidence').with_suffix('.zip')
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        files = [run.with_suffix('.html'), run.with_suffix('.csv'), run.with_suffix('.json'), original_video, comparison, copied_source]
        for key in ('validation_image', 'validation_file'):
            if summary.get(key): files.append(run.parent / summary[key])
        for file in files:
            archive.write(file, arcname=file.name)
    return comparison, bundle


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', required=True, help='Saved run stem, without extension')
    args = parser.parse_args()
    for artifact in build_review(args.source, args.run):
        print(artifact)

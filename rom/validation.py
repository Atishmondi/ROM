"""Compare exported frame measurements with independently marked image points.

References are approximate 2D visual marks, never clinical ground truth.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from utils.angle_utils import joint_angle
from .report import write_report


def read_rows(path):
    with Path(path).open(newline='') as stream:
        records = list(csv.DictReader(stream))
    result = {}
    for record in records:
        for key, value in record.items():
            if key == 'frame': record[key] = int(value)
            elif not key.endswith('_status'): record[key] = float(value) if value else None
        result[record['frame']] = record
    return result


def metric(values):
    return {'count': len(values), 'mae_deg': mean(values) if values else None,
            'max_error_deg': max(values) if values else None}


def evaluate(reference, run, source, baseline=None):
    reference, run, source = Path(reference), Path(run), Path(source)
    spec = json.loads(reference.read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != spec['input_sha256']:
        raise ValueError('Reference points belong to a different source video')
    summary = json.loads(run.with_suffix('.json').read_text())
    current = read_rows(run.with_suffix('.csv'))
    previous = read_rows(baseline) if baseline else {}
    records = []
    for item in spec['frames']:
        frame, side = item['frame'], item['side']
        expected = 180 - joint_angle(*[item[j] for j in ('shoulder', 'elbow', 'wrist')])
        row = current.get(frame, {})
        prediction = row.get(f'{side}_raw_flexion_deg')
        old = previous.get(frame, {}).get(f'{side}_raw_flexion_deg')
        records.append({'frame': frame, 'time_s': frame/summary['fps'], 'side': side,
                        'split': item.get('split', 'development'), 'reference_deg': expected,
                        'prediction_deg': prediction, 'baseline_deg': old,
                        'absolute_error_deg': abs(prediction-expected) if prediction is not None else None,
                        'baseline_absolute_error_deg': abs(old-expected) if old is not None else None})
    common = [row for row in records if row['prediction_deg'] is not None and row['baseline_deg'] is not None]
    metrics = {split: metric([r['absolute_error_deg'] for r in records if r['split'] == split and r['absolute_error_deg'] is not None]) for split in ('development', 'check')}
    result = {'reference_kind': spec['reference_kind'], 'notes': spec['notes'],
              'reference_frames': len(records), 'current': metric([r['absolute_error_deg'] for r in records if r['absolute_error_deg'] is not None]),
              'splits': metrics,
              'common_frames': {'current': metric([r['absolute_error_deg'] for r in common]),
                                'baseline': metric([r['baseline_absolute_error_deg'] for r in common])},
              'frames': records}
    output = run.with_name(run.name + '_validation').with_suffix('.json')
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    summary['validation'] = result
    summary['validation_file'] = output.name
    # Re-checks after rendering retain the same validated data.
    if summary.get('model', {}).get('backend') == 'yolo11_pose_flip_consensus':
        summary['review_notes'] = [
            'This is a fresh YOLO11 Pose run, checked against approximate visual marks on the visible arm.',
            'The comparison is a small check on this one clip. It does not establish clinical accuracy or validate the hidden arm.'
        ]
    summary['validation_image'] = make_contact_sheet(spec, summary, current, source, run)
    run.with_suffix('.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    write_report(run.with_suffix('.html'), summary, list(current.values()))
    return result, output


def make_contact_sheet(spec, summary, rows, source, run):
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(source))
    tiles = []
    try:
        for item in spec['frames']:
            cap.set(cv2.CAP_PROP_POS_FRAMES, item['frame'])
            ok, frame = cap.read()
            if not ok: raise ValueError('Cannot decode reference frame')
            frame = cv2.resize(frame, (spec['coordinate_width'], spec['coordinate_height']))
            row, side = rows[item['frame']], item['side']
            reference = [tuple(item[j]) for j in ('shoulder', 'elbow', 'wrist')]
            for a, b in zip(reference, reference[1:]): cv2.line(frame, a, b, (220, 60, 200), 3, cv2.LINE_AA)
            for p in reference: cv2.circle(frame, p, 10, (220, 60, 200), 2, cv2.LINE_AA)
            points = []
            for joint in ('shoulder', 'elbow', 'wrist'):
                x, y = row.get(f'{side}_{joint}_x_px'), row.get(f'{side}_{joint}_y_px')
                if x is None or y is None: break
                points.append((round(x/summary['width']*spec['coordinate_width']), round(y/summary['height']*spec['coordinate_height'])))
            if len(points) == 3:
                for a, b in zip(points, points[1:]): cv2.line(frame, a, b, (190, 200, 50), 3, cv2.LINE_AA)
                for p in points: cv2.circle(frame, p, 5, (190, 200, 50), -1, cv2.LINE_AA)
            expected = 180 - joint_angle(*reference)
            value = row.get(f'{side}_raw_flexion_deg')
            actual = 'unavailable' if value is None else f'{value:.1f}'
            cv2.rectangle(frame, (0,0), (frame.shape[1],65), (22,29,35), -1)
            cv2.putText(frame, f'Frame {item["frame"]} | {item.get("split", "development")} | reference {expected:.1f} | model {actual}', (14,40), cv2.FONT_HERSHEY_SIMPLEX, .85, (255,255,255), 2, cv2.LINE_AA)
            tiles.append(cv2.resize(frame, (640,360)))
    finally:
        cap.release()
    if not tiles: return None
    if len(tiles) % 2: tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i+2]) for i in range(0,len(tiles),2)])
    destination = run.with_name(run.name + '_validation').with_suffix('.jpg')
    if not cv2.imwrite(str(destination), sheet): raise OSError('Cannot save validation contact sheet')
    return destination.name


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--baseline', help='Previous run CSV for a paired comparison')
    args = parser.parse_args()
    result, destination = evaluate(args.reference, args.run, args.source, args.baseline)
    print(json.dumps({key: value for key, value in result.items() if key not in ('frames','notes')}, indent=2))
    print(destination)

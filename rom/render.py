"""Re-render a saved run's exported joints on the original footage, without new inference."""
import argparse
import json
import tempfile
from pathlib import Path
from .validation import read_rows
from .pipeline import annotate
from .report import write_report


def render(source, run):
    import cv2
    source, run = Path(source), Path(run)
    summary = json.loads(run.with_suffix('.json').read_text())
    rows = list(read_rows(run.with_suffix('.csv')).values())
    cap = cv2.VideoCapture(str(source))
    writer = None
    try:
        if not cap.isOpened(): raise ValueError('Cannot decode original video')
        with tempfile.TemporaryDirectory(prefix='.render-', dir=run.parent) as temporary:
            target = Path(temporary) / run.with_suffix('.mp4').name
            writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*'avc1'), summary['fps'], (summary['width'],summary['height']))
            if not writer.isOpened(): raise RuntimeError('H.264 writer unavailable')
            for row in rows:
                ok, frame = cap.read()
                if not ok: raise ValueError('Source ended before the saved run')
                measurements = {}
                for side in ('left','right'):
                    raw = row[f'{side}_raw_flexion_deg']
                    points = [(row[f'{side}_{j}_x_px'],row[f'{side}_{j}_y_px']) for j in ('shoulder','elbow','wrist')] if raw is not None else None
                    measurements[side] = (raw,row[f'{side}_status'],points)
                writer.write(annotate(cv2, frame, measurements, row['time_s']))
            writer.release();writer=None
            check=cv2.VideoCapture(str(target));count=0
            try:
                while check.read()[0]: count+=1
            finally: check.release()
            if count!=len(rows): raise RuntimeError('Rendered frame count mismatch')
            target.replace(run.with_suffix('.mp4'))
    finally:
        cap.release()
        if writer is not None: writer.release()
    summary['video_angles']='raw_current_frame'
    summary['rendered_from']='exported_joint_coordinates'
    run.with_suffix('.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    write_report(run.with_suffix('.html'),summary,rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--run',required=True)
    args=parser.parse_args();render(args.source,args.run)

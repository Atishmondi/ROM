"""Command-line entry point; use app.py for browser uploads."""
import argparse
import sys
from rom.service import run_analysis
from rom.yolo_pose import DEFAULT_MODEL


def main(argv=None):
    parser = argparse.ArgumentParser(description='Measure observed elbow movement in a single-person video.')
    parser.add_argument('--input', required=True, help='Input video path')
    parser.add_argument('--output', required=True, help='New annotated .mp4 path; CSV/JSON/HTML use the same stem')
    parser.add_argument('--model', default=DEFAULT_MODEL, help='Local YOLO11 Pose .pt weights')
    parser.add_argument('--download-model', action='store_true', help='Download official model if missing')
    parser.add_argument('--confidence', type=float, default=.6)
    parser.add_argument('--image-size', type=int, default=960)
    parser.add_argument('--max-disagreement', type=float, default=25.)
    parser.add_argument('--smoothing-window', type=int, default=5)
    parser.add_argument('--max-frames', type=int)
    args = parser.parse_args(argv)
    try:
        summary, paths = run_analysis(args.input, args.output, model_path=args.model,
            download=args.download_model, confidence=args.confidence, image_size=args.image_size,
            max_disagreement=args.max_disagreement, window=args.smoothing_window, max_frames=args.max_frames)
        print(f'Finished: {summary["frames"]} frames')
        for side, stats in summary['arms'].items():
            value = stats['observed_rom_deg']
            print(f'{side.title()}: ' + (f'{value:.1f}° observed range' if value is not None else 'insufficient data') + f' | {stats["coverage_percent"]:.1f}% usable frames')
        for kind, path in paths.items(): print(f'{kind}: {path}')
        return 0
    except ImportError as exc:
        print(f'Missing dependency: {exc}. Install with: uv pip install -r requirements.txt', file=sys.stderr)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

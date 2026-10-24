# Elbow ROM from video

Estimate left and right elbow flexion through a single-person video, inspect the
tracked joints, and report the movement range observed in the clip. The outputs
include an annotated video, a playable HTML report and frame-by-frame measurements.

## Upload any video through the browser

```sh
./scripts/setup.sh              # Once, for installation and model download
.venv/bin/python app.py
```

Open **http://127.0.0.1:8000**, choose or drop a video, and click **Analyze video**.
Watch the annotated result, pause to see both inside angle and elbow flexion,
and download the automatically generated **PDF report**, MP4, CSV, JSON, interactive
HTML report or a ZIP containing all the files. The PDF appears under **Analysis
report** in the right inspector as soon as processing finishes. It includes
measured ranges, coverage, the angle graph and minimum/maximum frame images.
Each upload is processed independently; the app is not tied to the sample video.
The interface is a video workspace with original/analyzed views, frame stepping,
timeline scrubbing, left/right arm selection and light/dark appearance. Recent
analysis links are saved in this browser. Measurements shown before analysis
are explicitly unavailable, not sample values.
On macOS, double-click `Start-Elbow-ROM.command` to start the server again.

The upload screen supports MP4, MOV, AVI, MKV, WEBM and other formats readable by
OpenCV. Unreadable files receive a clear error. A browser may not preview every
input format, even when the analysis can decode it. Output video uses H.264; if
OpenCV cannot encode H.264 on the host, install FFmpeg for automatic conversion.

Uploads run in a background queue, one analysis at a time. The default limit is
1 GB per file; set `ROM_MAX_UPLOAD_MB` before starting the server to change it.
Refresh or return to the analysis URL to see its status. Completed jobs survive
server restarts; interrupted jobs are marked for re-upload. Files remain under
`outputs/uploads/<job-id>/` until the server operator removes them.

The default address is local to this Mac. Running the Python backend on a hosted
server is needed for an internet-accessible upload link. For access from other
devices on a trusted local network, use `python app.py --host 0.0.0.0` and the
server's network address. This prototype does not provide user accounts.

The active model is **YOLO11m Pose**, using the full image and a second, mirrored
prediction. A frame is measured only when both passes have adequate joint scores
and agree on the arm angle. This replaces the original DensePose experiment and
the initial MediaPipe tracker, which made large errors on the included exercise clip.

## Check the latest sample

After the sample run, open:

```sh
open outputs/hello_rom_yolo.html
open outputs/hello_rom_yolo.mp4
```

The HTML includes playback, an angle graph, minimum/maximum frame buttons and a
frame inspector showing raw and smoothed values separately. The annotated video
labels shoulder (S), elbow (E) and wrist (W). Its displayed number is calculated
from the joint positions drawn on that exact frame.

`hello_rom_yolo_comparison.mp4`, when exported, shows source and annotated footage
side by side. `hello_rom_yolo_evidence.zip` packages the report, source, videos,
measurements and visual-reference checks. Extract the ZIP before opening the HTML.
The older `hello_rom.*` files are retained for comparison; they contain the previous
tracker's results.

## Install and run

Use Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
./scripts/setup.sh
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/my_run.mp4
open outputs/my_run.html
```

Setup installs the pinned Python dependencies, downloads the official pretrained
YOLO11m Pose weights and runs tests. After setup, processing runs locally without
an API key. CPU inference makes two passes per frame, so expect processing to take
longer than playback. Model weights stay under `models/` and are ignored by Git.

For manual installation:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/my_run.mp4 --download-model
```

Choose a new output filename each time. Existing final results and the source
video are protected from overwriting. Quote paths containing spaces.

## Outputs

| File | Contents |
| --- | --- |
| `my_run.mp4` | Current-frame joints and raw flexion angles; no audio |
| `my_run.csv` | Raw/smoothed angles, joint coordinates, confidence, mirrored disagreement and rejection reasons |
| `my_run.json` | Model fingerprint, settings, coverage, minimum/maximum angles and observed range |
| `my_run.html` | Video, frame inspector and angle graph |
| `my_run.landmarks.jsonl` | Inference checkpoint, matched to the source/model/settings by fingerprints |

Interrupted runs keep completed inference frames in the checkpoint. Repeating the
same command reuses those frames and continues; it still decodes and renders the
video from the beginning. Changing the source, model or inference settings requires
a new output filename. A checkpoint with mismatched fingerprints is rejected.

**0° means straight; 90° means a right-angle bend.** Left/right refer to the
person's anatomical sides. Flexion is `180 − shoulder–elbow–wrist interior angle`
in image pixels. Coordinates are scaled back to the source dimensions before
measurement, so non-square video frames do not distort the geometry.

Observed ROM is maximum minus minimum of usable, smoothed flexion estimates.
The report also gives P95 minus P05, which is less sensitive to isolated extremes
but can omit real endpoints. Neither quantity proves the person's full achievable
range. Fewer than two valid frames gives an unavailable range, not zero.

## Reliability checks

- Preserve full-body context; tight crops worsened some trial predictions.
- Map the mirrored prediction back to the original image and anatomical sides.
- Require confidence of at least 0.6 in both passes for all three arm joints.
- Withhold measurements when original/mirrored angles differ by more than 25°.
- Reject off-screen, degenerate or near-overlapping projected geometry. Shoulder–wrist distance below 15% of the summed projected limb lengths is treated as ambiguous. This conservative heuristic can reject genuine deep flexion.
- Reject frames with multiple detected people rather than mixing their measurements.
- Apply a trailing five-frame median to summaries; reset it after missing frames.
- Draw raw frame angles, never delayed smoothed numbers beside current-frame joints.

Confidence and agreement are quality filters, not guarantees of correctness.

## Inspect and share a run

```sh
.venv/bin/python -m rom.review --source inputs/hello.mp4 --run outputs/my_run
open outputs/my_run.html
```

This creates the side-by-side video and evidence ZIP, and updates the HTML to
play the comparison. It reuses the saved predictions rather than re-running the
model. To re-render new-style CSV joint coordinates with the current overlay:

```sh
.venv/bin/python -m rom.render --source inputs/hello.mp4 --run outputs/my_run
```

The included clip also has eight approximate visual references on the visible arm:
four development frames used to choose settings and four additional check frames
marked before evaluating those predictions. Run the check with:

```sh
.venv/bin/python -m rom.validation --reference validation/reference_points.json --source inputs/hello.mp4 --run outputs/hello_rom_yolo --baseline outputs/hello_rom.csv
```

This adds a per-frame comparison table and reference-versus-model image sheet to
the report. References are rough image marks with about 10–20px uncertainty at
1280 × 720. They are not clinical ground truth or an independent external test set.
The check measures agreement with those marks, not physical joint-angle accuracy.

## Options

```sh
# A short preview
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/preview.mp4 --max-frames 50

# Stricter filtering and no application-level smoothing
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/strict.mp4 --confidence 0.8 --max-disagreement 15 --smoothing-window 1
```

`--image-size` defaults to 960 and must be a positive multiple of 32. Increasing
resolution did not consistently improve the development frames. Model confidence
must be in [0,1], and the smoothing window must be a positive odd integer.

## Scope and limitations

This is a **2D video estimate**, affected by perspective, occlusion, blur and model
errors. Keep the measured arm side-on, with shoulder, elbow and wrist visible and
motion roughly parallel to the image plane. An obscured far arm may be unavailable
or inaccurate; its measurements have not been validated by the visible-arm check.
Unsigned image geometry cannot distinguish hyperextension from flexion.

Use a steady, single-person recording. Subject changes can still mix measurements
across time. Timestamps use frame index / source FPS, so variable-frame-rate timing
is approximate. Frames and measurements are held in memory during each run.

This prototype has not been clinically validated and does not diagnose limitations.
A convincing overlay is evidence of program behavior, not evidence of measurement
accuracy. Broader evaluation needs independently labeled recordings and a physical
reference such as a calibrated measurement setup.

## Tests and sources

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover geometry, filtering, mirrored disagreement, missing detections,
checkpoints, exports, failure cleanup and a real model/codec blank-video round trip.

[YOLO pose documentation](https://docs.ultralytics.com/tasks/pose/) ·
[YOLO11 model documentation](https://docs.ultralytics.com/models/yolo11/).
The pretrained model and Ultralytics package use their upstream licensing terms;
see [Ultralytics](https://github.com/ultralytics/ultralytics).

Original DensePose code is archived in `legacy/densepose/`. The optional
`detectron2/` checkout belongs to that experiment and is not required by the active
application. `rom/pose.py` retains the earlier MediaPipe backend for reference.

# Setup and technical guide

[Back to the project README](../README.md)

## Manual installation

The automated `scripts/setup.sh` workflow is tested on macOS. For other platforms, install [uv](https://docs.astral.sh/uv/getting-started/installation/) and make FFmpeg available on your system's PATH if OpenCV cannot encode H.264. The following manual paths have not been verified end to end on Windows or Linux.

**macOS / Linux shell**

```bash
git clone https://github.com/Atishmondi/ROM.git
cd ROM
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c "from rom.yolo_pose import ensure_model; ensure_model(download=True)"
.venv/bin/python app.py
```

**Windows PowerShell**

```powershell
git clone https://github.com/Atishmondi/ROM.git
cd ROM
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe -c "from rom.yolo_pose import ensure_model; ensure_model(download=True)"
.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:8000`. The Python environment and model are local to your checkout. No Detectron2 installation or recursive submodule checkout is required.

The model download is the official YOLO11m Pose checkpoint, saved as `models/yolo11m-pose.pt`. For an offline setup, install dependencies and transfer that model file in advance.

## Browser workflow

Choose or drop a video, then click **Analyze video**. The app accepts any file it can decode as video; the browser may not preview every format the backend can process.

Uploads enter a background queue, with one analysis running at a time. When finished, the inspector provides the PDF and ZIP downloads. Other formats are available under **Other formats**. The original and analyzed views share playback position; frame stepping and timeline scrubbing update the current measurements.

Keep the server running. Refreshing the analysis URL restores its status, and completed jobs survive restarts. Jobs interrupted by a server restart are marked for re-upload. Videos and generated results are retained under `outputs/uploads/<job-id>/` until removed manually.

The default upload limit is 1024 MiB. To change it before starting:

```bash
ROM_MAX_UPLOAD_MB=512 .venv/bin/python app.py
```

The default binding is `127.0.0.1:8000`, accessible on the server computer. To use a different port or allow connections from a trusted local network:

```bash
.venv/bin/python app.py --host 0.0.0.0 --port 8000
```

Connect using the server's network address. This prototype has no user-account system; public hosting needs a deployment appropriate for uploaded files and long-running CPU jobs. GitHub Pages cannot run the Python inference backend.

## Command-line analysis

```bash
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/sample.mp4
```

Choose a new output filename for each run. The CLI protects existing final results and the input video from overwriting. Quote paths containing spaces.

The CLI writes MP4, CSV, JSON, HTML and an inference checkpoint. **Automatic PDF and ZIP packaging is part of the browser upload workflow.**

```bash
# Process only the first 50 frames
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/preview.mp4 --max-frames 50

# Stricter filtering and no summary smoothing
.venv/bin/python main.py --input inputs/hello.mp4 --output outputs/strict.mp4 --confidence 0.8 --max-disagreement 15 --smoothing-window 1
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--confidence` | `0.6` | Minimum joint score in both original and mirrored predictions |
| `--image-size` | `960` | Inference size; must be a positive multiple of 32 |
| `--max-disagreement` | `25` | Maximum difference between original/mirrored arm angles, in degrees |
| `--smoothing-window` | `5` | Trailing median window; a positive odd number, with `1` disabling smoothing |
| `--max-frames` | Whole video | Optional preview cap |
| `--model` | `models/yolo11m-pose.pt` | Local pose checkpoint |
| `--download-model` | Off | Download the official model if missing |

Full-frame context and 960px inference were selected after trial comparisons. Increasing resolution or tightly cropping the person did not consistently improve those development frames.

## Measurement and filtering

1. Predict the full frame and a horizontally mirrored copy.
2. Restore the mirrored coordinates and left/right anatomical identities.
3. Average corresponding joint positions, accepting an arm only if its two angle estimates agree within the configured threshold and all joint scores pass.
4. Scale coordinates to source-image pixels and calculate the shoulder-elbow-wrist interior angle.
5. Convert to flexion with `180 - inside angle`.
6. Export the raw current-frame values; apply a trailing median to the summary series, resetting after every gap.

The CSV contains both angle conventions, smoothed flexion, joint coordinates, minimum model score, mirrored-angle disagreement and a rejection reason. Blank values mean unavailable, not zero.

The pipeline also rejects out-of-frame coordinates, projected segments shorter than five pixels, and geometries where shoulder-to-wrist distance is less than 15% of the summed projected limb lengths. That last check is conservative: it can withhold genuine deep flexion as well as ambiguous projections.

More than one pose candidate causes the frame to be withheld. This avoids quietly choosing among competing detections, but false extra detections can also reduce coverage. There is no identity tracking across subject changes.

Summaries need at least two usable measurements. Below 50% coverage, a range is marked `low_coverage`. This is a reporting heuristic, not a clinical threshold. The optional central-90% range is P95 minus P05; it reduces isolated extremes but may omit genuine endpoints.

## Checkpoints and recovery

Each CLI or browser analysis writes a `.landmarks.jsonl` checkpoint. It records completed inference frames and fingerprints of the source, model and inference settings.

If a CLI run is interrupted before final outputs are published, repeating the same command reuses its completed predictions and continues inference. The video is still decoded and rendered from the beginning. Changed inputs or inference settings require a new output filename; mismatched checkpoints are rejected.

Browser jobs use the same inference checkpoints internally, but the current web interface asks for a new upload after a server interruption. It does not provide a resume button.

## Comparison exports and visual checks

After creating `outputs/sample.*` with the CLI command above, evaluate the included source against its visual references:

```bash
.venv/bin/python -m rom.validation --reference validation/reference_points.json --source inputs/hello.mp4 --run outputs/sample
```

This adds a comparison table and joint-reference image to the HTML report. Reference points are specific to the bundled source video and verified against its fingerprint. They are approximate visual annotations, not clinical ground truth.

Then package source-versus-output playback:

```bash
.venv/bin/python -m rom.review --source inputs/hello.mp4 --run outputs/sample
```

This creates `sample_comparison.mp4` and `sample_evidence.zip`, then updates the report's video player. It reuses existing predictions; it does not improve the model's landmarks. Historical results are recorded in [the evaluation notes](../validation/RESULTS.md). Their previous-model baseline files are not included in a fresh clone.

To redraw annotations from saved joint coordinates without repeating inference:

```bash
.venv/bin/python -m rom.render --source inputs/hello.mp4 --run outputs/sample
```

## Tests

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers geometry, filtering, cached inference, missing detections, HTTP uploads, queue behavior, path isolation, downloads, PDFs and a real model/codec smoke test. Codec-dependent tests require the relevant encoder; the native H.264 writer checks have been verified on macOS. Passing software tests does not establish angle accuracy on people.

## Troubleshooting

- **Video cannot be read:** re-export it as a conventional MP4 with H.264 video. A readable filename extension alone does not mean the file contains a valid video stream.
- **Browser preview fails:** some input containers/codecs cannot play in the browser even though OpenCV can decode them. Analysis may still work.
- **H.264 output fails:** make FFmpeg available on PATH so the web worker can convert its output for browser playback.
- **An angle is unavailable:** inspect joint visibility and the rejected-frame reason. Better camera placement may help; lowering filters does not prove a measurement is correct.
- **Everything is slow:** the default CPU path performs two pose predictions per frame. Shorter clips are useful for an initial check.

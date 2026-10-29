# Elbow ROM

A local web app that measures elbow movement from video. Upload a recording, inspect the tracked shoulder, elbow and wrist, and export the annotated footage with a PDF report.

The app shows **both the visible inside angle and elbow flexion**, frame by frame. It also reports how much movement was observed across the clip, with tracking coverage alongside the result.

https://github.com/user-attachments/assets/89abc852-1a64-43d3-b2f3-4cf9c777acd1

**22-second demo** — original and annotated footage, the analysis workspace, and the generated PDF report.

[Try it locally](#try-it-locally) · [Example PDF](docs/example-report.pdf) · [Technical guide](docs/USAGE.md) · [Evaluation notes](validation/RESULTS.md)

## What you can do

- **Use your own recording.** Upload MP4, MOV, AVI, MKV, WEBM or another format the server can decode.
- **Inspect each measurement.** Switch between original and annotated footage, step through frames, or drag the timeline to a particular moment.
- **Follow either arm.** Select the left or right elbow to see its current angles, movement range and proportion of frames measured.
- **Take the results with you.** Download the PDF, annotated video, raw measurements or a ZIP containing the analysis files.

The interface supports light and dark appearance, a mobile layout and links to recent analyses saved in the browser. The demo includes the workspace from a real completed test upload.

## Try it locally

The automated setup has been tested on **macOS with Python 3.12**. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first, then run:

```bash
git clone https://github.com/Atishmondi/ROM.git
cd ROM
./scripts/setup.sh
.venv/bin/python app.py
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**, choose a video and click **Analyze video**.

Setup creates the Python environment, installs dependencies, downloads the pretrained model and runs the tests. No API key or GPU is required. Analysis runs on the machine serving the app and can take longer than the video's playback time.

For later launches on macOS, double-click **`Start-Elbow-ROM.command`**, or run `.venv/bin/python app.py` again. Keep the server running while using the website.

For Windows, Linux or manual installation, see the [setup guide](docs/USAGE.md#manual-installation). These platforms have not been verified end to end. **FFmpeg is needed when the host's OpenCV installation cannot encode H.264.**

## What the analysis produces

When processing finishes, **Download PDF report** becomes available in the measurement inspector.

| Output | What's inside |
| --- | --- |
| **PDF report** | Angle ranges, tracking coverage, a flexion graph and the frames behind minimum/maximum measurements |
| **Annotated MP4** | Tracked joints and current-frame inside/flexion angles; exported without audio |
| **CSV measurements** | Frame timestamps, joint coordinates, raw/smoothed angles, confidence and rejection reasons |
| **JSON summary** | Run settings, model fingerprint, movement ranges, coverage and warnings |
| **Interactive HTML report** | Video playback, an angle graph and links to inspect extreme frames |
| **ZIP download** | The source recording and analysis exports, including the PDF |

[Open an example PDF](docs/example-report.pdf) generated from a short test upload. Each new upload generates its own report.

Uploads are limited to **1 GB by default**. Completed analyses remain in `outputs/uploads/` until removed by the server operator. This directory, model weights and the local Python environment are excluded from Git.

## Understanding the angles

The two numbers describe the same joint using different conventions:

| Arm position | Inside angle | Elbow flexion |
| --- | ---: | ---: |
| Straight | 180° | 0° |
| Right-angle bend | 90° | 90° |
| Example obtuse angle | 108° | 72° |

**Inside angle + elbow flexion = 180°.** Left and right refer to the person's anatomical sides.

**Observed movement range** is the maximum minus minimum of valid, smoothed flexion estimates in the recording. It describes what the clip captured, not the person's full achievable range. The on-video labels use current-frame values so they correspond to the joints drawn on that frame.

## How it works

The active model is **YOLO11m Pose**, pretrained on COCO keypoints. OpenCV decodes the video; the model locates body joints in the full frame. The same frame is also analyzed after a horizontal flip, then mapped back to the original anatomical sides.

The pipeline compares the two predictions before accepting an arm measurement. By default, it requires a minimum joint score of **0.6** in both passes and rejects angles that disagree by more than **25°**. It also withholds competing pose detections, off-screen joints and ambiguous projected geometry.

Accepted shoulder, elbow and wrist coordinates are converted to source-image pixels before calculating the angle. A trailing **five-frame median** smooths the summary and resets whenever tracking is lost. Missing measurements remain gaps rather than being filled with invented values.

These checks help identify unreliable frames; confidence and agreement do not guarantee a correct measurement. More detail is in the [technical guide](docs/USAGE.md#measurement-and-filtering).

## What has been checked

The repository includes **48 automated tests** covering geometry, filtering, checkpoint recovery, uploads, background jobs, downloads, PDF generation and a real model/codec smoke test.

A separate development check compared the visible arm against approximate visual marks on eight frames from the included recording:

| Check | Result |
| --- | --- |
| Reference frames with accepted measurements | 7 of 8 |
| Mean absolute difference from the visual marks | 3.40° |
| Maximum difference on those accepted frames | 8.79° |

Four frames informed the settings; four additional frames were checked afterward. The marks are approximate, from one clip, and are **not clinical ground truth**. The rejected frame is not counted as a corrected measurement. See the [full evaluation notes](validation/RESULTS.md) for the comparison and limitations.

Run the tests after setup:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Recording advice and limitations

Record one person with a steady camera. Keep the measured shoulder, elbow and wrist visible, with arm movement roughly parallel to the image plane. A side view generally makes the projected angle easier to interpret.

This is a **2D prototype, not a clinically validated measurement system**. Perspective, occlusion, motion blur and landmark errors can affect the result. A hidden arm may be unavailable or inaccurate, and this unsigned angle cannot distinguish hyperextension from flexion. Variable-frame-rate timing is approximate.

The app does not diagnose movement limitations. A convincing overlay is not a substitute for checking the joint positions or validating against a physical reference.

## Working with the code

| Area | Location |
| --- | --- |
| Browser interface | [`web/`](web/) |
| Upload API and job queue | [`rom/web.py`](rom/web.py) |
| Shared analysis service | [`rom/service.py`](rom/service.py) |
| Pose model and mirrored predictions | [`rom/yolo_pose.py`](rom/yolo_pose.py) |
| Video processing and measurements | [`rom/pipeline.py`](rom/pipeline.py), [`rom/measurement.py`](rom/measurement.py) |
| PDF and interactive reports | [`rom/pdf_report.py`](rom/pdf_report.py), [`rom/report.py`](rom/report.py) |
| Tests and visual references | [`tests/`](tests/), [`validation/`](validation/) |

Command-line analysis, configurable thresholds, checkpoint recovery and comparison exports are documented in [the technical guide](docs/USAGE.md).

The original DensePose experiment is preserved in [`legacy/densepose/`](legacy/densepose/) for reference. The active app uses YOLO11 Pose; Detectron2 is not included or required.

## Built with

[Ultralytics YOLO11 Pose](https://docs.ultralytics.com/models/yolo11/), [PyTorch](https://pytorch.org/), [OpenCV](https://opencv.org/), [FastAPI](https://fastapi.tiangolo.com/) and [ReportLab](https://www.reportlab.com/). Interface icons are from [Tabler Icons](https://tabler.io/icons); their license is included in [`web/icons/LICENSE`](web/icons/LICENSE).

The pose weights are pretrained upstream models, not a model trained by this project. Refer to each upstream project's licensing terms when reusing its software or weights.

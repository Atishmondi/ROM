# Sample evaluation — 24 October 2026

The active backend is YOLO11m Pose at 960px, using original/mirrored predictions.
The full 226-frame (9.04s) sample was processed and both exported videos decoded
successfully. Measurements were available for 83.2% of near/left-arm frames and
71.7% of right-arm frames.

Eight visible-arm reference frames were marked approximately in image space.
Four development frames informed the inference configuration; four additional
check frames were marked before evaluating their new predictions. References
carry about 10–20px uncertainty at 1280×720, and are not clinical ground truth.

| Comparison | Usable frames | Mean absolute angle difference | Maximum difference |
| --- | --- | --- | --- |
| New model, all reference frames | 7/8 | 3.40° | 8.79° |
| New model, development subset | 3/4 | 2.26° | 2.53° |
| New model, additional check subset | 4/4 | 4.26° | 8.79° |
| Previous model, same 7 paired frames | 7/7 | 8.94° | 15.32° |

The problematic frame at 1.04s was withheld by the final strict pipeline because
there were competing pose candidates. Its earlier standalone trial estimate
(about 119°) is not a final accepted measurement and is not counted in these
metrics. Withholding an uncertain frame is not evidence that its angle was fixed.

The far arm is not covered by this reference check. These results describe one
small clip, and cannot establish general model accuracy or physical elbow ROM.
No model weights were trained or fine-tuned using these points.

Inspect `outputs/hello_rom_yolo.html` for video, per-frame comparisons and marked
joint images. The corresponding evidence ZIP includes those assets for sharing.
To reproduce the evaluation after inference:

```sh
.venv/bin/python -m rom.validation --reference validation/reference_points.json --source inputs/hello.mp4 --run outputs/hello_rom_yolo --baseline outputs/hello_rom.csv
.venv/bin/python -m rom.review --source inputs/hello.mp4 --run outputs/hello_rom_yolo
```

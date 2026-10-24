"""Offline report with an adjacent annotated video and gap-aware SVG plot."""
import html
import json
from urllib.parse import quote


def number(value):
    return '—' if value is None else f'{value:.1f}°'


def chart(rows):
    width, height, left, top = 960, 300, 50, 20
    plot_w, plot_h = 880, 230
    duration = max(rows[-1]['time_s'], .001) if rows else 1
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Elbow flexion over time">']
    for value in (0, 45, 90, 135, 180):
        y = top + plot_h * (1 - value / 180)
        parts.append(f'<path d="M{left},{y}h{plot_w}" stroke="#dce2e8"/><text x="8" y="{y+4}" font-size="12">{value}°</text>')
    for i in range(5):
        x = left + plot_w * i / 4
        parts.append(f'<text x="{x}" y="280" text-anchor="middle" font-size="12">{duration*i/4:.1f}s</text>')
    for side, color in [('left', '#007d82'), ('right', '#b85016')]:
        segments, current = [], []
        for row in rows:
            value = row[f'{side}_flexion_deg']
            if value is None:
                if current:
                    segments.append(current)
                current = []
            else:
                current.append((left + row['time_s'] / duration * plot_w, top + plot_h * (1-value/180)))
        if current:
            segments.append(current)
        for segment in segments:
            if len(segment) == 1:
                x, y = segment[0]
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="{color}"/>')
            else:
                points = ' '.join(f'{x:.2f},{y:.2f}' for x, y in segment)
                parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
    return ''.join(parts) + '</svg>'


def write_report(path, summary, rows):
    video_name = summary.get('evidence_video', path.with_suffix('.mp4').name)
    video_url = html.escape(quote(video_name), quote=True)
    review = summary.get('review_notes', [])
    review_title = 'Validation and run notes' if summary.get('validation') else 'Tracking needs review'
    review_box = '' if not review else f'<section class="review"><h2>{review_title}</h2>' + ''.join(f'<p>{html.escape(note)}</p>' for note in review) + '</section>'
    validation_section = ''
    if summary.get('validation'):
        validation = summary['validation']
        paired = validation['common_frames']
        before, after = paired['baseline']['mae_deg'], paired['current']['mae_deg']
        comparison = ''
        if before is not None and after is not None:
            comparison = f'<p>Mean absolute angle difference on {paired["current"]["count"]} common reference frames: previous model <b>{before:.1f}°</b>; current model <b>{after:.1f}°</b>.</p>'
        entries = ''
        for row in validation['frames']:
            entries += f'<tr><td><button type="button" data-seek="{row["time_s"]:.6f}">{row["frame"]} · {row["time_s"]:.2f}s</button></td><td>{html.escape(row["split"])}</td><td>{number(row["reference_deg"])}</td><td>{number(row["prediction_deg"])}</td><td>{number(row["absolute_error_deg"])}</td></tr>'
        illustration = ''
        if summary.get('validation_image'):
            image_url = html.escape(quote(summary['validation_image']), quote=True)
            illustration = f'<details><summary>Inspect marked joints on the reference frames</summary><p>Magenta outlines: approximate visual reference. Teal dots: model prediction.</p><img src="{image_url}" alt="Reference and predicted shoulder, elbow and wrist positions" style="width:100%;height:auto"></details>'
        validation_section = f'<section><h2>Check against visible joint positions</h2>{comparison}<p>Approximate visual marks on {validation["reference_frames"]} frames from this clip, with roughly 10–20 pixels of marking uncertainty at 1280 × 720. Development frames informed the settings; additional check frames were evaluated afterward. This small check does not establish clinical accuracy.</p><div style="overflow:auto"><table><thead><tr><th>Frame</th><th>Set</th><th>Visual reference</th><th>Model</th><th>Difference</th></tr></thead><tbody>{entries}</tbody></table></div>{illustration}</section>'
    source_player = ''
    if summary.get('source_video'):
        source_url = html.escape(quote(summary['source_video']), quote=True)
        source_player = f'<details><summary>Watch the original footage without overlays</summary><video controls playsinline preload="metadata" src="{source_url}" aria-label="Original source footage"></video><a href="{source_url}" download>Download original footage</a></details>'
    playback_rows = json.dumps([{key: row.get(key) for key in (
        'time_s', 'left_raw_flexion_deg', 'left_flexion_deg', 'left_status',
        'right_raw_flexion_deg', 'right_flexion_deg', 'right_status')}
        for row in rows], allow_nan=False).replace('<', '\\u003c')
    cards = []
    for side in ('left', 'right'):
        s = summary['arms'][side]
        valid = [row for row in rows if row[f'{side}_flexion_deg'] is not None]
        evidence = ''
        if len(valid) >= 2:
            for label, select in [('Minimum', min), ('Maximum', max)]:
                row = select(valid, key=lambda r: r[f'{side}_flexion_deg'])
                evidence += f'<button type="button" data-seek="{row["time_s"]:.6f}">{label} frame · {row["time_s"]:.2f}s</button> '
        cards.append(f'''<section><h2>{side.title()} elbow</h2>
        <p class="metric">{number(s['observed_rom_deg'])}</p><p>Observed movement range</p>
        <dl><dt>Flexion minimum → maximum</dt><dd>{number(s['min_flexion_deg'])} → {number(s['max_flexion_deg'])}</dd>
        <dt>Inside angle minimum → maximum</dt><dd>{number(None if s['max_flexion_deg'] is None else 180-s['max_flexion_deg'])} → {number(None if s['min_flexion_deg'] is None else 180-s['min_flexion_deg'])}</dd>
        <dt>Central 90% range (P95 − P05)</dt><dd>{number(s['central_90_range_deg'])}</dd>
        <dt>Usable frames</dt><dd>{s['valid_frames']} / {s['total_frames']} ({s['coverage_percent']:.1f}%)</dd>
        <dt>Data status</dt><dd>{s['status'].replace('_', ' ')}</dd></dl><div class="evidence">{evidence}</div></section>''')
    warnings = ''.join(f'<li>{html.escape(w)}</li>' for w in summary['warnings'])
    source = html.escape(summary['input_name'])
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Elbow ROM · {source}</title><style>
    body{{font:16px system-ui,sans-serif;background:#f4f6f8;color:#182530;max-width:1080px;margin:40px auto;padding:0 24px;line-height:1.6}}
    h1{{font-size:40px;letter-spacing:-1.5px;margin-bottom:0}}h2{{font-size:20px}}.sub{{color:#546573}}.cards{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
    section,.plot{{background:white;border:1px solid #dce2e8;border-radius:12px;padding:24px;margin:20px 0}}.metric{{font-size:48px;font-weight:700;line-height:1;margin:20px 0 0}}
    dt{{color:#546573;margin-top:12px}}dd{{margin:0;font-weight:600}}svg{{width:100%;height:auto}}.left{{color:#007d82}}.right{{color:#b85016}}
    video{{display:block;width:100%;max-height:70vh;background:#101820;border-radius:8px}}button,.download{{display:inline-block;padding:10px 14px;border:1px solid #aebdc8;border-radius:7px;background:white;color:#183b4b;font:inherit;cursor:pointer;margin:6px 6px 0 0;text-decoration:none}}button:hover,.download:hover{{background:#edf5f7}}.evidence{{margin-top:16px}}
    .review{{border-color:#c5832c;background:#fff7e8}}details{{margin-top:20px}}summary{{cursor:pointer;font-weight:600}}#frame-readout{{background:#eef2f5;padding:12px;border-radius:6px;font-variant-numeric:tabular-nums}}
    table{{border-collapse:collapse;width:100%;text-align:left;font-variant-numeric:tabular-nums}}th,td{{padding:10px;border-bottom:1px solid #dce2e8}}
    @media(max-width:640px){{.cards{{grid-template-columns:1fr;gap:0}}h1{{font-size:32px}}body{{padding:0 16px}}}}
    </style><h1>Elbow movement</h1><p class="sub">{source} · {summary['frames']} frames · {summary['duration_s']:.1f}s · 2D video estimate</p>
    {review_box}
    <section id="video-evidence"><h2>Watch the measured movement</h2><p>The actual input footage, annotated with tracked joints and frame-by-frame angle estimates. Use the minimum/maximum buttons below to inspect the frames behind the results.</p>
    <video id="evidence-video" controls playsinline preload="metadata" aria-label="Annotated elbow movement video"><source src="{video_url}" type="video/mp4">Your browser cannot play this video. Use the download link below.</video>
    <p id="frame-readout" aria-live="off">Pause or scrub to inspect the recorded raw angle and smoothed result for that frame.</p>
    <p><a class="download" href="{video_url}" target="_blank" rel="noopener">Open video</a><a class="download" href="{video_url}" download>Download annotated MP4</a></p>
    <p id="playback-note" class="sub">Keep the HTML and its matching MP4 in the same folder when sharing. The video shows the model's estimates; it is not independent validation of their accuracy.</p>{source_player}</section>
    <div class="cards">{''.join(cards)}</div><div class="plot"><h2>Flexion over time</h2><p><b class="left">Left arm</b> · <b class="right">Right arm</b> · gaps indicate unavailable measurements</p>{chart(rows)}</div>
    {validation_section}
    <h2>Two angle conventions</h2><p>The <b>inside angle</b> is the visible angle between the upper arm and forearm: a straight arm is 180°. <b>Elbow flexion</b> measures the bend away from straight: a straight arm is 0°. Inside angle + flexion = 180°; for example, 108° inside means 72° flexion. Both are shown on the video. Left/right refer to anatomical sides. Summary values use a trailing {summary['smoothing_window']}-frame median, reset whenever tracking is lost; the frame inspector shows current-frame values separately.</p>
    <p>Observed range is maximum minus minimum of valid, smoothed estimates in this clip. It is not the person's full achievable range. The central 90% range reduces the influence of isolated extremes but can omit genuine endpoints.</p>
    <h2>Limitations and run notes</h2><ul>{warnings}</ul><p>Single-person, side-on recordings work best. Keep the shoulder, elbow and wrist visible, with movement parallel to the camera. Perspective, occlusion and model errors affect the result. This prototype has not been clinically validated and does not diagnose movement limitations.</p>
    <p class="sub">Video is exported without audio. Per-frame raw angles, filtered values, confidence and rejection reasons are in the accompanying CSV; run settings and model SHA-256 are in the JSON.</p>
    <script>
    const video = document.getElementById('evidence-video');
    const measurements = {playback_rows};
    const fps = {summary['fps']};
    const displayAngle = value => value === null || value === undefined ? 'unavailable' : Number(value).toFixed(1) + '°';
    function updateReadout() {{
      const index = Math.min(measurements.length - 1, Math.max(0, Math.floor(video.currentTime * fps + 0.001)));
      const row = measurements[index];
      if (!row) return;
      const inside = value => value === null || value === undefined ? null : 180 - Number(value);
      document.getElementById('frame-readout').textContent = 'Frame ' + index + ' · ' + Number(row.time_s).toFixed(2) + 's | Left: inside ' + displayAngle(inside(row.left_raw_flexion_deg)) + ', flexion ' + displayAngle(row.left_raw_flexion_deg) + ', smoothed flexion ' + displayAngle(row.left_flexion_deg) + ' (' + row.left_status + ') | Right: inside ' + displayAngle(inside(row.right_raw_flexion_deg)) + ', flexion ' + displayAngle(row.right_raw_flexion_deg) + ', smoothed flexion ' + displayAngle(row.right_flexion_deg) + ' (' + row.right_status + ')';
    }}
    ['timeupdate', 'seeked', 'loadeddata'].forEach(event => video.addEventListener(event, updateReadout));
    document.querySelectorAll('[data-seek]').forEach(button => button.addEventListener('click', () => {{
      const seek = () => {{ video.pause(); video.currentTime = Number(button.dataset.seek); }};
      if (video.readyState >= 1) seek(); else {{ video.addEventListener('loadedmetadata', seek, {{once:true}}); video.load(); }}
      document.getElementById('video-evidence').scrollIntoView({{behavior:'smooth',block:'start'}});
    }}));
    video.addEventListener('error', () => {{ document.getElementById('playback-note').textContent = 'Video could not load. Keep the matching MP4 beside this HTML, or use Open video to play it in a desktop player.'; }});
    </script></html>'''
    path.write_text(document, encoding='utf-8')

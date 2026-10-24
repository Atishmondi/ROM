# Interface direction

Redesign / overhaul of a single-page video analysis tool. Apple-inspired web
utility; not an official Apple design system. Keep the existing FastAPI API,
upload field, recording-guide anchor and Elbow ROM identity.

The old site used a large promotional heading, a decorative diagram, numbered
steps, equal cards, green-tinted backgrounds and repeated helper paragraphs.
The working parts were upload, progress, playback, frame readouts and downloads.
Those remain the core interaction; the marketing shell is removed.

The design-taste skill is primarily for marketing pages and explicitly excludes
dense product UI. Its audit, anti-template and typography guidance are applied
here; apple-design's purpose, familiarity, response and proximity principles guide
the actual application. Dials: DESIGN_VARIANCE 4 / MOTION_INTENSITY 3 /
VISUAL_DENSITY 6. This is a predictable utility, not a kinetic landing page.

Use the platform system font, one green action color, neutral surfaces and
Tabler outline icons (MIT). Teal/orange graph traces distinguish measured arms;
they are data encodings, not additional UI action accents. Corners: controls 6px,
viewer 10px, floating surfaces 12px. Real media is allowed a dark viewing surface.

No fake sample measurements, traffic-light window buttons, animated backgrounds,
custom cursors or invented clinical accuracy. Before analysis, metrics read
'Not measured'. Every number and graph comes from the actual job's measurements.

Desktop: library / video workspace / measurement inspector. Mobile: a single
column with a dismissible library drawer. Playback, frame stepping and timeline
seeking use current video time with immediate feedback. Light and dark appearances
share semantic CSS tokens; system preference is the default. Reduced motion,
reduced transparency, keyboard controls and visible focus are supported.

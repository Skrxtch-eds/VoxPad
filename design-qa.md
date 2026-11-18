# QML design QA

Source visual truth: `C:/Users/Skretch/.codex/generated_images/01a1eabb-f792-7af0-b78e-d8226a3a5b71/` — `main screen.png`, `History.png`, `statistic.png`, `settings.png`.

Implementation screenshots: `C:/VoxPad/work/qml-migration/screenshots/` — `home.png`, `history.png`, `statistics-tooltip.png`, `settings.png`.

Viewport: 1100 × 1430 Qt logical pixels, DPR 2; rendered captures 2200 × 2860 physical pixels. Source images 1100 × 1430. Captures are downsampled to source size before comparison. No browser/CSS viewport is involved: this is the requested native Qt Quick application. Transparent window margins are composited against neutral gray for comparison; the reference's photographic desktop backdrop is excluded from app fidelity.

State: light theme, identical reference sample content and line breaks, statistics 8640 words / 128 dictations / 5040 seconds, hovered last chart bar. The settings theme field is explicitly light during capture rather than the reference's system choice; this is an intentional test state, not a missing option. System/light/dark choices function in the actual app.

## Full-view evidence

Combined source/implementation comparisons in `C:/VoxPad/work/qml-migration/`:

- `home-comparison.png`
- `history-comparison.png`
- `statistics-tooltip-comparison.png`
- `settings-comparison.png`

Focused source/implementation evidence: `focused-controls.png` (raised controls and microphone), `focused-history.png` (text wrapping, dividers and row rhythm). Dark mode and the color transition: `smoke-dark-home.png`, `smoke-dark.png`, `smoke-theme-midpoint.png`; compact layout: `smoke-compact.png`.

## Comparison history

1. P2: flat icon/navigation buttons had unwanted borders. Removed inner bevels for flat controls and re-captured.
2. P2: dropdowns moved to Qt's unscaled overlay and overflowed at reduced window sizes. Applied the scene scale to in-window Popup, including animated scale, and verified selection at 600 × 780 and a single top-level window.
3. P2: reference sample wrapping differed, changing history density. Matched fixture line breaks, adjusted row padding and measured geometry, and re-captured.
4. P2: initial library icons were angular and had the wrong copy orientation. Replaced relevant assets with licensed Lucide source icons and re-captured; kept the microphone and filled pause assets that better match the source.
5. Theme follow-up: centralized all animated color roles, inverted the primary control and icon, added light/dark icon crossfades. Verified intermediate and final color values and unchanged HWND.

## Required fidelity surfaces

- Fonts/typography: Segoe UI with measured pixel sizes, matching hierarchy, Russian copy and wrapping. Small font-rasterization differences against the generated source remain P3.
- Spacing/layout: frame and main card coordinates/radii, headers, navigation, row actions, settings sections, chart baseline and tooltip follow the reference. Responsive scaling preserves the whole composition; no persistent controls are clipped.
- Colors/tokens: neutral white/gray/black surfaces and cached soft shadows; graphite/white inversion in dark mode. The generated reference has photographic illumination and surface texture; the native scene uses clean vector surfaces with subtle gradients. This is P3 surface polish.
- Assets: real licensed library icons with high-density PNG rendering and smooth light/dark crossfades. Minor differences in gear teeth, pause rounding and chart icon strokes remain P3; no raster mockup is used as the functional UI.
- Copy/content: all four Russian page titles and requested settings labels match. The production app uses real history/statistics; reference figures are confined to the isolated capture fixture. A scrollbar thumb appears only for actual overflow; the four-entry fixture fits, while the 20-entry integration fixture verifies scrolling.

## Functional verification

`tests/qml_smoke.py` passed with one top-level window and no QML warnings. Navigation, zero/intermediate/final/reentry counters, independent bars, tooltip, settings persistence, popup selection, dark colors, transition midpoint, unchanged HWND and compact layout were checked. Latest timing evidence is `work/qml-migration/integration.json` (Direct3D11).

No remaining P0/P1/P2 findings. P3 differences are limited to generated-image material lighting, font rasterization and minor library-icon geometry; pixel identity is not claimed.

Implementation checklist: completed. New distribution binaries were not built.

## Latest verification: motion and compact window

This section supersedes the initial motion, system-theme and library-icon notes above. The follow-up specification is the current visual target.

- Taste Skill and its motion/icons/system/performance references were applied to the native stack. Its HTML/browser gate is not applicable; actual Qt rendering is checked.
- Exact 1.03 hover, unchanged fill, smaller cached shadow, return to 1.0 before action. Fast click, cancel, keyboard and QML hold-recording paths pass.
- Uniform shadows, darker in dark mode; diagonal bevel darker at bottom right. No hover background or mouse-focus frame on flat copy/delete actions.
- Ten glyphs now trace the supplied artwork; editable SVG sources: docs/design/reference-icons. Previous library look-alike differences are resolved.
- Recording changes only the microphone into three sequential bobbing dots. No stop glyph or pulsing border. Only Light and Dark are selectable.
- Default 392×510, 40% smaller. Short work areas scroll vertically, preserving text size. Four pages captured at five sizes, including short-window bottom.
- 20 resolution/scale calculations and real Direct3D11 rendering at DPR 1.0/1.5/2.0 passed without QML warnings. HWND and draft survive theme changes.

Evidence: work/qml-motion-qa/report.json, hover-103-percent.png, pressed-100-percent.png, recording-three-dots.png, page/size captures, dpi-1.0 and dpi-1.5. Details: docs/qml-motion-refinement.md.

final result: passed

<div align="center">

# Cadence

**Markerless running gait analysis · University of Roehampton**

Powered by [Sports2D](https://github.com/davidpagnon/Sports2D)

![Status](https://img.shields.io/badge/status-planning-f59e0b)
![Python](https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-Dash%20%2F%20Plotly-2a78d6)
![Engine](https://img.shields.io/badge/engine-Sports2D-ff6fb3)
![License](https://img.shields.io/badge/license-BSD--3--Clause-4a3aa7)

</div>

> ⚠️ **Planning stage.** Early development — not yet released or versioned. File
> layout, data conventions, and interfaces may change without notice.

---

Cadence turns a recorded running video into interactive joint-angle analysis.
**Sports2D** (the pose/kinematics engine) extracts keypoints and joint angles from
the video; Cadence wraps it in an operator-friendly processing menu and a **Dash**
web app that renders the results as interactive time-series plots.

The two stages are deliberately separate:

- **Processing** is heavy (minutes per video, wants a GPU). An operator runs it from a
  small command-line menu — no memorising flags.
- **Viewing** is instant. A researcher opens the Dash app, uploads a processed angles
  file, and reads the plots. The viewer never runs Sports2D.

## Requirements

- Python 3.12
- The dependencies in [`requirements.txt`](requirements.txt) — Sports2D pulls in a large
  tree via Pose2Sim (torch, OpenCV, etc.), so the first install is sizeable. The viewer's
  analytics add `numpy` and `scipy` as direct pins (both already in the Sports2D tree).

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Optional but recommended: capture a full reproducible lock after the first install
pip freeze > requirements.lock.txt
```

## Usage

### 1 · Process a video — operator

```bash
python main.py
```

An interactive arrow-key menu appears:

- **Run** — asks for a video, then processes it with the current settings.
- **Settings** — lists every setting with its current value; pick one to change it
  (time range, person count / height / mass, pose model, mode, detection frequency,
  backend / device, angle selection, inverse kinematics, and the save toggles). Each
  change is saved to `settings.json` and **remembered across restarts**. The annotated
  preview video is off by default — it re-encodes the whole clip and is the slow part.
- **Exit**

Output lands in `data/results/<video-name>/`, and Sports2D's live progress bar streams
to the terminal while it runs.

### 2 · View the angles — researcher

```bash
python app.py
```

Open <http://127.0.0.1:8050>, drop a Sports2D angles `.mot` file (from
`data/results/<video-name>/…`) onto the upload screen, and the **Gait Analysis**
page renders. **Clear workspace** in the pinned sidebar returns to the upload screen.

The page has four parts, top to bottom:

1. **Metadata cards** — one row of tiles derived from the file: `File`, `Frames`,
   `Duration`, `Sample rate`, `Angles`, `Units`, plus two computed analytics,
   `Cadence` and `Strides` (see below).
2. **Data table** — the raw table, sortable and paginated. Values display at 2 dp
   but the built-in **Export → CSV** downloads them at full precision; the stored
   data is never mutated.
3. **Angle plots** — one plot per body part, two per row, grouped into *Joints* and
   *Segments*. Left and Right of a joint share axes in distinct colours (Left =
   vermilion, Right = pine) so asymmetry reads at a glance; axial parts (pelvis,
   trunk, head, shoulders) draw a single graphite trace. Each plot has the Plotly
   mode bar for PNG download / zoom / pan.
4. **Gait cycle — mean ± SD** — the same angles collapsed into one representative
   stride (see below).

#### Analysis features

All analytics are computed on the fly from the single uploaded file — no training,
no stored model, just classical signal processing:

- **Cadence** (`~168 spm`) — estimated by **autocorrelation** of a cyclic joint
  (knee/ankle): the signal is correlated with itself, the first alignment peak
  within a 0.4–1.5 s window is the stride period, and cadence = `120 / stride_period`
  (one stride = two steps). A single average for the clip; shown with `~` to mark it
  an estimate.
- **Strides** — stride boundaries found with `scipy.signal.find_peaks` on the same
  joint (peaks ≥ 0.4 s apart, above a prominence floor so noise can't invent
  strides). The card reports complete strides (peaks − 1).
- **Gait cycle (mean ± SD)** — each stride between consecutive peaks is resampled
  onto a shared 0–100 % axis and averaged, with a ±1 SD band showing stride-to-stride
  variability. Right-side angles are normalised over the right knee/ankle cycle and
  left over the left, so Left and Right are phase-aligned and directly comparable.
  Dozens of noisy strides become one clean curve; a wide band means inconsistent
  striding.

These need a strong cyclic joint (knee or ankle) in the file. If none is present, or
the clip is too short to find a period, the affected cards and the gait-cycle section
are simply omitted rather than showing a misleading value.

## Project layout

```
main.py            Processing: interactive menu (Run / Settings / Exit)
app.py             Dash viewer: upload a .mot → metadata, table, plots, gait-cycle analytics
assets/cadence.css Viewer styling ("Tartan Track" theme; Dash auto-serves assets/)
requirements.txt   Pinned direct dependencies
settings.json      Saved CLI settings, remembered across restarts (gitignored)
data/              Uploaded videos and Sports2D output (gitignored)
```

## Note on the Sports2D output format

The viewer reads joint/segment angles from Sports2D's OpenSim `.mot` files (a header
block ending in `endheader`, then a tab-separated table). This was verified against
Sports2D `0.8.32`; if a future version emits angles in a different format, adapt
`read_mot` in [`app.py`](app.py).

## Credits

- **Engine — [Sports2D](https://github.com/davidpagnon/Sports2D)** by David Pagnon et al.
  Cadence uses it as an unmodified dependency; it is the engine, not our work. Please cite
  Sports2D per its own guidelines when publishing.
- **Cadence** (this application — processing menu + Dash viewer): © 2026 Bakhtiyor
  Sohibnazarov. Developed for running gait-analysis research at the University of Roehampton.

## License

Released under the **BSD 3-Clause License** — see [`LICENSE`](LICENSE). Sports2D and
Pose2Sim (the underlying engine) are separate BSD 3-Clause works by David Pagnon et al.
and remain under their own licenses.

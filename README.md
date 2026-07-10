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
  tree via Pose2Sim (torch, OpenCV, etc.), so the first install is sizeable.

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

Open <http://127.0.0.1:8050>, upload a Sports2D angles `.mot` file (from
`data/results/<video-name>/…`), and browse one interactive plot per joint angle.
**Clear workspace** in the sidebar returns to the upload screen.

## Project layout

```
main.py            Processing: interactive menu (Run / Settings / Exit)
app.py             Dash viewer: upload a .mot → plots. No processing.
assets/            CSS for the viewer (Dash auto-serves this folder)
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

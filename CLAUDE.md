# Cadence — Project Brief

*(formerly StrideLabV2)*

## What this is

**Cadence** is a markerless running gait analysis tool, built at the University of Roehampton.
Two stages: **Sports2D** (the engine — not our work) extracts pose keypoints and joint-angle
kinematics from a recorded video; a **Dash** web app loads Sports2D's output and renders it as
interactive analysis dashboards. Sports2D is used as an unmodified dependency and must be
credited as the engine.

This is a fresh build. There is no prior codebase to port, extend, or stay compatible with —
don't assume any particular file layout, data convention, or feature beyond what's specified
below.

## Stack

- **Engine**: [Sports2D](https://github.com/davidpagnon/Sports2D) — used as a normal Python
  dependency (`pip install sports2d`), invoked as a library or CLI. Do not vendor or fork its
  source into this repo.
- **UI**: [Dash](https://dash.plotly.com/) (Plotly). Not Streamlit, not Flask templates.
- **Language**: Python 3.12.

## Pipeline

1. **Input**: a recorded video file. Any resolution/fps/camera source — this repo does not
   do camera capture; assume the video already exists on disk.
2. **Processing**: run Sports2D on the video. It produces its own native output files
   (keypoint trajectories, joint/segment angles over time — check its actual current output
   format, likely TRC/MOT/CSV, when you get there rather than assuming).
3. **Analysis**: the Dash app loads Sports2D's output and presents it as interactive
   time-series plots, one per angle/metric Sports2D reports.

## Deliverables

- `README.md` — setup and how to run.
- Dash app entry point (`app.py`) — viewer only; loads processed output, never runs Sports2D.
- An operator-facing processing CLI (`main.py`) — an interactive `Run / Settings / Exit` menu
  that invokes Sports2D on a video, locates its output, and remembers settings across restarts.
- Pinned dependency file (exact versions, not ranges).

## Working style

- Small, legible codebase. One obvious way to do something, not a configurable one.
- Change small, always ask question, do not assume things
- Do not run heavy tests, builds, verifications unless absolutely necessary, save resources but work efficently
- Discuss the steps and whatever that you need to clarify to, do not assume or guess
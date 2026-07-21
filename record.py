"""
Cadence RealSense recorder — live-tuning capture.

Opens an Intel RealSense D435i colour stream in a preview window with live
trackbars for exposure, gain and auto-exposure. Tune the image, then press
'r' to start recording an RGB-only MP4. Press 'q'/ESC (or close the window)
to stop and save.

Resolution, frame rate and output folder are asked once at startup — nothing
is written to disk between runs, everything else is adjusted live.

Requires: pyrealsense2, opencv-python, numpy, InquirerPy
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs
from InquirerPy import inquirer

BASE_DIR = Path(__file__).resolve().parent

APP_NAME = "Cadence Recorder"
TAGLINE = "University of Roehampton - RealSense RGB capture"
PINK = (255, 111, 179)        # RGB, for the terminal banner
PINK_BGR = (179, 111, 255)    # same colour, for OpenCV overlays

WINDOW = "Cadence Recorder"

# Only 60-fps-capable colour profiles on the D435i are offered.
RESOLUTIONS = ["960x540", "848x480", "640x480"]
FPS_CHOICES = ["60", "30"]
DEFAULT_RESOLUTION = "960x540"
DEFAULT_FPS = "60"
DEFAULT_OUTPUT_DIR = "recordings"


def _banner() -> None:
    """Print a minimal title with a credit line, coloured if the terminal supports it."""
    if sys.stdout.isatty() and os.environ.get("NO_COLOR") is None:
        r, g, b = PINK
        print(f"\n\033[1;38;2;{r};{g};{b}m{APP_NAME}\033[0m")
        print(f"\033[2m{TAGLINE}\033[0m\n")
    else:
        print(f"\n{APP_NAME}")
        print(f"{TAGLINE}\n")


# --- startup prompt ----------------------------------------------------------

def ask_setup() -> dict | None:
    """Ask resolution / fps / output folder once. Return None if cancelled."""
    try:
        resolution = inquirer.select(
            message="Resolution:", choices=RESOLUTIONS, default=DEFAULT_RESOLUTION).execute()
        fps = inquirer.select(
            message="Frame rate:", choices=FPS_CHOICES, default=DEFAULT_FPS).execute()
        output_dir = inquirer.text(
            message="Output folder:", default=DEFAULT_OUTPUT_DIR).execute()
    except KeyboardInterrupt:
        return None
    return {"resolution": resolution, "fps": fps, "output_dir": output_dir}


# --- camera helpers ----------------------------------------------------------

def _try_set(sensor, option, value) -> None:
    """Set a sensor option, ignoring values the firmware rejects (out of range, etc.)."""
    try:
        sensor.set_option(option, float(value))
    except Exception:
        pass


def _option_range(sensor, option, fallback_max: int, fallback_default: int):
    """Return (min, max, default) for an option, falling back if it isn't supported."""
    try:
        r = sensor.get_option_range(option)
        return int(r.min), int(r.max), int(r.default)
    except Exception:
        return 0, fallback_max, fallback_default


# --- overlay -----------------------------------------------------------------

def _overlay(img, recording: bool, frames: int, exposure: int, gain: int,
             auto: bool, meta: str) -> None:
    """Draw status and current settings onto the displayed frame (not the saved one)."""
    if recording:
        cv2.circle(img, (24, 26), 9, (60, 60, 235), -1)
        cv2.putText(img, f"REC  {frames} frames", (42, 33),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 235), 2, cv2.LINE_AA)
    else:
        cv2.putText(img, "TUNING - press 'r' to record", (18, 33),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, PINK_BGR, 2, cv2.LINE_AA)

    mode = "auto-exposure" if auto else f"exp {exposure}  gain {gain}"
    line = f"{meta}   {mode}"
    h = img.shape[0]
    cv2.putText(img, line, (18, h - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
    cv2.putText(img, "q / ESC: stop & save", (18, h - 44),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)


# --- recording ---------------------------------------------------------------

def run(setup: dict) -> None:
    """Open the live preview, tune settings, and record on demand."""
    width, height = (int(x) for x in setup["resolution"].split("x"))
    fps = int(setup["fps"])

    out_dir = Path(setup["output_dir"]).expanduser()
    if not out_dir.is_absolute():
        out_dir = BASE_DIR / out_dir
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"  ! Could not create output folder '{out_dir}': {e}")
        return

    if not rs.context().query_devices():
        print("  ! No RealSense camera detected. Plug one in and try again.")
        return

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
    try:
        profile = pipeline.start(config)
    except RuntimeError as e:
        print(f"  ! Could not start the camera at {width}x{height}@{fps}: {e}")
        return

    try:
        sensor = profile.get_device().first_color_sensor()
        exp_min, exp_max, exp_def = _option_range(sensor, rs.option.exposure, 10000, 120)
        gain_min, gain_max, gain_def = _option_range(sensor, rs.option.gain, 128, 16)

        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.createTrackbar("Auto Exposure", WINDOW, 0, 1, lambda _v: None)
        cv2.createTrackbar("Exposure", WINDOW, exp_def, max(exp_max, 1), lambda _v: None)
        cv2.createTrackbar("Gain", WINDOW, gain_def, max(gain_max, 1), lambda _v: None)

        # Start in manual mode with the sensor defaults applied.
        _try_set(sensor, rs.option.enable_auto_exposure, 0)
        _try_set(sensor, rs.option.exposure, exp_def)
        _try_set(sensor, rs.option.gain, gain_def)
        last_auto, last_exp, last_gain = 0, exp_def, gain_def

        meta = f"{width}x{height}@{fps}"
        recording = False
        writer = None
        out_path = None
        frames = 0

        print("  Live preview open. Tune the image, press 'r' to record, 'q'/ESC to stop.")

        while True:
            try:
                frameset = pipeline.wait_for_frames(2000)
            except RuntimeError:
                print("  ! Lost the camera feed (timed out waiting for frames).")
                break
            color = frameset.get_color_frame()
            if not color:
                continue
            img = np.asanyarray(color.get_data())

            if recording and writer is not None:
                writer.write(img)   # save the clean frame, before the overlay
                frames += 1

            # Stop cleanly if the user closed the window with the title-bar X.
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break

            # All window/trackbar calls are guarded: if the window is torn down
            # mid-frame, OpenCV raises cv2.error — treat that as "closed" and stop.
            try:
                # Apply live control changes only when a trackbar actually moved.
                auto = cv2.getTrackbarPos("Auto Exposure", WINDOW)
                if auto != last_auto:
                    _try_set(sensor, rs.option.enable_auto_exposure, auto)
                    last_auto = auto
                if not auto:
                    exp = max(cv2.getTrackbarPos("Exposure", WINDOW), exp_min)
                    if exp != last_exp:
                        _try_set(sensor, rs.option.exposure, exp)
                        last_exp = exp
                    gain = max(cv2.getTrackbarPos("Gain", WINDOW), gain_min)
                    if gain != last_gain:
                        _try_set(sensor, rs.option.gain, gain)
                        last_gain = gain

                disp = img.copy()
                _overlay(disp, recording, frames, last_exp, last_gain, bool(auto), meta)
                cv2.imshow(WINDOW, disp)
                key = cv2.waitKey(1) & 0xFF
            except cv2.error:
                break

            if key == ord("r") and not recording:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = out_dir / f"realsense_{stamp}.mp4"
                writer = cv2.VideoWriter(
                    str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
                if not writer.isOpened():
                    print(f"  ! Could not open the video writer for {out_path}.")
                    writer = None
                    out_path = None
                    continue
                recording = True
                print(f"  Recording -> {out_path}")
            elif key in (ord("q"), 27):
                break
    finally:
        # Best-effort teardown — release every resource even if one step fails,
        # so closing the window always drops back to the terminal cleanly.
        for cleanup in (pipeline.stop, (writer.release if writer else None),
                        cv2.destroyAllWindows):
            if cleanup is None:
                continue
            try:
                cleanup()
            except Exception:
                pass

    if out_path is not None:
        if frames:
            print(f"  Saved {frames} frames -> {out_path}")
        else:
            print("  ! No frames were recorded; nothing saved.")


def main() -> None:
    _banner()
    setup = ask_setup()
    if setup is None:
        return
    run(setup)


if __name__ == "__main__":
    main()

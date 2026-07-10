from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "data" / "results"      # one subfolder per processed video
SETTINGS_FILE = BASE_DIR / "settings.json"      # remembered across restarts

APP_NAME = "Cadence"
TAGLINE = "University of Roehampton - powered by Sports2D"
PINK = (255, 111, 179)


def _banner() -> None:
    """Print a minimal title with a credit line, coloured if the terminal supports it."""
    if sys.stdout.isatty() and os.environ.get("NO_COLOR") is None:
        r, g, b = PINK
        print(f"\n\033[1;38;2;{r};{g};{b}m{APP_NAME}\033[0m")
        print(f"\033[2m{TAGLINE}\033[0m\n")
    else:
        print(f"\n{APP_NAME}")
        print(f"{TAGLINE}\n")

# Valid choices, taken from the installed Sports2D's CONFIG_HELP.
MODES = ["light", "balanced", "performance"]
BACKENDS = ["auto", "cpu", "cuda", "mps", "rocm"]
DEVICES = ["auto", "openvino", "onnxruntime", "opencv"]
VISIBLE_SIDES = ["auto", "front", "back", "left", "right", "none"]
POSE_MODELS = ["body_with_feet", "whole_body_wrist", "whole_body",
               "lower_body", "body", "hand", "face", "animal"]
JOINT_ANGLES = ["Right ankle", "Left ankle", "Right knee", "Left knee",
                "Right hip", "Left hip", "Right shoulder", "Left shoulder",
                "Right elbow", "Left elbow", "Right wrist", "Left wrist"]
SEGMENT_ANGLES = ["Right foot", "Left foot", "Right shank", "Left shank",
                  "Right thigh", "Left thigh", "Pelvis", "Trunk", "Shoulders",
                  "Head", "Right arm", "Left arm", "Right forearm", "Left forearm"]

# The curated settings, in menu order. Defaults match Sports2D's own defaults
# (except the save toggles, tuned here for fast data-only runs). "type" drives
# both the editor widget and how the value becomes a CLI flag.
FIELDS = [
    {"key": "time_range", "label": "Time range (s, blank = whole)", "type": "text", "default": ""},
    {"key": "nb_persons_to_detect", "label": "Persons to detect", "type": "text", "default": "all"},
    {"key": "first_person_height", "label": "First person height (m)", "type": "text", "default": "1.65"},
    {"key": "pose_model", "label": "Pose model", "type": "select", "choices": POSE_MODELS, "default": "body_with_feet"},
    {"key": "mode", "label": "Mode (accuracy vs speed)", "type": "select", "choices": MODES, "default": "balanced"},
    {"key": "det_frequency", "label": "Detect persons every N frames", "type": "text", "default": "4"},
    {"key": "backend", "label": "Backend", "type": "select", "choices": BACKENDS, "default": "auto"},
    {"key": "device", "label": "Device", "type": "select", "choices": DEVICES, "default": "auto"},
    {"key": "calculate_angles", "label": "Calculate angles", "type": "bool", "default": True},
    {"key": "joint_angles", "label": "Joint angles", "type": "checkbox", "choices": JOINT_ANGLES, "default": JOINT_ANGLES},
    {"key": "segment_angles", "label": "Segment angles", "type": "checkbox", "choices": SEGMENT_ANGLES, "default": SEGMENT_ANGLES},
    {"key": "do_ik", "label": "Inverse kinematics (slower)", "type": "bool", "default": False},
    {"key": "visible_side", "label": "Visible side (for IK)", "type": "select", "choices": VISIBLE_SIDES, "default": "auto"},
    {"key": "participant_mass", "label": "Participant mass(es) kg (blank = default)", "type": "text", "default": ""},
    {"key": "save_pose", "label": "Save pose (.trc)", "type": "bool", "default": True},
    {"key": "save_angles", "label": "Save angles (.mot)", "type": "bool", "default": True},
    {"key": "save_vid", "label": "Save preview video (slow)", "type": "bool", "default": False},
    {"key": "to_meters", "label": "Scale output to metres", "type": "bool", "default": True},
    {"key": "make_c3d", "label": "Also export .c3d", "type": "bool", "default": False},
]
FIELD_BY_KEY = {f["key"]: f for f in FIELDS}


class Sports2DError(RuntimeError):
    """Raised when the Sports2D CLI fails."""


# --- settings persistence ----------------------------------------------------

def default_settings() -> dict:
    return {f["key"]: (list(f["default"]) if isinstance(f["default"], list) else f["default"])
            for f in FIELDS}


def load_settings() -> dict:
    """Load saved settings, filling any missing keys from defaults."""
    settings = default_settings()
    if SETTINGS_FILE.is_file():
        try:
            saved = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            saved = {}
        for key in settings:
            if key in saved:
                settings[key] = saved[key]
    return settings


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


# --- settings editor ---------------------------------------------------------

def _display(field: dict, value) -> str:
    """Short human-readable current value for the settings list."""
    if field["type"] == "bool":
        return "yes" if value else "no"
    if field["type"] == "checkbox":
        return f"all ({len(value)})" if len(value) == len(field["choices"]) else f"{len(value)} selected"
    return value if str(value).strip() else "(default)"


def _edit(field: dict, current):
    """Re-prompt a single field with the right widget and return the new value.

    Raises KeyboardInterrupt (from InquirerPy) if the operator cancels — callers
    treat that as "leave this value unchanged".
    """
    t = field["type"]
    if t == "text":
        return inquirer.text(message=field["label"] + ":", default=current).execute()
    if t == "select":
        return inquirer.select(message=field["label"] + ":", choices=field["choices"],
                               default=current).execute()
    if t == "bool":
        return inquirer.confirm(message=field["label"] + "?", default=current).execute()
    if t == "checkbox":
        return inquirer.checkbox(
            message=field["label"] + ":",
            choices=[Choice(value=c, enabled=(c in current)) for c in field["choices"]],
        ).execute()
    return current


def settings_menu(settings: dict) -> None:
    """Show every setting with its value; edit any; save each change immediately."""
    while True:
        choices = [Choice(value=f["key"], name=f'{f["label"]}: {_display(f, settings[f["key"]])}')
                   for f in FIELDS]
        choices.append(Choice(value="__back__", name="← Back"))
        try:
            key = inquirer.select(message="Settings", choices=choices).execute()
        except KeyboardInterrupt:
            return
        if key == "__back__":
            return
        field = FIELD_BY_KEY[key]
        try:
            new_value = _edit(field, settings[key])
        except KeyboardInterrupt:
            continue  # cancel just this edit, back to the settings list
        settings[key] = new_value
        save_settings(settings)


# --- running -----------------------------------------------------------------

def _bool(flag: str, value: bool) -> list[str]:
    return [flag, "true" if value else "false"]


def settings_to_flags(s: dict) -> list[str]:
    """Turn the saved settings into Sports2D CLI tokens."""
    flags: list[str] = []
    if str(s["time_range"]).strip():
        flags += ["--time_range", *str(s["time_range"]).split()]
    flags += ["--nb_persons_to_detect", str(s["nb_persons_to_detect"]).strip()]
    flags += ["--first_person_height", str(s["first_person_height"]).strip()]
    flags += ["--pose_model", s["pose_model"]]
    flags += ["--mode", s["mode"]]
    flags += ["--det_frequency", str(s["det_frequency"]).strip()]
    flags += ["--backend", s["backend"]]
    flags += ["--device", s["device"]]
    flags += _bool("--calculate_angles", s["calculate_angles"])
    if s["calculate_angles"]:
        if s["joint_angles"]:
            flags += ["--joint_angles", *s["joint_angles"]]
        if s["segment_angles"]:
            flags += ["--segment_angles", *s["segment_angles"]]
    flags += _bool("--do_ik", s["do_ik"])
    if s["do_ik"]:
        flags += ["--visible_side", s["visible_side"]]
        if str(s["participant_mass"]).strip():
            flags += ["--participant_mass", *str(s["participant_mass"]).split()]
    flags += _bool("--save_pose", s["save_pose"])
    flags += _bool("--save_angles", s["save_angles"])
    flags += _bool("--save_vid", s["save_vid"])
    flags += _bool("--to_meters", s["to_meters"])
    flags += _bool("--make_c3d", s["make_c3d"])
    flags += _bool("--save_img", False)              # per-frame images: never needed here
    flags += _bool("--show_realtime_results", False)  # batch run: no blocking GUI windows
    flags += _bool("--show_graphs", False)
    flags += _bool("--save_graphs", False)
    return flags


def run(settings: dict) -> None:
    """Ask for a video and process it with the current settings."""
    try:
        raw = inquirer.filepath(message="Video file:").execute()
    except KeyboardInterrupt:
        return
    if not raw:
        return
    video = Path(raw).expanduser()
    if not video.is_file():
        print(f"  ! Not a file: {video}")
        return

    out_dir = RESULT_DIR / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["sports2d", "--video_input", str(video),
           "--result_dir", str(out_dir), *settings_to_flags(settings)]

    print("  Running Sports2D … live progress below.\n")
    # Do NOT capture output: let the tqdm bar and logs stream to the terminal.
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"  ! Sports2D failed (exit {proc.returncode}). See the log above.")
        return
    print(f"\n  Done. Output in: {out_dir}")


def main() -> None:
    _banner()
    settings = load_settings()
    while True:
        try:
            action = inquirer.select(
                message="Choose an action", choices=["Run", "Settings", "Exit"]).execute()
        except KeyboardInterrupt:
            return
        if action == "Run":
            run(settings)
        elif action == "Settings":
            settings_menu(settings)
        else:
            return


if __name__ == "__main__":
    main()

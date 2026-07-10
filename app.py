"""Cadence — Dash viewer (researchers).

Look at joint angles. Upload a Sports2D angles ``.mot`` file (produced by
``python main.py``) and the Gait Analysis page renders the run's metadata, the
raw table (inspect + export CSV), and every angle as a grid of plots. Left and
Right of a joint share axes in distinct colours so symmetry reads at a glance.
Does no processing of its own.

    python app.py    (serves at http://127.0.0.1:8050)
"""

from __future__ import annotations

import base64
import io

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import plotly.graph_objects as go
import plotly.io as pio
from dash import Dash, Input, Output, State, dash_table, dcc, html
from dash.dash_table.Format import Format, Scheme

APP_NAME = "Cadence"
TAGLINE = "University of Roehampton - powered by Sports2D"
PAGE_TITLE = "Gait Analysis"
TIME_COL = "time"


# --- theme -------------------------------------------------------------------
# One registered Plotly template so every figure matches the "Tartan Track"
# chrome in assets/cadence.css.
INK, SURFACE, MUTED = "#14130f", "#fcfbf8", "#6f6d66"
GRID, AXIS = "#e7e4dc", "#c9c5b9"
HEADER_BG = "#f0eee8"
FONT_BODY = 'inter, system-ui, -apple-system'
FONT_MONO = 'ui-monospace, Consolas, monospace'
CATEGORICAL = ["#d24e2b", "#e39a12", "#1f8f6b", "#8a3d72",
               "#9a8c1f", "#c2405f", "#4f7a3f", "#b5642a"]
LEFT_COLOUR, RIGHT_COLOUR = "#d24e2b", "#1f8f6b"   # vermilion / pine
SINGLE_COLOUR = "#454339"                          # graphite — axial, no side

_axis = dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=GRID,
             tickcolor=AXIS, tickfont=dict(color=MUTED, family=FONT_MONO, size=11),
             title_font=dict(color=MUTED))
pio.templates["cadence"] = go.layout.Template(layout=dict(
    font=dict(family=FONT_BODY, color=INK, size=13),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    colorway=CATEGORICAL, hovermode="x unified",
    xaxis=_axis, yaxis=_axis,
    margin=dict(l=52, r=18, t=42, b=40),
))
pio.templates.default = "cadence"


# --- reading Sports2D output -------------------------------------------------

def read_mot(text: str) -> pd.DataFrame:
    """Parse an OpenSim .mot file (header block, 'endheader', then a TSV table)."""
    lines = text.splitlines()
    header_end = next(
        (i for i, line in enumerate(lines) if line.strip().lower() == "endheader"),
        None,
    )
    if header_end is None:
        raise ValueError("not an OpenSim .mot file (no 'endheader' line)")
    df = pd.read_csv(io.StringIO(text), sep="\t", skiprows=header_end + 1)
    df.columns = [c.strip() for c in df.columns]
    in_degrees = next((line.strip().lower().endswith("yes")
                       for line in lines[:header_end]
                       if line.strip().lower().startswith("indegrees")), None)
    df.attrs["units"] = None if in_degrees is None else ("degrees" if in_degrees else "radians")
    return df


def mot_provenance(df: pd.DataFrame, filename: str) -> list[tuple[str, str]]:
    """(label, value) facts about the run, all derived from the table itself."""
    facts = [("File", filename)]
    if TIME_COL in df.columns and len(df) > 1:
        duration = float(df[TIME_COL].iloc[-1] - df[TIME_COL].iloc[0])
        step = df[TIME_COL].diff().median()
        facts.append(("Frames", str(len(df))))
        facts.append(("Duration", f"{duration:.1f} s"))
        if step and step > 0:
            facts.append(("Sample rate", f"{round(1 / step):g} fps"))
    facts.append(("Angles", str(len(df.columns) - (TIME_COL in df.columns))))
    if df.attrs.get("units"):
        facts.append(("Units", df.attrs["units"]))
    return facts


# --- analytics ---------------------------------------------------------------

# Prefer a strongly cyclic joint; each swings through a full arc once per stride.
CADENCE_SIGNALS = ("right knee", "left knee", "right ankle", "left ankle")


def cadence(df: pd.DataFrame) -> int | None:
    """Estimate running cadence (steps/min) from a cyclic joint by autocorrelation.

    A single knee's angle repeats once per gait cycle (one stride = two steps),
    so cadence = 120 / stride_period. Returns None when there's no suitable
    signal or no clear period. Nothing is trained — the signal is just
    correlated with itself, and the first peak's lag is the stride period.
    """
    signal_col = next((c for c in CADENCE_SIGNALS if c in df.columns), None)
    if signal_col is None or TIME_COL not in df.columns or len(df) < 20:
        return None
    dt = df[TIME_COL].diff().median()
    if not dt or dt <= 0:
        return None
    y = df[signal_col].to_numpy(dtype=float)
    y = np.nan_to_num(y - np.nanmean(y))
    autocorr = np.correlate(y, y, mode="full")[len(y) - 1:]
    lo, hi = max(int(round(0.4 / dt)), 1), min(int(round(1.5 / dt)), len(autocorr) - 1)
    if hi <= lo:
        return None
    stride_period = (lo + int(np.argmax(autocorr[lo:hi]))) * dt   # plausible stride 0.4–1.5 s
    return round(120.0 / stride_period)


def stride_peaks(df: pd.DataFrame) -> tuple[str | None, np.ndarray]:
    """Find gait-cycle boundaries in a cyclic joint via peak detection.

    Each stride makes one clear peak of knee flexion, so the peaks split the
    signal into strides (N peaks -> N-1 full strides). ``distance`` keeps peaks
    at least 0.4 s apart and ``prominence`` ignores small wiggles, so noise
    doesn't invent strides. Returns (signal column, peak indices).
    """
    signal_col = next((c for c in CADENCE_SIGNALS if c in df.columns), None)
    if signal_col is None or TIME_COL not in df.columns or len(df) < 20:
        return None, np.array([], dtype=int)
    dt = df[TIME_COL].diff().median()
    if not dt or dt <= 0:
        return None, np.array([], dtype=int)
    y = np.nan_to_num(df[signal_col].to_numpy(dtype=float))
    min_distance = max(int(round(0.4 / dt)), 1)
    peaks, _ = find_peaks(y, distance=min_distance, prominence=0.3 * np.nanstd(y))
    return signal_col, peaks


# Gait-cycle normalisation: every stride is stretched onto a shared 0-100% axis
# so strides of unequal length can be averaged into one representative cycle.
CYCLE_POINTS = 101


def _peaks_for(df: pd.DataFrame, col: str) -> np.ndarray:
    """Stride-boundary peaks for one column (same rule as ``stride_peaks``)."""
    dt = df[TIME_COL].diff().median()
    if not dt or dt <= 0:
        return np.array([], dtype=int)
    y = np.nan_to_num(df[col].to_numpy(dtype=float))
    peaks, _ = find_peaks(y, distance=max(int(round(0.4 / dt)), 1),
                          prominence=0.3 * np.nanstd(y))
    return peaks


def reference_peaks(df: pd.DataFrame) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Per-side stride boundaries. Right-side angles are normalised over the
    right knee/ankle cycle, left-side over the left; axial angles fall back to
    whichever side exists. Returns ({side: peaks}, default_peaks)."""
    refs: dict[str, np.ndarray] = {}
    for side in ("right", "left"):
        col = next((f"{side} {j}" for j in ("knee", "ankle")
                    if f"{side} {j}" in df.columns), None)
        if col is not None:
            refs[side] = _peaks_for(df, col)
    default = refs.get("right", np.array([], dtype=int))
    if len(default) < 2:
        default = refs.get("left", np.array([], dtype=int))
    return refs, default


def cycle_mean_std(values: np.ndarray, peaks: np.ndarray):
    """Resample each stride to 0-100% and return (mean, std) across strides, or
    None when no usable stride exists."""
    grid = np.linspace(0, 1, CYCLE_POINTS)
    strides = []
    for a, b in zip(peaks[:-1], peaks[1:]):
        seg = values[a:b]
        if len(seg) >= 3:
            strides.append(np.interp(grid, np.linspace(0, 1, len(seg)), seg))
    if not strides:
        return None
    stacked = np.vstack(strides)
    return stacked.mean(axis=0), stacked.std(axis=0)


# --- angle index -------------------------------------------------------------
# Sports2D lowercases angle names into the .mot header, e.g. "right knee",
# "left knee", "pelvis". Bilateral parts share a base ("knee") and pair on one
# plot; axial parts ("pelvis", "trunk", "head", "shoulders") stand alone.
SIDES = ("right", "left")
JOINT_PARTS = {"ankle", "knee", "hip", "shoulder", "elbow", "wrist"}


def _split_side(col: str) -> tuple[str | None, str]:
    """('right', 'knee') for 'right knee'; (None, 'pelvis') for 'pelvis'."""
    for side in SIDES:
        if col.startswith(side + " "):
            return side, col[len(side) + 1:]
    return None, col


def angle_index(df: pd.DataFrame) -> list[dict]:
    """Ordered parts from the angle columns, each grouped and side-mapped.

    A part is {"label", "group", "cols": {"left"/"right"/"single": column}}.
    File column order is preserved, so joints precede segments as Sports2D
    emits them.
    """
    parts: dict[str, dict] = {}
    order: list[str] = []
    for col in df.columns:
        if col == TIME_COL:
            continue
        side, base = _split_side(col)
        if base not in parts:
            group = "Joints" if base in JOINT_PARTS else "Segments"
            parts[base] = {"label": base.title(), "group": group, "cols": {}}
            order.append(base)
        parts[base]["cols"][side or "single"] = col
    return [parts[b] for b in order]


def part_figure(df: pd.DataFrame, part: dict) -> go.Figure:
    """A compact plot for one part: Left + Right in distinct colours, or a lone
    axial trace. Paired plots carry their own top-right legend. Units read
    inline off the y-tick suffix (30°)."""
    time = df[TIME_COL]
    cols = part["cols"]
    fig = go.Figure()
    if "single" in cols:
        fig.add_scatter(x=time, y=df[cols["single"]], mode="lines", name=part["label"],
                        line=dict(color=SINGLE_COLOUR, width=2))
    else:
        if "left" in cols:
            fig.add_scatter(x=time, y=df[cols["left"]], mode="lines", name="Left",
                            line=dict(color=LEFT_COLOUR, width=2))
        if "right" in cols:
            fig.add_scatter(x=time, y=df[cols["right"]], mode="lines", name="Right",
                            line=dict(color=RIGHT_COLOUR, width=2))
    fig.update_layout(
        title=dict(text=part["label"], font=dict(size=14, color=INK), x=0, xanchor="left"),
        height=300, showlegend="single" not in cols,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(size=11)),
    )
    fig.update_xaxes(title_text="time (s)", nticks=6, automargin=True)
    fig.update_yaxes(ticksuffix="°", nticks=5, automargin=True)
    return fig


def _decode(contents: str) -> str:
    """Decode a dcc.Upload 'data:...;base64,...' payload to text."""
    b64 = contents.split(",", 1)[1]
    return base64.b64decode(b64).decode("utf-8", errors="replace")


# --- views -------------------------------------------------------------------

def meta_cards(facts: list[tuple[str, str]]) -> html.Div:
    """Provenance as a single row of tiles, one card per fact."""
    return html.Div(className="meta-grid", children=[
        html.Div(className="meta-card", children=[
            html.Div(label, className="meta-label"),
            html.Div(value, title=value,
                     className="meta-value mono" + (" meta-file" if label == "File" else "")),
        ])
        for label, value in facts
    ])


def data_table(df: pd.DataFrame) -> html.Div:
    """The raw table: sortable, paginated, with a CSV export button. Values show
    at 2 dp but export at full precision (the stored data is untouched)."""
    columns = [{"name": c, "id": c, "type": "numeric",
                "format": Format(precision=2, scheme=Scheme.fixed)}
               for c in df.columns]
    table = dash_table.DataTable(
        data=df.to_dict("records"),
        columns=columns,
        sort_action="native",
        page_size=12,
        export_format="csv",
        export_headers="display",
        style_as_list_view=True,
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": FONT_MONO, "fontSize": "12px", "padding": "6px 12px",
                    "textAlign": "right", "color": INK, "backgroundColor": SURFACE,
                    "border": "none", "minWidth": "76px"},
        style_header={"fontFamily": FONT_BODY, "fontSize": "11px", "fontWeight": "600",
                      "textTransform": "uppercase", "letterSpacing": "0.04em",
                      "color": MUTED, "backgroundColor": HEADER_BG,
                      "border": "none", "textAlign": "right"},
        style_data={"borderBottom": f"1px solid {GRID}"},
    )
    return html.Div(className="table-card", children=[
        html.Div("Data", className="section-label"),
        table,
    ])


# Mode bar on: download / zoom / pan per plot, minus the marquee-select tools.
PLOT_CONFIG = {"displaylogo": False, "responsive": True,
               "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def _plot_card(fig: go.Figure) -> html.Div:
    return html.Div(dcc.Graph(figure=fig, config=PLOT_CONFIG, style={"width": "100%"}),
                    className="plot-card")


def grid_view(df: pd.DataFrame, parts: list[dict]) -> list:
    """Every part as a plot card, grouped into Joints and Segments sections."""
    out: list = []
    for group in ("Joints", "Segments"):
        members = [p for p in parts if p["group"] == group]
        if not members:
            continue
        out.append(html.Div(group, className="section-label"))
        out.append(html.Div([_plot_card(part_figure(df, p)) for p in members],
                            className="plot-grid"))
    return out


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"


def cycle_figure(df: pd.DataFrame, part: dict,
                 refs: dict[str, np.ndarray], default: np.ndarray) -> go.Figure | None:
    """Gait-cycle plot for one part: the mean stride (0-100%) with a ±SD band,
    per side. Returns None if no side yields a usable cycle."""
    grid = np.linspace(0, 100, CYCLE_POINTS)
    band_x = np.concatenate([grid, grid[::-1]])
    fig = go.Figure()
    drew = False
    for side, colour, name in (("left", LEFT_COLOUR, "Left"),
                               ("right", RIGHT_COLOUR, "Right"),
                               ("single", SINGLE_COLOUR, part["label"])):
        if side not in part["cols"]:
            continue
        peaks = default if side == "single" else refs.get(side, default)
        result = cycle_mean_std(df[part["cols"][side]].to_numpy(dtype=float), peaks)
        if result is None:
            continue
        mean, std = result
        fig.add_scatter(x=band_x, y=np.concatenate([mean + std, (mean - std)[::-1]]),
                        fill="toself", fillcolor=_rgba(colour, 0.15), line=dict(width=0),
                        hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=grid, y=mean, mode="lines", name=name,
                        line=dict(color=colour, width=2))
        drew = True
    if not drew:
        return None
    fig.update_layout(
        title=dict(text=part["label"], font=dict(size=14, color=INK), x=0, xanchor="left"),
        height=300, showlegend="single" not in part["cols"],
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
                    font=dict(size=11)),
    )
    fig.update_xaxes(title_text="gait cycle (%)", nticks=6, automargin=True, range=[0, 100])
    fig.update_yaxes(ticksuffix="°", nticks=5, automargin=True)
    return fig


def gait_cycle_view(df: pd.DataFrame, parts: list[dict]) -> list:
    """A section of gait-cycle (mean ± SD) plots, one per part that has strides.
    Empty when there's no cyclic reference to segment on."""
    refs, default = reference_peaks(df)
    if len(default) < 2:
        return []
    cards = [_plot_card(fig) for p in parts
             if (fig := cycle_figure(df, p, refs, default)) is not None]
    if not cards:
        return []
    return [html.Div("Gait cycle — mean ± SD", className="section-label"),
            html.Div(cards, className="plot-grid")]


# --- Dash app ----------------------------------------------------------------
# Both views live in the layout at all times; a file selection toggles which is
# shown. The sidebar is the fixed shell (brand + Clear, room for future page
# nav); the main pane is the Gait Analysis page: header, meta, table, plots.

app = Dash(__name__, title=APP_NAME)
app.layout = html.Div([
    html.Div(id="landing", className="landing", children=[
        html.H1(APP_NAME, className="brand-title"),
        html.P(TAGLINE, className="tagline"),
        dcc.Upload(id="upload", multiple=False, className="uploader", children=html.Div([
            html.Div("Drop a Sports2D angles file here"),
            html.Div([html.Span("browse", className="link"), " for a .mot file"],
                     className="uploader-hint"),
        ])),
    ]),
    html.Div(id="workspace", className="workspace", hidden=True, children=[
        html.Div(className="sidebar", children=[
            html.Div(APP_NAME, className="side-title"),
            html.Button("Clear workspace", id="clear-btn", className="btn"),
        ]),
        html.Div(className="main", children=[
            html.H2(PAGE_TITLE, className="page-title"),
            html.Div(id="content"),
        ]),
    ]),
])


@app.callback(
    Output("landing", "hidden"),
    Output("workspace", "hidden"),
    Output("content", "children"),
    Input("upload", "contents"),
    State("upload", "filename"),
    prevent_initial_call=True,
)
def load(contents: str | None, filename: str | None):
    """A file opens the workspace; no file (after Clear) returns to landing."""
    if not contents:
        return False, True, None
    try:
        df = read_mot(_decode(contents))
        parts = angle_index(df)
        if not parts:
            raise ValueError("no angle columns to plot")
        facts = mot_provenance(df, filename)
        spm = cadence(df)
        if spm:
            facts.append(("Cadence", f"~{spm} spm"))
        _, peaks = stride_peaks(df)
        if len(peaks) >= 2:
            facts.append(("Strides", str(len(peaks) - 1)))
        body = [meta_cards(facts),
                data_table(df),
                *grid_view(df, parts),
                *gait_cycle_view(df, parts)]
    except Exception as err:  # a bad upload should report, not crash the app
        body = [html.P(f"Couldn't read {filename}: {err}", className="error")]
    return True, False, body


@app.callback(
    Output("upload", "contents"),
    Input("clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_workspace(_n_clicks: int):
    """Reset the upload — which sends ``load`` back to the landing view."""
    return None


if __name__ == "__main__":
    app.run(debug=True)

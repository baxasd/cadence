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
import plotly.graph_objects as go
import plotly.io as pio
from dash import Dash, Input, Output, State, dash_table, dcc, html
from dash.dash_table.Format import Format, Scheme
from dash.exceptions import PreventUpdate

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

# Cadence-over-time sliding window: how much run each point averages, and how far
# the window hops between points. Defaults for both the function and the UI knobs.
CADENCE_WINDOW_S = 4.0
CADENCE_STEP_S = 1.0


def _stride_period(y: np.ndarray, dt: float) -> float | None:
    """Stride period (s) of a cyclic signal by autocorrelation, or None.

    The de-meaned signal is correlated with itself; the first peak in the
    0.4–1.5 s lag window is the stride period. That peak's lag is refined by a
    parabolic fit to its two neighbours, so the period is sub-frame accurate
    rather than capped at one-frame steps. Nothing is trained.
    """
    if len(y) < 20:
        return None
    y = np.nan_to_num(y - np.nanmean(y))
    autocorr = np.correlate(y, y, mode="full")[len(y) - 1:]
    lo, hi = max(int(round(0.4 / dt)), 1), min(int(round(1.5 / dt)), len(autocorr) - 1)
    if hi <= lo:
        return None
    k = lo + int(np.argmax(autocorr[lo:hi]))
    # Parabolic interpolation on the three points around the peak recovers a
    # sub-frame lag: offset in (-0.5, 0.5) samples from the integer peak k.
    a, b, c = autocorr[k - 1], autocorr[k], autocorr[k + 1]
    denom = a - 2 * b + c
    offset = 0.5 * (a - c) / denom if denom else 0.0
    return (k + offset) * dt


def _cadence_signal(df: pd.DataFrame) -> tuple[str | None, float | None]:
    """Pick a cyclic joint column and the median frame interval, or (None, None)."""
    signal_col = next((c for c in CADENCE_SIGNALS if c in df.columns), None)
    if signal_col is None or TIME_COL not in df.columns:
        return None, None
    dt = df[TIME_COL].diff().median()
    return (signal_col, dt) if dt and dt > 0 else (None, None)


def cadence(df: pd.DataFrame) -> int | None:
    """Overall running cadence (steps/min) over the whole clip: one stride is
    two steps, so cadence = 120 / stride_period. None if there's no clear period.
    """
    signal_col, dt = _cadence_signal(df)
    if signal_col is None:
        return None
    period = _stride_period(df[signal_col].to_numpy(dtype=float), dt)
    return round(120.0 / period) if period else None


def cadence_series(df: pd.DataFrame, window_s: float = CADENCE_WINDOW_S,
                   step_s: float = CADENCE_STEP_S) -> tuple[np.ndarray, np.ndarray]:
    """Cadence in sliding windows across the run, as (times, steps/min).

    Each window's stride period is estimated exactly as the overall number, so
    the trace shows how cadence drifts over the run (e.g. with fatigue) without
    a second, competing method. Windows with no clear period are dropped.
    """
    signal_col, dt = _cadence_signal(df)
    if signal_col is None:
        return np.array([]), np.array([])
    y = df[signal_col].to_numpy(dtype=float)
    t = df[TIME_COL].to_numpy(dtype=float)
    win = int(round(window_s / dt))
    step = max(int(round(step_s / dt)), 1)
    times, spm = [], []
    for start in range(0, len(y) - win + 1, step):
        period = _stride_period(y[start:start + win], dt)
        if period:
            times.append(t[start + win // 2])
            spm.append(120.0 / period)
    return np.array(times), np.array(spm)


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


def cadence_figure(times: np.ndarray, spm: np.ndarray) -> go.Figure:
    """The cadence-over-time line for a computed (times, steps/min) series."""
    fig = go.Figure()
    fig.add_scatter(x=times, y=spm, mode="lines", name="Cadence",
                    line=dict(color=SINGLE_COLOUR, width=2))
    fig.update_layout(
        title=dict(text="Cadence", font=dict(size=14, color=INK), x=0, xanchor="left"),
        height=300, showlegend=False)
    fig.update_xaxes(title_text="time (s)", nticks=6, automargin=True)
    fig.update_yaxes(title_text="steps/min", nticks=5, automargin=True)
    return fig


def _cadence_knob(label: str, control_id: str, value: float, minimum: float) -> html.Div:
    """A labelled numeric input for one sliding-window setting."""
    return html.Div(className="cadence-knob", children=[
        html.Label(label, htmlFor=control_id),
        dcc.Input(id=control_id, type="number", value=value, min=minimum, step=0.5,
                  debounce=True),
    ])


def cadence_view(df: pd.DataFrame, window_s: float, step_s: float) -> list:
    """A cadence-over-time line, so a drift (e.g. with fatigue) is visible.
    The window/step knobs live in the sidebar. Empty when there's no series."""
    times, spm = cadence_series(df, window_s, step_s)
    if len(times) < 2:
        return []
    graph = dcc.Graph(id="cadence-graph", figure=cadence_figure(times, spm),
                      config=PLOT_CONFIG, style={"width": "100%"})
    return [html.Div("Cadence over time", className="section-label"),
            html.Div([html.Div(graph, className="plot-card")], className="plot-grid")]


# --- Dash app ----------------------------------------------------------------
# Both views live in the layout at all times; a file selection toggles which is
# shown. The sidebar is the fixed shell (brand + Clear, room for future page
# nav); the main pane is the Gait Analysis page: header, meta, table, plots.

# suppress_callback_exceptions: the cadence knobs and graph are created inside
# the load callback, so they aren't in the initial layout Dash validates against.
app = Dash(__name__, title=APP_NAME, suppress_callback_exceptions=True)
app.layout = html.Div([
    dcc.Store(id="cadence-store"),
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
            html.Div(className="side-controls", children=[
                html.Div("Cadence window", className="side-label"),
                _cadence_knob("Window (s)", "cadence-window", CADENCE_WINDOW_S, 1.0),
                _cadence_knob("Step (s)", "cadence-step", CADENCE_STEP_S, 0.5),
            ]),
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
    Output("cadence-store", "data"),
    Input("upload", "contents"),
    State("upload", "filename"),
    State("cadence-window", "value"),
    State("cadence-step", "value"),
    prevent_initial_call=True,
)
def load(contents: str | None, filename: str | None,
         window_s: float | None, step_s: float | None):
    """A file opens the workspace; no file (after Clear) returns to landing."""
    if not contents:
        return False, True, None, None
    window_s = window_s or CADENCE_WINDOW_S   # knobs may be blank on first load
    step_s = step_s or CADENCE_STEP_S
    store = None
    try:
        df = read_mot(_decode(contents))
        parts = angle_index(df)
        if not parts:
            raise ValueError("no angle columns to plot")
        facts = mot_provenance(df, filename)
        spm = cadence(df)
        if spm:
            facts.append(("Cadence", f"~{spm} spm"))
        signal_col, _ = _cadence_signal(df)
        if signal_col:  # keep the cadence signal so the knobs can recompute live
            store = {"time": df[TIME_COL].tolist(), "col": signal_col,
                     "vals": df[signal_col].tolist()}
        body = [meta_cards(facts),
                data_table(df),
                *cadence_view(df, window_s, step_s),
                *grid_view(df, parts)]
    except Exception as err:  # a bad upload should report, not crash the app
        body = [html.P(f"Couldn't read {filename}: {err}", className="error")]
    return True, False, body, store


@app.callback(
    Output("cadence-graph", "figure"),
    Input("cadence-window", "value"),
    Input("cadence-step", "value"),
    State("cadence-store", "data"),
    prevent_initial_call=True,
)
def retune_cadence(window_s: float | None, step_s: float | None, store: dict | None):
    """Recompute the cadence-over-time line when a window/step knob changes."""
    if not store or not window_s or not step_s:
        raise PreventUpdate
    df = pd.DataFrame({TIME_COL: store["time"], store["col"]: store["vals"]})
    times, spm = cadence_series(df, window_s, step_s)
    return cadence_figure(times, spm)


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

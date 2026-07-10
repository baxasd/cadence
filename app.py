"""Cadence — Dash viewer (researchers).

Look at joint angles. Upload a Sports2D angles ``.mot`` file (produced by
``python main.py``) and it renders the run's provenance and one interactive
time-series plot per angle. Does no processing of its own.

    python app.py    (serves at http://127.0.0.1:8050)
"""

from __future__ import annotations

import base64
import io

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from dash import Dash, dcc, html, Input, Output, State

APP_NAME = "Cadence"
TAGLINE = "University of Roehampton - powered by Sports2D"
TIME_COL = "time"


# --- theme -------------------------------------------------------------------
# One registered Plotly template so every figure matches the CSS chrome in
# assets/cadence.css. Chart values come from the validated data-viz palette;
# the pink brand accent lives only in the CSS chrome.
INK, SURFACE, MUTED = "#0b0b0b", "#fcfcfb", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
               "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]

_axis = dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=GRID,
             tickcolor=AXIS, tickfont=dict(color=MUTED),
             title_font=dict(color=MUTED))
pio.templates["cadence"] = go.layout.Template(layout=dict(
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
              color=INK, size=13),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    colorway=CATEGORICAL, hovermode="x unified",
    xaxis=_axis, yaxis=_axis,
    margin=dict(l=52, r=20, t=40, b=40),
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
    return facts


def figures_for(df: pd.DataFrame) -> list[go.Figure]:
    """One time-series figure per angle column."""
    if TIME_COL not in df.columns:
        raise ValueError(f"no '{TIME_COL}' column in the file")
    time = df[TIME_COL]
    figs: list[go.Figure] = []
    for col in df.columns:
        if col == TIME_COL:
            continue
        fig = go.Figure(go.Scatter(x=time, y=df[col], mode="lines", name=col))
        fig.update_layout(
            title=col.capitalize(), xaxis_title="time (s)", yaxis_title="angle (°)",
            height=300, showlegend=False,
        )
        figs.append(fig)
    return figs


def _decode(contents: str) -> str:
    """Decode a dcc.Upload 'data:...;base64,...' payload to text."""
    b64 = contents.split(",", 1)[1]
    return base64.b64decode(b64).decode("utf-8", errors="replace")


# --- views -------------------------------------------------------------------

def provenance_view(facts: list[tuple[str, str]]) -> html.Div:
    """A row of stat tiles for the run's provenance."""
    return html.Div(className="stat-grid", children=[
        html.Div(className="stat-card", children=[
            html.Div(label, className="stat-label"),
            html.Div(value, className="stat-value"),
        ])
        for label, value in facts
    ])


def plots_view(df: pd.DataFrame) -> list:
    """The angle plots, each in a card, in a responsive grid."""
    cards = [html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}),
                      className="plot-card")
             for fig in figures_for(df)]
    return [
        html.Div("Joint & segment angles", className="section-label"),
        html.Div(cards, className="plot-grid"),
    ]


# --- Dash app ----------------------------------------------------------------
# Both views live in the layout at all times; a file selection toggles which is
# shown. Keeping `upload` and `clear-btn` always mounted is what lets their
# callbacks bind cleanly (no dynamically-created callback targets).

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
            html.Div(id="side-file", className="side-file"),
            html.Button("Clear workspace", id="clear-btn", className="btn"),
        ]),
        html.Div(id="main", className="main"),
    ]),
])


@app.callback(
    Output("landing", "hidden"),
    Output("workspace", "hidden"),
    Output("main", "children"),
    Output("side-file", "children"),
    Input("upload", "contents"),
    State("upload", "filename"),
    prevent_initial_call=True,
)
def show_upload(contents: str | None, filename: str | None):
    """A file opens the workspace; no file (after Clear) returns to landing."""
    if not contents:
        return False, True, None, None
    try:
        df = read_mot(_decode(contents))
        body = [provenance_view(mot_provenance(df, filename)), *plots_view(df)]
    except Exception as err:  # a bad upload should report, not crash the app
        body = [html.P(f"Couldn't read {filename}: {err}", className="error")]
    return True, False, body, filename


@app.callback(
    Output("upload", "contents"),
    Input("clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_workspace(_n_clicks: int):
    """Reset the upload — which sends ``show_upload`` back to the landing view."""
    return None


if __name__ == "__main__":
    app.run(debug=True)

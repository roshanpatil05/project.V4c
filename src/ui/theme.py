from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import streamlit as st


COLORS = {
    "bg_deep": "#120F3F",
    "bg_indigo": "#2B1658",
    "bg_purple": "#5B2A6E",
    "magenta": "#B93A96",
    "pink": "#E87CF7",
    "soft_pink": "#F2A9DA",
    "lavender": "#C9A7E8",
    "violet_blue": "#6C63FF",
    "text": "#FFFFFF",
    "muted": "#CFC3E6",
}

COLOURWAY = [
    COLORS["pink"], COLORS["magenta"], COLORS["violet_blue"], COLORS["soft_pink"],
    COLORS["lavender"], "#8E5BD6", "#FF7AB6", "#7A3FA0",
]
SEQUENTIAL_SCALE = [
    (0.0, COLORS["bg_indigo"]),
    (0.25, COLORS["bg_purple"]),
    (0.55, COLORS["magenta"]),
    (0.8, COLORS["pink"]),
    (1.0, COLORS["soft_pink"]),
]


def apply_theme() -> None:
    st.set_page_config(page_title="Enterprise Employee Analytics", page_icon="✦", layout="wide")
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Poppins:wght@600;700;800&display=swap');

        :root {
            --bg-deep: #120F3F;
            --bg-indigo: #2B1658;
            --bg-purple: #5B2A6E;
            --magenta: #B93A96;
            --pink: #E87CF7;
            --soft-pink: #F2A9DA;
            --lavender: #C9A7E8;
            --text: #FFFFFF;
            --muted: #CFC3E6;
            --card: rgba(255, 255, 255, 0.06);
            --border: rgba(255, 255, 255, 0.12);
        }

        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .stApp {
            color: var(--text);
            background: radial-gradient(circle at 90% 95%, rgba(91, 42, 110, .55), transparent 35%),
                        linear-gradient(135deg, var(--bg-deep) 0%, var(--bg-indigo) 58%, var(--bg-purple) 100%);
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(18, 15, 63, .98), rgba(43, 22, 88, .96));
            border-right: 1px solid rgba(232, 124, 247, .14);
        }
        [data-testid="stSidebar"] > div:first-child { padding-top: 2rem; }
        [data-testid="stSidebar"] [data-testid="stRadio"] > label {
            color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .14em;
        }
        [data-testid="stSidebar"] [role="radiogroup"] { gap: .35rem; }
        [data-testid="stSidebar"] [role="radio"] {
            border-radius: 12px; padding: .65rem .8rem; color: var(--muted); transition: all .2s ease;
        }
        [data-testid="stSidebar"] [role="radio"]:hover { background: rgba(232, 124, 247, .12); color: white; }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
            color: white; background: linear-gradient(90deg, rgba(185, 58, 150, .95), rgba(91, 42, 110, .72));
            box-shadow: 0 0 22px rgba(232, 124, 247, .2);
        }
        [data-testid="stSidebar"] [role="radio"] > div:first-child { display: none; }
        .brand-mark { margin: 0 0 2.2rem .6rem; font: 800 1.25rem 'Poppins', sans-serif; letter-spacing: -.03em; }
        .brand-mark span, .gradient-text {
            background: linear-gradient(90deg, var(--pink), var(--magenta), var(--soft-pink));
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .page-shell { animation: page-in .45s ease both; }
        @keyframes page-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        h1, h2, h3 { font-family: 'Poppins', sans-serif; color: white; letter-spacing: -.02em; }
        .hero-title { margin: .2rem 0 .25rem; font: 800 clamp(2rem, 4vw, 3.5rem) 'Poppins', sans-serif; line-height: 1.05; }
        .hero-subtitle, .muted { color: var(--muted); }
        .section-title { margin: 1.5rem 0 .8rem; font: 700 1.2rem 'Poppins', sans-serif; }
        .kpi-card, .glass-card {
            background: var(--card); border: 1px solid var(--border); border-radius: 16px;
            box-shadow: 0 14px 34px rgba(10, 5, 35, .22), 0 0 22px rgba(185, 58, 150, .08);
        }
        .kpi-card { padding: 1rem 1.1rem; min-height: 112px; }
        .kpi-label { color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .08em; }
        .kpi-value { margin-top: .42rem; color: white; font: 700 1.65rem 'Poppins', sans-serif; }
        .kpi-delta { color: var(--soft-pink); font-size: .78rem; margin-top: .18rem; }
        .status-badge, .info-pill, .score-band {
            display: inline-flex; align-items: center; gap: .4rem; border-radius: 999px; padding: .35rem .72rem;
            color: white; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); font-size: .78rem;
        }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--soft-pink); box-shadow: 0 0 10px currentColor; }
        .status-badge.success .status-dot { background: #71e6aa; }
        .status-badge.warning .status-dot { background: #f8c76a; }
        .info-pill { color: var(--lavender); }
        div[data-testid="stForm"], div[data-testid="stExpander"], div[data-testid="stDataFrame"] {
            border-color: var(--border); border-radius: 16px; background: var(--card);
        }
        div[data-testid="stForm"] { padding: 1rem 1.1rem; }
        input, textarea, [data-baseweb="select"] > div, [data-baseweb="input"] > div {
            background: rgba(18, 15, 63, .62) !important; color: white !important; border-color: rgba(255,255,255,.16) !important;
            border-radius: 10px !important;
        }
        input:focus, textarea:focus, [data-baseweb="select"] > div:focus-within { border-color: var(--pink) !important; box-shadow: 0 0 0 1px var(--pink) !important; }
        label, [data-testid="stWidgetLabel"] p { color: var(--muted) !important; }
        button[kind="primary"], [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(90deg, var(--pink), var(--magenta)) !important; color: white !important;
            border: 0 !important; border-radius: 10px !important; font-weight: 700 !important;
            box-shadow: 0 8px 20px rgba(185, 58, 150, .25); transition: transform .2s ease, box-shadow .2s ease;
        }
        button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover { transform: translateY(-2px); box-shadow: 0 12px 26px rgba(232, 124, 247, .28); }
        [data-testid="stTabs"] [role="tab"] { color: var(--muted); }
        [data-testid="stTabs"] [aria-selected="true"] { color: white; }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--pink); }
        [data-testid="stMetric"] { background: transparent; }
        [data-testid="stAlert"] { border-radius: 12px; }
        
        /* Department selection pills/buttons */
        div[data-testid="stPills"] { gap: 0.5rem; margin-top: 0.25rem; margin-bottom: 0.5rem; }
        div[data-testid="stPills"] button {
            border-radius: 20px !important;
            padding: 0.45rem 1rem !important;
            font-weight: 600 !important;
            font-size: 0.88rem !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            background: rgba(255, 255, 255, 0.07) !important;
            color: #E2E8F0 !important;
            cursor: pointer !important;
        }
        div[data-testid="stPills"] button:hover {
            border-color: var(--pink) !important;
            background: rgba(232, 124, 247, 0.18) !important;
            color: #FFFFFF !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(232, 124, 247, 0.25) !important;
        }
        div[data-testid="stPills"] button[aria-pressed="true"],
        div[data-testid="stPills"] button[aria-checked="true"],
        div[data-testid="stPills"] button[data-state="active"] {
            background: linear-gradient(90deg, #E87CF7, #B93A96) !important;
            color: #FFFFFF !important;
            border-color: #E87CF7 !important;
            box-shadow: 0 4px 16px rgba(232, 124, 247, 0.45) !important;
            font-weight: 700 !important;
        }
        footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="page-shell"><div class="hero-title">{title}</div><div class="hero-subtitle">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: Any, delta: str | None = None, icon: str | None = None) -> None:
    icon_text = f"{icon} " if icon else ""
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    st.markdown(
        f'<div class="kpi-card"><div class="kpi-label">{icon_text}{label}</div><div class="kpi-value">{value}</div>{delta_html}</div>',
        unsafe_allow_html=True,
    )


def status_badge(text: str, state: str = "warning") -> None:
    st.markdown(
        f'<span class="status-badge {state}"><span class="status-dot"></span>{text}</span>',
        unsafe_allow_html=True,
    )


def info_pill(text: str) -> None:
    st.markdown(f'<span class="info-pill">ⓘ&nbsp; {text}</span>', unsafe_allow_html=True)


def score_band(score: float) -> tuple[str, str]:
    if score >= 90:
        return "Outstanding", COLORS["pink"]
    if score >= 80:
        return "Exceeds expectations", COLORS["soft_pink"]
    if score >= 70:
        return "Meets expectations", COLORS["lavender"]
    return "Needs improvement", COLORS["magenta"]


def style_fig(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, sans-serif", "color": COLORS["muted"]},
        colorway=COLOURWAY,
        margin={"l": 24, "r": 24, "t": 58, "b": 34},
        legend={"font": {"color": COLORS["muted"]}, "bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"bgcolor": COLORS["bg_deep"], "font": {"color": "white", "family": "Inter"}},
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,.08)", zeroline=False, linecolor="rgba(255,255,255,.12)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,.08)", zeroline=False, linecolor="rgba(255,255,255,.12)")
    return fig

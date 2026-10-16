"""Styled login page for V4C.ai — matches existing dark theme."""
from __future__ import annotations

import streamlit as st

from src.auth.authenticator import login


def render_login() -> None:
    """Render the full-screen login page."""
    # ── Custom login page styles (extends theme.py) ──────────────────────
    st.markdown(
        """
        <style>
        /* Hide sidebar on login page */
        [data-testid="stSidebar"] { display: none !important; }

        .login-shell {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 80vh;
            animation: page-in .5s ease both;
        }
        .login-card {
            width: 100%;
            max-width: 420px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 20px;
            padding: 2.4rem 2rem;
            box-shadow: 0 24px 60px rgba(10,5,35,.45), 0 0 40px rgba(185,58,150,.12);
        }
        .login-brand {
            text-align: center;
            margin-bottom: 0.2rem;
            font: 800 2rem 'Poppins', sans-serif;
            letter-spacing: -.04em;
        }
        .login-brand span {
            background: linear-gradient(90deg, #E87CF7, #B93A96, #F2A9DA);
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .login-subtitle {
            text-align: center;
            color: #CFC3E6;
            font-size: .88rem;
            margin-bottom: 2rem;
        }
        .login-divider {
            height: 1px;
            background: rgba(255,255,255,0.1);
            margin: 1.4rem 0;
        }
        .login-footer {
            text-align: center;
            color: #CFC3E6;
            font-size: .75rem;
            margin-top: 1.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Layout: centre the card ──────────────────────────────────────────
    _, mid, _ = st.columns([1, 1.6, 1])

    with mid:
        st.markdown(
            """
            <div class="login-shell">
              <div class="login-card">
                <div class="login-brand"><span>V4C</span>.ai</div>
                <div class="login-subtitle">Enterprise Employee Analytics Platform</div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input(
                "Work email",
                placeholder="you@company.com",
                key="login_email",
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="••••••••",
                key="login_password",
            )
            submitted = st.form_submit_button(
                "Sign in →",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            with st.spinner("Authenticating…"):
                ok, err = login(email, password)
            if ok:
                st.rerun()   # triggers main app re-render with auth in session
            else:
                st.error(err)

        st.markdown(
            """
                <div class="login-divider"></div>
                <div class="login-footer">
                  Contact your HR administrator to set up or reset your account.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Read Streamlit secrets first, then environment variables."""
    try:
        import streamlit as st

        value = st.secrets.get(key)
        if value is not None:
            return str(value)
    except Exception:
        pass

    return os.getenv(key, default)


@dataclass(frozen=True)
class DatabaseSettings:
    host: str = _get_secret("DB_HOST", "localhost")
    port: int = int(_get_secret("DB_PORT", "3306"))
    user: str = _get_secret("DB_USER", "root")
    password: str = _get_secret("DB_PASSWORD", "")
    database: str = _get_secret(
        "DB_NAME", "employee_analytics"
    )
    ssl_mode: str = _get_secret("DB_SSL_MODE", "")


settings = DatabaseSettings()
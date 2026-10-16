"""Authenticator — login, logout, session management, and role resolution."""
from __future__ import annotations

import bcrypt
import streamlit as st

from src.database.db_manager import DatabaseConnection


# ---------------------------------------------------------------------------
# Internal DB helper (thin wrapper — no singleton needed for auth queries)
# ---------------------------------------------------------------------------
class _AuthDB(DatabaseConnection):
    """Dedicated DatabaseConnection subclass for auth operations."""


_db = _AuthDB()


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Role resolution
# ---------------------------------------------------------------------------

def resolve_role(job_title: str, department_id: int) -> str:
    """
    Derive the app user-role from *job_title* and *department_id* by querying
    the role_rules table in priority order.

    Falls back to 'Employee' if no rule matches.
    """
    rows = _db.fetch_all(
        """
        SELECT role_name
        FROM   role_rules
        WHERE  (department_id IS NULL OR department_id = %s)
          AND  %s LIKE title_pattern
        ORDER  BY priority ASC
        LIMIT  1
        """,
        (department_id, job_title),
    )
    return rows[0]["role_name"] if rows else "Employee"


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

def login(email: str, password: str) -> tuple[bool, str]:
    """
    Attempt login with *email* + *password*.

    Returns (True, "") on success — session state is populated.
    Returns (False, error_message) on failure.
    """
    if not email or not password:
        return False, "Please enter your email and password."

    # 1. Look up account by email
    row = _db.fetch_one(
        """
        SELECT ua.account_id, ua.password_hash, ua.is_active, ua.forced_role,
               e.employee_id, e.first_name, e.last_name, e.email,
               e.job_title, e.department_id, e.status,
               d.department_name
        FROM   user_accounts ua
        JOIN   employees     e  ON e.employee_id    = ua.employee_id
        JOIN   departments   d  ON d.department_id  = e.department_id
        WHERE  e.email = %s
        """,
        (email.strip().lower(),),
    )

    if row is None:
        _log_event(None, "login_failed", f"No account for email: {email}")
        return False, "Invalid email or password."

    if not row["is_active"]:
        _log_event(row["employee_id"], "login_failed", "Account inactive")
        return False, "Your account has been deactivated. Contact your administrator."

    if row["status"] == "inactive":
        _log_event(row["employee_id"], "login_failed", "Employee record inactive")
        return False, "Your employee record is inactive. Contact HR."

    # 2. Verify password
    if not verify_password(password, row["password_hash"]):
        _log_event(row["employee_id"], "login_failed", "Wrong password")
        return False, "Invalid email or password."

    # 3. Resolve role
    # forced_role (CLI-set) takes absolute priority over role_rules.
    # Super Admin can ONLY be granted this way — never via the UI.
    if row["forced_role"]:
        role = row["forced_role"]
    else:
        role = resolve_role(row["job_title"], row["department_id"])

    # 4. Stamp last_login
    try:
        _db.execute(
            "UPDATE user_accounts SET last_login = NOW() WHERE account_id = %s",
            (row["account_id"],),
            commit=True,
        )
    except Exception:
        pass  # Non-critical — don't fail the login

    # 5. Write session
    st.session_state["auth"] = {
        "employee_id":   row["employee_id"],
        "name":          f"{row['first_name']} {row['last_name']}",
        "email":         row["email"],
        "role":          role,
        "department_id": row["department_id"],
        "department_name": row["department_name"],
        "job_title":     row["job_title"],
    }

    _log_event(row["employee_id"], "login_success", f"Role resolved: {role}")
    return True, ""


def logout() -> None:
    """Clear session state and rerun."""
    employee_id = st.session_state.get("auth", {}).get("employee_id")
    _log_event(employee_id, "logout", "User logged out")
    st.session_state.pop("auth", None)
    st.rerun()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_current_user() -> dict | None:
    """Return the current auth dict from session state, or None."""
    return st.session_state.get("auth")


def require_auth() -> dict:
    """
    Call at the top of streamlit_app.py main flow.
    If not authenticated, renders the login page and stops execution.
    Returns the auth dict when authenticated.
    """
    user = get_current_user()
    if user is None:
        from src.ui.login_page import render_login  # avoid circular import
        render_login()
        st.stop()
    return user


# ---------------------------------------------------------------------------
# Account management (used by Super Admin panel)
# ---------------------------------------------------------------------------

def create_account(employee_id: int, plain_password: str, forced_role: str | None = None) -> None:
    """Create a user_account row for *employee_id*.

    Args:
        employee_id:  The employee to create an account for.
        plain_password: Plain-text password (will be hashed).
        forced_role:  When provided, this role overrides role_rules resolution
                      on every login. Only the CLI should pass a value here;
                      the UI always leaves this None.
    """
    hashed = hash_password(plain_password)
    _db.execute(
        """
        INSERT INTO user_accounts (employee_id, password_hash, forced_role)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            password_hash = VALUES(password_hash),
            is_active     = TRUE,
            forced_role   = COALESCE(VALUES(forced_role), forced_role)
        """,
        (employee_id, hashed, forced_role),
        commit=True,
    )


def deactivate_account(employee_id: int) -> None:
    """Disable the user_account for *employee_id*."""
    _db.execute(
        "UPDATE user_accounts SET is_active = FALSE WHERE employee_id = %s",
        (employee_id,),
        commit=True,
    )


def change_password(employee_id: int, new_plain: str) -> None:
    """Replace the password for *employee_id*."""
    hashed = hash_password(new_plain)
    _db.execute(
        "UPDATE user_accounts SET password_hash = %s WHERE employee_id = %s",
        (hashed, employee_id),
        commit=True,
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _log_event(
    employee_id: int | None,
    event_type: str,
    description: str = "",
) -> None:
    """Insert a row into auth_audit_log. Silently swallows exceptions."""
    try:
        _db.execute(
            """
            INSERT INTO auth_audit_log (employee_id, event_type, description)
            VALUES (%s, %s, %s)
            """,
            (employee_id, event_type, description),
            commit=True,
        )
    except Exception:
        pass

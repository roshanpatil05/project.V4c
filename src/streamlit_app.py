from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to sys.path so 'src.*' imports work on Streamlit Cloud
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from datetime import date
import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import importlib
import src.managers as _managers_mod
importlib.reload(_managers_mod)

from src.managers import AnalyticsManager, EmployeeManager, ProjectManager, ReviewManager
from src.models import Employee, Project, Review
from src.config.settings import settings
from src.config.job_titles import DEPT_JOB_TITLES
from src.ui.theme import (
    COLORS,
    COLOURWAY,
    apply_theme,
    info_pill,
    kpi_card,
    page_header,
    score_band,
    section_title,
    status_badge,
    style_fig,
)
from src.auth.authenticator import require_auth, logout
import importlib
from src.auth import rbac
importlib.reload(rbac)
from src.validators import (
    validate_employee_form,
    validate_employee_salary_update,
    validate_project_form,
    validate_project_update_form,
    validate_review_form,
    validate_password_change,
)


apply_theme()

# ── Authentication gate ──────────────────────────────────────────────────────
# require_auth() renders the login page and calls st.stop() if not logged in.
# Once authenticated it returns the session auth dict.
_user = require_auth()

DATA_DIR = Path(__file__).resolve().parent / "data"
ALL_PAGES   = ["Overview", "Employee Management", "Project Management", "Performance Reviews", "Analytics Dashboard"]
PAGE_ICONS  = {"Overview": " ", "Employee Management": " ", "Project Management": " ", "Performance Reviews": " ", "Analytics Dashboard": " "}
# Filter pages down to what the current role can access
PAGES = rbac.allowed_pages(_user["role"], _user.get("department_name")) if _user else []

# @st.cache_data
def load_local_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    employees_path = DATA_DIR / "synthetic_employees.csv"
    history_path = DATA_DIR / "employee_scd2_history.csv"
    reviews_path = DATA_DIR / "synthetic_performance_reviews.csv"
    if not all(path.exists() for path in (employees_path, history_path, reviews_path)):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    employees = pd.read_csv(employees_path, parse_dates=["hire_date"])
    history = pd.read_csv(history_path, parse_dates=["start_date", "end_date"])
    reviews = pd.read_csv(reviews_path, parse_dates=["review_date"])
    return employees, history, reviews


def local_analytics(department_basis: str, department_name: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    employees, history, reviews = load_local_data()
    if employees.empty:
        trend = pd.DataFrame({"review_year": [2023, 2024, 2025], "avg_score": [82.4, 85.1, 87.6]})
        top = pd.DataFrame(
            {
                "employee_id": [101, 203, 156, 287],
                "first_name": ["Alicia", "Daniel", "Priya", "Morgan"],
                "last_name": ["Stone", "Nguyen", "Rao", "West"],
                "department_name": ["Engineering", "Sales", "Finance", "Operations"],
                "overall_score": [96, 94, 92, 91],
                "department_rank": [1, 1, 1, 1],
            }
        )
        risk = pd.DataFrame(
            {
                "department_name": ["Engineering", "Sales", "Finance", "Operations"],
                "employees": [1200, 980, 720, 640],
                "avg_performance": [88, 80, 86, 82],
                "avg_attrition_risk": [24, 38, 29, 34],
            }
        )
        bottlenecks = pd.DataFrame(
            {
                "project_id": [1, 2],
                "project_name": ["Project Alpha", "Project Beta"],
                "department_name": ["Engineering", "Sales"],
                "budget": [100000, 50000],
                "assigned_employees": [1, 2],
                "total_allocation_pct": [50, 150],
            }
        )
        if department_name and department_name != "All departments":
            top = top[top["department_name"] == department_name]
            risk = risk[risk["department_name"] == department_name]
            bottlenecks = bottlenecks[bottlenecks["department_name"] == department_name]
        return trend, top, risk, bottlenecks

    if department_basis == "review":
        department_versions = history[["employee_id", "department_name", "start_date", "end_date"]]
        review_rows = reviews.merge(department_versions, on="employee_id", how="inner")
        review_rows = review_rows[
            (review_rows["review_date"] >= review_rows["start_date"])
            & (review_rows["end_date"].isna() | (review_rows["review_date"] < review_rows["end_date"]))
        ]
    else:
        current = history.loc[history["is_current"].astype(bool), ["employee_id", "department_name"]]
        review_rows = reviews.merge(current, on="employee_id", how="inner")

    identity = employees[["employee_id", "first_name", "last_name"]]
    review_rows = review_rows.merge(identity, on="employee_id", how="left", validate="many_to_one")
    
    if department_name and department_name != "All departments":
        review_rows = review_rows[review_rows["department_name"] == department_name]
    trend = (
        review_rows.assign(review_year=review_rows["review_date"].dt.year)
        .groupby("review_year", as_index=False)["overall_score"]
        .mean()
        .rename(columns={"overall_score": "avg_score"})
    )
    top = (
        review_rows.groupby(["employee_id", "first_name", "last_name", "department_name"], as_index=False)["overall_score"]
        .mean()
    )
    top["department_rank"] = top.groupby("department_name")["overall_score"].rank(method="dense", ascending=False)
    top = top[top["department_rank"] <= 5].sort_values(["department_name", "department_rank"])

    current_history = history[history["is_current"].astype(bool)]
    if department_name and department_name != "All departments":
        current_history = current_history[current_history["department_name"] == department_name]
        
    risk = (
        current_history.groupby("department_name", as_index=False)
        .agg(
            employees=("employee_id", "count"),
            avg_performance=("performance_score", "mean"),
            avg_attrition_risk=("attrition_risk", "mean"),
        )
        .sort_values("avg_attrition_risk", ascending=False)
    )
    bottlenecks = pd.DataFrame() # Local CSVs don't have projects yet
    return trend, top, risk, bottlenecks


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """Convert a pandas DataFrame into an in-memory Excel XLSX byte array."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


def get_department_choices() -> list[dict]:
    try:
        return EmployeeManager().list_departments()
    except Exception:
        return []


def get_job_titles_for_department(dept_name: str, dept_id: int | None = None) -> list[str]:
    """Return strictly the curated job titles for the given department."""
    if not dept_name:
        return ["Employee"]
    if dept_name in DEPT_JOB_TITLES:
        return list(DEPT_JOB_TITLES[dept_name])
    for k, v in DEPT_JOB_TITLES.items():
        if k.strip().lower() == dept_name.strip().lower():
            return list(v)
    return ["Employee"]


def render_form_message(message: str, success: bool) -> None:
    if success:
        st.success(message)
    else:
        st.error(message)

def render_department_field(departments: list[dict], key: str = "department") -> int:
    if departments:
        choices = {row["department_name"]: row["department_id"] for row in departments}
        selected = st.selectbox("Department", list(choices), key=key)
        return int(choices[selected])
    st.caption("Use the department ID when the warehouse is unavailable.")
    return int(st.number_input("Department ID", min_value=1, step=1, key=f"{key}_id"))


def render_overview() -> None:
    page_header("Enterprise Employee <span class='gradient-text'>Analytics</span>", "People, performance, and project allocation")
    section_title("Workforce overview")
    
    warehouse_connected = bool(get_department_choices())
    
    # Try fetching from MySQL first
    if warehouse_connected:
        try:
            metrics = AnalyticsManager().get_overview_metrics()
            total_employees = metrics["total_employees"]
            departments = metrics["total_departments"]
            average_score = f"{metrics['average_score']:.1f}"
            counts = pd.DataFrame(metrics["distribution"])
        except Exception:
            warehouse_connected = False

    # Fallback to CSV if MySQL is unreachable or failed
    if not warehouse_connected:
        employees, _, reviews = load_local_data()
        departments = int(employees["department_name"].nunique()) if not employees.empty else 8
        average_score = f"{reviews['overall_score'].mean():.1f}" if not reviews.empty else "--"
        total_employees = len(employees) if not employees.empty else 100_000
        counts = employees.groupby("department_name", as_index=False).size().sort_values("size", ascending=True) if not employees.empty else pd.DataFrame()
        info_pill("Showing local synthetic data for the overview page (MySQL connection failed)")

    is_local_db = settings.host in ("127.0.0.1", "localhost")
    if warehouse_connected:
        db_label = "Local MySQL" if is_local_db else "Cloud MySQL"
        badge_text = f"Connected to Local MySQL ({settings.database})" if is_local_db else "Connected to Cloud MySQL"
    else:
        db_label = "Local preview"
        badge_text = "Local preview (CSV offline mode)"

    kpis = st.columns(4)
    with kpis[0]:
        kpi_card("Total employees", f"{total_employees:,}", icon="♙")
    with kpis[1]:
        kpi_card("Departments", departments, icon="⌘")
    with kpis[2]:
        kpi_card("Data source", db_label, icon="◉")
    with kpis[3]:
        kpi_card("Average review score", average_score, icon="✦")
        
    st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
    status_badge(badge_text, "success" if warehouse_connected else "warning")
    
    if not counts.empty:
        fig = px.bar(
            counts,
            x="size",
            y="department_name",
            orientation="h",
            text="size",
            color="size",
            color_continuous_scale=[[0, COLORS["bg_purple"]], [.55, COLORS["magenta"]], [1, COLORS["pink"]]],
            labels={"size": "Employees", "department_name": "Department"},
            title="Employees by department",
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", hovertemplate="%{y}: %{x:,}<extra></extra>")
        fig.update_layout(coloraxis_showscale=False, xaxis_title="Employees", yaxis_title="Department")
        with st.container(border=True):
            section_title("Workforce distribution")
            st.plotly_chart(style_fig(fig, 410), use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Generate the included sample data with `python -m src.ETL.synthesizer` to preview workforce metrics.")


def render_employees() -> None:
    page_header("Employee <span class='gradient-text'>management</span>", "Create and manage workforce records")
    departments = get_department_choices()

    # Department Managers only see their own department in the dropdown
    dept_scope = rbac.scoped_department_id(_user)
    if dept_scope is not None:
        departments = [d for d in departments if d["department_id"] == dept_scope]

    # Feature 5: One-click Workforce Roster Excel Export
    if rbac.can_export_workforce(_user):
        can_sal = rbac.can_export_salary(_user)
        try:
            emp_export_data = EmployeeManager().get_employees_export(department_id=dept_scope, include_salary=can_sal)
            if emp_export_data:
                emp_df = pd.DataFrame(emp_export_data)
                excel_data = to_excel_bytes(emp_df, sheet_name="Workforce Roster")
                scope_tag = _user.get("department_name", "department") if dept_scope else "full_roster"
                fn = f"workforce_roster_{scope_tag.lower().replace(' ', '_')}_{date.today()}.xlsx"
                sal_note = "includes verified compensation" if can_sal else "confidential compensation excluded"

                exp_col1, exp_col2 = st.columns([3, 1.3])
                with exp_col2:
                    st.download_button(
                        label="📊 Export Workforce Roster (Excel)",
                        data=excel_data,
                        file_name=fn,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_workforce_roster",
                        use_container_width=True,
                        help=f"Download employee roster in Excel (.xlsx) format ({sal_note})",
                    )
        except Exception as exc:
            st.caption(f"Workforce export unavailable: {exc}")

    create_tab, manage_tab = st.tabs(["Onboard employee", "Manage employee"])
    
    with create_tab:
        with st.container(border=True):
            section_title("New employee profile")
            # ── Department selection buttons (OUTSIDE form so job titles update reactively) ──
            dept_choices = {row["department_name"]: row["department_id"] for row in departments}
            dept_names = list(dept_choices.keys()) if dept_choices else []

            st.markdown("**Department:** Select department using the buttons below:")
            selected_pill = st.pills(
                "Department",
                options=dept_names,
                default=dept_names[0] if dept_names else None,
                key="onboard_dept_pills",
                label_visibility="collapsed",
            )
            # Ensure deselecting doesn't leave the department empty
            if not selected_pill and dept_names:
                selected_dept_name = dept_names[0]
            else:
                selected_dept_name = selected_pill or (dept_names[0] if dept_names else "")

            department_id = int(dept_choices[selected_dept_name]) if (dept_choices and selected_dept_name in dept_choices) else 0
            dept_titles = get_job_titles_for_department(selected_dept_name, department_id)

            st.markdown(
                f"<div style='margin-bottom: 0.85rem; padding: 0.45rem 0.85rem; background: rgba(232, 124, 247, 0.08); "
                f"border-left: 3px solid #E87CF7; border-radius: 6px; font-size: 0.88rem; color: #E2E8F0;'>"
                f"🏢 Selected Department: <b>{selected_dept_name}</b> &nbsp;|&nbsp; "
                f"Showing only <b>{len(dept_titles)}</b> {selected_dept_name} roles in dropdown below"
                f"</div>",
                unsafe_allow_html=True,
            )

            with st.form("employee_form"):
                first_col, last_col = st.columns(2)
                with first_col:
                    first_name = st.text_input("First name")
                    email = st.text_input("Work email")
                with last_col:
                    last_name = st.text_input("Last name")
                    job_title = st.selectbox(
                        f"Job title ({selected_dept_name})",
                        dept_titles,
                        key=f"onboard_title_{selected_dept_name}",
                        help=f"Select an official {selected_dept_name} role",
                    )
                salary_col, _ = st.columns([1, 1])
                with salary_col:
                    salary = st.number_input("Annual salary (₹)", min_value=1_000.0, step=1_000.0, format="%.2f")
                st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
                pwd_col1, pwd_col2 = st.columns(2)
                with pwd_col1:
                    initial_password = st.text_input(
                        "Initial login password",
                        type="password",
                        placeholder="Min 8 characters",
                        help="HR sets this. The employee can change it after first login.",
                    )
                with pwd_col2:
                    confirm_password = st.text_input(
                        "Confirm password",
                        type="password",
                        placeholder="Repeat password",
                    )
                st.caption("Employee details are validated before they are written to OLTP and the current warehouse dimension.")
                submitted = st.form_submit_button("Add employee", type="primary", use_container_width=True)
        if submitted:
            errors = validate_employee_form(
                first_name, last_name, email, job_title,
                float(salary), department_id,
                initial_password, confirm_password,
            )
            if errors:
                for err in errors:
                    st.error(err)
            else:
                employee = Employee(first_name=first_name, last_name=last_name, email=email, department_id=department_id, job_title=job_title, salary=float(salary))
                try:
                    employee_id = EmployeeManager().create_employee(employee)
                    # Auto-create login account with the password HR entered
                    from src.auth.authenticator import create_account
                    create_account(employee_id, initial_password)
                    st.success(
                        f"✅ Employee **{first_name} {last_name}** (ID: {employee_id}) onboarded.  \n\n"
                        f"**Login email:** `{email}`  \n"
                        f"**Temporary password:** `{initial_password}`  \n\n"
                        "Share these credentials with the employee — ask them to change the password on first login."
                    )
                except Exception as exc:
                    render_form_message(f"Employee could not be added: {exc}", False)
                
    with manage_tab:
        with st.container(border=True):
            section_title("Find employee")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_id = st.number_input("Employee ID", min_value=1, step=1, key="search_emp_id")
                search_btn = st.button("Search")
        
        if search_btn:
            try:
                emp = EmployeeManager().get_employee(search_id)
                if emp:
                    st.session_state["selected_employee"] = emp
                else:
                    st.session_state.pop("selected_employee", None)
                    st.error("Employee not found.")
            except Exception as exc:
                 st.error(f"Error fetching employee: {exc}")
                 
        if "selected_employee" in st.session_state:
            emp = st.session_state["selected_employee"]

            # Dept Managers can only look up employees from their own department
            if _user["role"] == "Department Manager" and emp["department_id"] != _user["department_id"]:
                st.error(
                    f"Access denied — you can only view employees in your department ({_user['department_name']})."
                )
                st.session_state.pop("selected_employee", None)
            else:
                if emp.get("status") == "inactive":
                    st.warning("This employee record is marked as inactive.")

                # ── Determine edit capabilities ───────────────────────────────
                _can_sal      = rbac.can_edit_salary(_user)
                _can_dept_rol = rbac.can_edit_dept_and_role(_user)

                # Resolve dept name for job title list
                all_depts_full = get_department_choices()
                emp_dept_name = next(
                    (d["department_name"] for d in all_depts_full if d["department_id"] == emp["department_id"]),
                    None,
                )

                with st.container(border=True):
                    section_title(f"{emp['first_name']} {emp['last_name']}")

                    # Always-visible read-only summary
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.write(f"**Employee ID:** {emp['employee_id']}")
                        st.write(f"**Email:** {emp['email']}")
                        st.write(f"**Department:** {emp_dept_name or emp['department_id']}")
                    with info_col2:
                        st.write(f"**Job Title:** {emp['job_title']}")
                        st.write(f"**Salary:** ₹{float(emp['salary']):,.2f}")
                        st.write(f"**Status:** {emp['status']}")

                    if not _can_sal and not _can_dept_rol:
                        st.info("ℹ️ You have view-only access to this employee's record.")

                # ── HR section: Department + Job Title ────────────────────────
                if _can_dept_rol:
                    with st.container(border=True):
                        section_title("Update department & role")
                        dept_names_full = [d["department_name"] for d in all_depts_full]
                        dept_ids_full   = [d["department_id"]   for d in all_depts_full]
                        try:
                            dept_idx = dept_ids_full.index(emp["department_id"])
                        except ValueError:
                            dept_idx = 0

                        # Dynamic department buttons so changing department immediately updates job titles
                        st.markdown("**Department:** Select department using the buttons below:")
                        cur_dept_name = dept_names_full[dept_idx] if (dept_names_full and 0 <= dept_idx < len(dept_names_full)) else None
                        chosen_upd_dept = st.pills(
                            "Update Department",
                            options=dept_names_full,
                            default=cur_dept_name,
                            key=f"hr_upd_dept_pills_{emp['employee_id']}",
                            label_visibility="collapsed",
                        )
                        if not chosen_upd_dept and dept_names_full:
                            chosen_upd_dept = cur_dept_name or dept_names_full[0]
                        new_dept_name = chosen_upd_dept
                        new_dept_id = dept_ids_full[dept_names_full.index(new_dept_name)]

                        titles_for_new_dept = get_job_titles_for_department(new_dept_name, new_dept_id)
                        cur_title = emp["job_title"]
                        t_idx = titles_for_new_dept.index(cur_title) if cur_title in titles_for_new_dept else 0
                        new_job_title = st.selectbox(
                            f"Job title ({new_dept_name})",
                            titles_for_new_dept,
                            index=t_idx,
                            key=f"hr_upd_title_{emp['employee_id']}_{new_dept_name}",
                            help=f"Select an official {new_dept_name} role",
                        )

                        st.caption("Changing department or job title triggers an SCD2 warehouse update.")
                        hr_upd_btn = st.button(
                            "Save department & role",
                            type="primary",
                            use_container_width=True,
                            key=f"hr_upd_btn_{emp['employee_id']}",
                        )

                        if hr_upd_btn:
                            try:
                                mgr = EmployeeManager()
                                dept_changed = int(new_dept_id) != int(emp["department_id"])
                                title_changed = new_job_title != emp["job_title"]

                                if dept_changed or title_changed:
                                    mgr.update_department_and_role(
                                        emp["employee_id"],
                                        int(new_dept_id),
                                        new_job_title,
                                    )
                                    st.success("Department / role updated. (SCD2 applied)")
                                    st.session_state["selected_employee"] = mgr.get_employee(emp["employee_id"])
                                    st.rerun()
                                else:
                                    st.info("No changes to save.")
                            except Exception as exc:
                                st.error(f"Failed to update: {exc}")

                # ── Finance / HR section: Salary ──────────────────────────────
                if _can_sal:
                    with st.container(border=True):
                        section_title("Update salary")
                        with st.form("update_salary_form"):
                            new_salary = st.number_input(
                                "Annual salary (₹)",
                                min_value=1_000.0,
                                value=float(emp["salary"]),
                                step=1_000.0,
                                format="%.2f",
                                key="fin_upd_sal",
                            )
                            st.caption("Max 2× hike enforced. Changes trigger an SCD2 warehouse update.")
                            sal_upd_btn = st.form_submit_button("Save salary", type="primary", use_container_width=True)

                        if sal_upd_btn:
                            errors: list[str] = validate_employee_salary_update(float(emp["salary"]), float(new_salary))
                            if errors:
                                for err in errors:
                                    st.error(err)
                            elif float(new_salary) == float(emp["salary"]):
                                st.info("No change to salary.")
                            else:
                                try:
                                    EmployeeManager().update_salary(emp["employee_id"], float(new_salary))
                                    st.success("Salary updated. (SCD2 applied)")
                                    st.session_state["selected_employee"] = EmployeeManager().get_employee(emp["employee_id"])
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Failed to update salary: {exc}")

                # ── Deactivate (Super Admin + HR Admin only) ──────────────────
                if rbac.can(_user["role"], "employee.deactivate"):
                    with st.container(border=True):
                        section_title("Deactivate employee")
                        st.warning(
                            "This marks the employee as inactive. It does not permanently delete "
                            "the employee, performance reviews, project assignments, or historical versions."
                        )
                        confirm_deactivation = st.checkbox(
                            f"I confirm that I want to deactivate {emp['first_name']} "
                            f"{emp['last_name']} (ID: {emp['employee_id']}).",
                            key=f"confirm_deactivate_{emp['employee_id']}",
                        )
                        if st.button(
                            "Deactivate employee",
                            type="primary",
                            key=f"deactivate_employee_{emp['employee_id']}",
                            disabled=not confirm_deactivation,
                            use_container_width=True,
                        ):
                            try:
                                EmployeeManager().delete_employee(emp["employee_id"])
                                st.success(
                                    f"{emp['first_name']} {emp['last_name']} has been deactivated. "
                                    "Historical records have been preserved."
                                )
                                st.session_state.pop("selected_employee", None)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed to deactivate employee: {exc}")

            


def render_my_assigned_projects_section(employee_id: int, employee_name: str) -> None:
    section_title(f"Project assignments: {employee_name}")
    try:
        assignments = ProjectManager().get_employee_assignments(employee_id)
    except Exception as exc:
        st.error(f"Error retrieving project assignments: {exc}")
        return

    if not assignments:
        st.info(f"ℹ️ Welcome, **{employee_name}**. You are currently not assigned to any project initiatives. As soon as your manager allocates you, details will appear here.")
        return

    total_alloc = sum(float(a.get("allocation_pct", 0)) for a in assignments)
    active_cnt = len([a for a in assignments if str(a.get("status", "")).lower() == "active"])

    mcol1, mcol2, mcol3 = st.columns(3)
    with mcol1:
        kpi_card("Assigned Initiatives", len(assignments), f"{active_cnt} active initiatives")
    with mcol2:
        alloc_status = "Fully allocated (100%)" if total_alloc == 100 else (f"{total_alloc:.0f}% allocated")
        kpi_card("My Total Allocation", f"{total_alloc:.0f}%", alloc_status)
    with mcol3:
        latest_date = assignments[0].get("assigned_date", "N/A")
        kpi_card("Latest Assignment", str(latest_date), "Active allocation")

    # ── Personal Schedule Timeline (for Employee / Assignee) ────────────────
    valid_dates = [a for a in assignments if a.get("start_date") and a.get("end_date")]
    if valid_dates:
        with st.expander("My Initiative Delivery Schedule", expanded=True):
            my_df = pd.DataFrame(valid_dates)
            my_df["start_date"] = pd.to_datetime(my_df["start_date"])
            my_df["end_date"] = pd.to_datetime(my_df["end_date"])
            fig_my = px.timeline(
                my_df,
                x_start="start_date",
                x_end="end_date",
                y="project_name",
                color="status",
                color_discrete_map={"active": "#71e6aa", "planned": "#f8c76a", "completed": "#C9A7E8", "on_hold": "#B93A96"},
                hover_name="project_name",
                hover_data={"allocation_pct": ":.0f", "department_name": True, "start_date": "|%b %d, %Y", "end_date": "|%b %d, %Y"},
            )
            fig_my.update_yaxes(autorange="reversed", title="")
            fig_my.update_xaxes(title="Initiative Schedule")
            st.plotly_chart(style_fig(fig_my, height=max(200, len(my_df) * 45 + 70)), use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height: .6rem'></div>", unsafe_allow_html=True)
    section_title("Assigned projects")

    for a in assignments:
        st_val = str(a.get("status", "active")).lower()
        status_color = "#71e6aa" if st_val == "active" else ("#f8c76a" if st_val == "planned" else "#E87CF7")
        budget_str = f"₹{float(a['budget']):,.2f}" if a.get("budget") is not None else "N/A"
        alloc_val = float(a.get("allocation_pct", 100))

        with st.container(border=True):
            col_main, col_badge = st.columns([3, 1])
            with col_main:
                st.markdown(f"### {a['project_name']} `#{a['project_id']}`")
                st.markdown(
                    f"🏢 **Department:** {a.get('department_name', 'General')} &nbsp;|&nbsp; "
                    f"**Status:** <span style='color: {status_color}; font-weight: 700;'>{st_val.upper()}</span> &nbsp;|&nbsp; "
                    f"**Assigned Date:** {a.get('assigned_date', 'N/A')} &nbsp;|&nbsp; "
                    f"**Budget:** {budget_str}",
                    unsafe_allow_html=True,
                )
            with col_badge:
                st.markdown(
                    f"<div style='text-align: right; padding-top: 0.5rem;'>"
                    f"<span style='background: linear-gradient(90deg, rgba(232, 124, 247, 0.25), rgba(185, 58, 150, 0.3)); "
                    f"border: 1px solid #E87CF7; padding: 0.45rem 0.9rem; border-radius: 20px; font-weight: 700; color: #FFFFFF; font-size: 0.95rem;'>"
                    f"⚡ {alloc_val:.0f}% Allocation</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def generate_printable_appraisal_html(
    rev: dict,
    emp_name: str,
    emp_id: int,
    dept: str,
    title: str,
    mgr_name: str,
    mgr_title: str,
) -> str:
    """Generate executive-grade printable HTML appraisal letter / scorecard."""
    score = float(rev.get("overall_score", 80.0))
    rating = rev.get("rating", "Meets Expectations")
    r_date = str(rev.get("review_date", date.today()))
    comments = rev.get("comments") or "Consistent performance demonstrated throughout the evaluation cycle."
    rev_id = rev.get("review_id", 1001)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Official Performance Appraisal - {emp_name} ({r_date})</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:wght@700&display=swap');
        * {{ box-sizing: border-box; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            margin: 0;
            padding: 24px;
            font-size: 14px;
            line-height: 1.5;
        }}
        .print-btn-bar {{
            max-width: 800px;
            margin: 0 auto 20px auto;
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }}
        .btn {{
            background: #2563eb;
            color: white;
            border: none;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
        }}
        .btn:hover {{ background: #1d4ed8; }}
        .sheet {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 44px 48px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
            position: relative;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #0f172a;
            padding-bottom: 20px;
            margin-bottom: 28px;
        }}
        .corp-brand {{
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #64748b;
        }}
        .doc-title {{
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
            margin: 4px 0 0 0;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px 28px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 18px 22px;
            margin-bottom: 28px;
        }}
        .meta-item {{ display: flex; flex-direction: column; }}
        .meta-label {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: #64748b;
        }}
        .meta-val {{
            font-size: 14px;
            font-weight: 600;
            color: #0f172a;
            margin-top: 2px;
        }}
        .score-card {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: white;
            border-radius: 10px;
            padding: 20px 28px;
            margin-bottom: 28px;
        }}
        .score-num {{
            font-size: 38px;
            font-weight: 800;
            color: #38bdf8;
            line-height: 1;
        }}
        .score-rating {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.18);
            border: 1px solid rgba(56, 189, 248, 0.4);
            color: #38bdf8;
            font-weight: 700;
            font-size: 13px;
            padding: 4px 14px;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-top: 6px;
        }}
        .section-h {{
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #0f172a;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 6px;
            margin: 24px 0 12px 0;
        }}
        .comments-box {{
            background: #fff;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #2563eb;
            border-radius: 6px;
            padding: 16px 20px;
            font-size: 13.5px;
            color: #334155;
            line-height: 1.6;
            margin-bottom: 28px;
        }}
        .signatures {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 56px;
            padding-top: 14px;
        }}
        .sig-block {{
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }}
        .sig-line {{
            width: 100%;
            border-bottom: 1px solid #94a3b8;
            height: 32px;
            margin-bottom: 6px;
        }}
        .sig-title {{ font-size: 12px; font-weight: 700; color: #0f172a; }}
        .sig-sub {{ font-size: 11px; color: #64748b; }}
        @media print {{
            body {{ background: white; padding: 0; }}
            .print-btn-bar {{ display: none; }}
            .sheet {{ border: none; box-shadow: none; padding: 12px 0; max-width: 100%; }}
        }}
    </style>
</head>
<body>
    <div class="print-btn-bar">
        <button class="btn" onclick="window.print()">🖨️ Print or Save as PDF</button>
    </div>
    <div class="sheet">
        <div class="header">
            <div>
                <div class="corp-brand">Enterprise Workforce Platform</div>
                <h1 class="doc-title">Official Performance Appraisal</h1>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 11px; color: #64748b;">Document Ref</div>
                <div style="font-weight: 700; font-family: monospace;">APP-2026-{rev_id}</div>
                <div style="font-size: 11px; color: #16a34a; font-weight: 600; margin-top: 4px;">● VERIFIED APPRAISAL</div>
            </div>
        </div>

        <div class="meta-grid">
            <div class="meta-item"><span class="meta-label">Employee Name</span><span class="meta-val">{emp_name}</span></div>
            <div class="meta-item"><span class="meta-label">Employee ID</span><span class="meta-val">#{emp_id}</span></div>
            <div class="meta-item"><span class="meta-label">Department</span><span class="meta-val">{dept}</span></div>
            <div class="meta-item"><span class="meta-label">Job Title</span><span class="meta-val">{title}</span></div>
            <div class="meta-item"><span class="meta-label">Evaluation Date</span><span class="meta-val">{r_date}</span></div>
            <div class="meta-item"><span class="meta-label">Reviewing Official</span><span class="meta-val">{mgr_name} ({mgr_title})</span></div>
        </div>

        <div class="score-card">
            <div>
                <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #94a3b8; font-weight: 700;">Overall Evaluation Result</div>
                <div class="score-rating">{rating}</div>
            </div>
            <div style="text-align: right;">
                <div class="score-num">{score:.1f}<span style="font-size: 18px; color: #64748b;">/100</span></div>
            </div>
        </div>

        <div class="section-h">Evaluator Qualitative Assessment & Recommendations</div>
        <div class="comments-box">
            {comments}
        </div>

        <div class="signatures">
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-title">{mgr_name}</div>
                <div class="sig-sub">Reviewing Official</div>
            </div>
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-title">Corporate HR Division</div>
                <div class="sig-sub">People & Talent Director</div>
            </div>
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-title">{emp_name}</div>
                <div class="sig-sub">Employee Acknowledgment</div>
            </div>
        </div>
    </div>
</body>
</html>"""
    return html


def generate_appraisal_excel_bytes(
    rev: dict,
    emp_name: str,
    emp_id: int,
    dept: str,
    title: str,
    mgr_name: str,
    mgr_title: str,
) -> bytes:
    """Generate structured multi-tab employee performance appraisal in Excel XLSX format."""
    score = float(rev.get("overall_score", 80.0))
    rating = rev.get("rating", "Meets Expectations")
    r_date = str(rev.get("review_date", date.today()))
    comments = rev.get("comments") or "Consistent performance demonstrated throughout the evaluation cycle."
    rev_id = rev.get("review_id", 1001)

    summary_data = [
        {"Attribute": "Document ID", "Value": f"APP-2026-{rev_id}"},
        {"Attribute": "Evaluation Date", "Value": r_date},
        {"Attribute": "Employee ID", "Value": emp_id},
        {"Attribute": "Employee Name", "Value": emp_name},
        {"Attribute": "Department", "Value": dept},
        {"Attribute": "Job Title", "Value": title},
        {"Attribute": "Reviewing Official", "Value": f"{mgr_name} ({mgr_title})"},
        {"Attribute": "Overall Score", "Value": f"{score:.1f} / 100"},
        {"Attribute": "Performance Rating", "Value": rating},
        {"Attribute": "Evaluator Comments", "Value": comments},
        {"Attribute": "Verification Status", "Value": "VERIFIED OFFICIAL RECORD"},
    ]

    competency_data = [
        {"Competency Dimension": "Technical & Domain Execution", "Weight": "35%", "Rating": rating, "Remarks": "Consistently delivers high-standard project milestones."},
        {"Competency Dimension": "Cross-Functional Collaboration", "Weight": "30%", "Rating": rating, "Remarks": "Engages proactively with stakeholders and team members."},
        {"Competency Dimension": "Initiative & Operational Ownership", "Weight": "20%", "Rating": rating, "Remarks": "Identifies improvements and resolves roadblocks independently."},
        {"Competency Dimension": "Continuous Growth & Leadership", "Weight": "15%", "Rating": rating, "Remarks": "Shares domain knowledge and supports peer onboarding."},
    ]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Appraisal Summary")
        pd.DataFrame(competency_data).to_excel(writer, index=False, sheet_name="Competencies")
    return output.getvalue()


def render_timeline_and_burn_section(user_auth: dict) -> None:
    """Render interactive Gantt schedule and dynamic staffing budget burn-down."""
    section_title("Project Portfolio Timeline & Budget Burn-Down")

    role = user_auth.get("role", "")
    user_dept_id = user_auth.get("department_id")
    user_dept_name = user_auth.get("department_name", "General")
    is_global = role in ("Super Admin", "Analyst") or user_dept_name == "Operations"

    col_scope, col_status, col_search = st.columns([1.5, 2, 1.5])

    with col_scope:
        if is_global:
            all_depts = get_department_choices()
            dept_map = {"All Departments": None}
            dept_map.update({d["department_name"]: d["department_id"] for d in all_depts})
            selected_dept_label = st.selectbox("Department Scope", list(dept_map.keys()), key="gantt_dept_sel")
            filter_dept_id = dept_map[selected_dept_label]
        else:
            filter_dept_id = user_dept_id
            st.markdown(
                f"<div style='margin-top: 1.7rem; padding: 0.5rem 0.85rem; background: rgba(232, 124, 247, 0.08); "
                f"border-left: 3px solid #E87CF7; border-radius: 6px; font-size: 0.88rem; color: #E2E8F0;'>"
                f"🏢 Scoped to <b>{user_dept_name}</b>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with col_status:
        status_filter = st.multiselect(
            "Project Status",
            options=["active", "planned", "completed", "on_hold"],
            default=["active", "planned"],
            key="gantt_status_filter",
        )

    with col_search:
        search_query = st.text_input("Search Initiative", placeholder="Filter by initiative name...", key="gantt_search")

    try:
        raw_data = ProjectManager().get_projects_timeline(department_id=filter_dept_id, limit=500)
    except Exception as exc:
        st.error(f"Error fetching portfolio timeline: {exc}")
        return

    if not raw_data:
        st.info("No initiatives found matching the active department scope.")
        return

    df = pd.DataFrame(raw_data)

    if status_filter:
        df = df[df["status"].isin(status_filter)]
    if search_query.strip():
        df = df[df["project_name"].str.lower().str.contains(search_query.strip().lower(), na=False)]

    if df.empty:
        st.info("No initiatives match the active filters.")
        return

    df["budget"] = df["budget"].astype(float)
    df["staff_count"] = df["staff_count"].astype(int)
    df["total_allocation_pct"] = df["total_allocation_pct"].astype(float)
    df["annual_staffing_burn"] = df["annual_staffing_burn"].astype(float)
    df["monthly_staffing_burn"] = df["monthly_staffing_burn"].astype(float)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])

    # KPI Summary Cards
    total_projs = len(df)
    total_budget = df["budget"].sum()
    total_monthly_burn = df["monthly_staffing_burn"].sum()
    total_annual_burn = df["annual_staffing_burn"].sum()
    total_headcount = df["staff_count"].sum()

    kcol1, kcol2, kcol3, kcol4 = st.columns(4)
    with kcol1:
        kpi_card("Active Initiatives", total_projs, f"{len(df[df['status'] == 'active'])} active / {len(df[df['status'] == 'planned'])} planned")
    with kcol2:
        kpi_card("Portfolio Budget", f"₹{total_budget:,.0f}", "Approved initiative capital")
    with kcol3:
        kpi_card("Monthly Staff Burn", f"₹{total_monthly_burn:,.0f}", f"Annualized: ₹{total_annual_burn:,.0f}")
    with kcol4:
        kpi_card("Assigned Headcount", f"{total_headcount:,}", "Total employee allocations")

    st.markdown("<div style='height: .8rem'></div>", unsafe_allow_html=True)

    # Plotly Gantt Chart
    st.markdown("#### Schedule & Delivery Roadmaps")
    gantt_df = df.sort_values(by=["start_date", "project_name"], ascending=[True, True]).head(45).copy()

    color_map = {
        "active": "#71e6aa",
        "planned": "#f8c76a",
        "completed": "#C9A7E8",
        "on_hold": "#B93A96",
    }

    fig_gantt = px.timeline(
        gantt_df,
        x_start="start_date",
        x_end="end_date",
        y="project_name",
        color="status",
        color_discrete_map=color_map,
        hover_name="project_name",
        hover_data={
            "department_name": True,
            "status": True,
            "budget": ":,.2f",
            "staff_count": True,
            "monthly_staffing_burn": ":,.2f",
            "start_date": "|%b %d, %Y",
            "end_date": "|%b %d, %Y",
        },
    )
    chart_h = max(380, min(800, len(gantt_df) * 26 + 90))
    fig_gantt.update_yaxes(autorange="reversed", title="")
    fig_gantt.update_xaxes(title="Project Horizon (2025 – 2027)")
    st.plotly_chart(style_fig(fig_gantt, height=chart_h), use_container_width=True, config={"displayModeBar": False})

    if len(df) > 45:
        st.caption(f"Displaying top 45 initiatives in Gantt timeline for optimal visibility ({len(df)} total initiatives match filters).")

    # Export Toolbar & Initiatives Table
    st.markdown("<div style='height: .6rem'></div>", unsafe_allow_html=True)
    st.markdown("#### Detailed Initiative Breakdown & Data Export")

    exp_col1, exp_col2 = st.columns([1, 1])
    with exp_col1:
        timeline_excel = to_excel_bytes(df, sheet_name="Portfolio Timeline")
        st.download_button(
            label="📊 Export Portfolio Timeline & Burn (Excel)",
            data=timeline_excel,
            file_name=f"portfolio_timeline_burn_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_timeline_excel",
            use_container_width=True,
            help="Download filtered project timeline and staffing burn metrics in Excel (.xlsx)",
        )
    with exp_col2:
        if rbac.can_export_projects(user_auth):
            try:
                matrix_data = ProjectManager().get_staffing_allocation_matrix(department_id=filter_dept_id)
                if matrix_data:
                    m_df = pd.DataFrame(matrix_data)
                    matrix_excel = to_excel_bytes(m_df, sheet_name="Staffing Matrix")
                    st.download_button(
                        label="📊 Export Complete Staffing Allocation Matrix (Excel)",
                        data=matrix_excel,
                        file_name=f"staffing_allocation_matrix_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_matrix_excel",
                        use_container_width=True,
                        help="Export every employee-to-project allocation percentage and date in Excel (.xlsx)",
                    )
            except Exception as exc:
                st.caption(f"Staffing matrix export error: {exc}")

    display_df = df[[
        "project_id", "project_name", "department_name", "status", "budget",
        "staff_count", "total_allocation_pct", "monthly_staffing_burn", "annual_staffing_burn",
        "start_date", "end_date"
    ]].copy()
    display_df["start_date"] = display_df["start_date"].dt.strftime("%Y-%m-%d")
    display_df["end_date"] = display_df["end_date"].dt.strftime("%Y-%m-%d")
    display_df["budget"] = display_df["budget"].apply(lambda v: f"₹{v:,.2f}")
    display_df["monthly_staffing_burn"] = display_df["monthly_staffing_burn"].apply(lambda v: f"₹{v:,.2f}")
    display_df["annual_staffing_burn"] = display_df["annual_staffing_burn"].apply(lambda v: f"₹{v:,.2f}")
    display_df["total_allocation_pct"] = display_df["total_allocation_pct"].apply(lambda v: f"{v:.0f}%")

    st.dataframe(
        display_df,
        column_config={
            "project_id": "ID",
            "project_name": "Project Name",
            "department_name": "Department",
            "status": "Status",
            "budget": "Budget (₹)",
            "staff_count": "Staff Headcount",
            "total_allocation_pct": "Total Alloc %",
            "monthly_staffing_burn": "Monthly Burn (₹)",
            "annual_staffing_burn": "Annual Burn (₹)",
            "start_date": "Start Date",
            "end_date": "End Date",
        },
        use_container_width=True,
        hide_index=True,
    )


def render_projects() -> None:
    page_header("Project <span class='gradient-text'>management</span>", "Create initiatives and balance employee allocations")
    departments = get_department_choices()

    # Determine cross-department capabilities (Super Admin and Operations can create & staff cross-departmentally)
    can_cross_proj = rbac.can_create_cross_department_projects(_user)
    can_cross_assign = rbac.can_assign_cross_department(_user)

    if not can_cross_proj:
        dept_scope = rbac.scoped_department_id(_user)
        if dept_scope is not None:
            departments = [d for d in departments if d["department_id"] == dept_scope]

    # Analysts and Employees see their assigned projects and can explore initiatives
    _can_edit_proj = rbac.can_manage_projects(_user)

    if not _can_edit_proj:
        if rbac.can_view_timeline(_user):
            timeline_tab, my_tab, explore_tab = st.tabs(["Timeline & Budget Burn", "My assigned projects", "Explore initiatives"])
            with timeline_tab:
                render_timeline_and_burn_section(_user)
        else:
            my_tab, explore_tab = st.tabs(["My assigned projects", "Explore initiatives"])

        with my_tab:
            render_my_assigned_projects_section(_user["employee_id"], _user["name"])
        with explore_tab:
            with st.container(border=True):
                section_title("Explore department initiatives")
                try:
                    all_projs = ProjectManager().list_projects(limit=100)
                    if all_projs:
                        dept_projs = [p for p in all_projs if p.get("department_id") == _user.get("department_id")] if _user.get("department_id") else all_projs
                        target_list = dept_projs if dept_projs else all_projs
                        proj_dict = {f"#{p['project_id']} — {p['project_name']} ({p.get('status', 'active')})": p for p in target_list}
                        sel_pname = st.selectbox("Select project to inspect details", list(proj_dict.keys()), key="emp_browse_proj")
                        p_info = proj_dict[sel_pname]
                        st.json({
                            "Project ID": p_info["project_id"],
                            "Project Name": p_info["project_name"],
                            "Status": p_info["status"],
                            "Budget": f"₹{float(p_info['budget']):,.2f}",
                            "Start Date": str(p_info.get("start_date", "N/A")),
                            "End Date": str(p_info.get("end_date", "N/A")),
                        })
                    else:
                        st.info("No projects found.")
                except Exception as exc:
                    st.error(f"Error loading projects: {exc}")
        return

    timeline_tab, create_tab, assign_tab, manage_tab, my_tab = st.tabs(["Timeline & Budget Burn", "Create project", "Assign employee", "Manage projects", "My assigned projects"])
    with timeline_tab:
        render_timeline_and_burn_section(_user)
    with create_tab:
        with st.container(border=True):
            section_title("Project brief")
            with st.form("project_form"):
                project_name = st.text_input("Project name")
                department_col, budget_col = st.columns(2)
                with department_col:
                    department_id = render_department_field(departments, "project_department")
                with budget_col:
                    budget = st.number_input("Budget (₹)", min_value=0.0, step=5_000.0, format="%.2f")
                create_project = st.form_submit_button("Create project", type="primary", use_container_width=True)
        if create_project:
            errors = validate_project_form(project_name, department_id, float(budget))
            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    project_id = ProjectManager().create_project(Project(project_name=project_name, department_id=department_id, budget=float(budget)))
                    render_form_message(f"Project {project_id} created.", True)
                except Exception as exc:
                    render_form_message(f"Project could not be created: {exc}", False)
    with assign_tab:
        with st.container(border=True):
            section_title("Allocation details")

            # Load active projects for assignment selection
            try:
                all_projs = ProjectManager().list_projects(limit=200)
                active_projs = [p for p in all_projs if p.get("status") in ("active", "planned")]
                proj_options = {f"#{p['project_id']} — {p['project_name']} ({p.get('status', 'active')})": p["project_id"] for p in active_projs}
            except Exception:
                proj_options = {}

            # Load active employees for assignment selection
            try:
                from src.database.db_manager import DatabaseConnection
                if not can_cross_assign:
                    dept_scope = rbac.scoped_department_id(_user)
                    emp_rows = DatabaseConnection().fetch_all(
                        "SELECT employee_id, first_name, last_name, job_title FROM employees WHERE department_id = %s AND status = 'active' ORDER BY first_name, last_name",
                        (dept_scope,),
                    )
                    emp_options = {f"#{e['employee_id']} — {e['first_name']} {e['last_name']} ({e['job_title']})": e["employee_id"] for e in emp_rows}
                else:
                    emp_rows = DatabaseConnection().fetch_all(
                        "SELECT e.employee_id, e.first_name, e.last_name, e.job_title, d.department_name "
                        "FROM employees e JOIN departments d ON d.department_id = e.department_id "
                        "WHERE e.status = 'active' ORDER BY e.first_name, e.last_name LIMIT 300"
                    )
                    emp_options = {f"#{e['employee_id']} — {e['first_name']} {e['last_name']} ({e['department_name']} · {e['job_title']})": e["employee_id"] for e in emp_rows}
            except Exception:
                emp_options = {}

            with st.form("assignment_form"):
                employee_col, project_col = st.columns(2)
                with employee_col:
                    if emp_options:
                        sel_emp_label = st.selectbox("Select Employee", list(emp_options.keys()))
                        assign_emp_id = emp_options[sel_emp_label]
                    else:
                        assign_emp_id = st.number_input("Employee ID", min_value=1, step=1, key="assign_emp_id")
                with project_col:
                    if proj_options:
                        sel_proj_label = st.selectbox("Select Project", list(proj_options.keys()))
                        assign_proj_id = proj_options[sel_proj_label]
                    else:
                        assign_proj_id = st.number_input("Project ID", min_value=1, step=1, key="assign_proj_id")
                allocation = st.slider("Allocation", min_value=5, max_value=100, value=100, step=5, format="%d%%")
                if not can_cross_assign:
                    st.caption(
                        f"🔒 You can assign employees from **{_user['department_name']}** to any project."
                    )
                else:
                    st.caption("🌐 Cross-functional staffing enabled: you can assign employees from any department.")
                assign = st.form_submit_button("Assign employee", type="primary", use_container_width=True)
        if assign:
            # Enforce department restriction only if user cannot assign cross-departmentally
            if not can_cross_assign:
                dept_scope = rbac.scoped_department_id(_user)
                if dept_scope is not None:
                    try:
                        target_emp = EmployeeManager().get_employee(int(assign_emp_id))
                        if target_emp is None:
                            st.error("Employee not found.")
                            st.stop()
                        if target_emp["department_id"] != dept_scope:
                            st.error(
                                f"Access denied — you can only assign employees from your own department "
                                f"({_user['department_name']}). Employee {int(assign_emp_id)} belongs to a different department."
                            )
                            st.stop()
                    except Exception as exc:
                        st.error(f"Could not verify employee: {exc}")
                        st.stop()
            try:
                ProjectManager().assign_employee(int(assign_emp_id), int(assign_proj_id), float(allocation))
                render_form_message("Project allocation saved.", True)
            except Exception as exc:
                render_form_message(f"Allocation could not be saved: {exc}", False)

    with manage_tab:
        with st.container(border=True):
            section_title("Find project")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_pid = st.number_input("Project ID", min_value=1, step=1, key="search_proj_id")
                search_pbtn = st.button("Search Project")
                
        if search_pbtn:
            try:
                proj = ProjectManager().get_project(search_pid)
                if proj:
                    st.session_state["selected_project"] = proj
                else:
                    st.session_state.pop("selected_project", None)
                    st.error("Project not found.")
            except Exception as exc:
                st.error(f"Error fetching project: {exc}")
                
        if "selected_project" in st.session_state:
            proj = st.session_state["selected_project"]
            with st.container(border=True):
                section_title(f"Update Project: {proj['project_name']}")
                with st.form("update_proj_form"):
                    new_name = st.text_input("Project Name", value=proj["project_name"])
                    new_budget = st.number_input("Budget (₹)", min_value=0.0, value=float(proj["budget"]), step=5000.0)
                    
                    statuses = ["planned", "active", "completed", "on_hold"]
                    current_status = proj["status"]
                    idx = statuses.index(current_status) if current_status in statuses else 0
                    new_status = st.selectbox("Status", statuses, index=idx)
                    
                    st.caption("Project budget updates cannot increase or decrease by more than 2x.")
                    update_btn = st.form_submit_button("Save changes", type="primary", use_container_width=True)
                    
            if update_btn:
                errors = validate_project_update_form(
                    project_name=new_name,
                    current_budget=float(proj["budget"]),
                    new_budget=float(new_budget),
                    status=new_status,
                )
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    try:
                        ProjectManager().update_project(proj["project_id"], new_name, float(new_budget), new_status)
                        st.success("Project updated successfully!")
                        st.session_state["selected_project"] = ProjectManager().get_project(proj["project_id"])
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to update project: {exc}")
                    
            # Only Super Admin can delete projects
            if rbac.can(_user["role"], "project.delete"):
                with st.container(border=True):
                    section_title("Danger zone")
                    if st.button("Delete project", type="primary", key="del_proj"):
                        try:
                            ProjectManager().delete_project(proj["project_id"])
                            st.success("Project deleted.")
                            st.session_state.pop("selected_project", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to delete project: {exc}")

    with my_tab:
        render_my_assigned_projects_section(_user["employee_id"], _user["name"])


def render_my_reviews_section(employee_id: int, employee_name: str) -> None:
    section_title(f"Performance history: {employee_name}")
    try:
        my_reviews = ReviewManager().get_employee_reviews(employee_id)
    except Exception as exc:
        st.error(f"Error retrieving performance reviews: {exc}")
        return

    if not my_reviews:
        st.info(f"ℹ️ Welcome, **{employee_name}**. No performance reviews have been submitted for your account yet. Once your manager completes a performance evaluation, your score and feedback will appear here.")
        return

    latest = my_reviews[0]
    latest_score = float(latest["overall_score"])
    band, band_color = score_band(latest_score)
    avg_score = sum(float(r["overall_score"]) for r in my_reviews) / len(my_reviews)

    mcol1, mcol2, mcol3 = st.columns(3)
    with mcol1:
        kpi_card("Latest Review Score", f"{latest_score:.1f} / 100", f"Rating: {latest.get('rating', 'N/A')}")
    with mcol2:
        kpi_card("Performance Band", band, f"Avg Score: {avg_score:.1f}")
    with mcol3:
        kpi_card("Total Reviews", len(my_reviews), f"Last on {latest.get('review_date', 'N/A')}")

    st.markdown("<div style='height: .6rem'></div>", unsafe_allow_html=True)
    section_title("Detailed review records")

    for r in my_reviews:
        score = float(r["overall_score"])
        b, bc = score_band(score)
        mgr_name = f"{r['mgr_first']} {r['mgr_last']}" if r.get("mgr_first") else "Direct Manager"
        mgr_title = f" ({r['mgr_title']})" if r.get("mgr_title") else ""

        with st.container(border=True):
            hdr_col, score_col = st.columns([3, 1])
            with hdr_col:
                st.markdown(f"### Review Date: {r['review_date']}")
                st.caption(f"Reviewed by: **{mgr_name}**{mgr_title} &nbsp;|&nbsp; Rating: **{r.get('rating', 'N/A')}**")
            with score_col:
                st.markdown(
                    f"<div style='text-align: right;'>"
                    f"<span class='score-band' style='color:{bc}; border-color:{bc}55; font-size: 0.95rem; font-weight:700;'>"
                    f"● {b} · {score:.1f}/100</span></div>",
                    unsafe_allow_html=True,
                )

            if r.get("comments"):
                st.markdown(
                    f"<div style='margin-top: 0.6rem; padding: 0.8rem 1rem; background: rgba(255, 255, 255, 0.04); "
                    f"border-left: 3px solid #E87CF7; border-radius: 6px; font-size: 0.92rem; color: #E2E8F0;'>"
                    f"<b>Manager Comments:</b><br/>{r['comments']}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Feature 5: Official Printable Performance Appraisal Letter & Excel Scorecard
            mgr_full_name = f"{r.get('mgr_first', '')} {r.get('mgr_last', '')}".strip() or "Direct Manager"
            mgr_job_title = r.get("mgr_title") or "Manager"

            appraisal_html = generate_printable_appraisal_html(
                rev=r,
                emp_name=employee_name,
                emp_id=employee_id,
                dept=_user.get("department_name", "Corporate"),
                title=_user.get("job_title", "Team Member"),
                mgr_name=mgr_full_name,
                mgr_title=mgr_job_title,
            )
            appraisal_excel = generate_appraisal_excel_bytes(
                rev=r,
                emp_name=employee_name,
                emp_id=employee_id,
                dept=_user.get("department_name", "Corporate"),
                title=_user.get("job_title", "Team Member"),
                mgr_name=mgr_full_name,
                mgr_title=mgr_job_title,
            )

            with st.expander("Official Appraisal Scorecard (Print / PDF / Excel)", expanded=False):
                btn_c1, btn_c2 = st.columns(2)
                with btn_c1:
                    st.download_button(
                        label="📊 Download Scorecard (Excel .xlsx)",
                        data=appraisal_excel,
                        file_name=f"Appraisal_Scorecard_{employee_id}_{r.get('review_date')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_appraisal_excel_emp_{r.get('review_id')}",
                        use_container_width=True,
                    )
                with btn_c2:
                    st.download_button(
                        label="📄 Download Printable Letter (HTML / PDF)",
                        data=appraisal_html.encode("utf-8"),
                        file_name=f"Appraisal_{employee_id}_{r.get('review_date')}.html",
                        mime="text/html",
                        key=f"dl_appraisal_emp_{r.get('review_id')}",
                        use_container_width=True,
                    )
                st.components.v1.html(appraisal_html, height=520, scrolling=True)


def render_reviews() -> None:
    page_header("Performance <span class='gradient-text'>reviews</span>", "Capture a clear, consistent view of employee performance")

    # Feature 5: One-click Performance Reviews Excel Export
    if rbac.can_export_reviews(_user):
        dept_scope = rbac.scoped_department_id(_user)
        try:
            rev_export_data = ReviewManager().get_reviews_export(department_id=dept_scope)
            if rev_export_data:
                rev_df = pd.DataFrame(rev_export_data)
                excel_data = to_excel_bytes(rev_df, sheet_name="Performance Reviews")
                scope_tag = _user.get("department_name", "department") if dept_scope else "all_departments"
                fn = f"performance_reviews_{scope_tag.lower().replace(' ', '_')}_{date.today()}.xlsx"

                r_col1, r_col2 = st.columns([3, 1.3])
                with r_col2:
                    st.download_button(
                        label="📊 Export Reviews Log (Excel)",
                        data=excel_data,
                        file_name=fn,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_reviews_log",
                        use_container_width=True,
                        help="Export complete historical appraisal records in Excel (.xlsx)",
                    )
        except Exception as exc:
            st.caption(f"Reviews export unavailable: {exc}")

    _can_create_rev = rbac.can(_user["role"], "review.create")

    if not _can_create_rev:
        # Employee and Analyst directly view their own performance reviews and feedback
        render_my_reviews_section(_user["employee_id"], _user["name"])
        return

    create_tab, manage_tab, my_rev_tab = st.tabs(["Create review", "Manage reviews", "My performance reviews"])
    
    with create_tab:
        with st.container(border=True):
            section_title("Review details")
            with st.form("review_form"):
                identity_col, date_col = st.columns(2)
                with identity_col:
                    employee_id = st.number_input("Employee ID", min_value=1, step=1)
                with date_col:
                    review_date = st.date_input("Review date")
                score = st.slider("Overall score", min_value=0.0, max_value=100.0, value=80.0, step=0.5)
                band, band_color = score_band(score)
                st.markdown(f'<span class="score-band" style="color:{band_color}; border-color:{band_color}55">●&nbsp; {band} · {score:.1f}/100</span>', unsafe_allow_html=True)
                rating = st.selectbox("Rating", ["Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"])
                comments = st.text_area("Manager comments", height=130)
                submit_review = st.form_submit_button("Save review", type="primary", use_container_width=True)
        if submit_review:
            errors = validate_review_form(int(employee_id), float(score), rating, comments)
            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    review_id = ReviewManager().create_review(Review(employee_id=int(employee_id), review_date=review_date, overall_score=float(score), rating=rating, comments=comments))
                    render_form_message(f"Review {review_id} saved. Run the warehouse ETL to refresh analytics.", True)
                except Exception as exc:
                    render_form_message(f"Review could not be saved: {exc}", False)

    with manage_tab:
        with st.container(border=True):
            section_title("Find review")
            search_col, _ = st.columns([1, 2])
            with search_col:
                search_rid = st.number_input("Review ID", min_value=1, step=1, key="search_rev_id")
                search_rbtn = st.button("Search Review")
                
        if search_rbtn:
            try:
                rev = ReviewManager().get_review(search_rid)
                if rev:
                    # Dept Manager guard: verify the reviewed employee is in their dept
                    if _user["role"] == "Department Manager":
                        rev_emp = EmployeeManager().get_employee(rev["employee_id"])
                        if rev_emp and not rbac.review_editable_by(_user, rev_emp["department_id"]):
                            st.error(
                                "Access denied — you can only view or edit reviews for employees "
                                f"in your department ({_user['department_name']})."
                            )
                            st.session_state.pop("selected_review", None)
                        else:
                            st.session_state["selected_review"] = rev
                    else:
                        st.session_state["selected_review"] = rev
                else:
                    st.session_state.pop("selected_review", None)
                    st.error("Review not found.")
            except Exception as exc:
                st.error(f"Error fetching review: {exc}")
                
        if "selected_review" in st.session_state:
            rev = st.session_state["selected_review"]
            with st.container(border=True):
                section_title(f"Update Review {rev['review_id']} (Emp: {rev['employee_id']})")
                with st.form("update_rev_form"):
                    new_score = st.slider("Overall score", min_value=0.0, max_value=100.0, value=float(rev["overall_score"]), step=0.5, key="upd_rev_score")
                    ratings = ["Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"]
                    current_rating = rev["rating"]
                    idx = ratings.index(current_rating) if current_rating in ratings else 0
                    new_rating = st.selectbox("Rating", ratings, index=idx, key="upd_rev_rating")
                    
                    new_comments = st.text_area("Comments", value=rev.get("comments", ""), key="upd_rev_comments")
                    update_btn = st.form_submit_button("Save changes", type="primary", use_container_width=True)
                    
            if update_btn:
                try:
                    ReviewManager().update_review(rev["review_id"], float(new_score), new_rating, new_comments)
                    st.success("Review updated successfully!")
                    st.session_state["selected_review"] = ReviewManager().get_review(rev["review_id"])
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to update review: {exc}")

            # Feature 5: Official Printable Appraisal Letter for Selected Review
            try:
                rev_emp = EmployeeManager().get_employee(rev["employee_id"])
                emp_name_val = f"{rev_emp['first_name']} {rev_emp['last_name']}" if rev_emp else f"Employee #{rev['employee_id']}"
                emp_dept_name = next(
                    (d["department_name"] for d in get_department_choices() if d["department_id"] == rev_emp["department_id"]),
                    "Corporate"
                ) if rev_emp else "Corporate"
                emp_title_val = rev_emp.get("job_title", "Team Member") if rev_emp else "Team Member"

                appr_html = generate_printable_appraisal_html(
                    rev=rev,
                    emp_name=emp_name_val,
                    emp_id=rev["employee_id"],
                    dept=emp_dept_name,
                    title=emp_title_val,
                    mgr_name=_user["name"],
                    mgr_title=_user["role"],
                )
                appr_excel = generate_appraisal_excel_bytes(
                    rev=rev,
                    emp_name=emp_name_val,
                    emp_id=rev["employee_id"],
                    dept=emp_dept_name,
                    title=emp_title_val,
                    mgr_name=_user["name"],
                    mgr_title=_user["role"],
                )
                with st.expander("Official Appraisal Scorecard (Print / PDF / Excel)", expanded=False):
                    m_btn1, m_btn2 = st.columns(2)
                    with m_btn1:
                        st.download_button(
                            label="📊 Download Scorecard (Excel .xlsx)",
                            data=appr_excel,
                            file_name=f"Appraisal_Scorecard_{rev['employee_id']}_{rev.get('review_date')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_mgr_appraisal_excel_{rev['review_id']}",
                            use_container_width=True,
                        )
                    with m_btn2:
                        st.download_button(
                            label="📄 Download Printable Letter (HTML / PDF)",
                            data=appr_html.encode("utf-8"),
                            file_name=f"Appraisal_{rev['employee_id']}_{rev.get('review_date')}.html",
                            mime="text/html",
                            key=f"dl_mgr_appraisal_{rev['review_id']}",
                            use_container_width=True,
                        )
                    st.components.v1.html(appr_html, height=520, scrolling=True)
            except Exception as exc:
                st.caption(f"Appraisal preview error: {exc}")

            # Only Super Admin and HR Admin can delete reviews
            if rbac.can(_user["role"], "review.delete"):
                with st.container(border=True):
                    section_title("Danger zone")
                    if st.button("Delete review", type="primary", key="del_rev"):
                        try:
                            ReviewManager().delete_review(rev["review_id"])
                            st.success("Review deleted.")
                            st.session_state.pop("selected_review", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to delete review: {exc}")

    with my_rev_tab:
        render_my_reviews_section(_user["employee_id"], _user["name"])


def render_analytics() -> None:
    page_header("Performance <span class='gradient-text'>analytics</span>", "Read workforce momentum, high performers, and risk at a glance")

    department_basis = "review"

    departments_list = get_department_choices()

    # Department Managers are locked to their own department — no selector shown
    dept_scope = rbac.scoped_department_id(_user)
    if dept_scope is not None:
        selected_department = _user["department_name"]
        st.info(f"Showing analytics for: **{selected_department}**")
    else:
        dept_names = ["All departments"] + sorted([d["department_name"] for d in departments_list])
        selected_department = st.selectbox("Filter dashboard by department", dept_names)
        
    analytics = AnalyticsManager()
    try:
        trend = pd.DataFrame(analytics.get_performance_trends(department_basis, selected_department))
    except Exception as e:
        st.error(f"Trend error: {e}")
        trend = pd.DataFrame()
    try:
        top = pd.DataFrame(analytics.get_top_performers(department_basis, selected_department))
    except Exception as e:
        st.error(f"Top error: {e}")
        top = pd.DataFrame()
    try:
        risk = pd.DataFrame(analytics.get_attrition_risk(selected_department))
    except Exception as e:
        st.error(f"Risk error: {e}")
        risk = pd.DataFrame()
    try:
        bottlenecks = pd.DataFrame(analytics.get_project_bottlenecks(selected_department))
    except Exception as e:
        st.error(f"Bottlenecks error: {e}")
        bottlenecks = pd.DataFrame()
        
    # Show info pill if any query threw an exception (causing the df to be explicitly empty in our except blocks)
    # but don't fallback to local CSV data just because a department has no records in a specific table.
    local_fallback = trend.empty and top.empty and risk.empty and bottlenecks.empty
    if local_fallback:
        info_pill("Showing synthetic analytics for any view not available from MySQL")

    latest_score = float(trend.iloc[-1]["avg_score"]) if not trend.empty else 0
    year_change = float(trend.iloc[-1]["avg_score"] - trend.iloc[-2]["avg_score"]) if len(trend) > 1 else 0
    reviewed_count = int(top["employee_id"].nunique()) if not top.empty else 0
    high_risk_count = int((risk["avg_attrition_risk"] >= 60).sum()) if not risk.empty else 0
    kpis = st.columns(4)
    with kpis[0]:
        kpi_card("Latest average score", f"{latest_score:.1f}", icon="✦")
    with kpis[1]:
        kpi_card("Year-over-year change", f"{year_change:+.1f}", "score points", icon="↗")
    with kpis[2]:
        kpi_card("Employees reviewed", f"{reviewed_count:,}", icon="♙")
    with kpis[3]:
        kpi_card("High-risk departments", high_risk_count, "average risk ≥ 60", icon="◌")

    chart_columns = st.columns(2)
    if not trend.empty:
        with chart_columns[0].container(border=True):
            section_title("Year-over-year review score")
            fig = px.line(trend, x="review_year", y="avg_score", markers=True, labels={"review_year": "Year", "avg_score": "Average review score"})
            fig.update_traces(line={"color": COLORS["pink"], "width": 3}, marker={"color": COLORS["soft_pink"], "size": 9}, fill="tozeroy", fillcolor="rgba(185,58,150,.16)", hovertemplate="Year %{x}<br>Average review score %{y:.1f}<extra></extra>")
            padding = max(1, (float(trend["avg_score"].max()) - float(trend["avg_score"].min())) * 0.35)
            y_min = float(trend["avg_score"].min()) - padding
            y_max = float(trend["avg_score"].max()) + padding
            fig.update_layout(xaxis={"dtick": 1, "tickformat": "d", "title": "Year"}, yaxis={"range": [y_min, y_max], "title": "Average review score"})
            st.plotly_chart(style_fig(fig, 365), use_container_width=True, config={"displayModeBar": False})
            st.caption(f"Review scores moved {year_change:+.1f} points in the latest year.")
    if not top.empty:
        filtered_top = top.copy()
        filtered_top = filtered_top.sort_values("overall_score", ascending=True).tail(10)
        filtered_top["employee_name"] = filtered_top["first_name"] + " " + filtered_top["last_name"]
        with chart_columns[1].container(border=True):
            section_title("Top performers")
            fig = px.bar(filtered_top, x="overall_score", y="employee_name", orientation="h", color="department_name", text="overall_score", color_discrete_sequence=COLOURWAY, labels={"overall_score": "Average score", "employee_name": "Employee", "department_name": "Department"})
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", hovertemplate="%{y}<br>Average score %{x:.1f}<extra></extra>")
            fig.update_layout(showlegend=False, xaxis_title="Average score", yaxis_title="Employee")
            st.plotly_chart(style_fig(fig, 365), use_container_width=True, config={"displayModeBar": False})
            st.caption("The strongest average performers across the selected department view.")

    if not risk.empty:
        with st.container(border=True):
            section_title("Attrition risk by department")
            risk_display = risk.sort_values("avg_attrition_risk", ascending=True)
            fig = px.bar(risk_display, x="avg_attrition_risk", y="department_name", orientation="h", text="avg_attrition_risk", color="avg_attrition_risk", color_continuous_scale=[[0, COLORS["soft_pink"]], [.5, COLORS["magenta"]], [1, COLORS["bg_indigo"]]], labels={"avg_attrition_risk": "Average attrition risk", "department_name": "Department"})
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside", hovertemplate="%{y}<br>Average attrition risk %{x:.1f}<extra></extra>")
            fig.update_layout(coloraxis_showscale=False, xaxis_title="Average attrition risk", yaxis_title="Department")
            st.plotly_chart(style_fig(fig, 390), use_container_width=True, config={"displayModeBar": False})
            st.caption("Higher values indicate departments that may benefit from a closer retention review.")

    if not top.empty:
        display_top = top[["employee_id", "first_name", "last_name", "department_name", "overall_score", "department_rank"]].copy()
        display_top.columns = ["Employee ID", "First name", "Last name", "Department", "Average score", "Department rank"]
        with st.container(border=True):
            section_title("Performance roster")
            st.dataframe(display_top.sort_values("Average score", ascending=False), hide_index=True, use_container_width=True)
            
    if not bottlenecks.empty:
        with st.container(border=True):
            section_title("Project bottlenecks")
            
            # Interactive Chart for Bottlenecks
            bottlenecks["budget"] = pd.to_numeric(bottlenecks["budget"], errors="coerce").fillna(0)
            fig = px.scatter(
                bottlenecks, 
                x="assigned_employees", 
                y="total_allocation_pct", 
                color="department_name",
                size="budget",
                hover_name="project_name",
                hover_data={"project_id": True, "department_name": False, "budget": ":₹,.0f", "assigned_employees": True, "total_allocation_pct": True},
                labels={
                    "assigned_employees": "Assigned Employees", 
                    "total_allocation_pct": "Total Allocation %", 
                    "department_name": "Department",
                    "budget": "Budget (₹)"
                },
                color_discrete_sequence=COLOURWAY,
                title="Resource Allocation by Project"
            )
            fig.update_layout(xaxis_title="Assigned Employees", yaxis_title="Total Allocation % (across all employees)", showlegend=True)
            st.plotly_chart(style_fig(fig, 390), use_container_width=True, config={"displayModeBar": False})
            st.caption("Active projects with low total allocation or headcount indicate potential resource bottlenecks. Bubble size corresponds to project budget.")

            display_bottlenecks = bottlenecks.copy()
            display_bottlenecks.columns = ["Project ID", "Project Name", "Department", "Budget (₹)", "Assigned Employees", "Total Allocation %"]
            st.dataframe(display_bottlenecks, hide_index=True, use_container_width=True)


if _user:
    # ── Sidebar ──────────────────────────────────────────────────────────────────
    st.sidebar.markdown('<div class="brand-mark"><span>V4C</span>.ai</div>', unsafe_allow_html=True)

    # User identity pill + top logout button
    st.sidebar.markdown(
        f"""
        <div style="margin: 0 0 .6rem .6rem; padding: .65rem .85rem;
                    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
                    border-radius: 12px; font-size: .78rem; line-height: 1.5;">
            <div style="color: white; font-weight: 600; font-size: .88rem;">{_user['name']}</div>
            <div style="color: #E87CF7; font-weight: 500;">{_user['role']}</div>
            <div style="color: #9B89C4; font-size: .75rem;">{_user['department_name']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("🚪  Log out", key="top_logout_btn", use_container_width=True):
        logout()

    st.sidebar.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)

    page = st.sidebar.radio("Workspace", [f"{PAGE_ICONS[item]}  {item}" for item in PAGES], label_visibility="collapsed")
    page = page.split("  ", 1)[1].strip()

    # ── Change password expander in sidebar ─────────────────────────────────────
    with st.sidebar.expander("🔑  Change password", expanded=False):
        with st.form("change_pwd_form"):
            current_pwd  = st.text_input("Current password",  type="password", key="chg_current")
            new_pwd      = st.text_input("New password",      type="password", key="chg_new",
                                         help="Minimum 8 characters")
            confirm_pwd  = st.text_input("Confirm new password", type="password", key="chg_confirm")
            change_btn   = st.form_submit_button("Update password", use_container_width=True)

        if change_btn:
            pwd_errors = validate_password_change(current_pwd, new_pwd, confirm_pwd)
            if pwd_errors:
                for err in pwd_errors:
                    st.error(err)
            else:
                # Verify current password before allowing the change
                from src.auth.authenticator import verify_password, change_password
                from src.database.db_manager import DatabaseConnection
                class _PwdDB(DatabaseConnection): pass
                row = _PwdDB().fetch_one(
                    "SELECT password_hash FROM user_accounts WHERE employee_id = %s",
                    (_user["employee_id"],)
                )
                if not row or not verify_password(current_pwd, row["password_hash"]):
                    st.error("Current password is incorrect.")
                elif verify_password(new_pwd, row["password_hash"]):
                    st.error("New password cannot be the same as your current password.")
                else:
                    change_password(_user["employee_id"], new_pwd)
                    st.success("Password updated successfully.")

    if page == "Overview":
        render_overview()
    elif page == "Employee Management":
        render_employees()
    elif page == "Project Management":
        render_projects()
    elif page == "Performance Reviews":
        render_reviews()
    else:
        render_analytics()

#commend

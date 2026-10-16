from __future__ import annotations

import pytest
from datetime import date
from src.managers import EmployeeManager, ProjectManager, ReviewManager
from src.streamlit_app import generate_printable_appraisal_html


def test_get_projects_timeline():
    pm = ProjectManager()
    # Test global timeline
    projs = pm.get_projects_timeline(department_id=None, limit=10)
    assert len(projs) > 0
    first = projs[0]
    assert "project_id" in first
    assert "project_name" in first
    assert "start_date" in first
    assert "end_date" in first
    assert "status" in first
    assert "budget" in first
    assert "staff_count" in first
    assert "annual_staffing_burn" in first
    assert "monthly_staffing_burn" in first

    # Test department scoped timeline
    dept_projs = pm.get_projects_timeline(department_id=9, limit=10)
    for p in dept_projs:
        assert p["department_id"] == 9


def test_get_staffing_allocation_matrix():
    pm = ProjectManager()
    matrix = pm.get_staffing_allocation_matrix(department_id=None)
    assert len(matrix) > 0
    row = matrix[0]
    assert "project_id" in row
    assert "project_name" in row
    assert "employee_id" in row
    assert "employee_name" in row
    assert "allocation_pct" in row
    assert "assigned_date" in row


def test_get_employees_export():
    em = EmployeeManager()
    # Test export with salary
    with_sal = em.get_employees_export(department_id=None, include_salary=True)
    assert len(with_sal) > 0
    assert "salary" in with_sal[0]
    assert "employee_id" in with_sal[0]
    assert "first_name" in with_sal[0]

    # Test export without salary (for non-finance dept managers)
    without_sal = em.get_employees_export(department_id=9, include_salary=False)
    assert len(without_sal) > 0
    assert "salary" not in without_sal[0]
    assert "employee_id" in without_sal[0]


def test_get_reviews_export():
    rm = ReviewManager()
    revs = rm.get_reviews_export(department_id=None)
    assert len(revs) > 0
    r = revs[0]
    assert "review_id" in r
    assert "employee_id" in r
    assert "employee_name" in r
    assert "overall_score" in r
    assert "rating" in r
    assert "comments" in r


def test_generate_printable_appraisal_html():
    rev = {
        "review_id": 99999,
        "review_date": date(2026, 10, 16),
        "overall_score": 92.5,
        "rating": "Exceeds Expectations",
        "comments": "Exceptional leadership on high-impact projects.",
    }
    html = generate_printable_appraisal_html(
        rev=rev,
        emp_name="Test Employee",
        emp_id=12345,
        dept="Engineering",
        title="Senior Architect",
        mgr_name="Test Manager",
        mgr_title="Director",
    )
    assert "<!DOCTYPE html>" in html
    assert "Test Employee" in html
    assert "#12345" in html
    assert "92.5" in html
    assert "Exceeds Expectations" in html
    assert "Exceptional leadership on high-impact projects." in html
    assert "@media print" in html
    assert "window.print()" in html


def test_to_excel_bytes():
    import pandas as pd
    from src.streamlit_app import to_excel_bytes
    df = pd.DataFrame({"colA": [10, 20], "colB": ["Alpha", "Beta"]})
    raw_excel = to_excel_bytes(df, sheet_name="TestSheet")
    assert isinstance(raw_excel, bytes)
    assert len(raw_excel) > 1000  # valid zip-based xlsx content


def test_generate_appraisal_excel_bytes():
    from src.streamlit_app import generate_appraisal_excel_bytes
    rev = {
        "review_id": 88888,
        "review_date": date(2026, 10, 16),
        "overall_score": 95.0,
        "rating": "Exceeds Expectations",
        "comments": "Consistent architectural excellence.",
    }
    excel_bytes = generate_appraisal_excel_bytes(
        rev=rev,
        emp_name="Alice Smith",
        emp_id=54321,
        dept="Operations",
        title="Operations Director",
        mgr_name="John Doe",
        mgr_title="VP Operations",
    )
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 2000


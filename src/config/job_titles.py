"""
job_titles.py
─────────────
Department-specific job title catalog and department-level page rules.

Used by:
  - streamlit_app.py  → dynamic job title dropdown
  - rbac.py           → dept-aware page filtering for Department Managers
  - validators.py     → whitelist validation of submitted job titles
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Job title catalog — ordered senior → junior within each department
# ---------------------------------------------------------------------------
DEPT_JOB_TITLES: dict[str, list[str]] = {
    "Engineering": [
        "Engineering Director",
        "Engineering Manager",
        "Software Engineer",
        "Data Engineer",
        "QA Engineer",
        "Junior Software Engineer",
    ],
    "Research & Development": [
        "R&D Director",
        "Manager",
        "Research Scientist",
        "Research Analyst",
        "Laboratory Technician",
    ],
    "Sales": [
        "Sales Director",
        "Sales Manager",
        "Account Executive",
        "Sales Executive",
        "Business Development Rep",
        "Sales Development Representative",
    ],
    "Operations": [
        "Operations Director",
        "Operations Manager",
        "Operations Analyst",
        "Project Coordinator",
        "Logistics Coordinator",
    ],
    "Finance": [
        "Finance Director",
        "Finance Manager",
        "Financial Analyst",
        "Controller",
        "Accountant",
        "Junior Financial Analyst",
    ],
    "Human Resources": [
        "HR Director",
        "HR Manager",
        "HR Business Partner",
        "HR Generalist",
        "Talent Partner",
        "HR Coordinator",
    ],
    "Marketing": [
        "Marketing Director",
        "Brand Manager",
        "Growth Manager",
        "Marketing Analyst",
        "Content Strategist",
    ],
    "Customer Success": [
        "Customer Success Director",
        "Customer Success Manager",
        "Account Manager",
        "Support Engineer",
        "Customer Support Specialist",
    ],
    "Supply Chain": [
        "Supply Chain Director",
        "Logistics Manager",
        "Supply Planner",
        "Procurement Analyst",
        "Inventory Specialist",
    ],
}

# Flat set of every valid job title (used for whitelist validation)
ALL_JOB_TITLES: frozenset[str] = frozenset(
    title for titles in DEPT_JOB_TITLES.values() for title in titles
)

# ---------------------------------------------------------------------------
# Department-level page access rules for the "Department Manager" role
# ---------------------------------------------------------------------------

# All Department Managers can access Project Management to create initiatives & assign employees
PROJECT_MGMT_DEPTS: frozenset[str] = frozenset(DEPT_JOB_TITLES.keys())

# Only HR and Finance Department Managers can access Employee Management.
EMPLOYEE_MGMT_DEPTS: frozenset[str] = frozenset({
    "Human Resources",
    "Finance",
})

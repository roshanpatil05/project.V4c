"""
validators.py
─────────────
Central validation layer for V4C.ai.

All user-supplied data must pass through these validators before being
written to the database.  Two layers are provided:

  1. Backend validators (used inside dataclass .validate() methods and managers)
     – raise ValueError with a human-readable message on failure.

  2. Frontend helpers (used in streamlit_app.py form handlers)
     – return a list of error strings so multiple errors can be shown at once.

SQL-injection defence summary
──────────────────────────────
• All DB calls already use PyMySQL parameterised queries (%s placeholders).
  User-supplied values never reach the SQL string itself.
• Dynamic structural SQL (JOIN / WHERE clause selection) uses whitelist dicts
  keyed on trusted Python literals — never on user input directly.
• This module adds a sanitize_text() step that strips dangerous characters
  from free-text fields before they reach the DB layer.
"""
from __future__ import annotations

import re
from datetime import date

# Lazy-loaded to avoid circular imports at module load time
def _valid_job_titles() -> frozenset[str]:
    try:
        from src.config.job_titles import ALL_JOB_TITLES
        return ALL_JOB_TITLES
    except Exception:
        return frozenset()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_NAME_LEN       = 80
MAX_EMAIL_LEN      = 255
MAX_JOB_TITLE_LEN  = 120
MAX_PROJECT_LEN    = 160
MAX_COMMENT_LEN    = 5000
MIN_SALARY         = 1_000.0
MAX_SALARY         = 10_000_000.0
MIN_SCORE          = 0.0
MAX_SCORE          = 100.0
MIN_ALLOCATION     = 5.0
MAX_ALLOCATION     = 100.0

# Only these values are valid for DB ENUM columns
VALID_STATUSES     = {"active", "inactive"}
VALID_PROJECT_STATUSES = {"planned", "active", "completed", "on_hold"}
VALID_RATINGS      = {"Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"}

# Regex: strictly letters and spaces only — no numbers or special characters allowed
_NAME_RE    = re.compile(r"^[A-Za-z\s]+$")
# Stricter: project/job-title allows alphanumeric, spaces, common punctuation
_TITLE_RE   = re.compile(r"^[\w\s\-\',\.&()\/]+$", re.UNICODE)
# Basic email structure
_EMAIL_RE   = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Strip characters that are meaningless in text but dangerous near SQL
_DANGEROUS_CHARS = re.compile(r"[;\"\x00]")


# ---------------------------------------------------------------------------
# Sanitisation (defence-in-depth on top of parameterised queries)
# ---------------------------------------------------------------------------

def sanitize_text(value: str) -> str:
    """
    Strip characters that have no legitimate place in a name / title / comment
    but could be confusing or dangerous if they ever reached a raw SQL context.

    This is defence-in-depth — PyMySQL's parameterisation is the primary
    protection.  We do NOT need to escape quotes here because parameterisation
    already handles that; we just remove obviously malicious fragments.
    """
    # Remove null bytes and lone semicolons that could break multi-statement
    # guards in some DB drivers.
    cleaned = _DANGEROUS_CHARS.sub("", value)
    # Collapse runs of whitespace to a single space
    return " ".join(cleaned.split())


def whitelist_check(value: str, allowed: set[str], field: str) -> None:
    """Raise ValueError if *value* is not in the *allowed* whitelist."""
    if value not in allowed:
        raise ValueError(
            f"Invalid {field} '{value}'. "
            f"Allowed values: {', '.join(sorted(allowed))}."
        )


# ---------------------------------------------------------------------------
# Backend validators (raise ValueError)
# ---------------------------------------------------------------------------

def validate_name(value: str, field: str = "Name") -> str:
    """
    Validate and return a sanitised name string.
    Rule: Only letters and spaces allowed — strictly no numbers or special characters.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a text string.")
    value = sanitize_text(value.strip())
    if not value:
        raise ValueError(f"{field} is required.")
    if len(value) > MAX_NAME_LEN:
        raise ValueError(f"{field} must be {MAX_NAME_LEN} characters or fewer.")
    if any(char.isdigit() for char in value):
        raise ValueError(f"{field} cannot contain numbers.")
    if not _NAME_RE.match(value):
        raise ValueError(
            f"{field} cannot contain special characters or numbers. "
            "Use letters and spaces only."
        )
    return value


def validate_email(value: str) -> str:
    """Validate and return a normalised (lowercased, stripped) email."""
    value = value.strip().lower()
    if not value:
        raise ValueError("Email address is required.")
    if len(value) > MAX_EMAIL_LEN:
        raise ValueError(f"Email must be {MAX_EMAIL_LEN} characters or fewer.")
    if not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address (e.g. name@company.com).")
    # Block obvious injection attempts hidden in the email local part
    if _DANGEROUS_CHARS.search(value):
        raise ValueError("Email contains invalid characters.")
    return value


def validate_job_title(value: str, check_whitelist: bool = False) -> str:
    """Validate and return a sanitised job title.

    Args:
        value: The job title string to validate.
        check_whitelist: When True, also verifies the title is one of the
            known titles from the department catalog (ALL_JOB_TITLES).
            Set to True when the value comes from a dropdown; leave False
            for legacy free-text paths.
    """
    value = sanitize_text(value.strip())
    if not value:
        raise ValueError("Job title is required.")
    if len(value) > MAX_JOB_TITLE_LEN:
        raise ValueError(f"Job title must be {MAX_JOB_TITLE_LEN} characters or fewer.")
    if not _TITLE_RE.match(value):
        raise ValueError(
            "Job title contains invalid characters. "
            "Use letters, numbers, spaces and common punctuation only."
        )
    if check_whitelist:
        known = _valid_job_titles()
        if known and value not in known:
            raise ValueError(
                f"'{value}' is not a recognised job title. "
                "Please select a title from the dropdown."
            )
    return value


def validate_salary(value: float) -> float:
    """Validate salary is within acceptable bounds."""
    if value < MIN_SALARY:
        raise ValueError(f"Salary must be at least ₹{MIN_SALARY:,.0f}.")
    if value > MAX_SALARY:
        raise ValueError(f"Salary cannot exceed ₹{MAX_SALARY:,.0f}.")
    return value


def validate_salary_hike(current_salary: float, new_salary: float) -> float:
    """
    Validate an employee salary revision.
    Enforces policy: No more than 2x hike for employee (new_salary <= 2 * current_salary).
    """
    new_salary = validate_salary(float(new_salary))
    current_salary = float(current_salary)

    if current_salary > 0:
        max_allowed = round(2.0 * current_salary, 2)
        if new_salary > max_allowed:
            hike_ratio = new_salary / current_salary
            raise ValueError(
                f"Salary hike cannot exceed 2x the current salary. "
                f"Current: ₹{current_salary:,.2f}, New: ₹{new_salary:,.2f} ({hike_ratio:.2f}x). "
                f"Maximum allowed salary is ₹{max_allowed:,.2f}."
            )
    return new_salary


def validate_project_name(value: str) -> str:
    """Validate and return a sanitised project name."""
    value = sanitize_text(value.strip())
    if not value:
        raise ValueError("Project name is required.")
    if len(value) > MAX_PROJECT_LEN:
        raise ValueError(f"Project name must be {MAX_PROJECT_LEN} characters or fewer.")
    if not _TITLE_RE.match(value):
        raise ValueError("Project name contains invalid characters.")
    return value


def validate_project_budget_change(current_budget: float, new_budget: float) -> float:
    """
    Validate a project budget revision.
    Enforces policy: No more than 2x budget increase or decrease for projects.
      - Max increase: new_budget <= 2.0 * current_budget
      - Max decrease: new_budget >= current_budget / 2.0 (cannot drop below 50% of current)
    Note: If current_budget is 0.0 (unbudgeted project), initial non-negative allocation is permitted.
    """
    new_budget = float(new_budget)
    current_budget = float(current_budget)

    if new_budget < 0:
        raise ValueError("Project budget cannot be negative.")

    if current_budget > 0:
        max_allowed = round(2.0 * current_budget, 2)
        min_allowed = round(current_budget / 2.0, 2)

        if new_budget > max_allowed:
            mult = new_budget / current_budget
            raise ValueError(
                f"Project budget increase cannot exceed 2x the current budget. "
                f"Current: ₹{current_budget:,.2f}, New: ₹{new_budget:,.2f} ({mult:.2f}x). "
                f"Maximum allowed budget is ₹{max_allowed:,.2f}."
            )
        if new_budget < min_allowed:
            raise ValueError(
                f"Project budget decrease cannot exceed 2x (cannot be reduced below 50% of current budget). "
                f"Current: ₹{current_budget:,.2f}, New: ₹{new_budget:,.2f}. "
                f"Minimum allowed budget is ₹{min_allowed:,.2f}."
            )

    return new_budget


def validate_score(value: float) -> float:
    """Validate review score is in [0, 100]."""
    if not MIN_SCORE <= value <= MAX_SCORE:
        raise ValueError(f"Score must be between {MIN_SCORE} and {MAX_SCORE}.")
    return value


def validate_rating(value: str) -> str:
    """Validate rating against the allowed set."""
    whitelist_check(value, VALID_RATINGS, "rating")
    return value


def validate_project_status(value: str) -> str:
    """Validate project status against the allowed set."""
    whitelist_check(value, VALID_PROJECT_STATUSES, "project status")
    return value


def validate_allocation(value: float) -> float:
    """Validate project allocation percentage."""
    if not MIN_ALLOCATION <= value <= MAX_ALLOCATION:
        raise ValueError(
            f"Allocation must be between {MIN_ALLOCATION:.0f}% and {MAX_ALLOCATION:.0f}%."
        )
    return value


def validate_date_range(start: date | None, end: date | None) -> None:
    """Raise ValueError if end < start."""
    if start and end and end < start:
        raise ValueError("End date cannot be before start date.")


def validate_comment(value: str) -> str:
    """Sanitise a free-text comment."""
    value = sanitize_text(value.strip())
    if len(value) > MAX_COMMENT_LEN:
        raise ValueError(f"Comment must be {MAX_COMMENT_LEN} characters or fewer.")
    return value


def validate_department_basis(value: str) -> str:
    """Whitelist check for the dynamic JOIN selector in AnalyticsManager."""
    allowed = {"review", "current"}
    if value not in allowed:
        raise ValueError(
            f"department_basis must be one of: {', '.join(sorted(allowed))}."
        )
    return value


# ---------------------------------------------------------------------------
# Frontend helpers — return list[str] of errors (empty = all good)
# ---------------------------------------------------------------------------

def validate_employee_form(
    first_name: str,
    last_name: str,
    email: str,
    job_title: str,
    salary: float,
    department_id: int,
    password: str,
    confirm_password: str,
) -> list[str]:
    """Run all employee onboard form checks. Returns list of error messages."""
    errors: list[str] = []
    checks = [
        (lambda: validate_name(first_name, "First name"),       None),
        (lambda: validate_name(last_name,  "Last name"),        None),
        (lambda: validate_email(email),                         None),
        (lambda: validate_job_title(job_title),                 None),
        (lambda: validate_salary(salary),                       None),
    ]
    for fn, _ in checks:
        try:
            fn()
        except ValueError as exc:
            errors.append(str(exc))

    if department_id < 1:
        errors.append("Please select a valid department.")
    if not password:
        errors.append("Initial login password is required.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != confirm_password:
        errors.append("Passwords do not match.")

    return errors


def validate_password_change(
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> list[str]:
    """Run password change validation. Returns list of error messages."""
    errors: list[str] = []
    if not current_password or not new_password or not confirm_password:
        errors.append("All fields are required.")
        return errors
    if len(new_password) < 8:
        errors.append("New password must be at least 8 characters.")
    if new_password != confirm_password:
        errors.append("New passwords do not match.")
    if current_password == new_password:
        errors.append("New password cannot be the same as your current password.")
    return errors


def validate_employee_salary_update(current_salary: float, new_salary: float) -> list[str]:
    """Run salary update checks. Returns list of error messages."""
    errors: list[str] = []
    try:
        validate_salary_hike(current_salary, new_salary)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def validate_project_form(
    project_name: str,
    department_id: int,
    budget: float,
) -> list[str]:
    """Run all project creation form checks. Returns list of error messages."""
    errors: list[str] = []
    try:
        validate_project_name(project_name)
    except ValueError as exc:
        errors.append(str(exc))
    if department_id < 1:
        errors.append("Please select a valid department.")
    if budget < 0:
        errors.append("Budget cannot be negative.")
    return errors


def validate_project_update_form(
    project_name: str,
    current_budget: float,
    new_budget: float,
    status: str,
) -> list[str]:
    """Run all project update form checks. Returns list of error messages."""
    errors: list[str] = []
    try:
        validate_project_name(project_name)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_project_budget_change(current_budget, new_budget)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_project_status(status)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def validate_review_form(
    employee_id: int,
    score: float,
    rating: str,
    comments: str,
) -> list[str]:
    """Run all review form checks. Returns list of error messages."""
    errors: list[str] = []
    if employee_id < 1:
        errors.append("Employee ID must be a positive integer.")
    try:
        validate_score(score)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_rating(rating)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_comment(comments)
    except ValueError as exc:
        errors.append(str(exc))
    return errors

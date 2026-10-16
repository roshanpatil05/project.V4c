"""
reseed_role_rules.py
─────────────────────
Re-seeds the role_rules table with the updated rule set that covers
all job titles from the DEPT_JOB_TITLES catalog.

Usage:
    venv\\Scripts\\python reseed_role_rules.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.database.db_manager import DatabaseConnection


class DB(DatabaseConnection):
    pass


def run() -> None:
    db = DB()

    # Clear existing rules
    db.execute("DELETE FROM role_rules", commit=True)
    print("Cleared existing role_rules.")

    base_rules: list[tuple] = [
        # (title_pattern, department_id, role_name, priority)

        # P5: Director & VP titles (any dept) → Department Manager
        ("%Director%",          None, "Department Manager", 5),
        ("%VP%",                None, "Department Manager", 5),

        # P10: Manager titles (any dept) → Department Manager
        ("%Manager%",           None, "Department Manager", 10),

        # P20: Analyst, Coordinator, Controller → Analyst
        ("%Analyst%",           None, "Analyst",            20),
        ("Project Coordinator", None, "Analyst",            20),
        ("Controller",          None, "Analyst",            20),

        # P99: Catch-all → Employee
        ("%",                   None, "Employee",           99),
    ]

    for pattern, dept_id, role, priority in base_rules:
        db.execute(
            "INSERT INTO role_rules (title_pattern, department_id, role_name, priority) "
            "VALUES (%s, %s, %s, %s)",
            (pattern, dept_id, role, priority),
            commit=True,
        )

    # P1: HR department (any title) → HR Admin
    hr = db.fetch_one(
        "SELECT department_id FROM departments WHERE department_name = 'Human Resources'"
    )
    if hr:
        db.execute(
            "INSERT INTO role_rules (title_pattern, department_id, role_name, priority) "
            "VALUES (%s, %s, %s, %s)",
            ("%", hr["department_id"], "HR Admin", 1),
            commit=True,
        )
        print(f"HR Admin rule seeded for dept_id={hr['department_id']}")
    else:
        print("WARNING: 'Human Resources' department not found — HR Admin rule NOT seeded.")

    # Verify
    rows = db.fetch_all("SELECT * FROM role_rules ORDER BY priority, rule_id")
    print(f"\nTotal rules seeded: {len(rows)}")
    print(f"{'Pri':>4}  {'Dept':>6}  {'Pattern':<26}  Role")
    print("-" * 60)
    for r in rows:
        print(
            f"  P{r['priority']:>2}  {str(r['department_id'] or 'any'):>6}  "
            f"{r['title_pattern']:<26}  {r['role_name']}"
        )
    print("\nDone. Re-login required for existing sessions to pick up new roles.")


if __name__ == "__main__":
    run()

"""
setup_auth.py
─────────────
CLI script to create or update a V4C.ai user account.

Common usages
─────────────
# Create a normal account (role resolved from job title at login):
    python setup_auth.py --employee-id 42 --password "ChangeMe123!"

# Grant Super Admin (overrides all role_rules — CLI only, never from UI):
    python setup_auth.py --employee-id 1 --password "ChangeMe123!" --role "Super Admin"

# Revoke a forced role (revert to normal role_rules resolution):
    python setup_auth.py --employee-id 1 --password "ChangeMe123!" --revoke-role
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.auth.authenticator import create_account, resolve_role
from src.auth.rbac import ALL_ROLES
from src.database.db_manager import DatabaseConnection


# Roles that must NEVER be granted through the UI — CLI gate enforced here.
CLI_ONLY_ROLES: frozenset[str] = frozenset({"Super Admin"})


class SetupDB(DatabaseConnection):
    pass


def run(employee_id: int, password: str, forced_role: str | None, revoke_role: bool) -> None:
    db = SetupDB()

    # ── Verify the employee exists ───────────────────────────────────────
    emp = db.fetch_one(
        "SELECT employee_id, first_name, last_name, job_title, department_id "
        "FROM employees WHERE employee_id = %s",
        (employee_id,),
    )
    if emp is None:
        print(f"ERROR: Employee {employee_id} not found.")
        sys.exit(1)

    # ── Validate the requested forced_role ───────────────────────────────
    if forced_role is not None and forced_role not in ALL_ROLES:
        print(f"ERROR: '{forced_role}' is not a valid role.")
        print(f"  Valid roles: {', '.join(ALL_ROLES)}")
        sys.exit(1)

    # ── Revoke forced role (restore normal role_rules resolution) ────────
    if revoke_role:
        db.execute(
            "UPDATE user_accounts SET forced_role = NULL WHERE employee_id = %s",
            (employee_id,),
            commit=True,
        )
        resolved = resolve_role(emp["job_title"], emp["department_id"])
        print(f"\n✅  Forced role revoked for employee {employee_id}.")
        print(f"    Role will now resolve from job title: '{emp['job_title']}' → {resolved}")
        return

    # ── Create / update the account ──────────────────────────────────────
    create_account(employee_id, password, forced_role=forced_role)

    # Determine what role they will actually get on login
    display_role = forced_role if forced_role else resolve_role(emp["job_title"], emp["department_id"])
    role_source  = "forced (CLI override)" if forced_role else "resolved from job title"

    print(f"\n✅  Account created/updated for employee {employee_id}:")
    print(f"    Name       : {emp['first_name']} {emp['last_name']}")
    print(f"    Job title  : {emp['job_title']}")
    print(f"    Role       : {display_role}  [{role_source}]")
    if forced_role in CLI_ONLY_ROLES:
        print(f"\n⚠️   '{forced_role}' is a privileged CLI-only role.")
        print("    It cannot be viewed or changed through the web UI.")
    print(f"\nLog in with the employee's registered work email.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or update a V4C.ai user account")
    parser.add_argument(
        "--employee-id", type=int, required=True,
        help="Employee ID to create/update account for",
    )
    parser.add_argument(
        "--password", type=str, required=True,
        help="Initial plain-text password (will be hashed)",
    )
    parser.add_argument(
        "--role", type=str, default=None,
        dest="forced_role",
        metavar="ROLE",
        help=(
            "Force a specific app role, overriding role_rules on every login. "
            f"CLI-only roles (e.g. 'Super Admin') can only be set here. "
            f"Valid: {', '.join(ALL_ROLES)}"
        ),
    )
    parser.add_argument(
        "--revoke-role", action="store_true",
        help="Remove the forced_role override so the account reverts to normal role_rules resolution.",
    )
    args = parser.parse_args()

    if args.forced_role and args.revoke_role:
        print("ERROR: --role and --revoke-role are mutually exclusive.")
        sys.exit(1)

    run(args.employee_id, args.password, args.forced_role, args.revoke_role)

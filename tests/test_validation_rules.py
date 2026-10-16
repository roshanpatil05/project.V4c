from __future__ import annotations

import unittest

from src.models import Employee
from src.validators import (
    validate_name,
    validate_salary_hike,
    validate_project_budget_change,
    validate_employee_salary_update,
    validate_project_update_form,
    validate_password_change,
)


class ValidationRulesTests(unittest.TestCase):
    # ── 1. Employee Name Validation ───────────────────────────────────────────
    def test_name_accepts_letters_and_spaces(self):
        self.assertEqual(validate_name("Alice", "First name"), "Alice")
        self.assertEqual(validate_name("John Doe", "Full name"), "John Doe")
        self.assertEqual(validate_name("Mary Jane Watson"), "Mary Jane Watson")

    def test_name_rejects_numbers(self):
        with self.assertRaises(ValueError) as ctx:
            validate_name("John123", "First name")
        self.assertIn("cannot contain numbers", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_name("Agent 007", "First name")
        self.assertIn("cannot contain numbers", str(ctx.exception))

    def test_name_rejects_special_characters(self):
        for invalid_name in ["John_Doe", "John-Doe", "O'Connor", "Dr. Smith", "Jane@Doe", "Alex!"]:
            with self.subTest(name=invalid_name):
                with self.assertRaises(ValueError) as ctx:
                    validate_name(invalid_name, "Name")
                self.assertTrue(
                    "cannot contain special characters" in str(ctx.exception)
                    or "cannot contain numbers" in str(ctx.exception)
                )

    def test_name_rejects_empty_or_whitespace(self):
        with self.assertRaises(ValueError):
            validate_name("", "First name")
        with self.assertRaises(ValueError):
            validate_name("   ", "First name")

    def test_employee_model_enforces_name_rule(self):
        # Valid names work
        emp = Employee(
            first_name="Bruce",
            last_name="Wayne",
            email="bruce@wayne.com",
            department_id=1,
            job_title="Executive",
            salary=150000.0,
        )
        emp.validate()
        self.assertEqual(emp.first_name, "Bruce")

        # Number in name fails model validation
        emp_bad = Employee(
            first_name="Bruce2",
            last_name="Wayne",
            email="bruce@wayne.com",
            department_id=1,
            job_title="Executive",
            salary=150000.0,
        )
        with self.assertRaises(ValueError):
            emp_bad.validate()

    # ── 2. Salary Hike Validation (Max 2x Hike) ──────────────────────────────
    def test_salary_hike_within_2x_allowed(self):
        # 1.5x hike
        self.assertEqual(validate_salary_hike(50000.0, 75000.0), 75000.0)
        # Exactly 2x hike
        self.assertEqual(validate_salary_hike(50000.0, 100000.0), 100000.0)
        # No hike (unchanged)
        self.assertEqual(validate_salary_hike(50000.0, 50000.0), 50000.0)
        # Salary decrease
        self.assertEqual(validate_salary_hike(50000.0, 45000.0), 45000.0)

    def test_salary_hike_exceeding_2x_rejected(self):
        # 2.0001x hike
        with self.assertRaises(ValueError) as ctx:
            validate_salary_hike(50000.0, 100001.0)
        self.assertIn("Salary hike cannot exceed 2x", str(ctx.exception))

        # 3x hike
        with self.assertRaises(ValueError) as ctx:
            validate_salary_hike(50000.0, 150000.0)
        self.assertIn("Salary hike cannot exceed 2x", str(ctx.exception))

    def test_employee_salary_update_helper(self):
        # Allowed
        self.assertEqual(validate_employee_salary_update(60000.0, 90000.0), [])
        # Exceeded
        errors = validate_employee_salary_update(60000.0, 130000.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("Salary hike cannot exceed 2x", errors[0])

    # ── 3. Project Budget Increase/Decrease Validation (Max 2x) ──────────────
    def test_budget_increase_within_2x_allowed(self):
        # 1.5x increase
        self.assertEqual(validate_project_budget_change(100000.0, 150000.0), 150000.0)
        # Exactly 2x increase
        self.assertEqual(validate_project_budget_change(100000.0, 200000.0), 200000.0)
        # Unchanged
        self.assertEqual(validate_project_budget_change(100000.0, 100000.0), 100000.0)

    def test_budget_increase_exceeding_2x_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_project_budget_change(100000.0, 200001.0)
        self.assertIn("Project budget increase cannot exceed 2x", str(ctx.exception))

    def test_budget_decrease_within_2x_allowed(self):
        # Exactly 2x decrease (50% reduction)
        self.assertEqual(validate_project_budget_change(100000.0, 50000.0), 50000.0)
        # 25% reduction
        self.assertEqual(validate_project_budget_change(100000.0, 75000.0), 75000.0)

    def test_budget_decrease_exceeding_2x_rejected(self):
        # Dropping below 50%
        with self.assertRaises(ValueError) as ctx:
            validate_project_budget_change(100000.0, 49999.0)
        self.assertIn("Project budget decrease cannot exceed 2x", str(ctx.exception))

        # Dropping to 0 from positive
        with self.assertRaises(ValueError) as ctx:
            validate_project_budget_change(100000.0, 0.0)
        self.assertIn("Project budget decrease cannot exceed 2x", str(ctx.exception))

    def test_budget_initial_allocation_from_zero(self):
        # Project created with 0 budget can receive initial allocation
        self.assertEqual(validate_project_budget_change(0.0, 75000.0), 75000.0)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_project_budget_change(100000.0, -100.0)
        self.assertIn("cannot be negative", str(ctx.exception))

    def test_project_update_form_helper(self):
        # Valid form
        errors = validate_project_update_form("Apollo Mission", 100000.0, 150000.0, "active")
        self.assertEqual(errors, [])

        # Exceeds 2x increase
        errors = validate_project_update_form("Apollo Mission", 100000.0, 250000.0, "active")
        self.assertEqual(len(errors), 1)
        self.assertIn("increase cannot exceed 2x", errors[0])

        # Exceeds 2x decrease
        errors = validate_project_update_form("Apollo Mission", 100000.0, 30000.0, "active")
        self.assertEqual(len(errors), 1)
        self.assertIn("decrease cannot exceed 2x", errors[0])

        # Invalid project name with bad characters
        errors = validate_project_update_form("Bad<Project>", 100000.0, 150000.0, "active")
        self.assertIn("contains invalid characters", errors[0])

    def test_password_change_validation(self):
        # Valid password change
        errors = validate_password_change("CurrentPass1!", "NewSecretPass2@", "NewSecretPass2@")
        self.assertEqual(errors, [])

        # Missing fields
        errors = validate_password_change("", "NewSecretPass2@", "NewSecretPass2@")
        self.assertIn("All fields are required.", errors)

        # Same current and new password
        errors = validate_password_change("SamePassword1!", "SamePassword1!", "SamePassword1!")
        self.assertIn("New password cannot be the same as your current password.", errors)

        # New password too short
        errors = validate_password_change("OldPassword1!", "short", "short")
        self.assertIn("New password must be at least 8 characters.", errors)

        # Passwords mismatch
        errors = validate_password_change("OldPassword1!", "NewPassword123!", "MismatchPass123!")
        self.assertIn("New passwords do not match.", errors)


if __name__ == "__main__":
    unittest.main()

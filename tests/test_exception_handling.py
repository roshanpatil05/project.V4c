from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pymysql

from src.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseOperationError,
    DuplicateRecordError,
    ForeignKeyConstraintError,
    RecordNotFoundError,
    ValidationError,
    map_mysql_error,
    user_facing_error,
)
from src.managers import EmployeeManager, ProjectManager, ReviewManager
from src.models import Employee, Project, Review


class ExceptionHandlingTests(unittest.TestCase):
    def test_user_facing_error_with_custom_app_exceptions(self):
        conn_err = DatabaseConnectionError("Internal details: host=127.0.0.1 port=3306")
        self.assertEqual(
            user_facing_error(conn_err),
            "Unable to connect to the database. Please verify the database service is running.",
        )
        self.assertNotIn("127.0.0.1", user_facing_error(conn_err))

        dup_err = DuplicateRecordError("Internal: duplicate key 1062 on table employees.email")
        self.assertEqual(
            user_facing_error(dup_err),
            "A record with this information already exists.",
        )
        self.assertNotIn("employees.email", user_facing_error(dup_err))

        fk_err = ForeignKeyConstraintError("Internal: foreign key constraint fails on project_id")
        self.assertEqual(
            user_facing_error(fk_err),
            "This action could not be completed because related records depend on or are missing for this item.",
        )

    def test_user_facing_error_masks_raw_sql_leaks(self):
        raw_db_exc = RuntimeError(
            "Database operation failed: (1064, \"You have an error in your SQL syntax; check manual for SELECT * FROM employees WHERE\")"
        )
        msg = user_facing_error(raw_db_exc)
        self.assertNotIn("SELECT", msg)
        self.assertNotIn("employees", msg)
        self.assertNotIn("1064", msg)
        self.assertEqual(msg, "An unexpected system error occurred. Please try again later.")

    def test_user_facing_error_allows_safe_validation_errors(self):
        val_err = ValidationError("Annual salary must be greater than zero.")
        self.assertEqual(user_facing_error(val_err), "Annual salary must be greater than zero.")

        safe_val_err = ValueError("Employee ID must be a positive integer.")
        self.assertEqual(user_facing_error(safe_val_err), "Employee ID must be a positive integer.")

    def test_map_mysql_error_duplicate_entry(self):
        exc = pymysql.err.IntegrityError(1062, "Duplicate entry 'test@example.com' for key 'employees.email'")
        mapped = map_mysql_error(exc, operation="insert employee")
        self.assertIsInstance(mapped, DuplicateRecordError)
        self.assertIn("email address already exists", mapped.user_message)
        self.assertNotIn("employees.email", mapped.user_message)

    def test_map_mysql_error_foreign_key_delete(self):
        exc = pymysql.err.IntegrityError(1451, "Cannot delete or update a parent row: a foreign key constraint fails")
        mapped = map_mysql_error(exc, operation="delete project")
        self.assertIsInstance(mapped, ForeignKeyConstraintError)
        self.assertIn("other active records depend", mapped.user_message)

    def test_map_mysql_error_foreign_key_insert(self):
        exc = pymysql.err.IntegrityError(1452, "Cannot add or update a child row: a foreign key constraint fails")
        mapped = map_mysql_error(exc, operation="insert review")
        self.assertIsInstance(mapped, ForeignKeyConstraintError)
        self.assertIn("referenced department, employee, or project does not exist", mapped.user_message)

    def test_map_mysql_error_connection_refused(self):
        exc = pymysql.err.OperationalError(2003, "Can't connect to MySQL server on 'localhost' (61)")
        mapped = map_mysql_error(exc, operation="connection")
        self.assertIsInstance(mapped, DatabaseConnectionError)
        self.assertIn("temporarily unreachable", mapped.user_message)

    def test_model_validations(self):
        with self.assertRaises(ValidationError):
            Employee(first_name="", last_name="Smith", email="a@b.com", department_id=1, job_title="Dev", salary=50000).validate()

        with self.assertRaises(ValidationError):
            Employee(first_name="John", last_name="Smith", email="notanemail", department_id=1, job_title="Dev", salary=50000).validate()

        with self.assertRaises(ValidationError):
            Project(project_name="", department_id=1, budget=1000).validate()

        with self.assertRaises(ValidationError):
            Project(project_name="P1", department_id=1, budget=-50).validate()

        with self.assertRaises(ValidationError):
            Review(employee_id=0, review_date=date.today(), overall_score=50, rating="Strong").validate()

        with self.assertRaises(ValidationError):
            Review(employee_id=1, review_date=date.today(), overall_score=150, rating="Strong").validate()

    def test_project_manager_delete_with_assignments_rejected(self):
        pm = ProjectManager()
        pm.get_project = MagicMock(return_value={"project_id": 1, "project_name": "Phoenix"})
        pm.fetch_one = MagicMock(return_value={"cnt": 3})

        with self.assertRaises(ValidationError) as ctx:
            pm.delete_project(1)
        self.assertIn("Cannot delete project 'Phoenix' because active employee assignments are linked", str(ctx.exception))

    def test_project_manager_update_invalid_status_rejected(self):
        pm = ProjectManager()
        with self.assertRaises(ValidationError):
            pm.update_project(1, "Name", 1000.0, "invalid_status")

    def test_review_manager_update_invalid_score_rejected(self):
        rm = ReviewManager()
        with self.assertRaises(ValidationError):
            rm.update_review(1, 120.0, "Strong", "Good")

    def test_employee_manager_update_invalid_inputs(self):
        em = EmployeeManager()
        with self.assertRaises(ValidationError):
            em.update_salary(1, -500.0)
        with self.assertRaises(ValidationError):
            em.update_salary(1, 0.0)
        with self.assertRaises(ValidationError):
            em.update_department(1, 0)
        with self.assertRaises(ValidationError):
            em.update_department(-1, 2)


if __name__ == "__main__":
    unittest.main()

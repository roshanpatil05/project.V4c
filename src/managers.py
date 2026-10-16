from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from pymysql import Error as MySQLError

from src.database.db_manager import DatabaseConnection
from src.exceptions import (
    DatabaseError,
    DuplicateRecordError,
    ForeignKeyConstraintError,
    RecordNotFoundError,
    ValidationError,
    map_mysql_error,
)
from src.models import Employee, Project, Review

logger = logging.getLogger("employee_analytics.managers")


class EmployeeManager(DatabaseConnection):
    def list_departments(self) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT department_id, department_name FROM departments ORDER BY department_name")

    def create_employee(self, employee: Employee) -> int:
        employee.validate()
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            # Check department existence in warehouse first
            department = self.fetch_one(
                "SELECT department_key FROM dim_department WHERE department_id = %s",
                (employee.department_id,),
            )
            if department is None:
                raise ValidationError(f"Department ID {employee.department_id} does not exist in the warehouse.")

            cursor.execute(
                """INSERT INTO employees
                   (first_name, last_name, email, department_id, job_title, hire_date, manager_id, salary, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    employee.first_name, employee.last_name, employee.email, employee.department_id,
                    employee.job_title, employee.hire_date or date.today(), employee.manager_id,
                    employee.salary, employee.status,
                ),
            )
            employee.employee_id = int(cursor.lastrowid)

            cursor.execute(
                """INSERT INTO dim_employee
                   (employee_id, first_name, last_name, email, department_key, job_title,
                    hire_date, salary, start_date, end_date, is_current, attrition_risk)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, TRUE, 0)""",
                (
                    employee.employee_id, employee.first_name, employee.last_name, employee.email,
                    department["department_key"], employee.job_title, employee.hire_date or date.today(),
                    employee.salary, datetime.now(),
                )
            )
            connection.commit()
            return employee.employee_id
        except MySQLError as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            logger.error("Database error while creating employee: %s", exc, exc_info=True)
            raise map_mysql_error(exc, operation="create employee") from exc
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            cursor.close()

    def update_department(self, employee_id: int, new_department_id: int) -> None:
        if new_department_id < 1:
            raise ValidationError("Department ID must be a positive integer.")
        self._apply_scd2_change(employee_id, department_id=new_department_id)

    def update_job_title(self, employee_id: int, new_job_title: str) -> None:
        if not new_job_title or not new_job_title.strip():
            raise ValidationError("Job title cannot be empty.")
        self._apply_scd2_change(employee_id, job_title=new_job_title.strip())

    def update_department_and_role(self, employee_id: int, new_department_id: int, new_job_title: str) -> None:
        if new_department_id < 1:
            raise ValidationError("Department ID must be a positive integer.")
        if not new_job_title or not new_job_title.strip():
            raise ValidationError("Job title cannot be empty.")
        self._apply_scd2_change(employee_id, department_id=new_department_id, job_title=new_job_title.strip())

    def update_salary(self, employee_id: int, new_salary: float) -> None:
        if new_salary <= 0:
            raise ValidationError("Salary must be greater than zero.")
        self._apply_scd2_change(employee_id, salary=new_salary)

    def _apply_scd2_change(
        self,
        employee_id: int,
        department_id: int | None = None,
        job_title: str | None = None,
        salary: float | None = None,
    ) -> None:
        if employee_id < 1:
            raise ValidationError("Employee ID must be a positive integer.")
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT * FROM employees WHERE employee_id = %s FOR UPDATE",
                (employee_id,),
            )
            employee = cursor.fetchone()
            if employee is None:
                raise RecordNotFoundError(f"Employee {employee_id} does not exist.")
            if employee["status"] != "active":
                raise ValidationError(f"Employee {employee_id} is inactive and cannot be updated.")
            next_department_id = department_id if department_id is not None else employee["department_id"]
            next_job_title = job_title.strip() if job_title is not None else employee["job_title"]
            next_salary = salary if salary is not None else employee["salary"]
            cursor.execute(
                "SELECT department_key FROM dim_department WHERE department_id = %s",
                (next_department_id,),
            )
            department = cursor.fetchone()
            if department is None:
                raise ValidationError(f"Department {next_department_id} does not exist.")
            cursor.execute(
                "SELECT * FROM dim_employee WHERE employee_id = %s AND is_current = TRUE FOR UPDATE",
                (employee_id,),
            )
            current = cursor.fetchone()
            if current is None:
                raise ValidationError(f"Current warehouse version for employee {employee_id} is missing.")
            if (
                current["department_key"] == department["department_key"]
                and current.get("job_title") == next_job_title
                and float(current["salary"]) == float(next_salary)
            ):
                connection.rollback()
                return

            now = datetime.now()
            curr_start = current.get("start_date")
            if curr_start is not None:
                if isinstance(curr_start, date) and not isinstance(curr_start, datetime):
                    curr_start = datetime.combine(curr_start, datetime.min.time())
                if now <= curr_start:
                    effective_time = curr_start + timedelta(seconds=1)
                else:
                    effective_time = now
            else:
                effective_time = now

            cursor.execute(
                "UPDATE dim_employee SET end_date = %s, is_current = FALSE WHERE employee_key = %s",
                (effective_time, current["employee_key"]),
            )
            cursor.execute(
                "UPDATE employees SET department_id = %s, job_title = %s, salary = %s WHERE employee_id = %s",
                (next_department_id, next_job_title, next_salary, employee_id),
            )
            cursor.execute(
                """INSERT INTO dim_employee
                   (employee_id, first_name, last_name, email, department_key, job_title,
                    hire_date, salary, start_date, end_date, is_current, attrition_risk)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, TRUE, 0)""",
                (
                    employee_id, employee["first_name"], employee["last_name"], employee["email"],
                    department["department_key"], next_job_title, employee["hire_date"],
                    next_salary, effective_time,
                ),
            )
            connection.commit()
        except MySQLError as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            logger.error("Database error in _apply_scd2_change for employee %s: %s", employee_id, exc, exc_info=True)
            raise map_mysql_error(exc, operation="update employee SCD2") from exc
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            cursor.close()

    def list_employees(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT employee_id, first_name, last_name, email, department_id, job_title, salary, status "
            "FROM employees WHERE status = 'active' ORDER BY employee_id DESC LIMIT %s",
            (limit,),
        )

    def get_employee(self, employee_id: int) -> dict[str, Any] | None:
        if employee_id < 1:
            raise ValidationError("Employee ID must be a positive integer.")
        return self.fetch_one(
            "SELECT * FROM employees WHERE employee_id = %s",
            (employee_id,)
        )

    def delete_employee(self, employee_id: int) -> None:
        """Deactivate an employee while preserving reviews, assignments, and SCD2 history."""
        if employee_id < 1:
            raise ValidationError("Employee ID must be a positive integer.")
        connection = self.get_connection()
        cursor = connection.cursor()
        today = date.today()

        try:
            # Lock and verify the OLTP employee row before changing anything.
            cursor.execute(
                "SELECT employee_id, status FROM employees WHERE employee_id = %s FOR UPDATE",
                (employee_id,),
            )
            employee = cursor.fetchone()

            if employee is None:
                raise RecordNotFoundError(f"Employee {employee_id} does not exist.")

            if employee["status"] == "inactive":
                raise ValidationError(f"Employee {employee_id} is already inactive.")

            # Lock the current warehouse version, if one exists.
            cursor.execute(
                """SELECT employee_key
                   FROM dim_employee
                   WHERE employee_id = %s AND is_current = TRUE
                   FOR UPDATE""",
                (employee_id,),
            )
            current = cursor.fetchone()

            # Deactivate the OLTP record.
            cursor.execute(
                "UPDATE employees SET status = 'inactive' WHERE employee_id = %s",
                (employee_id,),
            )

            # Close the current SCD Type 2 version. Do not delete prior versions.
            if current:
                cursor.execute(
                    """UPDATE dim_employee
                       SET end_date = %s, is_current = FALSE
                       WHERE employee_key = %s""",
                    (today, current["employee_key"]),
                )

            # Keep existing performance reviews and project assignments for history.
            connection.commit()

        except MySQLError as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            logger.error("Database error while deactivating employee %s: %s", employee_id, exc, exc_info=True)
            raise map_mysql_error(exc, operation="deactivate employee") from exc
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            cursor.close()

    def get_employees_export(
        self,
        department_id: int | None = None,
        include_salary: bool = False,
    ) -> list[dict[str, Any]]:
        """Return workforce roster formatted for CSV export, respecting salary visibility."""
        if include_salary:
            query = """
                SELECT 
                    e.employee_id,
                    e.first_name,
                    e.last_name,
                    e.email,
                    COALESCE(d.department_name, 'Unassigned') AS department,
                    e.job_title,
                    e.hire_date,
                    e.salary,
                    e.performance_score,
                    e.attrition_risk,
                    e.status
                FROM employees e
                LEFT JOIN departments d ON d.department_id = e.department_id
                WHERE (%s IS NULL OR e.department_id = %s)
                ORDER BY e.employee_id ASC
            """
        else:
            query = """
                SELECT 
                    e.employee_id,
                    e.first_name,
                    e.last_name,
                    e.email,
                    COALESCE(d.department_name, 'Unassigned') AS department,
                    e.job_title,
                    e.hire_date,
                    e.performance_score,
                    e.attrition_risk,
                    e.status
                FROM employees e
                LEFT JOIN departments d ON d.department_id = e.department_id
                WHERE (%s IS NULL OR e.department_id = %s)
                ORDER BY e.employee_id ASC
            """
        return self.fetch_all(query, (department_id, department_id))


class ProjectManager(DatabaseConnection):
    def create_project(self, project: Project) -> int:
        project.validate()
        dept = self.fetch_one(
            "SELECT department_id FROM departments WHERE department_id = %s",
            (project.department_id,),
        )
        if dept is None:
            raise ValidationError(f"Department ID {project.department_id} does not exist.")

        cursor = self.execute(
            """INSERT INTO projects
               (project_name, department_id, budget, start_date, end_date, status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                project.project_name, project.department_id, project.budget,
                project.start_date, project.end_date, project.status,
            ),
            commit=True,
        )
        try:
            project.project_id = int(cursor.lastrowid)
            return project.project_id
        finally:
            cursor.close()

    def assign_employee(
        self,
        employee_id: int,
        project_id: int,
        allocation_pct: float = 100,
    ) -> None:
        if employee_id < 1 or project_id < 1:
            raise ValidationError("Employee ID and Project ID must be positive integers.")
        if not 0 < allocation_pct <= 100:
            raise ValidationError("Allocation must be greater than 0 and at most 100 percent.")

        employee = self.fetch_one(
            "SELECT employee_id, status FROM employees WHERE employee_id = %s",
            (employee_id,),
        )
        if employee is None:
            raise RecordNotFoundError(f"Employee {employee_id} does not exist.")
        if employee["status"] != "active":
            raise ValidationError(
                f"Employee {employee_id} is inactive and cannot be assigned to a project."
            )

        project = self.fetch_one(
            "SELECT project_id, status FROM projects WHERE project_id = %s",
            (project_id,),
        )
        if project is None:
            raise RecordNotFoundError(f"Project {project_id} does not exist.")
        if project["status"] != "active":
            raise ValidationError(
                f"Project {project_id} is not active and cannot receive new assignments."
            )

        cursor = self.execute(
            """INSERT INTO project_assignments
               (employee_id, project_id, allocation_pct, assigned_date)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   allocation_pct = VALUES(allocation_pct),
                   assigned_date = VALUES(assigned_date)""",
            (employee_id, project_id, allocation_pct, date.today()),
            commit=True,
        )
        cursor.close()

    def get_employee_assignments(self, employee_id: int) -> list[dict[str, Any]]:
        """Return all project assignments for an employee with project and department details."""
        if employee_id < 1:
            raise ValidationError("Employee ID must be a positive integer.")
        return self.fetch_all(
            """
            SELECT pa.assignment_id, pa.project_id, p.project_name, d.department_name,
                   p.status, p.budget, pa.allocation_pct, pa.assigned_date,
                   p.start_date, p.end_date
            FROM project_assignments pa
            JOIN projects p ON p.project_id = pa.project_id
            LEFT JOIN departments d ON d.department_id = p.department_id
            WHERE pa.employee_id = %s
            ORDER BY pa.assigned_date DESC, pa.assignment_id DESC
            """,
            (employee_id,),
        )

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        if project_id < 1:
            raise ValidationError("Project ID must be a positive integer.")
        return self.fetch_one("SELECT * FROM projects WHERE project_id = %s", (project_id,))

    def list_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM projects ORDER BY project_id DESC LIMIT %s", (limit,))

    def update_project(self, project_id: int, project_name: str, budget: float, status: str) -> None:
        if project_id < 1:
            raise ValidationError("Project ID must be a positive integer.")
        if not project_name.strip():
            raise ValidationError("Project name cannot be empty.")
        if budget < 0:
            raise ValidationError("Budget cannot be negative.")
        valid_statuses = {"planned", "active", "completed", "on_hold"}
        if status not in valid_statuses:
            raise ValidationError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}.")

        proj = self.get_project(project_id)
        if proj is None:
            raise RecordNotFoundError(f"Project {project_id} does not exist.")

        cursor = self.execute(
            "UPDATE projects SET project_name = %s, budget = %s, status = %s WHERE project_id = %s",
            (project_name.strip(), budget, status, project_id),
            commit=True,
        )
        cursor.close()

    def delete_project(self, project_id: int) -> None:
        if project_id < 1:
            raise ValidationError("Project ID must be a positive integer.")
        proj = self.get_project(project_id)
        if proj is None:
            raise RecordNotFoundError(f"Project {project_id} does not exist.")

        # Check for active assignments to give a clean user-friendly message rather than a raw FK database error
        assignment = self.fetch_one(
            "SELECT COUNT(*) AS cnt FROM project_assignments WHERE project_id = %s",
            (project_id,),
        )
        if assignment and assignment.get("cnt", 0) > 0:
            raise ValidationError(
                f"Cannot delete project '{proj['project_name']}' because active employee assignments are linked to it. Remove assignments first."
            )

        cursor = self.execute("DELETE FROM projects WHERE project_id = %s", (project_id,), commit=True)
        cursor.close()

    def get_projects_timeline(
        self,
        department_id: int | None = None,
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        """Return projects with schedule dates and dynamic staffing burn-down metrics."""
        query = """
            SELECT 
                p.project_id,
                p.project_name,
                p.department_id,
                COALESCE(d.department_name, 'Unassigned') AS department_name,
                p.status,
                p.budget,
                p.start_date,
                p.end_date,
                COUNT(DISTINCT pa.employee_id) AS staff_count,
                COALESCE(SUM(pa.allocation_pct), 0) AS total_allocation_pct,
                COALESCE(SUM(e.salary * (pa.allocation_pct / 100.0)), 0) AS annual_staffing_burn,
                COALESCE(SUM(e.salary * (pa.allocation_pct / 100.0)) / 12.0, 0) AS monthly_staffing_burn
            FROM projects p
            LEFT JOIN departments d ON d.department_id = p.department_id
            LEFT JOIN project_assignments pa ON pa.project_id = p.project_id
            LEFT JOIN employees e ON e.employee_id = pa.employee_id AND e.status = 'active'
            WHERE (%s IS NULL OR p.department_id = %s)
            GROUP BY p.project_id, p.project_name, p.department_id, d.department_name, p.status, p.budget, p.start_date, p.end_date
            ORDER BY p.start_date ASC, p.project_id ASC
            LIMIT %s
        """
        return self.fetch_all(query, (department_id, department_id, limit))

    def get_staffing_allocation_matrix(
        self,
        department_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return project-to-employee staffing allocation matrix for export."""
        query = """
            SELECT 
                p.project_id,
                p.project_name,
                COALESCE(d.department_name, 'Unassigned') AS project_department,
                p.status AS project_status,
                p.budget AS project_budget,
                p.start_date,
                p.end_date,
                e.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                COALESCE(ed.department_name, 'Unassigned') AS employee_department,
                e.job_title,
                pa.allocation_pct,
                pa.assigned_date
            FROM project_assignments pa
            JOIN projects p ON p.project_id = pa.project_id
            LEFT JOIN departments d ON d.department_id = p.department_id
            JOIN employees e ON e.employee_id = pa.employee_id
            LEFT JOIN departments ed ON ed.department_id = e.department_id
            WHERE (%s IS NULL OR p.department_id = %s)
            ORDER BY p.project_name, e.last_name
        """
        return self.fetch_all(query, (department_id, department_id))


class ReviewManager(DatabaseConnection):
    def create_review(self, review: Review) -> int:
        review.validate()
        emp = self.fetch_one(
            "SELECT employee_id FROM employees WHERE employee_id = %s",
            (review.employee_id,),
        )
        if emp is None:
            raise RecordNotFoundError(f"Employee {review.employee_id} does not exist.")

        cursor = self.execute(
            """INSERT INTO performance_reviews
               (employee_id, review_date, manager_id, overall_score, rating, comments)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                review.employee_id, review.review_date, review.manager_id,
                review.overall_score, review.rating, review.comments,
            ),
            commit=True,
        )
        try:
            return int(cursor.lastrowid)
        finally:
            cursor.close()

    def get_employee_reviews(self, employee_id: int) -> list[dict[str, Any]]:
        """Return all performance reviews for a specific employee ordered latest first."""
        if employee_id < 1:
            raise ValidationError("Employee ID must be a positive integer.")
        return self.fetch_all(
            """
            SELECT r.review_id, r.employee_id, r.review_date, r.overall_score,
                   r.rating, r.comments, r.manager_id,
                   m.first_name AS mgr_first, m.last_name AS mgr_last, m.job_title AS mgr_title
            FROM performance_reviews r
            LEFT JOIN employees m ON m.employee_id = r.manager_id
            WHERE r.employee_id = %s
            ORDER BY r.review_date DESC, r.review_id DESC
            """,
            (employee_id,),
        )

    def get_review(self, review_id: int) -> dict[str, Any] | None:
        if review_id < 1:
            raise ValidationError("Review ID must be a positive integer.")
        return self.fetch_one("SELECT * FROM performance_reviews WHERE review_id = %s", (review_id,))

    def list_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM performance_reviews ORDER BY review_date DESC LIMIT %s", (limit,))

    def delete_review(self, review_id: int) -> None:
        if review_id < 1:
            raise ValidationError("Review ID must be a positive integer.")
        rev = self.get_review(review_id)
        if rev is None:
            raise RecordNotFoundError(f"Review {review_id} does not exist.")
        cursor = self.execute("DELETE FROM performance_reviews WHERE review_id = %s", (review_id,), commit=True)
        cursor.close()

    def update_review(self, review_id: int, overall_score: float, rating: str, comments: str) -> None:
        if review_id < 1:
            raise ValidationError("Review ID must be a positive integer.")
        if not 0 <= overall_score <= 100:
            raise ValidationError("Overall score must be between 0 and 100.")
        valid_ratings = {"Exceeds Expectations", "Strong", "Meets Expectations", "Needs Improvement"}
        if rating not in valid_ratings:
            raise ValidationError(f"Invalid rating '{rating}'.")

        rev = self.get_review(review_id)
        if rev is None:
            raise RecordNotFoundError(f"Review {review_id} does not exist.")

        cursor = self.execute(
            "UPDATE performance_reviews SET overall_score = %s, rating = %s, comments = %s WHERE review_id = %s",
            (overall_score, rating, comments, review_id),
            commit=True,
        )
        cursor.close()

    def get_reviews_export(
        self,
        department_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return performance review history for export."""
        query = """
            SELECT 
                r.review_id,
                r.employee_id,
                CONCAT(e.first_name, ' ', e.last_name) AS employee_name,
                COALESCE(d.department_name, 'Unassigned') AS department,
                e.job_title,
                r.review_date,
                r.overall_score,
                r.rating,
                CONCAT(COALESCE(m.first_name, ''), ' ', COALESCE(m.last_name, '')) AS manager_name,
                r.comments
            FROM performance_reviews r
            JOIN employees e ON e.employee_id = r.employee_id
            LEFT JOIN departments d ON d.department_id = e.department_id
            LEFT JOIN employees m ON m.employee_id = r.manager_id
            WHERE (%s IS NULL OR e.department_id = %s)
            ORDER BY r.review_date DESC, r.review_id DESC
        """
        return self.fetch_all(query, (department_id, department_id))


class AnalyticsManager(DatabaseConnection):
    def get_performance_trends(self, department_basis: str = "review", department_name: str | None = None) -> list[dict[str, Any]]:
        employee_join = {
            "review": """JOIN dim_employee e
                ON e.employee_id = f.employee_id
                AND f.review_date >= e.start_date
                AND (e.end_date IS NULL OR f.review_date < e.end_date)""",
            "current": """JOIN dim_employee e
                ON e.employee_id = f.employee_id AND e.is_current = TRUE""",
        }
        if department_basis not in employee_join:
            raise ValidationError("department_basis must be 'review' or 'current'")
            
        where_clause = ""
        params: list[Any] = []
        if department_name and department_name != "All departments":
            where_clause = "WHERE d.department_name = %s"
            params.append(department_name)
            
        query = f"""
            SELECT YEAR(f.review_date) AS review_year, AVG(f.overall_score) AS avg_score
            FROM fact_performance_reviews f
            {employee_join[department_basis]}
            JOIN dim_department d ON d.department_key = e.department_key
            {where_clause}
            GROUP BY YEAR(f.review_date)
            ORDER BY review_year
        """
        return self.fetch_all(query, tuple(params) if params else None)

    def get_top_performers(self, department_basis: str = "review", department_name: str | None = None) -> list[dict[str, Any]]:
        employee_join = {
            "review": """JOIN dim_employee e
                ON e.employee_id = f.employee_id
                AND f.review_date >= e.start_date
                AND (e.end_date IS NULL OR f.review_date < e.end_date)""",
            "current": """JOIN dim_employee e
                ON e.employee_id = f.employee_id AND e.is_current = TRUE""",
        }
        if department_basis not in employee_join:
            raise ValidationError("department_basis must be 'review' or 'current'")
            
        where_clause = ""
        params: list[Any] = []
        if department_name and department_name != "All departments":
            where_clause = "WHERE d.department_name = %s"
            params.append(department_name)
            
        query = f"""
            WITH employee_scores AS (
                SELECT f.employee_id, e.first_name, e.last_name,
                       d.department_name, AVG(f.overall_score) AS overall_score
                FROM fact_performance_reviews f
                {employee_join[department_basis]}
                JOIN dim_department d ON d.department_key = e.department_key
                {where_clause}
                GROUP BY f.employee_id, e.first_name, e.last_name, d.department_name
            ), ranked AS (
                SELECT employee_id, first_name, last_name, department_name, overall_score,
                       DENSE_RANK() OVER (
                           PARTITION BY department_name ORDER BY overall_score DESC
                       ) AS department_rank
                FROM employee_scores
            )
            SELECT * FROM ranked
            WHERE department_rank <= 5
            ORDER BY department_name, department_rank, employee_id
        """
        return self.fetch_all(query, tuple(params) if params else None)

    def get_attrition_risk(self, department_name: str | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE e.is_current = TRUE"
        params: list[Any] = []
        if department_name and department_name != "All departments":
            where_clause += " AND d.department_name = %s"
            params.append(department_name)
            
        query = f"""SELECT d.department_name, COUNT(*) AS employees,
                      AVG(e.performance_score) AS avg_performance,
                      AVG(e.attrition_risk) AS avg_attrition_risk
               FROM dim_employee e
               JOIN dim_department d ON d.department_key = e.department_key
               {where_clause}
               GROUP BY d.department_name ORDER BY avg_attrition_risk DESC"""
        return self.fetch_all(query, tuple(params) if params else None)

    def get_project_bottlenecks(self, department_name: str | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE p.status = 'active'"
        params: list[Any] = []
        if department_name and department_name != "All departments":
            where_clause += " AND d.department_name = %s"
            params.append(department_name)
            
        query = f"""SELECT p.project_id, p.project_name, d.department_name, p.budget,
                      COUNT(e.employee_id) AS assigned_employees,
                      COALESCE(SUM(CASE WHEN e.employee_id IS NOT NULL THEN a.allocation_pct ELSE 0 END), 0) AS total_allocation_pct
               FROM projects p
               JOIN departments d ON p.department_id = d.department_id
               LEFT JOIN project_assignments a ON p.project_id = a.project_id
               LEFT JOIN employees e ON a.employee_id = e.employee_id AND e.status = 'active'
               {where_clause}
               GROUP BY p.project_id, p.project_name, d.department_name, p.budget
               ORDER BY total_allocation_pct ASC, assigned_employees ASC
               LIMIT 10"""
        return self.fetch_all(query, tuple(params) if params else None)

    def get_overview_metrics(self) -> dict[str, Any]:
        total_emp_row = self.fetch_one("SELECT COUNT(*) as count FROM employees WHERE status = 'active'")
        total_employees = total_emp_row["count"] if total_emp_row else 0

        dept_row = self.fetch_one("SELECT COUNT(*) as count FROM departments")
        total_departments = dept_row["count"] if dept_row else 0

        avg_score_row = self.fetch_one("SELECT AVG(overall_score) as avg_score FROM performance_reviews")
        avg_score = float(avg_score_row["avg_score"]) if (avg_score_row and avg_score_row["avg_score"] is not None) else 0.0

        distribution = self.fetch_all("""
            SELECT d.department_name, COUNT(e.employee_id) as size
            FROM employees e
            JOIN departments d ON e.department_id = d.department_id
            WHERE e.status = 'active'
            GROUP BY d.department_name
            ORDER BY size ASC
        """) or []

        return {
            "total_employees": total_employees,
            "total_departments": total_departments,
            "average_score": avg_score,
            "distribution": distribution,
        }


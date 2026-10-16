from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.ETL.extractor import CSVExtractor
from src.ETL.transformer import DataTransformer
from src.database.db_manager import DatabaseConnection


class DataWarehouseLoader(DatabaseConnection):
	"""Load synthesized employee snapshots and SCD2 versions into MySQL."""

	batch_size = 1_000

	def load_synthesized_data(
		self,
		employee_path: str | Path,
		history_path: str | Path,
		review_path: str | Path | None = None,
		project_path: str | Path | None = None,
		assignment_path: str | Path | None = None,
	) -> None:
		print("\nExtracting CSV files into memory.")
		extractor = CSVExtractor()
		employees = extractor.extract(employee_path)
		raw_history = extractor.extract(history_path)
		versions = DataTransformer.build_employee_history(employees, raw_history)
		connection = self.get_connection()
		try:
			print("Loading departments.")
			self._load_departments(connection, employees["department_name"].unique())
			
			if project_path is not None and Path(project_path).exists():
				projects = extractor.extract(project_path)
				print(f"Loading {len(projects)} projects.")
				self._load_oltp_projects(connection, projects)
				
			print(f"Loading {len(employees)} employee records.")
			self._load_oltp_employees(connection, employees)
			
			if assignment_path is not None and Path(assignment_path).exists():
				assignments = extractor.extract(assignment_path)
				print(f"Loading {len(assignments)} project assignments.")
				self._load_oltp_assignments(connection, assignments)
				
			if review_path is not None and Path(review_path).exists():
				reviews = extractor.extract(review_path)
				print(f"Loading {len(reviews)} performance reviews.")
				self._load_oltp_reviews(connection, reviews)
				
			print(f"Loading {len(versions)} employee SCD2 historical versions.")
			self._load_employee_versions(connection, versions)
			connection.commit()
		except Exception:
			connection.rollback()
			raise
		
		if review_path is not None:
			print("Triggering Stored Procedures for Data Warehouse facts...")
			self.load_review_facts()
			print("ETL pipeline finished!")

	def _load_oltp_projects(self, connection, projects: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO projects (project_id, project_name, department_id, budget, status)
			VALUES (%s, %s, %s, %s, %s)
		"""
		for start in range(0, len(projects), self.batch_size):
			batch = projects.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.project_id), row.project_name, self._department_ids[row.department_name],
					float(row.budget), row.status
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def _load_oltp_assignments(self, connection, assignments: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO project_assignments (assignment_id, project_id, employee_id, allocation_pct, assigned_date)
			VALUES (%s, %s, %s, %s, %s)
		"""
		for start in range(0, len(assignments), self.batch_size):
			batch = assignments.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.assignment_id), int(row.project_id), int(row.employee_id),
					int(row.allocation_pct), row.assigned_date
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def _load_oltp_reviews(self, connection, reviews: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO performance_reviews (review_id, employee_id, review_date, overall_score, rating, comments)
			VALUES (%s, %s, %s, %s, %s, %s)
		"""
		for start in range(0, len(reviews), self.batch_size):
			batch = reviews.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.review_id), int(row.employee_id), row.review_date.date(),
					float(row.overall_score), row.rating, row.comments,
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def _load_departments(self, connection, department_names: Iterable[str]) -> None:
		cursor = connection.cursor()
		cursor.executemany(
			"INSERT INTO departments (department_name) VALUES (%s)",
			[(name,) for name in department_names],
		)
		cursor.execute("SELECT department_id, department_name FROM departments")
		self._department_ids = {row["department_name"]: row["department_id"] for row in cursor.fetchall()}
		cursor.executemany(
			"INSERT INTO dim_department (department_id, department_name) VALUES (%s, %s)",
			[(department_id, name) for name, department_id in self._department_ids.items()],
		)
		cursor.execute("SELECT department_key, department_id FROM dim_department")
		self._department_keys = {row["department_id"]: row["department_key"] for row in cursor.fetchall()}
		cursor.close()

	def _load_oltp_employees(self, connection, employees: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO employees (
				employee_id, first_name, last_name, email, department_id,
				job_title, hire_date, salary, performance_score, attrition_risk, status
			) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		"""
		for start in range(0, len(employees), self.batch_size):
			batch = employees.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.employee_id), row.first_name, row.last_name, row.email,
					self._department_ids[row.department_name], row.job_title,
					row.hire_date.date(), float(row.salary), int(row.performance_score),
					int(row.attrition_risk), 'active'
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

	def load_review_facts(self) -> None:
		connection = self.get_connection()
		cursor = connection.cursor()
		try:
			cursor.execute("CALL sp_etl_dim_date()")
			cursor.execute("CALL sp_etl_dim_project()")
			cursor.execute("CALL sp_etl_fact_reviews()")
			connection.commit()
		except Exception:
			connection.rollback()
			raise
		finally:
			cursor.close()

	def _load_employee_versions(self, connection, versions: pd.DataFrame) -> None:
		cursor = connection.cursor()
		query = """
			INSERT INTO dim_employee (
				employee_id, first_name, last_name, email, department_key,
				job_title, hire_date, salary, performance_score, attrition_risk,
				start_date, end_date, is_current
			) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		"""
		for start in range(0, len(versions), self.batch_size):
			batch = versions.iloc[start : start + self.batch_size]
			cursor.executemany(query, [
				(
					int(row.employee_id), row.first_name, row.last_name, row.email,
					self._department_keys[self._department_ids[row.department_name]], row.job_title,
					row.hire_date.date(), float(row.salary), int(row.performance_score),
					int(row.attrition_risk),
					row.start_date.to_pydatetime() if hasattr(row.start_date, "to_pydatetime") else row.start_date,
					row.end_date.to_pydatetime() if pd.notna(row.end_date) and hasattr(row.end_date, "to_pydatetime") else (row.end_date if pd.notna(row.end_date) else None),
					bool(row.is_current),
				)
				for row in batch.itertuples(index=False)
			])
		cursor.close()

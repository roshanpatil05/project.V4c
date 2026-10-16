from __future__ import annotations

import logging
from threading import RLock
from typing import Any

import pymysql
import pymysql.cursors
from pymysql import Error as MySQLError

from src.config.settings import settings
from src.exceptions import (
	DatabaseConnectionError,
	DatabaseError,
	DatabaseOperationError,
	map_mysql_error,
)

logger = logging.getLogger("employee_analytics.database")


class DatabaseConnection:
	"""Singleton owner for the application's MySQL connection."""

	_instances: dict[type, DatabaseConnection] = {}
	_instance_lock = RLock()

	def __new__(cls) -> DatabaseConnection:
		with cls._instance_lock:
			if cls not in cls._instances:
				cls._instances[cls] = super().__new__(cls)
		return cls._instances[cls]

	def __init__(self) -> None:
		if getattr(self, "_initialized", False):
			return
		self._connection = None
		self._connection_lock = RLock()
		self._initialized = True

	def _is_alive(self) -> bool:
		"""Check whether the current connection is usable."""
		if self._connection is None:
			return False
		try:
			self._connection.ping(reconnect=False)
			return True
		except Exception:
			return False

	def get_connection(self):
		with self._connection_lock:
			try:
				if not self._is_alive():
					connect_kwargs = {
						"host": settings.host,
						"port": settings.port,
						"user": settings.user,
						"password": settings.password,
						"database": settings.database,
						"cursorclass": pymysql.cursors.DictCursor,
					}
					if getattr(settings, "ssl_mode", "") or "aivencloud.com" in settings.host:
						ssl_mode = getattr(settings, "ssl_mode", "") or "REQUIRED"
						connect_kwargs["ssl"] = {"ssl_mode": ssl_mode}
					self._connection = pymysql.connect(**connect_kwargs)
				return self._connection
			except MySQLError as exc:
				logger.error("Failed to connect to MySQL database: %s", exc, exc_info=True)
				raise map_mysql_error(exc, operation="connection") from exc
			except Exception as exc:
				logger.error("Unexpected error establishing MySQL connection: %s", exc, exc_info=True)
				raise DatabaseConnectionError(
					f"Unexpected connection error: {exc}",
					user_message="Unable to connect to the database. Please verify the database service is running.",
					original_error=exc,
				) from exc

	def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None, commit: bool = False):
		if params is None:
			params = ()
		connection = self.get_connection()
		cursor = connection.cursor()
		try:
			cursor.execute(query, params)
			if commit:
				connection.commit()
			return cursor
		except MySQLError as exc:
			try:
				connection.rollback()
			except Exception as rb_exc:
				logger.warning("Rollback failed after query error: %s", rb_exc)
			finally:
				cursor.close()
			logger.error("Database query execution failed: %s | Query: %s", exc, query, exc_info=True)
			raise map_mysql_error(exc, operation="query") from exc
		except Exception as exc:
			try:
				connection.rollback()
			except Exception:
				pass
			finally:
				cursor.close()
			logger.error("Unexpected error during query execution: %s | Query: %s", exc, query, exc_info=True)
			raise DatabaseOperationError(
				f"Unexpected query error: {exc}",
				user_message="A database error occurred while processing your request. Please try again later.",
				original_error=exc,
			) from exc

	def fetch_all(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> list[dict[str, Any]]:
		try:
			# Commit any open read-transaction so InnoDB gives a fresh snapshot.
			self.get_connection().commit()
		except Exception as exc:
			logger.debug("Non-fatal commit before fetch_all: %s", exc)

		cursor = self.execute(query, params)
		try:
			return cursor.fetchall()
		except MySQLError as exc:
			logger.error("Error fetching results: %s", exc, exc_info=True)
			raise map_mysql_error(exc, operation="fetch_all") from exc
		finally:
			cursor.close()

	def fetch_one(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> dict[str, Any] | None:
		try:
			# Commit any open read-transaction so InnoDB gives a fresh snapshot.
			self.get_connection().commit()
		except Exception as exc:
			logger.debug("Non-fatal commit before fetch_one: %s", exc)

		cursor = self.execute(query, params)
		try:
			return cursor.fetchone()
		except MySQLError as exc:
			logger.error("Error fetching single result: %s", exc, exc_info=True)
			raise map_mysql_error(exc, operation="fetch_one") from exc
		finally:
			cursor.close()

	def close(self) -> None:
		with self._connection_lock:
			if self._connection is not None:
				try:
					self._connection.close()
				except Exception as exc:
					logger.debug("Non-fatal error closing connection: %s", exc)
			self._connection = None



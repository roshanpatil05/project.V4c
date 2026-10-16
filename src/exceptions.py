from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("employee_analytics")


class AppError(Exception):
    """Base application exception with a developer message and a user-facing message."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message or message


class DatabaseError(AppError, RuntimeError):
    """Base exception for all database errors. Inherits from RuntimeError for backwards compatibility."""

    def __init__(
        self,
        message: str,
        user_message: str | None = None,
        original_error: Exception | None = None,
    ):
        default_user = "A database error occurred while processing your request. Please try again later."
        super().__init__(message, user_message or default_user)
        self.original_error = original_error


class DatabaseConnectionError(DatabaseError):
    """Raised when connecting to the database fails."""

    def __init__(
        self,
        message: str = "Database connection failed",
        user_message: str | None = None,
        original_error: Exception | None = None,
    ):
        default_user = "Unable to connect to the database. Please verify the database service is running."
        super().__init__(message, user_message or default_user, original_error=original_error)


class DatabaseOperationError(DatabaseError):
    """Raised when a query or execution fails."""

    def __init__(
        self,
        message: str = "Database operation failed",
        user_message: str | None = None,
        original_error: Exception | None = None,
    ):
        default_user = "A database error occurred while processing your request. Please try again later."
        super().__init__(message, user_message or default_user, original_error=original_error)


class DuplicateRecordError(DatabaseOperationError):
    """Raised when an operation violates a uniqueness constraint (e.g., duplicate email)."""

    def __init__(
        self,
        message: str = "Record already exists",
        user_message: str | None = None,
        original_error: Exception | None = None,
    ):
        default_user = "A record with this information already exists."
        super().__init__(message, user_message or default_user, original_error=original_error)


class ForeignKeyConstraintError(DatabaseOperationError):
    """Raised when an operation violates a foreign key constraint."""

    def __init__(
        self,
        message: str = "Foreign key constraint violation",
        user_message: str | None = None,
        original_error: Exception | None = None,
    ):
        default_user = "This action could not be completed because related records depend on or are missing for this item."
        super().__init__(message, user_message or default_user, original_error=original_error)


class RecordNotFoundError(AppError, ValueError):
    """Raised when a requested record does not exist."""

    def __init__(self, message: str = "Record not found", user_message: str | None = None):
        super().__init__(message, user_message or message)


class ValidationError(AppError, ValueError):
    """Raised when user input validation fails."""

    def __init__(self, message: str = "Invalid input", user_message: str | None = None):
        super().__init__(message, user_message or message)


def map_mysql_error(exc: Exception, operation: str = "operation") -> DatabaseError:
    """Map a raw PyMySQL error to a typed DatabaseError with a sanitized user message."""
    errno: int | None = None
    if hasattr(exc, "args") and len(exc.args) > 0 and isinstance(exc.args[0], int):
        errno = exc.args[0]

    err_str = str(exc)

    # 1062 = ER_DUP_ENTRY
    if errno == 1062 or "duplicate entry" in err_str.lower():
        if "email" in err_str.lower():
            user_msg = "An employee with this email address already exists."
        else:
            user_msg = "A record with these details already exists."
        return DuplicateRecordError(
            f"Duplicate record during {operation}: {exc}",
            user_message=user_msg,
            original_error=exc,
        )

    # 1451 = ER_ROW_IS_REFERENCED_2, 1217 = ER_ROW_IS_REFERENCED
    if errno in (1451, 1217) or "foreign key constraint fails" in err_str.lower() and "delete" in err_str.lower():
        return ForeignKeyConstraintError(
            f"Cannot delete or update record because dependent records exist: {exc}",
            user_message="Cannot complete this operation because other active records depend on this item.",
            original_error=exc,
        )

    # 1452 = ER_NO_REFERENCED_ROW_2, 1216 = ER_NO_REFERENCED_ROW
    if errno in (1452, 1216) or "cannot add or update a child row" in err_str.lower():
        return ForeignKeyConstraintError(
            f"Referenced foreign record does not exist: {exc}",
            user_message="The referenced department, employee, or project does not exist.",
            original_error=exc,
        )

    # Connection errors: 2003 (Can't connect), 2006 (Server gone), 2013 (Connection lost), 1045 (Access denied), 1049 (Unknown db)
    if errno in (2003, 2006, 2013, 1045, 1049) or any(
        phrase in err_str.lower()
        for phrase in ("can't connect to mysql", "server has gone away", "lost connection", "access denied")
    ):
        return DatabaseConnectionError(
            f"Database connection error during {operation}: {exc}",
            user_message="Database is temporarily unreachable. Please verify the database service is running.",
            original_error=exc,
        )

    # Generic database error
    return DatabaseOperationError(
        f"Database {operation} failed: {exc}",
        user_message="A database error occurred while processing your request. Please try again later.",
        original_error=exc,
    )


_DB_LEAK_KEYWORDS = {
    "select", "insert", "update", "delete", "pymysql", "mysql", "sql", "syntax",
    "table", "cursor", "innodb", "database operation failed", "could not connect to mysql",
    "fk_", "pk_", "foreign key", "duplicate entry", "errno", "for key", "column", "where"
}


def user_facing_error(exc: Exception, default_message: str | None = None) -> str:
    """Sanitize any exception into a safe, user-friendly message without leaking database internals."""
    # 1. Custom app exceptions with explicit user messages
    if hasattr(exc, "user_message") and getattr(exc, "user_message"):
        return str(getattr(exc, "user_message"))

    # 2. Domain / validation errors (ValueError, ValidationError)
    if isinstance(exc, (ValueError, KeyError)):
        msg = str(exc)
        # Check if the message contains raw SQL / database error leaks
        msg_lower = msg.lower()
        if not any(keyword in msg_lower for keyword in _DB_LEAK_KEYWORDS):
            return msg

    # 3. Fallback sanitized message
    return default_message or "An unexpected system error occurred. Please try again later."

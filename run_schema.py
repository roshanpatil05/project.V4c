"""Run schema.sql against the database configured in .env"""
from pathlib import Path
from dotenv import load_dotenv
import os
import pymysql

# Load .env (checks Mini_project_V4C/.env then parent dir)
load_dotenv()
if not os.getenv("DB_HOST"):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", 3306))
user = os.getenv("DB_USER", "root")
password = os.getenv("DB_PASSWORD", "")

print(f"Connecting to MySQL at {host}:{port} as user '{user}'...")
conn = pymysql.connect(
    host=host,
    port=port,
    user=user,
    password=password,
)

schema_path = Path(__file__).resolve().parent / "src" / "database" / "schema.sql"
schema_sql = schema_path.read_text(encoding="utf-8")


def parse_sql_script(sql_text: str) -> list[str]:
    """Parse SQL script handling DELIMITER directives and skipping comments."""
    delimiter = ";"
    statements: list[str] = []
    current_lines: list[str] = []

    for line in sql_text.splitlines():
        trimmed = line.strip()

        # Handle DELIMITER change command (e.g. DELIMITER $$, DELIMITER ;)
        if trimmed.upper().startswith("DELIMITER"):
            parts = trimmed.split()
            if len(parts) >= 2:
                delimiter = parts[1].strip()
            continue

        # Skip standalone comment lines when outside a statement
        if trimmed.startswith("--") and not current_lines:
            continue

        current_lines.append(line)

        # Statement boundary reached
        if trimmed.endswith(delimiter):
            stmt_text = "\n".join(current_lines).rstrip()
            if stmt_text.endswith(delimiter):
                stmt_text = stmt_text[:-len(delimiter)]

            cleaned = stmt_text.strip()
            if cleaned:
                statements.append(cleaned)
            current_lines = []

    if current_lines:
        cleaned = "\n".join(current_lines).strip()
        if cleaned:
            statements.append(cleaned)

    return statements


statements = parse_sql_script(schema_sql)
cursor = conn.cursor()

try:
    for stmt in statements:
        cursor.execute(stmt)
        # Display clean summary of what was executed
        summary = stmt.strip().split("\n")[0][:75]
        print(f"  [OK] {summary}...")
    conn.commit()
    print("\n[SUCCESS] Schema and stored procedures created successfully!")
except Exception:
    conn.rollback()
    raise
finally:
    cursor.close()
    conn.close()

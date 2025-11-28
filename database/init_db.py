#!/usr/bin/env python3
"""Initialize SQLite database for database

This script:
- Reads the SQLite DB file path from db_connection.txt when available.
- Creates or opens the SQLite database.
- Initializes required tables including the todos table.
- Adds a trigger to keep updated_at in sync on UPDATE.
- Writes connection information and sqlite.env for the visualizer.

All SQL statements are executed one at a time as per container rules.
"""

import os
import re
import sqlite3
from typing import Optional, Tuple

DEFAULT_DB_NAME = "myapp.db"


def _parse_db_path_from_file(contents: str) -> Optional[str]:
    """Extract the SQLite DB file path from db_connection.txt content."""
    # Look for a line like: "# File path: /abs/path/to/myapp.db"
    for line in contents.splitlines():
        line = line.strip()
        if line.lower().startswith("# file path:"):
            # after colon
            path = line.split(":", 1)[1].strip()
            if path:
                return path
        # fallback: parse connection string line if available
        if line.lower().startswith("# connection string:"):
            # Example: sqlite:////abs/path/to/myapp.db
            val = line.split(":", 1)[1].strip()
            m = re.search(r"sqlite:(/+)(.+\.db)$", val)
            if m:
                # Normalize multiple leading slashes to abs path
                return "/" + m.group(2)
        # python hint line fallback
        if "sqlite3.connect(" in line and ".db" in line:
            m = re.search(r"sqlite3\.connect\(['\"](.+\.db)['\"]\)", line)
            if m:
                return os.path.abspath(m.group(1))
    return None


def _read_db_path_from_connection_file(conn_file: str) -> Optional[str]:
    """Read db_connection.txt and return detected DB file path if present."""
    if not os.path.exists(conn_file):
        return None
    try:
        with open(conn_file, "r") as f:
            contents = f.read()
        return _parse_db_path_from_file(contents)
    except Exception:
        return None


# PUBLIC_INTERFACE
def get_database_path() -> Tuple[str, bool]:
    """Return the SQLite database file path and whether it was discovered from db_connection.txt.

    Priority:
    1) db_connection.txt (File path or connection string)
    2) Default myapp.db in current working directory

    Returns:
        (db_path, discovered)
        - db_path: absolute path to the sqlite db file
        - discovered: True if path came from db_connection.txt, else False
    """
    conn_file = "db_connection.txt"
    db_path = _read_db_path_from_connection_file(conn_file)
    if db_path:
        return (db_path, True)
    # Default to local myapp.db
    return (os.path.abspath(DEFAULT_DB_NAME), False)


def _ensure_dir(path: str) -> None:
    """Ensure directory exists for the given file path."""
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _exec_one(cursor: sqlite3.Cursor, sql: str, params: Tuple = ()) -> None:
    """Execute a single SQL statement."""
    cursor.execute(sql, params)


def main():
    print("Starting SQLite setup...")

    db_path, discovered = get_database_path()
    _ensure_dir(db_path)

    if os.path.exists(db_path):
        print(f"SQLite database already exists at {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            print("Database is accessible and working.")
        except Exception as e:
            print(f"Warning: Database exists but may be corrupted: {e}")
    else:
        print(f"Creating new SQLite database at {db_path} ...")

    # Create/open database and initialize schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enforce foreign keys
    _exec_one(cursor, "PRAGMA foreign_keys = ON")

    # app_info table
    _exec_one(cursor, """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # users table (retained for compatibility)
    _exec_one(cursor, """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # REQUIRED: todos table
    # Fields:
    # - id INTEGER PK
    # - title TEXT NOT NULL
    # - description TEXT
    # - completed INTEGER NOT NULL DEFAULT 0 (0=false,1=true)
    # - created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    # - updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    _exec_one(cursor, """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Trigger to update updated_at on UPDATE
    _exec_one(cursor, """
        CREATE TRIGGER IF NOT EXISTS trg_todos_updated_at
        AFTER UPDATE ON todos
        FOR EACH ROW
        BEGIN
            UPDATE todos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
    """)

    # Seed minimal app_info
    _exec_one(cursor, "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("project_name", "database"))
    _exec_one(cursor, "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("version", "0.1.0"))
    _exec_one(cursor, "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("author", "John Doe"))
    _exec_one(cursor, "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", ("description", ""))

    conn.commit()

    # Stats
    _exec_one(cursor, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    table_count = cursor.fetchone()[0]

    _exec_one(cursor, "SELECT COUNT(*) FROM app_info")
    record_count = cursor.fetchone()[0]

    conn.close()

    # Persist connection details for downstream tools
    try:
        with open("db_connection.txt", "w") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_path}')\n")
            f.write(f"# Connection string: sqlite:///{db_path}\n")
            f.write(f"# File path: {db_path}\n")
        print("Connection information saved to db_connection.txt")
    except Exception as e:
        print(f"Warning: Could not save connection info: {e}")

    # Update db_visualizer env
    try:
        os.makedirs("db_visualizer", exist_ok=True)
        with open("db_visualizer/sqlite.env", "w") as f:
            f.write(f'export SQLITE_DB="{db_path}"\n')
        print("Environment variables saved to db_visualizer/sqlite.env")
    except Exception as e:
        print(f"Warning: Could not save environment variables: {e}")

    print("\nSQLite setup complete!")
    print(f"Database: {os.path.basename(db_path)}")
    print(f"Location: {db_path}\n")
    print("To use with Node.js viewer, run: source db_visualizer/sqlite.env")
    print("\nTo connect to the database, use one of the following methods:")
    print(f"1. Python: sqlite3.connect('{db_path}')")
    print(f"2. Connection string: sqlite:///{db_path}")
    print(f"3. Direct file access: {db_path}\n")
    print("Database statistics:")
    print(f"  Tables: {table_count}")
    print(f"  App info records: {record_count}")

    # Optional info for sqlite3 CLI
    try:
        import subprocess
        result = subprocess.run(['which', 'sqlite3'], capture_output=True, text=True)
        if result.returncode == 0:
            print("\nSQLite CLI is available. You can also use:")
            print(f"  sqlite3 {db_path}")
    except Exception:
        pass

    print("\nScript completed successfully.")


if __name__ == "__main__":
    main()

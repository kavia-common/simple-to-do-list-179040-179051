#!/usr/bin/env python3
"""Test SQLite database connection and todos table presence."""

import os
import re
import sqlite3
import sys
from typing import Optional


DEFAULT_DB_NAME = "myapp.db"


def _parse_db_path_from_file(contents: str) -> Optional[str]:
    """Extract the SQLite DB file path from db_connection.txt content."""
    for line in contents.splitlines():
        line = line.strip()
        if line.lower().startswith("# file path:"):
            path = line.split(":", 1)[1].strip()
            if path:
                return path
        if line.lower().startswith("# connection string:"):
            val = line.split(":", 1)[1].strip()
            m = re.search(r"sqlite:(/+)(.+\.db)$", val)
            if m:
                return "/" + m.group(2)
        if "sqlite3.connect(" in line and ".db" in line:
            m = re.search(r"sqlite3\.connect\(['\"](.+\.db)['\"]\)", line)
            if m:
                return os.path.abspath(m.group(1))
    return None


def get_db_path() -> str:
    """Return the DB path using db_connection.txt when available."""
    conn_file = "db_connection.txt"
    if os.path.exists(conn_file):
        try:
            with open(conn_file, "r") as f:
                contents = f.read()
            parsed = _parse_db_path_from_file(contents)
            if parsed:
                return parsed
        except Exception:
            pass
    return os.path.abspath(DEFAULT_DB_NAME)


def main():
    db_path = get_db_path()

    # Check if database file exists
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' not found")
        sys.exit(1)

    try:
        # Connect to database and get version
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]

        # Validate todos table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='todos'")
        if not cursor.fetchone():
            print("Connection OK but 'todos' table not found")
            conn.close()
            sys.exit(2)

        # Validate expected columns exist
        cursor.execute("PRAGMA table_info(todos)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {"id", "title", "description", "completed", "created_at", "updated_at"}
        missing = expected - cols
        if missing:
            print(f"Todos table missing columns: {', '.join(sorted(missing))}")
            conn.close()
            sys.exit(3)

        conn.close()
        print(f"SQLite version: {version}. Todos table OK.")
        sys.exit(0)

    except sqlite3.Error as e:
        print(f"Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

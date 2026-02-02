# init_db.py
import sqlite3
from datetime import datetime

def get_db_connection():
    conn = sqlite3.connect("interview.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resume_email TEXT UNIQUE,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interview_results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            scorecard TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resume_email TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

if __name__ == "__main__":
    init_db()

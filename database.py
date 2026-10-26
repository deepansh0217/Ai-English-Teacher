

import sqlite3
from pathlib import Path
from uuid import uuid4

DB_PATH = Path("data/english_teacher.db")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS credentials (
                user_id TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS conversations (
                thread_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS learner_progress (
                user_id TEXT PRIMARY KEY,
                current_level TEXT NOT NULL DEFAULT 'A0',
                current_lesson TEXT NOT NULL DEFAULT 'A0-01',
                completed_lessons TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                thread_id TEXT,
                category TEXT NOT NULL,
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );
        """)


def get_or_create_user(display_name):
    # This is a local demo identity, not secure authentication.
    user_id = display_name.strip().casefold()

    if not user_id:
        raise ValueError("Please enter a learner name.")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name
            """,
            (user_id, display_name.strip()),
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO learner_progress(user_id)
            VALUES (?)
            """,
            (user_id,),
        )

    return user_id


def register_user(username, password_hash):
    """Create a new account. Raises ValueError if the username is taken."""
    username = username.strip()
    user_id = username.casefold()

    if not user_id:
        raise ValueError("Please enter a username.")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name
            """,
            (user_id, username),
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO learner_progress(user_id)
            VALUES (?)
            """,
            (user_id,),
        )

        try:
            conn.execute(
                """
                INSERT INTO credentials(user_id, password_hash)
                VALUES (?, ?)
                """,
                (user_id, password_hash),
            )
        except sqlite3.IntegrityError:
            raise ValueError("This username is already taken.")

    return user_id


def get_credentials(user_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM credentials WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return row["password_hash"] if row else None


def get_user(user_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT user_id, display_name FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def get_progress(user_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM learner_progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return dict(row)


def update_progress(user_id, current_lesson, completed_lessons):
    import json

    with connect() as conn:
        conn.execute(
            """
            UPDATE learner_progress
            SET current_lesson = ?, completed_lessons = ?
            WHERE user_id = ?
            """,
            (
                current_lesson,
                json.dumps(completed_lessons),
                user_id,
            ),
        )


def create_conversation(user_id, title="English lesson"):
    thread_id = str(uuid4())

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations(thread_id, user_id, title)
            VALUES (?, ?, ?)
            """,
            (thread_id, user_id, title),
        )

    return thread_id


def list_conversations(user_id):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT thread_id, title, created_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC, created_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_conversation(user_id, thread_id):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM conversations
            WHERE user_id = ? AND thread_id = ?
            """,
            (user_id, thread_id),
        ).fetchone()

    return dict(row) if row else None


def rename_conversation(user_id, thread_id, title):
    with connect() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND thread_id = ?
            """,
            (title[:100], user_id, thread_id),
        )


def touch_conversation(user_id, thread_id):
    with connect() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND thread_id = ?
            """,
            (user_id, thread_id),
        )


def save_test_result(
    user_id, thread_id, category, score, total_questions
):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO test_results
            (user_id, thread_id, category, score, total_questions)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, thread_id, category, score, total_questions),
        )


def get_test_results(user_id):
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT category, score, total_questions, created_at
            FROM test_results
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]

"""
tokens.py
─────────
SQLite-backed one-time token store for SavvySipping.

Each token is tied to a customer email, valid for 72 hours, and
consumed (marked used) once the ZIP is delivered.
"""

import secrets
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "tokens.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the tokens table if it doesn't exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token      TEXT PRIMARY KEY,
                email      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used       INTEGER NOT NULL DEFAULT 0
            )
        """)
    logger.info("Token DB initialised at %s", DB_PATH)


def create_token(email: str) -> str:
    """Generate a secure token for email, valid 72 hours. Returns the token."""
    token      = secrets.token_urlsafe(32)
    now        = datetime.utcnow()
    expires_at = now + timedelta(hours=72)
    with _conn() as conn:
        conn.execute(
            "INSERT INTO tokens (token, email, created_at, expires_at, used) "
            "VALUES (?, ?, ?, ?, 0)",
            (token, email, now.isoformat(), expires_at.isoformat()),
        )
    logger.info("Token created for %s (expires %s)", email, expires_at.isoformat())
    return token


def validate_token(token: str) -> dict | None:
    """
    Return the token row as a dict if valid (exists, not used, not expired).
    Returns None otherwise.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT token, email, created_at, expires_at, used "
            "FROM tokens WHERE token = ?",
            (token,),
        ).fetchone()

    if row is None:
        return None
    if row["used"]:
        return None
    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        return None

    return dict(row)


def mark_used(token: str) -> None:
    """Mark a token as used so it cannot be reused."""
    with _conn() as conn:
        conn.execute("UPDATE tokens SET used = 1 WHERE token = ?", (token,))
    logger.info("Token marked used: %s…", token[:8])

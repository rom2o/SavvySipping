"""
tokens.py
─────────
One-time token store for SavvySipping.

Uses PostgreSQL when DATABASE_URL is set (Railway production),
falls back to SQLite for local development.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ─── Backend detection ────────────────────────────────────────────────────────

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    # Railway uses postgres:// but psycopg2 requires postgresql://
    _DSN = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    if "?" not in _DSN:
        _DSN += "?sslmode=require"
    elif "sslmode=" not in _DSN:
        _DSN += "&sslmode=require"

    def _conn():
        conn = psycopg2.connect(_DSN)
        return conn

else:
    import sqlite3
    from pathlib import Path

    _DB_PATH = str(Path(__file__).parent / "tokens.db")

    def _conn():
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


# ─── Public API ───────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the tokens table if it doesn't exist."""
    if DATABASE_URL:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tokens (
                        token      TEXT PRIMARY KEY,
                        email      TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        used       BOOLEAN NOT NULL DEFAULT FALSE
                    )
                """)
            conn.commit()
        finally:
            conn.close()
        logger.info("Token DB initialised (PostgreSQL)")
    else:
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
        logger.info("Token DB initialised (SQLite)")


def create_token(email: str) -> str:
    """Generate a secure token for email, valid 72 hours. Returns the token."""
    token      = secrets.token_urlsafe(32)
    now        = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=72)

    if DATABASE_URL:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tokens (token, email, created_at, expires_at, used) "
                    "VALUES (%s, %s, %s, %s, FALSE)",
                    (token, email, now, expires_at),
                )
            conn.commit()
        finally:
            conn.close()
    else:
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
    if DATABASE_URL:
        logger.info("validate_token called for token %s…", token[:8])

        conn = _conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT token, email, created_at, expires_at, used "
                    "FROM tokens WHERE token = %s",
                    (token,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            logger.warning(
                "validate_token: no row found for token %s… — token does not exist in DB",
                token[:8],
            )
            return None

        logger.info(
            "validate_token: row found for token %s… — used=%r (type=%s), expires_at=%r (type=%s)",
            token[:8],
            row["used"],
            type(row["used"]).__name__,
            row["expires_at"],
            type(row["expires_at"]).__name__,
        )

        if row["used"]:
            logger.warning(
                "validate_token: returning None — token %s… is already marked used (used=%r)",
                token[:8],
                row["used"],
            )
            return None

        expires_at = row["expires_at"]
        now_utc = datetime.now(timezone.utc)
        logger.info(
            "validate_token: checking expiry — expires_at=%r (tzinfo=%r), now_utc=%r",
            expires_at,
            expires_at.tzinfo,
            now_utc,
        )

        if expires_at.tzinfo:
            if now_utc > expires_at:
                logger.warning(
                    "validate_token: returning None — token %s… is expired "
                    "(expires_at=%r, now_utc=%r, delta=%s)",
                    token[:8],
                    expires_at,
                    now_utc,
                    now_utc - expires_at,
                )
                return None
        else:
            naive_now = datetime.utcnow()
            if naive_now > expires_at:
                logger.warning(
                    "validate_token: returning None — token %s… is expired (naive comparison) "
                    "(expires_at=%r, utcnow=%r, delta=%s)",
                    token[:8],
                    expires_at,
                    naive_now,
                    naive_now - expires_at,
                )
                return None

        logger.info(
            "validate_token: token %s… passed all checks — returning row",
            token[:8],
        )
        return dict(row)
    else:
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
    if DATABASE_URL:
        conn = _conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE tokens SET used = TRUE WHERE token = %s", (token,))
            conn.commit()
        finally:
            conn.close()
    else:
        with _conn() as conn:
            conn.execute("UPDATE tokens SET used = 1 WHERE token = ?", (token,))

    logger.info("Token marked used: %s…", token[:8])

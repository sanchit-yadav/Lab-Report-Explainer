"""Database engine, session management, and lifecycle initialization.

Supports SQLite for zero-configuration local runs and PostgreSQL with pgvector for production.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("db_session")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'lab_cds.db'}"

DATABASE_URL = os.environ.get("DATABASE_URL") or DEFAULT_SQLITE_URL

# Handle Heroku/Render/Neon legacy postgres:// prefix if encountered
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30
elif DATABASE_URL.startswith("postgresql"):
    # Serverless & Cloud PostgreSQL optimization (Neon, Supabase, Render, AWS RDS)
    engine_kwargs.update(
        {
            "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
            "pool_recycle": int(
                os.environ.get("DB_POOL_RECYCLE", "300")
            ),  # Prevents stale serverless disconnects
            "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", "30")),
        }
    )

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding an isolated database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all relational database tables defined in models if they do not exist."""
    import src.db.models  # noqa: F401 - Register models with Base.metadata

    try:
        Base.metadata.create_all(bind=engine)
        # Safe backward-compatible schema migration for new columns and dropped roles
        with engine.connect() as conn:
            from sqlalchemy import text

            try:
                conn.execute(text("ALTER TABLE reports ADD COLUMN current_step VARCHAR(500)"))
                conn.commit()
            except Exception:
                pass  # Column already exists or table was freshly created with it
            try:
                # Step 2: Safe schema migration to drop unused role column
                conn.execute(text("ALTER TABLE users DROP COLUMN role"))
                conn.commit()
            except Exception:
                pass  # SQLite <3.35 or column already dropped
        logger.info(
            f"Database schema initialized successfully using engine: {engine.url.drivername}"
        )
    except Exception as exc:
        logger.error(f"Failed to initialize database schema: {exc}")
        raise


def check_db_connection() -> bool:
    """Verify that the database is reachable and accepting queries."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database health probe failed: {exc}")
        return False

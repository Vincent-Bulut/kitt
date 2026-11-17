import logging
import os

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

DB_USER = os.environ.get("DATABASE_USER", "admin")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DB_HOST = os.environ.get("DATABASE_HOST", "localhost")
DB_PORT = os.environ.get("DATABASE_PORT", "5433")
DB_NAME = os.environ.get("DATABASE_NAME", "kitt")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def commit_or_conflict(db: Session) -> None:
    """Commit; a constraint violation becomes a 409 with a generic message (details only in the logs)."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        log.warning("integrity error: %s", e.orig)
        raise HTTPException(
            status_code=409, detail="The request conflicts with existing data (duplicate or invalid reference)."
        ) from e
    except SQLAlchemyError:
        db.rollback()
        raise

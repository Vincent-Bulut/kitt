from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

if os.environ.get("ENV_KITT") == 'prod':
    SQLALCHEMY_DATABASE_URL = "postgresql://admin:commando@postgres:5432/kitt"
else:
    SQLALCHEMY_DATABASE_URL = "postgresql://admin:commando@localhost/kitt"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
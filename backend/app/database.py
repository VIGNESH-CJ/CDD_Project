import os
from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from app.config import settings

# Ensure database directory exists if using sqlite
if "sqlite" in settings.DATABASE_URL:
    db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    db_dir = Path(db_path).parent
    if db_dir and not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
    engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
else:
    # MySQL / PostgreSQL connection
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600
    )

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

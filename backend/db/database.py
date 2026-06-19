from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import settings

db_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Supabase's transaction-mode pooler reuses connections across transactions, which
# breaks server-side prepared statements (DuplicatePreparedStatement errors).
# Disable them at the psycopg level. Same fix as in dora and quizventure.
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
) if settings.database_url else None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None
Base = declarative_base()


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not set")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

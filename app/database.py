"""
Database - Connexion et session SQLAlchemy
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models.models import (
        User, Plant, EnergyReading, HourlyAggregate,
        AlertRule, AlertLog, Invoice, DailySummary,
        SystemSetting, DEFAULT_SETTINGS, PushSubscription
    )
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Seed paramètres par défaut
        for s in DEFAULT_SETTINGS:
            existing = db.query(SystemSetting).filter(SystemSetting.key == s["key"]).first()
            if not existing:
                db.add(SystemSetting(**s))

        # Seed utilisateurs par défaut
        from app.auth.auth import init_default_users
        init_default_users(db)

        db.commit()
    finally:
        db.close()

    print("✅ Base de données initialisée")

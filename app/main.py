"""
BBL-ELECTRA Monitoring — Application principale
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db, SessionLocal
from app.api.routes import router
from app.auth.routes import auth_router
from app.services.collector import collect_data
from app.services.rules_engine import init_rules
from app.services.daily_report import generate_daily_report, generate_monthly_invoice
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌞" * 20)
    logger.info("  BBL-ELECTRA MONITORING — Démarrage")
    logger.info("🌞" * 20)

    init_db()

    db = SessionLocal()
    try:
        init_rules(db)
    finally:
        db.close()

    # Collecte toutes les 5 min
    scheduler.add_job(
        collect_data,
        "interval",
        minutes=settings.COLLECT_INTERVAL_MINUTES,
        id="collect_fusionsolar",
        name="Collecte FusionSolar",
        replace_existing=True,
        max_instances=1
    )

    # B2 — Bilan journalier à 00:00
    scheduler.add_job(
        generate_daily_report,
        CronTrigger(hour=0, minute=0),
        id="daily_report",
        name="Bilan journalier B2",
        replace_existing=True,
        max_instances=1
    )

    # B3 — Facture mensuelle le 1er à 00:05
    scheduler.add_job(
        generate_monthly_invoice,
        CronTrigger(day=1, hour=0, minute=5),
        id="monthly_invoice",
        name="Facture mensuelle B3",
        replace_existing=True,
        max_instances=1
    )

    scheduler.start()
    logger.info(f"⏰ Scheduler démarré:")
    logger.info(f"   • Collecte toutes les {settings.COLLECT_INTERVAL_MINUTES} min")
    logger.info(f"   • Bilan journalier B2 à 00:00")
    logger.info(f"   • Facture mensuelle B3 le 1er à 00:05")

    logger.info("🔄 Première collecte...")
    collect_data()

    yield

    scheduler.shutdown()
    logger.info("🔒 BBL-ELECTRA Monitoring arrêté")


app = FastAPI(
    title="BBL-ELECTRA Monitoring",
    description="Système de monitoring solaire et alertes pour ferme agricole",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth")

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")


@app.get("/")
def serve_app():
    index_path = os.path.join(frontend_dir, "index.html")
    return FileResponse(index_path)


@app.get("/login")
def serve_login():
    login_path = os.path.join(frontend_dir, "login.html")
    return FileResponse(login_path)


@app.get("/health")
def health():
    return {"status": "ok", "scheduler_running": scheduler.running}

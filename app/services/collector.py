"""
Collector - Collecte périodique des données FusionSolar
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.services.fusionsolar import fusionsolar_service
from app.models.models import Plant, EnergyReading, HourlyAggregate
from app.utils.tariffs import (
    get_tariff_period, get_season, correct_power,
    calculate_grid_flows, get_tariff_rate
)
from app.config import settings
from app.database import SessionLocal
from app.services.rules_engine import evaluate_rules
import logging

# Maroc = UTC+1
MOROCCO_TZ = timezone(timedelta(hours=1))

def now_morocco():
    return datetime.now(MOROCCO_TZ).replace(tzinfo=None)

# Cache pour détecter les données figées
_last_pv_values = []  # Historique des 3 dernières valeurs PV
_is_frozen = False    # True si données figées (centrale hors ligne)

def _check_frozen_data(pv_power: float) -> bool:
    """Détecte si FusionSolar retourne des données figées (centrale hors ligne)"""
    global _last_pv_values, _is_frozen
    now = now_morocco()
    hour = now.hour
    
    _last_pv_values.append(round(pv_power, 1))
    if len(_last_pv_values) > 4:
        _last_pv_values.pop(0)
    
    # Vérifier seulement pendant les heures de jour (7h-19h)
    if 7 <= hour <= 19 and len(_last_pv_values) >= 3:
        # Si les 3 dernières valeurs sont identiques ET non nulles → figées
        if len(set(_last_pv_values[-3:])) == 1 and _last_pv_values[-1] > 5:
            _is_frozen = True
            return True
    
    # Si PV est nul en plein jour → hors ligne
    if 9 <= hour <= 16 and pv_power < 1:
        _is_frozen = True
        return True
    
    _is_frozen = False
    return False

logger = logging.getLogger(__name__)


def collect_data():
    logger.info("⏰ Début de la collecte...")
    db = SessionLocal()

    try:
        if not fusionsolar_service.connect():
            logger.error("❌ Impossible de se connecter à FusionSolar")
            return

        plant = _get_or_create_target_plant(db)
        if not plant:
            logger.error("❌ Centrale cible introuvable")
            return

        reading = _collect_plant_data(db, plant)
        if reading:
            evaluate_rules(reading, db)

        db.commit()
        logger.info("✅ Collecte terminée")

    except Exception as e:
        logger.error(f"❌ Erreur collecte: {e}")
        db.rollback()
    finally:
        fusionsolar_service.disconnect()
        db.close()


def _get_or_create_target_plant(db: Session) -> Plant:
    plant = db.query(Plant).filter(
        Plant.fusionsolar_code == settings.TARGET_PLANT_ID
    ).first()

    if not plant:
        plant = Plant(
            name=settings.TARGET_PLANT_NAME,
            fusionsolar_code=settings.TARGET_PLANT_ID,
            capacity_kwp=settings.TARGET_PLANT_CAPACITY_KWP,
            is_active=True
        )
        db.add(plant)
        db.commit()
        db.refresh(plant)
        logger.info(f"✅ Centrale créée: {plant.name}")

    return plant


def _collect_plant_data(db: Session, plant: Plant) -> EnergyReading:
    data = fusionsolar_service.get_realtime_data(plant.fusionsolar_code)
    if not data:
        logger.warning(f"⚠️ Pas de données pour {plant.name}")
        return None

    now = now_morocco()
    tariff_period = get_tariff_period(now)
    season = get_season(now)

    consumption_corrected = correct_power(
        data["consumption_raw"],
        settings.POWER_CORRECTION_KW
    )

    grid_import, grid_export, self_consumption = calculate_grid_flows(
        data["pv_power"],
        consumption_corrected
    )

    # Détecter données figées — NE PAS stocker si hors ligne
    frozen = _check_frozen_data(data["pv_power"])
    if frozen:
        logger.warning(f"⚠️ Données figées — centrale hors ligne. Collecte ignorée (PV: {data['pv_power']} kW)")
        _send_offline_alert(db, plant)
        return None  # ← On ne sauvegarde rien

    reading = EnergyReading(
        plant_id=plant.id,
        timestamp=now,
        pv_power=data["pv_power"],
        consumption_raw=data["consumption_raw"],
        grid_import_raw=data.get("grid_import_raw", 0),
        consumption_corrected=consumption_corrected,
        grid_import=grid_import,
        grid_export=grid_export,
        self_consumption=self_consumption,
        tariff_period=tariff_period,
        season=season
    )
    db.add(reading)

    logger.info(
        f"📊 {plant.name} | PV: {data['pv_power']:.1f} kW | "
        f"Conso: {consumption_corrected:.1f} kW | "
        f"Import: {grid_import:.1f} kW | Export: {grid_export:.1f} kW | "
        f"Autoconso: {self_consumption:.1f} kW | {tariff_period.value}"
    )

    _update_hourly_aggregate(db, plant, reading)
    return reading


def _send_offline_alert(db, plant):
    """Envoyer une alerte centrale hors ligne"""
    from app.models.models import AlertRule, AlertLog, AlertStatus
    from app.services.notifications import send_alert
    from datetime import timedelta
    now = now_morocco()
    rule = db.query(AlertRule).filter(AlertRule.rule_code == 'PLANT_OFFLINE').first()
    if not rule or not rule.is_active:
        return
    cooldown_time = now - timedelta(minutes=rule.cooldown_minutes)
    recent = db.query(AlertLog).filter(
        AlertLog.rule_id == rule.id,
        AlertLog.triggered_at > cooldown_time
    ).first()
    if recent:
        return
    msg = f"⚠️ CENTRALE HORS LIGNE | {plant.name} | Aucune donnée depuis +15 min | {now.strftime('%H:%M')}"
    alert_log = AlertLog(
        rule_id=rule.id,
        plant_id=plant.id,
        triggered_at=now,
        measured_value=0,
        threshold_value=0,
        message=msg,
        status=AlertStatus.ACTIVE
    )
    db.add(alert_log)
    send_alert(msg, rule.notify_telegram, rule.notify_email)
    logger.warning(f"🚨 {msg}")


def _update_hourly_aggregate(db: Session, plant: Plant, reading: EnergyReading):
    hour_start = reading.timestamp.replace(minute=0, second=0, microsecond=0)

    aggregate = db.query(HourlyAggregate).filter(
        HourlyAggregate.plant_id == plant.id,
        HourlyAggregate.hour_start == hour_start
    ).first()

    if not aggregate:
        aggregate = HourlyAggregate(
            plant_id=plant.id,
            hour_start=hour_start,
            avg_pv_power=0, avg_consumption=0,
            avg_grid_import=0, avg_grid_export=0,
            avg_self_consumption=0,
            sample_count=0,
            tariff_period=reading.tariff_period,
            season=reading.season
        )
        db.add(aggregate)

    n = aggregate.sample_count
    aggregate.avg_pv_power = _update_avg(aggregate.avg_pv_power, reading.pv_power, n)
    aggregate.avg_consumption = _update_avg(aggregate.avg_consumption, reading.consumption_corrected, n)
    aggregate.avg_grid_import = _update_avg(aggregate.avg_grid_import, reading.grid_import, n)
    aggregate.avg_grid_export = _update_avg(aggregate.avg_grid_export, reading.grid_export, n)
    aggregate.avg_self_consumption = _update_avg(aggregate.avg_self_consumption, reading.self_consumption, n)
    aggregate.sample_count = n + 1

    # kWh = moyenne × 1h
    aggregate.pv_energy_kwh = aggregate.avg_pv_power
    aggregate.consumption_kwh = aggregate.avg_consumption
    aggregate.grid_import_kwh = aggregate.avg_grid_import
    aggregate.grid_export_kwh = aggregate.avg_grid_export
    aggregate.self_consumption_kwh = aggregate.avg_self_consumption

    # Coût import — tarifs lus depuis la DB
    tariff = get_tariff_rate(aggregate.tariff_period, db)
    aggregate.estimated_cost_dh = aggregate.grid_import_kwh * tariff

    # Économies solaires = autoconsommation × tarif de la tranche
    aggregate.savings_dh = aggregate.self_consumption_kwh * tariff


def _update_avg(current_avg: float, new_value: float, count: int) -> float:
    if current_avg is None:
        current_avg = 0
    if count == 0:
        return new_value
    return (current_avg * count + new_value) / (count + 1)
